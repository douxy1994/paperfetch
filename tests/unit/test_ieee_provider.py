from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from paper_fetch.extraction.html import assets as html_assets
from paper_fetch.http import DEFAULT_FULLTEXT_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS, RequestFailure
from paper_fetch.providers import ieee as ieee_provider
from paper_fetch.providers._pdf_common import PdfFetchFailure, PdfFetchResult
from paper_fetch.providers.ieee import IeeeClient
from paper_fetch.runtime import RuntimeContext
from paper_fetch.workflow.types import FetchStrategy
from tests.golden_criteria import golden_criteria_manifest
from tests.paths import REPO_ROOT


class RecordingTransport:
    def __init__(self, responses: dict[tuple[str, str], dict[str, object] | Exception]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def request(
        self,
        method,
        url,
        *,
        headers=None,
        query=None,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        retry_on_rate_limit=False,
        rate_limit_retries=1,
        max_rate_limit_wait_seconds=5,
        retry_on_transient=False,
        transient_retries=2,
        transient_backoff_base_seconds=0.5,
    ):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "query": dict(query or {}),
                "timeout": timeout,
                "retry_on_transient": retry_on_transient,
            }
        )
        key = (method, url)
        if key not in self.responses:
            raise AssertionError(f"Missing fake response for {method} {url}")
        response = self.responses[key]
        if isinstance(response, Exception):
            raise response
        return response


def _landing_html(
    *,
    doi: str = "10.1109/ACCESS.2024.3352924",
    article_number: str = "10388355",
    dynamic: bool = True,
    abstract: str = "IEEE abstract text.",
) -> bytes:
    metadata = {
        "articleNumber": article_number,
        "articleId": article_number,
        "doi": doi,
        "title": "IEEE Dynamic Article",
        "publicationTitle": "IEEE Access",
        "publicationDate": "2024",
        "abstract": abstract,
        "authors": [{"name": "Alice Example"}, {"name": "Bob Example"}],
        "isDynamicHtml": dynamic,
        "html_flag": False,
        "ml_html_flag": dynamic,
        "pdfUrl": f"/stamp/stamp.jsp?tp=&arnumber={article_number}",
        "pdfPath": f"/iel7/6287639/10380310/{article_number}.pdf",
    }
    return (
        "<html><head><title>IEEE Dynamic Article</title></head><body>"
        "<script>xplGlobal = {document: {}}; xplGlobal.document.metadata = "
        + json.dumps(metadata)
        + ";</script></body></html>"
    ).encode("utf-8")


def _dynamic_html(article_number: str = "10388355") -> bytes:
    paragraph = "This IEEE body paragraph describes methods, results, and evaluation evidence across several experiments. "
    return (
        '<?xml version="1.0" encoding="UTF-8"?><response><accessType>Open Access</accessType>'
        '<div id="BodyWrapper"><div id="article">'
        '<div class="section" id="sec1"><h2>Introduction</h2><p>'
        + paragraph * 25
        + '</p><figure id="fig1"><figcaption>Fig. 1. Example system overview.</figcaption></figure></div>'
        '<div class="section_2" id="sec2"><h3>Results</h3><p>'
        + paragraph * 25
        + '</p><tex-math>\\alpha + \\beta</tex-math><table><tr><td>Metric</td></tr></table></div>'
        '<a href="javascript:void()" data-docId="'
        + article_number
        + '">Show All</a></div></div></response>'
    ).encode("utf-8")


def _raw_ieee_html_payload(
    *,
    doi: str,
    article_number: str,
    html_text: str,
    source_url: str,
    trace_markers: list[str] | None = None,
) -> ieee_provider.RawFulltextPayload:
    metadata = {
        "doi": doi,
        "title": "IEEE Dynamic Article",
        "abstract": "IEEE abstract text.",
        "authors": ["Alice Example", "Bob Example"],
        "article_number": article_number,
        "articleNumber": article_number,
        "landing_page_url": f"https://ieeexplore.ieee.org/document/{article_number}/",
    }
    extraction = ieee_provider._extract_ieee_html(html_text, source_url, metadata=metadata)
    body = extraction.html_text.encode("utf-8")
    return ieee_provider.RawFulltextPayload(
        provider="ieee",
        source_url=source_url,
        content_type="text/html",
        body=body,
        content=ieee_provider.ProviderContent(
            route_kind="html",
            source_url=source_url,
            content_type="text/html",
            body=body,
            markdown_text=extraction.markdown_text,
            merged_metadata=dict(metadata),
            diagnostics={
                "extraction": {
                    "abstract_sections": extraction.abstract_sections,
                    "section_hints": extraction.section_hints,
                    "marker_counts": extraction.marker_counts,
                }
            },
            reason="Downloaded full text from the IEEE Xplore clean-browser HTML fallback route.",
            fetcher="playwright_html",
            extracted_assets=extraction.extracted_assets,
        ),
        trace=ieee_provider.trace_from_markers(trace_markers or ["fulltext:ieee_html_ok"]),
        merged_metadata=metadata,
    )


def _dynamic_html_with_ieee_media_assets(article_number: str = "10388355") -> bytes:
    paragraph = "This IEEE body paragraph describes methods, results, and evaluation evidence across several experiments. "
    return (
        '<?xml version="1.0" encoding="UTF-8"?><response><accessType>Open Access</accessType>'
        '<div id="BodyWrapper"><div id="article">'
        '<div class="section" id="sec1"><h2>Introduction</h2><p>'
        + paragraph * 25
        + '</p>'
        '<a href="/assets/img/icon.support.gif">support</a>'
        '<img src="/assets/img/icon.support.gif" alt="Formula"/>'
        '<div class="figure figure-full" id="fig1">'
        '<a href="/mediastore/IEEE/content/media/'
        + article_number
        + "/"
        + article_number
        + '-fig-1-large.gif">'
        '<img src="/mediastore/IEEE/content/media/'
        + article_number
        + "/"
        + article_number
        + '-fig-1-small.gif" alt="System overview image"/></a>'
        '<div class="figcaption"><span class="title">Fig. 1.</span> Example system overview.</div>'
        "</div>"
        '<div class="figure figure-full table" id="table1">'
        '<a href="/mediastore/IEEE/content/media/'
        + article_number
        + "/"
        + article_number
        + '-table-1-large.gif">'
        '<img src="/mediastore/IEEE/content/media/'
        + article_number
        + "/"
        + article_number
        + '-table-1-small.gif" alt="Table comparison image"/></a>'
        '<div class="figcaption"><span class="title">Table I.</span> Comparison of methods.</div>'
        "</div>"
        '<a href="/documents/supplementary.pdf">Supplementary PDF</a>'
        '<a href="/documents/multimedia.mp4" title="Multimedia file">Movie clip</a>'
        '</div><div class="section_2" id="sec2"><h3>Results</h3><p>'
        + paragraph * 25
        + "</p></div></div></div></response>"
    ).encode("utf-8")


def _dynamic_html_with_ieee_equation_alt_table_asset(article_number: str = "10388355") -> bytes:
    paragraph = "This IEEE body paragraph describes methods, results, and evaluation evidence across several experiments. "
    return (
        '<?xml version="1.0" encoding="UTF-8"?><response><accessType>Open Access</accessType>'
        '<div id="BodyWrapper"><div id="article">'
        '<div class="section" id="sec1"><h2>Results</h2><p>'
        + paragraph * 25
        + "</p>"
        '<div class="figure figure-full table" id="table1">'
        '<a href="/mediastore/IEEE/content/media/'
        + article_number
        + "/"
        + article_number
        + '-table-1-large.gif">'
        '<img src="/mediastore/IEEE/content/media/'
        + article_number
        + "/"
        + article_number
        + '-table-1-small.gif" alt="Equation comparison table image"/></a>'
        '<div class="figcaption"><span class="title">Table I.</span> Equation comparison table.</div>'
        "</div></div></div></div></response>"
    ).encode("utf-8")


IEEE_REAL_HTML_SAMPLES = {
    "ACCESS": ("10.1109/ACCESS.2024.3352924", "10.1109_ACCESS.2024.3352924", "10388355"),
    "CICTN": ("10.1109/CICTN64563.2025.10932570", "10.1109_CICTN64563.2025.10932570", "10932570"),
    "TBME": ("10.1109/TBME.2024.3434477", "10.1109_TBME.2024.3434477", "10612240"),
    "TCOMM": ("10.1109/TCOMM.2024.3395332", "10.1109_TCOMM.2024.3395332", "10511075"),
    "TDEI": ("10.1109/TDEI.2024.3373549", "10.1109_TDEI.2024.3373549", "10459335"),
    "TE": ("10.1109/TE.2024.3376795", "10.1109_TE.2024.3376795", "10496257"),
    "TIM": ("10.1109/TIM.2024.3509573", "10.1109_TIM.2024.3509573", "10772041"),
}


def _real_ieee_fixture_metadata(*, doi: str, fixture_dir: str, article_number: str) -> dict[str, object]:
    fixture_root = REPO_ROOT / "tests" / "fixtures" / "golden_criteria" / fixture_dir
    landing_metadata = ieee_provider._parse_landing_metadata(
        (fixture_root / "landing.html").read_text(encoding="utf-8")
    )
    metadata = ieee_provider._merge_ieee_metadata(
        {"doi": doi},
        landing_metadata,
        f"https://ieeexplore.ieee.org/document/{article_number}/",
    )
    references_payload = json.loads((fixture_root / "references.json").read_text(encoding="utf-8"))
    references = ieee_provider._references_from_ieee_reference_payload(references_payload)
    if references:
        metadata["references"] = references
    return metadata


def _real_ieee_fixture_article(
    *,
    doi: str,
    fixture_dir: str,
    article_number: str,
    tmpdir: Path,
):
    fixture_root = REPO_ROOT / "tests" / "fixtures" / "golden_criteria" / fixture_dir
    source_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
    metadata = _real_ieee_fixture_metadata(doi=doi, fixture_dir=fixture_dir, article_number=article_number)
    extraction = ieee_provider._extract_ieee_html(
        (fixture_root / "original.html").read_text(encoding="utf-8"),
        source_url,
        metadata=metadata,
    )
    downloaded_assets: list[dict[str, object]] = []
    for index, item in enumerate(extraction.extracted_assets, start=1):
        if item.get("kind") not in {"figure", "table"} or item.get("section") != "body":
            continue
        asset_url = item.get("url") or item.get("full_size_url") or item.get("preview_url")
        if not asset_url:
            continue
        path = tmpdir / f"ieee-asset-{index}.gif"
        path.write_bytes(b"GIF89a\x01\x00\x01\x00\x00\x00;")
        downloaded = dict(item)
        downloaded.update(
            {
                "path": str(path),
                "download_url": asset_url,
                "source_url": asset_url,
                "content_type": "image/gif",
                "download_tier": "full_size",
            }
        )
        downloaded_assets.append(downloaded)

    body = extraction.html_text.encode("utf-8")
    raw_payload = ieee_provider.RawFulltextPayload(
        provider="ieee",
        source_url=source_url,
        content_type="text/html",
        body=body,
        content=ieee_provider.ProviderContent(
            route_kind="html",
            source_url=source_url,
            content_type="text/html",
            body=body,
            markdown_text=extraction.markdown_text,
            merged_metadata=metadata,
            diagnostics={
                "extraction": {
                    "abstract_sections": extraction.abstract_sections,
                    "section_hints": extraction.section_hints,
                    "marker_counts": extraction.marker_counts,
                }
            },
            reason="Loaded IEEE real HTML fixture.",
            extracted_assets=extraction.extracted_assets,
        ),
        trace=ieee_provider.trace_from_markers(["fulltext:ieee_html_ok"]),
        merged_metadata=metadata,
    )
    client = IeeeClient(RecordingTransport({}), {})
    article = client.to_article_model({"doi": doi}, raw_payload, downloaded_assets=downloaded_assets)
    markdown = article.to_ai_markdown(asset_profile="body", include_figures="inline", max_tokens="full_text")
    return extraction, article, markdown


class IeeeProviderTests(unittest.TestCase):
    def test_ieee_preferred_provider_is_accepted(self) -> None:
        strategy = FetchStrategy(preferred_providers=["ieee"])

        self.assertEqual(strategy.normalized_preferred_providers(), {"ieee"})

    def test_landing_metadata_and_article_number_parsing(self) -> None:
        html = _landing_html(article_number="10388355").decode("utf-8")
        metadata = ieee_provider._parse_landing_metadata(html)

        self.assertEqual(metadata["articleNumber"], "10388355")
        self.assertEqual(ieee_provider._article_number_from_url("https://ieeexplore.ieee.org/document/10388355/"), "10388355")
        self.assertTrue(metadata["isDynamicHtml"])

    def test_landing_attempt_merges_ieee_keywords_and_reference_text(self) -> None:
        """rule: rule-fulltext-reference-priority"""
        doi = "10.1109/ACCESS.2024.3352924"
        article_number = "10388355"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        references_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/references"
        landing_metadata = {
            "articleNumber": article_number,
            "articleId": article_number,
            "doi": doi,
            "title": "IEEE Dynamic Article",
            "publicationTitle": "IEEE Access",
            "publicationDate": "2024",
            "abstract": "IEEE abstract text.",
            "authors": [{"name": "Alice Example"}],
            "isDynamicHtml": True,
            "ml_html_flag": True,
            "referenceCount": 1,
            "keywords": [
                {"type": "IEEE Keywords", "kwd": ["Random access memory"]},
                {"type": "Author Keywords", "kwd": ["near-data processing"]},
            ],
        }
        landing_html = (
            "<html><body><script>xplGlobal = {document: {}}; xplGlobal.document.metadata = "
            + json.dumps(landing_metadata)
            + ";</script></body></html>"
        ).encode("utf-8")
        references_json = json.dumps(
            {
                "references": [
                    {
                        "order": "1",
                        "text": "A. Author, “Full IEEE reference title,” <em>Proc. Test</em>, 2024.",
                        "title": "Full IEEE reference title",
                        "links": {"crossRefLink": "https://doi.org/10.1109/TEST.2024.1"},
                    }
                ]
            }
        ).encode("utf-8")
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": landing_html,
                    "url": landing_url,
                },
                ("GET", references_url): {
                    "status_code": 200,
                    "headers": {"content-type": "application/json"},
                    "body": references_json,
                    "url": references_url,
                },
            }
        )
        client = IeeeClient(transport, {})

        attempt = client._fetch_landing_attempt(
            doi,
            {
                "doi": doi,
                "landing_page_url": landing_url,
                "references": [
                    {"title": "Metadata fallback title without IEEE citation text"},
                    {"doi": "10.1109/test.2024.2"},
                ],
            },
        )

        self.assertEqual(attempt.merged_metadata["keywords"], ["Random access memory", "near-data processing"])
        self.assertEqual(len(attempt.merged_metadata["references"]), 1)
        self.assertEqual(attempt.merged_metadata["references"][0]["label"], "1")
        self.assertIn("Full IEEE reference title", attempt.merged_metadata["references"][0]["raw"])
        self.assertEqual(attempt.merged_metadata["references"][0]["doi"], "10.1109/test.2024.1")
        self.assertNotIn(
            "Metadata fallback title without IEEE citation text",
            json.dumps(attempt.merged_metadata["references"]),
        )

    def test_landing_attempt_keeps_metadata_references_when_ieee_payload_is_empty(self) -> None:
        """rule: rule-fulltext-reference-priority"""
        doi = "10.1109/ACCESS.2024.3352924"
        article_number = "10388355"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        references_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/references"
        landing_metadata = {
            "articleNumber": article_number,
            "articleId": article_number,
            "doi": doi,
            "title": "IEEE Dynamic Article",
            "publicationTitle": "IEEE Access",
            "publicationDate": "2024",
            "abstract": "IEEE abstract text.",
            "authors": [{"name": "Alice Example"}],
            "isDynamicHtml": True,
            "ml_html_flag": True,
            "referenceCount": 1,
        }
        landing_html = (
            "<html><body><script>xplGlobal = {document: {}}; xplGlobal.document.metadata = "
            + json.dumps(landing_metadata)
            + ";</script></body></html>"
        ).encode("utf-8")
        fallback_references = [
            {"title": "Metadata fallback title", "doi": "10.5555/fallback"},
        ]
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": landing_html,
                    "url": landing_url,
                },
                ("GET", references_url): {
                    "status_code": 200,
                    "headers": {"content-type": "application/json"},
                    "body": json.dumps({"references": []}).encode("utf-8"),
                    "url": references_url,
                },
            }
        )
        client = IeeeClient(transport, {})

        attempt = client._fetch_landing_attempt(
            doi,
            {"doi": doi, "landing_page_url": landing_url, "references": fallback_references},
        )

        self.assertEqual(attempt.merged_metadata["references"], fallback_references)

    def test_dynamic_html_success_uses_ieee_html_source_and_rest_headers(self) -> None:
        doi = "10.1109/ACCESS.2024.3352924"
        article_number = "10388355"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _landing_html(doi=doi, article_number=article_number),
                    "url": landing_url,
                },
                ("GET", rest_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _dynamic_html(article_number),
                    "url": rest_url,
                },
            }
        )
        client = IeeeClient(transport, {})

        raw_payload = client.fetch_raw_fulltext(doi, {"doi": doi, "landing_page_url": landing_url})
        article = client.to_article_model({"doi": doi}, raw_payload)

        self.assertEqual(raw_payload.content.route_kind, "html")
        self.assertEqual(article.source, "ieee_html")
        self.assertEqual(article.metadata.authors, ["Alice Example", "Bob Example"])
        self.assertEqual(article.quality.content_kind, "fulltext")
        self.assertIn("fulltext:ieee_html_ok", article.quality.source_trail)
        rest_call = transport.calls[1]
        self.assertEqual(rest_call["url"], rest_url)
        self.assertEqual(rest_call["timeout"], DEFAULT_FULLTEXT_TIMEOUT_SECONDS)
        self.assertTrue(rest_call["retry_on_transient"])
        headers = rest_call["headers"]
        self.assertEqual(headers["Referer"], landing_url)
        self.assertEqual(headers["x-security-request"], "required")
        self.assertIn("application/json", headers["Accept"])
        diagnostics = raw_payload.content.diagnostics["extraction"]
        self.assertGreaterEqual(diagnostics["marker_counts"]["sections"], 2)
        self.assertGreaterEqual(diagnostics["marker_counts"]["formulas"], 1)

    def test_direct_rest_401_uses_browser_html_fallback_before_pdf(self) -> None:
        doi = "10.1109/TIM.2024.3509573"
        article_number = "10772041"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _landing_html(doi=doi, article_number=article_number),
                    "url": landing_url,
                },
                ("GET", rest_url): RequestFailure(401, f"HTTP 401 for {rest_url}", url=rest_url),
            }
        )
        client = IeeeClient(transport, {})
        browser_payload = _raw_ieee_html_payload(
            doi=doi,
            article_number=article_number,
            html_text=_dynamic_html(article_number).decode("utf-8"),
            source_url=rest_url,
            trace_markers=["fulltext:ieee_html_fail", "fulltext:ieee_browser_html_ok", "fulltext:ieee_html_ok"],
        )

        with (
            mock.patch.object(client, "_fetch_browser_html_payload", return_value=browser_payload) as mocked_browser,
            mock.patch.object(ieee_provider, "fetch_pdf_over_http") as mocked_pdf,
        ):
            raw_payload = client.fetch_raw_fulltext(doi, {"doi": doi, "landing_page_url": landing_url})
            article = client.to_article_model({"doi": doi}, raw_payload)

        self.assertEqual(raw_payload.content.route_kind, "html")
        self.assertEqual(raw_payload.content.fetcher, "playwright_html")
        self.assertEqual(article.source, "ieee_html")
        self.assertEqual(article.quality.content_kind, "fulltext")
        self.assertIn("fulltext:ieee_browser_html_ok", article.quality.source_trail)
        self.assertIn("fulltext:ieee_html_ok", article.quality.source_trail)
        mocked_browser.assert_called_once()
        self.assertEqual(mocked_browser.call_args.kwargs["direct_html_failure"].code, "no_access")
        mocked_pdf.assert_not_called()

    def test_browser_html_fallback_uses_response_listener_without_wait_for_response_api(self) -> None:
        doi = "10.1109/TIM.2024.3509573"
        article_number = "10772041"
        document_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
        landing_attempt = ieee_provider.IeeeLandingAttempt(
            normalized_doi=doi,
            landing_url=document_url,
            response_url=document_url,
            html_text=_landing_html(doi=doi, article_number=article_number).decode("utf-8"),
            merged_metadata={
                "doi": doi,
                "title": "IEEE Dynamic Article",
                "abstract": "IEEE abstract text.",
                "article_number": article_number,
                "articleNumber": article_number,
                "landing_page_url": document_url,
            },
            article_number=article_number,
            landing_metadata={},
        )

        class FakeResponse:
            url = rest_url
            status = 200
            headers = {"content-type": "text/html;charset=utf-8"}

            def body(self):
                return _dynamic_html(article_number)

            def all_headers(self):
                return dict(self.headers)

        class FakeRequest:
            resource_type = "xhr"

        class FakeRoute:
            request = FakeRequest()

            def continue_(self):
                return None

        class FakePage:
            url = document_url

            def __init__(self):
                self._response_handler = None
                self.closed = False

            def on(self, event_name, handler):
                assert event_name == "response"
                self._response_handler = handler

            def goto(self, url, **kwargs):
                assert url == document_url
                del kwargs
                if self._response_handler is not None:
                    self._response_handler(FakeResponse())
                return None

            def wait_for_timeout(self, timeout):
                assert timeout == ieee_provider.IEEE_BROWSER_HTML_REST_WAIT_TIMEOUT_MS

            def close(self):
                self.closed = True

        class FakeBrowserContext:
            def __init__(self):
                self.page = FakePage()
                self.closed = False
                self.route_pattern = ""

            def route(self, pattern, handler):
                self.route_pattern = pattern
                handler(FakeRoute())

            def new_page(self):
                return self.page

            def close(self):
                self.closed = True

        fake_browser_context = FakeBrowserContext()
        fake_runtime = mock.Mock()
        fake_runtime.new_playwright_context.return_value = fake_browser_context
        client = IeeeClient(RecordingTransport({}), {})

        raw_payload = client._fetch_browser_html_payload(
            landing_attempt,
            direct_html_failure=ieee_provider.ProviderFailure("no_access", "Forced direct failure."),
            context=fake_runtime,
        )

        self.assertEqual(raw_payload.content.route_kind, "html")
        self.assertEqual(raw_payload.content.fetcher, "playwright_html")
        self.assertEqual(raw_payload.content.diagnostics["browser_html"]["payload_source"], "rest_response")
        self.assertEqual(raw_payload.content.diagnostics["browser_html"]["direct_html_failure"]["code"], "no_access")
        self.assertEqual(fake_browser_context.route_pattern, "**/*")
        self.assertTrue(fake_browser_context.closed)
        self.assertTrue(fake_browser_context.page.closed)

    def test_direct_rest_and_browser_html_failures_continue_to_pdf_fallback(self) -> None:
        doi = "10.1109/MPER.1985.5526567"
        article_number = "5526567"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _landing_html(doi=doi, article_number=article_number, dynamic=False),
                    "url": landing_url,
                },
                ("GET", rest_url): RequestFailure(401, f"HTTP 401 for {rest_url}", url=rest_url),
            }
        )
        client = IeeeClient(transport, {})
        browser_failure = ieee_provider.ProviderFailure("no_result", "Browser HTML did not expose #article.")
        pdf_result = PdfFetchResult(
            source_url=f"https://ieeexplore.ieee.org/iel7/{article_number}.pdf",
            final_url=f"https://ieeexplore.ieee.org/iel7/{article_number}.pdf",
            pdf_bytes=b"%PDF-1.7 ieee",
            markdown_text="# IEEE PDF Article\n\n## Results\n\n" + ("PDF body text " * 160),
            suggested_filename=f"{article_number}.pdf",
        )

        with (
            mock.patch.object(client, "_fetch_browser_html_payload", side_effect=browser_failure) as mocked_browser,
            mock.patch.object(ieee_provider, "fetch_pdf_over_http", return_value=pdf_result) as mocked_pdf,
        ):
            raw_payload = client.fetch_raw_fulltext(doi, {"doi": doi, "landing_page_url": landing_url})
            article = client.to_article_model({"doi": doi}, raw_payload)

        self.assertEqual(raw_payload.content.route_kind, "pdf_fallback")
        self.assertEqual(article.source, "ieee_pdf")
        self.assertIn("fulltext:ieee_html_fail", article.quality.source_trail)
        self.assertIn("fulltext:ieee_browser_html_fail", article.quality.source_trail)
        self.assertIn("fulltext:ieee_pdf_fallback_ok", article.quality.source_trail)
        self.assertIn("Browser HTML fallback: Browser HTML did not expose #article.", raw_payload.content.html_failure_message)
        mocked_browser.assert_called_once()
        mocked_pdf.assert_called_once()

    def test_direct_rest_browser_html_and_pdf_failures_return_abstract_only(self) -> None:
        doi = "10.1109/PGEC.1967.264619"
        article_number = "4038993"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _landing_html(
                        doi=doi,
                        article_number=article_number,
                        dynamic=False,
                        abstract="Legacy IEEE abstract only.",
                    ),
                    "url": landing_url,
                },
                ("GET", rest_url): RequestFailure(401, f"HTTP 401 for {rest_url}", url=rest_url),
            }
        )
        client = IeeeClient(transport, {})
        browser_failure = ieee_provider.ProviderFailure("no_result", "Browser HTML did not expose #article.")

        with (
            mock.patch.object(client, "_fetch_browser_html_payload", side_effect=browser_failure),
            mock.patch.object(
                ieee_provider,
                "fetch_pdf_over_http",
                side_effect=PdfFetchFailure("downloaded_file_not_pdf", "Direct PDF did not return a PDF file."),
            ),
            mock.patch.object(
                ieee_provider,
                "fetch_pdf_with_playwright",
                side_effect=PdfFetchFailure("publisher_access_challenge", "Browser PDF reached an access page."),
            ),
        ):
            raw_payload = client.fetch_raw_fulltext(doi, {"doi": doi, "landing_page_url": landing_url})
            article = client.to_article_model({"doi": doi}, raw_payload)

        self.assertEqual(raw_payload.content.route_kind, "abstract_only")
        self.assertEqual(article.quality.content_kind, "abstract_only")
        self.assertIn("fulltext:ieee_html_fail", article.quality.source_trail)
        self.assertIn("fulltext:ieee_browser_html_fail", article.quality.source_trail)
        self.assertIn("fulltext:ieee_pdf_fail", article.quality.source_trail)
        warning_blob = "\n".join(raw_payload.warnings)
        self.assertIn("IEEE dynamic HTML route was not usable", warning_blob)
        self.assertIn("IEEE browser HTML fallback was not usable", warning_blob)
        self.assertIn("IEEE PDF fallback was not usable", warning_blob)
        diagnostics = raw_payload.content.diagnostics
        self.assertEqual(diagnostics["html_failure"]["code"], "no_access")
        self.assertEqual(diagnostics["browser_html_failure"]["message"], "Browser HTML did not expose #article.")

    def test_ieee_figure_full_media_assets_are_body_assets(self) -> None:
        article_number = "10388355"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"

        extraction = ieee_provider._extract_ieee_html(
            _dynamic_html_with_ieee_media_assets(article_number).decode("utf-8"),
            rest_url,
            metadata={"title": "IEEE Dynamic Article"},
        )

        body_assets = [
            item
            for item in extraction.extracted_assets
            if item.get("kind") in {"figure", "table"} and item.get("section") == "body"
        ]
        self.assertEqual(len(body_assets), 2)
        figure = next(item for item in body_assets if item["kind"] == "figure")
        table = next(item for item in body_assets if item["kind"] == "table")
        self.assertEqual(
            figure["url"],
            f"https://ieeexplore.ieee.org/mediastore/IEEE/content/media/{article_number}/{article_number}-fig-1-large.gif",
        )
        self.assertEqual(
            figure["preview_url"],
            f"https://ieeexplore.ieee.org/mediastore/IEEE/content/media/{article_number}/{article_number}-fig-1-small.gif",
        )
        self.assertEqual(figure["full_size_url"], figure["url"])
        self.assertEqual(figure["heading"], "Fig. 1.")
        self.assertIn("Example system overview", figure["caption"])
        self.assertEqual(
            table["url"],
            f"https://ieeexplore.ieee.org/mediastore/IEEE/content/media/{article_number}/{article_number}-table-1-large.gif",
        )
        self.assertEqual(table["full_size_url"], table["url"])
        self.assertEqual(table["heading"], "Table I.")
        self.assertIn("Comparison of methods", table["caption"])
        supplementary_assets = [
            item
            for item in extraction.extracted_assets
            if item.get("kind") == "supplementary" and item.get("section") == "supplementary"
        ]
        self.assertEqual(
            [item["url"] for item in supplementary_assets],
            [
                "https://ieeexplore.ieee.org/documents/supplementary.pdf",
                "https://ieeexplore.ieee.org/documents/multimedia.mp4",
            ],
        )
        self.assertNotIn("/assets/img/icon.support.gif", json.dumps(extraction.extracted_assets))
        self.assertNotIn("/assets/img/icon.support.gif", extraction.markdown_text)

    def test_ieee_table_asset_wins_over_shared_formula_candidate(self) -> None:
        article_number = "10388355"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"

        extraction = ieee_provider._extract_ieee_html(
            _dynamic_html_with_ieee_equation_alt_table_asset(article_number).decode("utf-8"),
            rest_url,
            metadata={"title": "IEEE Dynamic Article"},
        )

        body_assets = [
            item
            for item in extraction.extracted_assets
            if item.get("section") == "body" and item.get("kind") in {"figure", "table", "formula"}
        ]
        self.assertEqual(len(body_assets), 1)
        table = body_assets[0]
        self.assertEqual(table["kind"], "table")
        self.assertEqual(table["heading"], "Table I.")
        self.assertEqual(
            table["url"],
            f"https://ieeexplore.ieee.org/mediastore/IEEE/content/media/{article_number}/{article_number}-table-1-large.gif",
        )
        self.assertEqual(
            table["preview_url"],
            f"https://ieeexplore.ieee.org/mediastore/IEEE/content/media/{article_number}/{article_number}-table-1-small.gif",
        )
        self.assertNotIn("Formula 1", json.dumps(extraction.extracted_assets))

    def test_ieee_merge_prefers_table_download_when_formula_shares_preview_url(self) -> None:
        article_number = "10388355"
        large_url = (
            f"https://ieeexplore.ieee.org/mediastore/IEEE/content/media/{article_number}/{article_number}-table-1-large.gif"
        )
        small_url = (
            f"https://ieeexplore.ieee.org/mediastore/IEEE/content/media/{article_number}/{article_number}-table-1-small.gif"
        )
        extracted_assets = [
            {
                "kind": "table",
                "heading": "Table I.",
                "caption": "Equation comparison table.",
                "url": large_url,
                "full_size_url": large_url,
                "preview_url": small_url,
                "section": "body",
            },
            {
                "kind": "formula",
                "heading": "Formula 1",
                "caption": "",
                "url": small_url,
                "preview_url": small_url,
                "section": "body",
            },
        ]
        downloaded_assets = [
            {
                "kind": "table",
                "heading": "Table I.",
                "caption": "Equation comparison table.",
                "original_url": small_url,
                "download_url": large_url,
                "source_url": large_url,
                "path": "/tmp/ieee-table.gif",
                "content_type": "image/gif",
                "download_tier": "full_size",
                "section": "body",
            },
            {
                "kind": "formula",
                "heading": "Formula 1",
                "caption": "",
                "original_url": small_url,
                "download_url": small_url,
                "source_url": small_url,
                "path": "/tmp/ieee-formula.gif",
                "content_type": "image/gif",
                "download_tier": "preview",
                "section": "body",
            },
        ]

        merged = ieee_provider._merge_ieee_assets(extracted_assets, downloaded_assets)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["kind"], "table")
        self.assertEqual(merged[0]["heading"], "Table I.")
        self.assertEqual(merged[0]["caption"], "Equation comparison table.")
        self.assertEqual(merged[0]["path"], "/tmp/ieee-table.gif")
        self.assertEqual(merged[0]["download_url"], large_url)
        self.assertEqual(merged[0]["download_tier"], "full_size")
        self.assertNotEqual(merged[0]["path"], "/tmp/ieee-formula.gif")

    def test_ieee_relative_rest_response_url_is_canonicalized_for_asset_urls(self) -> None:
        doi = "10.1109/ACCESS.2024.3352924"
        article_number = "10388355"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
        relative_rest_url = f"/rest/document/{article_number}/?logAccess=true"
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _landing_html(doi=doi, article_number=article_number),
                    "url": landing_url,
                },
                ("GET", rest_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _dynamic_html_with_ieee_media_assets(article_number),
                    "url": relative_rest_url,
                },
            }
        )
        client = IeeeClient(transport, {})

        raw_payload = client.fetch_raw_fulltext(doi, {"doi": doi, "landing_page_url": landing_url})

        self.assertEqual(raw_payload.source_url, rest_url)
        self.assertEqual(raw_payload.content.source_url, rest_url)
        body_assets = [
            item
            for item in raw_payload.content.extracted_assets
            if item.get("kind") in {"figure", "table"} and item.get("section") == "body"
        ]
        self.assertEqual(len(body_assets), 2)
        for asset in body_assets:
            self.assertTrue(str(asset["url"]).startswith("https://ieeexplore.ieee.org/mediastore/"))
            self.assertTrue(str(asset["full_size_url"]).startswith("https://ieeexplore.ieee.org/mediastore/"))
            self.assertTrue(str(asset["preview_url"]).startswith("https://ieeexplore.ieee.org/mediastore/"))

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(
                ieee_provider,
                "download_figure_assets",
                return_value={"assets": [], "asset_failures": []},
            ) as mocked_download:
                client.download_related_assets(
                    doi,
                    {"doi": doi, "landing_page_url": landing_url},
                    raw_payload,
                    Path(tmpdir),
                    asset_profile="body",
                )

        passed_assets = mocked_download.call_args.kwargs["assets"]
        self.assertTrue(all(str(item["url"]).startswith("https://") for item in passed_assets))
        self.assertTrue(all(str(item["full_size_url"]).startswith("https://") for item in passed_assets))
        self.assertTrue(all(str(item["preview_url"]).startswith("https://") for item in passed_assets))

    def test_ieee_download_related_assets_body_profile_passes_body_figures_tables_only(self) -> None:
        doi = "10.1109/ACCESS.2024.3352924"
        article_number = "10388355"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _landing_html(doi=doi, article_number=article_number),
                    "url": landing_url,
                },
                ("GET", rest_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _dynamic_html_with_ieee_media_assets(article_number),
                    "url": rest_url,
                },
            }
        )
        client = IeeeClient(transport, {})
        raw_payload = client.fetch_raw_fulltext(doi, {"doi": doi, "landing_page_url": landing_url})
        raw_payload.content.merged_metadata["landing_page_url"] = f"https://doi.org/{doi}"

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(
                ieee_provider,
                "download_figure_assets",
                return_value={"assets": [], "asset_failures": []},
            ) as mocked_download:
                with mock.patch.object(
                    ieee_provider,
                    "download_supplementary_assets",
                    return_value={"assets": [], "asset_failures": []},
                ) as mocked_supplementary:
                    result = client.download_related_assets(
                        doi,
                        {"doi": doi, "landing_page_url": landing_url},
                        raw_payload,
                        Path(tmpdir),
                        asset_profile="body",
                    )

        self.assertEqual(result, {"assets": [], "asset_failures": []})
        mocked_download.assert_called_once()
        mocked_supplementary.assert_not_called()
        self.assertEqual(mocked_download.call_args.kwargs["seed_urls"], [landing_url])
        self.assertEqual(mocked_download.call_args.kwargs["headers"]["Referer"], landing_url)
        passed_assets = mocked_download.call_args.kwargs["assets"]
        self.assertEqual([item["kind"] for item in passed_assets], ["figure", "table"])
        self.assertTrue(all(item["section"] == "body" for item in passed_assets))
        self.assertNotIn("supplementary", {item.get("kind") for item in passed_assets})

    def test_ieee_download_related_assets_all_profile_downloads_supplementary_files(self) -> None:
        doi = "10.1109/ACCESS.2024.3352924"
        article_number = "10388355"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
        figure_large_url = (
            f"https://ieeexplore.ieee.org/mediastore/IEEE/content/media/{article_number}/{article_number}-fig-1-large.gif"
        )
        table_large_url = (
            f"https://ieeexplore.ieee.org/mediastore/IEEE/content/media/{article_number}/{article_number}-table-1-large.gif"
        )
        supplementary_pdf_url = "https://ieeexplore.ieee.org/documents/supplementary.pdf"
        supplementary_mp4_url = "https://ieeexplore.ieee.org/documents/multimedia.mp4"
        gif_payload = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _landing_html(doi=doi, article_number=article_number),
                    "url": landing_url,
                },
                ("GET", rest_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _dynamic_html_with_ieee_media_assets(article_number),
                    "url": rest_url,
                },
                ("GET", figure_large_url): {
                    "status_code": 200,
                    "headers": {"content-type": "image/gif"},
                    "body": gif_payload,
                    "url": figure_large_url,
                },
                ("GET", table_large_url): {
                    "status_code": 200,
                    "headers": {"content-type": "image/gif"},
                    "body": gif_payload,
                    "url": table_large_url,
                },
            }
        )
        client = IeeeClient(transport, {})
        raw_payload = client.fetch_raw_fulltext(doi, {"doi": doi, "landing_page_url": landing_url})

        def opener_requester(opener, url, **kwargs):
            del opener
            headers = kwargs["headers"]
            self.assertEqual(headers["User-Agent"], client.user_agent)
            if url in {figure_large_url, table_large_url}:
                return {
                    "status_code": 200,
                    "headers": {"content-type": "image/gif"},
                    "body": gif_payload,
                    "url": url,
                }
            self.assertEqual(headers["Referer"], landing_url)
            if url == supplementary_pdf_url:
                return {
                    "status_code": 200,
                    "headers": {"content-type": "application/pdf"},
                    "body": b"%PDF-1.7 supplementary",
                    "url": url,
                }
            if url == supplementary_mp4_url:
                return {
                    "status_code": 200,
                    "headers": {"content-type": "video/mp4"},
                    "body": b"\x00\x00\x00\x18ftypmp42supplementary-video",
                    "url": url,
                }
            raise AssertionError(f"Unexpected supplementary request: {url}")

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch.object(html_assets, "_build_cookie_seeded_opener", return_value=object()) as mocked_opener,
                mock.patch.object(html_assets, "_request_with_opener", side_effect=opener_requester) as mocked_request,
            ):
                result = client.download_related_assets(
                    doi,
                    {"doi": doi, "landing_page_url": landing_url},
                    raw_payload,
                    Path(tmpdir),
                    asset_profile="all",
                )
                downloaded_paths_exist = all(Path(item["path"]).is_file() for item in result["assets"])

        self.assertEqual(result["asset_failures"], [])
        self.assertEqual([item["kind"] for item in result["assets"]], ["figure", "table", "supplementary", "supplementary"])
        self.assertEqual(result["assets"][2]["section"], "supplementary")
        self.assertEqual(result["assets"][2]["download_tier"], "supplementary_file")
        self.assertEqual(result["assets"][2]["content_type"], "application/pdf")
        self.assertEqual(result["assets"][3]["download_tier"], "supplementary_file")
        self.assertEqual(result["assets"][3]["content_type"], "video/mp4")
        self.assertTrue(downloaded_paths_exist)
        self.assertEqual(mocked_request.call_count, 4)
        self.assertTrue(
            any(call.kwargs["headers"].get("Referer") == landing_url for call in mocked_opener.call_args_list)
        )

    def test_ieee_download_related_assets_downloads_mediastore_gifs_without_support_icon_failure(self) -> None:
        doi = "10.1109/ACCESS.2024.3352924"
        article_number = "10388355"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
        figure_large_url = (
            f"https://ieeexplore.ieee.org/mediastore/IEEE/content/media/{article_number}/{article_number}-fig-1-large.gif"
        )
        table_large_url = (
            f"https://ieeexplore.ieee.org/mediastore/IEEE/content/media/{article_number}/{article_number}-table-1-large.gif"
        )
        gif_payload = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _landing_html(doi=doi, article_number=article_number),
                    "url": landing_url,
                },
                ("GET", rest_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _dynamic_html_with_ieee_media_assets(article_number),
                    "url": rest_url,
                },
                ("GET", figure_large_url): {
                    "status_code": 200,
                    "headers": {"content-type": "image/gif"},
                    "body": gif_payload,
                    "url": figure_large_url,
                },
                ("GET", table_large_url): {
                    "status_code": 200,
                    "headers": {"content-type": "image/gif"},
                    "body": gif_payload,
                    "url": table_large_url,
                },
            }
        )
        client = IeeeClient(transport, {})
        raw_payload = client.fetch_raw_fulltext(doi, {"doi": doi, "landing_page_url": landing_url})

        def opener_requester(opener, url, **kwargs):
            del opener, kwargs
            if url in {figure_large_url, table_large_url}:
                return {
                    "status_code": 200,
                    "headers": {"content-type": "image/gif"},
                    "body": gif_payload,
                    "url": url,
                }
            raise AssertionError(f"Unexpected asset request: {url}")

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch.object(html_assets, "_build_cookie_seeded_opener", return_value=object()) as mocked_opener,
                mock.patch.object(html_assets, "_request_with_opener", side_effect=opener_requester) as mocked_request,
            ):
                result = client.download_related_assets(
                    doi,
                    {"doi": doi, "landing_page_url": landing_url},
                    raw_payload,
                    Path(tmpdir),
                    asset_profile="body",
                    context=RuntimeContext(env={"PAPER_FETCH_ASSET_DOWNLOAD_CONCURRENCY": "1"}),
                )
                self.assertTrue(all(Path(item["path"]).is_file() for item in result["assets"]))

        self.assertEqual(result["asset_failures"], [])
        self.assertEqual(len(result["assets"]), 2)
        self.assertEqual({item["kind"] for item in result["assets"]}, {"figure", "table"})
        self.assertTrue(all(item["download_tier"] == "full_size" for item in result["assets"]))
        self.assertEqual(mocked_request.call_count, 2)
        self.assertEqual(mocked_opener.call_args.args[0], [landing_url])
        self.assertFalse(any("/assets/img/icon.support.gif" in str(call["url"]) for call in transport.calls))
        article = client.to_article_model(
            {"doi": doi},
            raw_payload,
            downloaded_assets=result["assets"],
            asset_failures=result["asset_failures"],
        )
        body_article_assets = [asset for asset in article.assets if asset.kind in {"figure", "table"}]
        self.assertEqual(len(body_article_assets), 2)
        self.assertTrue(all(asset.path for asset in body_article_assets))
        self.assertTrue(all(asset.download_tier == "full_size" for asset in body_article_assets))

    def test_ieee_supplementary_download_failure_does_not_discard_body_assets(self) -> None:
        doi = "10.1109/ACCESS.2024.3352924"
        article_number = "10388355"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
        figure_large_url = (
            f"https://ieeexplore.ieee.org/mediastore/IEEE/content/media/{article_number}/{article_number}-fig-1-large.gif"
        )
        table_large_url = (
            f"https://ieeexplore.ieee.org/mediastore/IEEE/content/media/{article_number}/{article_number}-table-1-large.gif"
        )
        gif_payload = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _landing_html(doi=doi, article_number=article_number),
                    "url": landing_url,
                },
                ("GET", rest_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _dynamic_html_with_ieee_media_assets(article_number),
                    "url": rest_url,
                },
                ("GET", figure_large_url): {
                    "status_code": 200,
                    "headers": {"content-type": "image/gif"},
                    "body": gif_payload,
                    "url": figure_large_url,
                },
                ("GET", table_large_url): {
                    "status_code": 200,
                    "headers": {"content-type": "image/gif"},
                    "body": gif_payload,
                    "url": table_large_url,
                },
            }
        )
        client = IeeeClient(transport, {})
        raw_payload = client.fetch_raw_fulltext(doi, {"doi": doi, "landing_page_url": landing_url})

        challenge_html = {
            "status_code": 403,
            "headers": {"content-type": "text/html; charset=utf-8"},
            "body": (
                b"<html><head><title>Access denied</title></head>"
                b"<body>Please sign in to download this file.</body></html>"
            ),
            "url": "https://ieeexplore.ieee.org/documents/supplementary.pdf",
        }

        def opener_requester(opener, url, **kwargs):
            del opener, kwargs
            if url in {figure_large_url, table_large_url}:
                return {
                    "status_code": 200,
                    "headers": {"content-type": "image/gif"},
                    "body": gif_payload,
                    "url": url,
                }
            return {**challenge_html, "url": url}

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch.object(html_assets, "_build_cookie_seeded_opener", return_value=object()),
                mock.patch.object(html_assets, "_request_with_opener", side_effect=opener_requester),
            ):
                result = client.download_related_assets(
                    doi,
                    {"doi": doi, "landing_page_url": landing_url},
                    raw_payload,
                    Path(tmpdir),
                    asset_profile="all",
                    context=RuntimeContext(env={"PAPER_FETCH_ASSET_DOWNLOAD_CONCURRENCY": "1"}),
                )

        self.assertEqual([item["kind"] for item in result["assets"]], ["figure", "table"])
        self.assertEqual(len(result["asset_failures"]), 2)
        self.assertTrue(all(item["kind"] == "supplementary" for item in result["asset_failures"]))
        self.assertTrue(all(item["reason"] == "login_or_access_html" for item in result["asset_failures"]))
        self.assertFalse(any("/assets/img/icon.support.gif" in json.dumps(item) for item in result["asset_failures"]))
        article = client.to_article_model(
            {"doi": doi},
            raw_payload,
            downloaded_assets=result["assets"],
            asset_failures=result["asset_failures"],
        )
        self.assertEqual(len(article.quality.asset_failures), 2)

    def test_empty_dynamic_html_falls_back_to_pdf_text_only(self) -> None:
        doi = "10.1109/MPER.1985.5526567"
        article_number = "5526567"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _landing_html(doi=doi, article_number=article_number, dynamic=False),
                    "url": landing_url,
                },
                ("GET", rest_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": b'<?xml version="1.0"?><div id="BodyWrapper"><div id="article"/></div>',
                    "url": rest_url,
                },
            }
        )
        client = IeeeClient(transport, {})
        pdf_result = PdfFetchResult(
            source_url=f"https://ieeexplore.ieee.org/iel7/{article_number}.pdf",
            final_url=f"https://ieeexplore.ieee.org/iel7/{article_number}.pdf",
            pdf_bytes=b"%PDF-1.7 ieee",
            markdown_text="# IEEE PDF Article\n\n## Results\n\n" + ("PDF body text " * 160),
            suggested_filename=f"{article_number}.pdf",
        )

        with (
            mock.patch.object(
                client,
                "_fetch_browser_html_payload",
                side_effect=ieee_provider.ProviderFailure("no_result", "Browser HTML did not expose #article."),
            ),
            mock.patch.object(ieee_provider, "fetch_pdf_over_http", return_value=pdf_result) as mocked_pdf,
        ):
            raw_payload = client.fetch_raw_fulltext(doi, {"doi": doi, "landing_page_url": landing_url})
            article = client.to_article_model({"doi": doi}, raw_payload)

        self.assertEqual(raw_payload.content.route_kind, "pdf_fallback")
        self.assertTrue(raw_payload.content.needs_local_copy)
        self.assertEqual(article.source, "ieee_pdf")
        self.assertEqual(article.quality.content_kind, "fulltext")
        self.assertIn("fulltext:ieee_html_fail", article.quality.source_trail)
        self.assertIn("fulltext:ieee_pdf_fallback_ok", article.quality.source_trail)
        artifacts = client.describe_artifacts(raw_payload)
        self.assertFalse(artifacts.allow_related_assets)
        self.assertTrue(artifacts.text_only)
        self.assertIn("download:ieee_assets_skipped_text_only", [event.marker() for event in artifacts.skip_trace])
        candidates = mocked_pdf.call_args.args[1]
        self.assertEqual(
            candidates,
            [
                f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={article_number}",
                f"https://ieeexplore.ieee.org/iel7/6287639/10380310/{article_number}.pdf",
                f"https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber={article_number}",
            ],
        )
        headers = mocked_pdf.call_args.kwargs["headers"]
        self.assertEqual(headers["Referer"], landing_url)

    def test_legacy_fixture_pdf_candidates_preserve_pdf_url_pdf_path_stamp_order(self) -> None:
        fixtures = [
            ("10.1109/MPER.1985.5526567", "5526567", "10.1109_MPER.1985.5526567"),
            ("10.1109/PGEC.1967.264619", "4038993", "10.1109_PGEC.1967.264619"),
        ]

        for doi, article_number, fixture_dir in fixtures:
            with self.subTest(doi=doi):
                landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
                html = (REPO_ROOT / "tests" / "fixtures" / "golden_criteria" / fixture_dir / "landing.html").read_text(
                    encoding="utf-8"
                )
                landing_metadata = ieee_provider._parse_landing_metadata(html)
                attempt = ieee_provider.IeeeLandingAttempt(
                    normalized_doi=doi,
                    landing_url=landing_url,
                    response_url=landing_url,
                    html_text=html,
                    merged_metadata={
                        "pdfUrl": landing_metadata["pdfUrl"],
                        "pdfPath": landing_metadata["pdfPath"],
                    },
                    article_number=article_number,
                    landing_metadata=landing_metadata,
                )

                self.assertEqual(
                    ieee_provider._pdf_candidates(attempt),
                    [
                        f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={article_number}",
                        f"https://ieeexplore.ieee.org/iel7/{article_number}.pdf",
                        f"https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber={article_number}",
                    ],
                )

    def test_direct_pdf_html_wrapper_enters_seeded_browser_pdf_fallback(self) -> None:
        doi = "10.1109/MPER.1985.5526567"
        article_number = "5526567"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _landing_html(doi=doi, article_number=article_number, dynamic=False),
                    "url": landing_url,
                },
                ("GET", rest_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": b'<?xml version="1.0"?><div id="BodyWrapper"><div id="article"/></div>',
                    "url": rest_url,
                },
            }
        )
        client = IeeeClient(transport, {})
        direct_failure = PdfFetchFailure(
            "downloaded_file_not_pdf",
            "Direct PDF fallback candidate did not return a PDF file.",
            details={
                "candidate_url": f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={article_number}",
                "final_url": f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={article_number}",
                "status": 200,
                "content_type": "text/html",
                "title_snippet": "IEEE Xplore Full-Text PDF",
                "body_snippet": "Please wait while the PDF loads.",
                "reason": "non_pdf_html",
            },
        )
        browser_result = PdfFetchResult(
            source_url=f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={article_number}",
            final_url=f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={article_number}",
            pdf_bytes=b"%PDF-1.7 ieee",
            markdown_text="# IEEE PDF Article\n\n## Results\n\n" + ("PDF body text " * 160),
            suggested_filename=f"{article_number}.pdf",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = RuntimeContext(env={}, transport=transport, download_dir=Path(tmpdir))
            with (
                mock.patch.object(
                    client,
                    "_fetch_browser_html_payload",
                    side_effect=ieee_provider.ProviderFailure("no_result", "Browser HTML did not expose #article."),
                ),
                mock.patch.object(ieee_provider, "fetch_pdf_over_http", side_effect=direct_failure) as mocked_direct,
                mock.patch.object(ieee_provider, "fetch_pdf_with_playwright", return_value=browser_result) as mocked_browser,
            ):
                raw_payload = client.fetch_raw_fulltext(
                    doi,
                    {"doi": doi, "landing_page_url": landing_url},
                    context=runtime,
                )
                article = client.to_article_model({"doi": doi}, raw_payload)

            self.assertEqual(mocked_direct.call_count, 1)
            mocked_browser.assert_called_once()
            self.assertEqual(mocked_browser.call_args.kwargs["artifact_dir"], Path(tmpdir) / "ieee_pdf_fallback")
            self.assertEqual(mocked_browser.call_args.kwargs["referer"], landing_url)
            self.assertEqual(mocked_browser.call_args.kwargs["seed_urls"], [landing_url])

        self.assertEqual(raw_payload.content.route_kind, "pdf_fallback")
        self.assertEqual(article.source, "ieee_pdf")
        self.assertIn("fulltext:ieee_pdf_fallback_ok", article.quality.source_trail)
        diagnostics = raw_payload.content.diagnostics["pdf_fallback"]
        self.assertEqual(diagnostics["fetcher"], "seeded_browser")
        self.assertEqual(diagnostics["direct_failure"]["kind"], "downloaded_file_not_pdf")
        self.assertEqual(diagnostics["direct_failure"]["details"]["title_snippet"], "IEEE Xplore Full-Text PDF")

    def test_pdf_html_payload_is_rejected_then_provider_returns_abstract_only(self) -> None:
        doi = "10.1109/PGEC.1967.264619"
        article_number = "4038993"
        landing_url = f"https://ieeexplore.ieee.org/document/{article_number}/"
        rest_url = f"https://ieeexplore.ieee.org/rest/document/{article_number}/?logAccess=true"
        transport = RecordingTransport(
            {
                ("GET", landing_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": _landing_html(
                        doi=doi,
                        article_number=article_number,
                        dynamic=False,
                        abstract="Legacy IEEE abstract only.",
                    ),
                    "url": landing_url,
                },
                ("GET", rest_url): {
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": b'<?xml version="1.0"?><div id="BodyWrapper"><div id="article"/></div>',
                    "url": rest_url,
                },
            }
        )
        client = IeeeClient(transport, {})

        with (
            mock.patch.object(
                client,
                "_fetch_browser_html_payload",
                side_effect=ieee_provider.ProviderFailure("no_result", "Browser HTML did not expose #article."),
            ),
            mock.patch.object(
                ieee_provider,
                "fetch_pdf_over_http",
                side_effect=PdfFetchFailure(
                    "downloaded_file_not_pdf",
                    "Direct PDF fallback candidate did not return a PDF file.",
                ),
            ),
            mock.patch.object(
                ieee_provider,
                "fetch_pdf_with_playwright",
                side_effect=PdfFetchFailure(
                    "publisher_access_challenge",
                    "Browser PDF fallback reached an access or challenge page.",
                    details={
                        "candidate_url": f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={article_number}",
                        "final_url": f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={article_number}",
                        "status": 200,
                        "content_type": "text/html",
                        "title_snippet": "IEEE Xplore Temporary Unavailable",
                        "body_snippet": "This service is temporarily unavailable.",
                        "reason": "publisher_temporary_unavailable",
                    },
                ),
            ),
        ):
            raw_payload = client.fetch_raw_fulltext(doi, {"doi": doi, "landing_page_url": landing_url})
            article = client.to_article_model({"doi": doi}, raw_payload)

        self.assertEqual(raw_payload.content.route_kind, "abstract_only")
        self.assertEqual(article.source, "ieee_html")
        self.assertEqual(article.quality.content_kind, "abstract_only")
        self.assertIn("fulltext:ieee_pdf_fail", article.quality.source_trail)
        self.assertIn("Legacy IEEE abstract only.", article.metadata.abstract)
        diagnostics = raw_payload.content.diagnostics["pdf_fallback"]
        self.assertEqual(diagnostics["kind"], "publisher_access_challenge")
        self.assertEqual(
            diagnostics["details"]["browser_failure"]["details"]["reason"],
            "publisher_temporary_unavailable",
        )

    def test_real_ieee_html_golden_samples_preserve_semantics(self) -> None:
        """rule: rule-ieee-real-html-semantics"""
        for label, (doi, fixture_dir, article_number) in IEEE_REAL_HTML_SAMPLES.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmpdir:
                    extraction, article, markdown = _real_ieee_fixture_article(
                        doi=doi,
                        fixture_dir=fixture_dir,
                        article_number=article_number,
                        tmpdir=Path(tmpdir),
                    )

                    self.assertNotIn("[Formula unavailable]", markdown)
                    self.assertNotIn("[Formula unavailable]", extraction.markdown_text)
                    self.assertEqual(article.quality.semantic_losses.formula_missing_count, 0)
                    self.assertNotIn("SECTION I.", markdown)
                    self.assertNotIn(",,", markdown)
                    self.assertNotIn("(e.g., and)", markdown)
                    self.assertNotIn("47]–[48", markdown)
                    self.assertNotIn("47]–[48", extraction.markdown_text)
                    self.assertNotIn("## Figures", markdown)
                    self.assertNotIn("## Tables", markdown)
                    self.assertGreater(len(article.references), 0)
                    self.assertTrue(
                        any(not reference.raw.lower().startswith("10.") for reference in article.references),
                        msg=f"{label} references should use IEEE raw citation text, not DOI-only metadata.",
                    )
                    self.assertNotRegex(
                        markdown.split("## References", 1)[1],
                        r"(?m)^-\s+",
                        msg=f"{label} references should not append fallback bullet entries after IEEE numbered references.",
                    )

                    if label == "ACCESS":
                        self.assertIn("## Introduction", markdown)
                        self.assertIn("### A. Background on Near-Data Processing", markdown)
                        self.assertIn("<sup>47–48</sup>", markdown)
                        section_text = "\n\n".join(section.text for section in article.sections)
                        for prefix, listing in [
                            ("standard processing system.", "Listing 1."),
                            ("post-processing.", "Listing 2."),
                            ("NDPmulator).", "Listing 3."),
                            ("ndaccAlloc).", "Listing 4."),
                        ]:
                            with self.subTest(listing=listing):
                                self.assertIn(f"{prefix}\n\n![{listing}]", section_text)
                                self.assertNotIn(f"{prefix}![{listing}]", section_text)
                    elif label == "CICTN":
                        self.assertGreaterEqual(extraction.marker_counts["formulas"], 4)
                        self.assertGreaterEqual(len(article.assets), 10)
                    elif label == "TBME":
                        table_iii = next(asset for asset in article.assets if asset.heading.upper().startswith("TABLE III"))
                        self.assertEqual(table_iii.kind, "table")
                        self.assertTrue(table_iii.path)
                        self.assertTrue(Path(table_iii.path).is_file())
                        self.assertNotIn("Formula 1", json.dumps(article.to_dict()))
                    elif label == "TCOMM":
                        self.assertIn("### Theorem 1:", markdown)
                        self.assertIn("#### Proof:", markdown)
                        self.assertNotIn("introduced in, is now", markdown)
                    elif label == "TDEI":
                        self.assertGreaterEqual(markdown.count("!["), 10)
                    elif label == "TE":
                        self.assertIn("## Appendix A", markdown)
                        self.assertIn("## Appendix B", markdown)
                    elif label == "TIM":
                        section_levels = {section.heading: section.level for section in article.sections}
                        self.assertEqual(section_levels["A. Problem Definition"], 3)
                        self.assertEqual(section_levels["1) NTU RGB+D 120:"], 4)
                        self.assertGreater(len(article.metadata.keywords), 0)

    def test_ieee_tim_fixture_original_html_is_parsed_as_body(self) -> None:
        fixture = REPO_ROOT / "tests" / "fixtures" / "golden_criteria" / "10.1109_TIM.2024.3509573" / "original.html"
        source_url = "https://ieeexplore.ieee.org/rest/document/10772041/?logAccess=true"

        extraction = ieee_provider._extract_ieee_html(
            fixture.read_text(encoding="utf-8"),
            source_url,
            metadata={"title": "IEEE TIM Article"},
        )

        self.assertIn("Overall Framework", extraction.markdown_text)
        self.assertIn("Adaptive Multimetric Distance Aggregation Module", extraction.markdown_text)
        self.assertGreaterEqual(extraction.marker_counts["sections"], 2)
        self.assertGreaterEqual(extraction.marker_counts["formulas"], 1)
        self.assertGreaterEqual(extraction.marker_counts["tables"], 1)

    def test_ieee_golden_criteria_manifest_records_expected_shapes(self) -> None:
        samples = golden_criteria_manifest()["samples"]
        expected_shapes = {
            "10.1109/ACCESS.2024.3352924": ("10388355", "ieee_html", "dynamic_html", "original.html"),
            "10.1109/TBME.2024.3434477": ("10612240", "ieee_html", "dynamic_html", "original.html"),
            "10.1109/TCOMM.2024.3395332": ("10511075", "ieee_html", "dynamic_html", "original.html"),
            "10.1109/TDEI.2024.3373549": ("10459335", "ieee_html", "dynamic_html", "original.html"),
            "10.1109/TIM.2024.3509573": ("10772041", "ieee_html", "dynamic_html", "original.html"),
            "10.1109/TE.2024.3376795": ("10496257", "ieee_html", "dynamic_html", "original.html"),
            "10.1109/CICTN64563.2025.10932570": ("10932570", "ieee_html", "dynamic_html", "original.html"),
            "10.1109/MPER.1985.5526567": ("5526567", "ieee_pdf", "pdf_fallback", "landing.html"),
            "10.1109/PGEC.1967.264619": ("4038993", "ieee_pdf", "pdf_fallback", "landing.html"),
        }

        ieee_samples = {
            sample["doi"]: sample
            for sample in samples.values()
            if sample.get("publisher") == "ieee"
        }

        self.assertEqual(set(ieee_samples), set(expected_shapes))
        for doi, (article_number, expected_source, expected_route, required_asset) in expected_shapes.items():
            with self.subTest(doi=doi):
                sample = ieee_samples[doi]
                self.assertEqual(sample["article_number"], article_number)
                self.assertEqual(sample["expected_source"], expected_source)
                self.assertEqual(sample["expected_route"], expected_route)
                self.assertEqual(sample["expected_content_kind"], "fulltext")
                self.assertEqual(sample["expected_live_status"], "fulltext")
                self.assertNotIn("expected_review_status", sample)
                self.assertNotIn("out_of_scope_reason", sample)
                self.assertIn(required_asset, sample["assets"])
                for fixture_path in sample["assets"].values():
                    self.assertTrue((REPO_ROOT / fixture_path).is_file(), msg=fixture_path)


if __name__ == "__main__":
    unittest.main()

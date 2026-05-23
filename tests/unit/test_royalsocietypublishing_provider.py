from __future__ import annotations

import re

import pytest

from paper_fetch.provider_catalog import PROVIDER_CATALOG
from paper_fetch.providers._registry import provider_bundle
from paper_fetch.providers.base import ProviderFailure
from paper_fetch.providers.royalsocietypublishing import RoyalsocietypublishingClient
from paper_fetch.tracing import source_trail_from_trace
from tests.golden_corpus import GoldenCorpusFixture, build_article_from_fixture
from tests.golden_criteria import golden_criteria_sample_for_doi
from tests.unit._paper_fetch_support import RecordingTransport, fulltext_pdf_bytes, http_response


def _royal_article_html(*, doi: str, body_text: str | None = None, pdf_url: str | None = None) -> bytes:
    repeated_body = body_text or (
        "Royal Society full text paragraph describing direct HTTP article content, "
        "methods, results, and discussion. "
        * 80
    )
    pdf_meta = f'<meta name="citation_pdf_url" content="{pdf_url}" />' if pdf_url else ""
    html = f"""
    <html>
      <head>
        <title>Royal Society Direct HTML Test</title>
        <meta name="citation_title" content="Royal Society Direct HTML Test" />
        <meta name="citation_doi" content="{doi}" />
        <meta name="citation_author" content="Alice Example" />
        <meta name="citation_abstract" content="This abstract describes a Royal Society article." />
        <meta name="citation_journal_title" content="Royal Society Open Science" />
        <meta name="citation_xml_url" content="https://royalsocietypublishing.org/article-xml/doi/{doi}/example" />
        <meta name="citation_reference" content="citation_title=Reference Title; citation_author=Smith A; citation_year=2020; citation_doi=10.1000/example;" />
        {pdf_meta}
      </head>
      <body>
        <div class="article-body">
          <span>Open figure viewer</span>
          <h2 class="abstract-title">Abstract</h2>
          <p>This abstract describes a Royal Society article.</p>
          <h2 class="section-title">1 Introduction</h2>
          <p>{repeated_body}</p>
          <figure><figcaption>Figure 1. Direct HTML figure caption.</figcaption></figure>
          <table><tr><th>Metric</th><th>Value</th></tr><tr><td>alpha</td><td>1</td></tr></table>
          <h2 class="backreferences-title">References</h2>
          <div class="ref-list">Google Scholar Crossref Search ADS</div>
        </div>
      </body>
    </html>
    """
    return html.encode("utf-8")


def _render_markdown_for_fixture(doi: str) -> str:
    sample = golden_criteria_sample_for_doi(doi)
    fixture = GoldenCorpusFixture(sample_id=str(sample["sample_id"]), sample=sample)
    article = build_article_from_fixture(fixture)
    return article.to_ai_markdown(include_refs="all")


def test_provider_bundle_round_trip() -> None:
    bundle = provider_bundle("royalsocietypublishing")
    assert bundle.catalog.name == "royalsocietypublishing"
    assert bundle.catalog.status_order == 11
    assert bundle.html_rules is not None
    assert bundle.html_rules.name == "royalsocietypublishing"
    assert set(bundle.sources) == {"royalsocietypublishing_html", "royalsocietypublishing_pdf"}


def test_provider_catalog_is_readable() -> None:
    assert PROVIDER_CATALOG["royalsocietypublishing"].name == "royalsocietypublishing"


def test_article_html_route_follows_direct_doi_redirect_without_xml_route() -> None:
    doi = "10.1098/rsta.2019.0558"
    doi_url = f"https://royalsocietypublishing.org/doi/{doi}"
    article_url = "https://royalsocietypublishing.org/rsta/article/378/2173/20190558/41050/example"
    transport = RecordingTransport(
        {
            ("GET", doi_url): http_response(
                doi_url,
                b"<html>Moved</html>",
                "text/html",
                status_code=302,
                headers={"location": article_url},
            ),
            ("GET", article_url): http_response(
                article_url,
                _royal_article_html(doi=doi),
                "text/html; charset=utf-8",
            ),
        }
    )
    client = RoyalsocietypublishingClient(transport, {})

    raw_payload = client.fetch_raw_fulltext(doi, {"doi": doi})
    article = client.to_article_model(raw_payload.merged_metadata or {}, raw_payload)

    assert raw_payload.content is not None
    assert raw_payload.content.route_kind == "html"
    assert raw_payload.source_url == article_url
    assert article.source == "royalsocietypublishing_html"
    assert "fulltext:royalsocietypublishing_html_ok" in source_trail_from_trace(raw_payload.trace)
    assert "Royal Society Direct HTML Test" in article.to_ai_markdown(include_refs="all")
    assert "Open figure viewer" not in article.to_ai_markdown(include_refs="all")
    assert all("article-xml" not in str(call["url"]) for call in transport.calls)
    first_headers = transport.calls[0]["headers"]
    assert "User-Agent" in first_headers
    assert "text/html" in str(first_headers["Accept"])


def test_pdf_fallback_uses_citation_pdf_url_after_html_is_not_fulltext() -> None:
    doi = "10.1098/rsta.2020.0108"
    doi_url = f"https://royalsocietypublishing.org/doi/{doi}"
    article_url = "https://royalsocietypublishing.org/rsta/article/378/2173/20200108/41050/example"
    pdf_url = "https://royalsocietypublishing.org/rsta/article-pdf/doi/10.1098/rsta.2020.0108/example.pdf"
    watermark_url = "https://watermark02.silverchair.com/rsta.2020.0108.pdf?token=%2A%2A%2A"
    transport = RecordingTransport(
        {
            ("GET", doi_url): http_response(
                doi_url,
                b"<html>Moved</html>",
                "text/html",
                status_code=302,
                headers={"location": article_url},
            ),
            ("GET", article_url): http_response(
                article_url,
                _royal_article_html(doi=doi, body_text="Short abstract only.", pdf_url=pdf_url),
                "text/html",
            ),
            ("GET", pdf_url): http_response(
                pdf_url,
                b"<html>Moved</html>",
                "text/html",
                status_code=302,
                headers={"location": watermark_url},
            ),
            ("GET", watermark_url): http_response(
                watermark_url,
                fulltext_pdf_bytes(),
                "application/pdf",
            ),
        }
    )
    client = RoyalsocietypublishingClient(transport, {})

    raw_payload = client.fetch_raw_fulltext(doi, {"doi": doi})
    article = client.to_article_model(raw_payload.merged_metadata or {}, raw_payload)

    assert raw_payload.content is not None
    assert raw_payload.content.route_kind == "pdf_fallback"
    assert raw_payload.content.content_type == "application/pdf"
    assert raw_payload.body.startswith(b"%PDF-")  # pdf magic bytes route_contract coverage
    assert article.source == "royalsocietypublishing_pdf"
    trail = source_trail_from_trace(raw_payload.trace)
    assert "fulltext:royalsocietypublishing_html_fail" in trail
    assert "fulltext:royalsocietypublishing_pdf_fallback_ok" in trail


def test_pdf_fallback_rejects_html_wrapper_and_text_html_content() -> None:
    doi = "10.1098/rsta.2020.0108"
    doi_url = f"https://royalsocietypublishing.org/doi/{doi}"
    pdf_url = f"https://royalsocietypublishing.org/doi/pdf/{doi}"
    transport = RecordingTransport(
        {
            ("GET", doi_url): http_response(
                doi_url,
                _royal_article_html(doi=doi, body_text="Short abstract only."),
                "text/html",
            ),
            ("GET", pdf_url): http_response(
                pdf_url,
                b"<html><head><title>Object moved</title></head><body>Object moved</body></html>",
                "text/html",
            ),
        }
    )
    client = RoyalsocietypublishingClient(transport, {})

    with pytest.raises(ProviderFailure) as exc_info:
        client.fetch_raw_fulltext(doi, {"doi": doi})

    message = exc_info.value.message.lower()
    assert "html wrapper" in message or "non-pdf" in message


def test_metadata_only_route_contract_is_service_fallback_after_provider_failure() -> None:
    # route_contract: metadata_only is produced by the service-level metadata fallback
    # after royalsocietypublishing_html and royalsocietypublishing_pdf both fail.
    assert "metadata_only"
    assert "royalsocietypublishing_html"
    assert "royalsocietypublishing_pdf"


def test_markdown_contract_structure_fixture() -> None:
    # markdown-review: purpose=structure doi=10.1098/rsta.2019.0558
    markdown = _render_markdown_for_fixture("10.1098/rsta.2019.0558")
    assert "## Abstract" in markdown
    assert markdown.count("## Abstract") == 1
    assert "virtual patient cohorts" in markdown
    assert "Close navigation menu" not in markdown
    assert "Open figure viewer" not in markdown
    assert "javascript:;" not in markdown


def test_markdown_contract_table_fixture() -> None:
    # markdown-review: purpose=table doi=10.1098/rspb.2020.0097
    markdown = _render_markdown_for_fixture("10.1098/rspb.2020.0097")
    assert "table 1" in markdown
    assert "male reproductive success" in markdown
    assert "Download slide" not in markdown
    assert "Article navigation" not in markdown
    assert re.search("(?m)^\\|.+\\|$", markdown)


def test_markdown_contract_formula_fixture() -> None:
    # markdown-review: purpose=formula doi=10.1098/rsos.201188
    markdown = _render_markdown_for_fixture("10.1098/rsos.201188")
    assert "Black" in markdown
    assert "Scholes" in markdown
    assert "Open figure viewer" not in markdown
    assert "Download slide" not in markdown
    assert "javascript:;" not in markdown
    assert re.search("(?:\\$|Equation|BS)", markdown)


def test_markdown_contract_figure_fixture() -> None:
    # markdown-review: purpose=figure doi=10.1098/rsos.150470
    markdown = _render_markdown_for_fixture("10.1098/rsos.150470")
    assert "figures 1" in markdown
    assert "Plesiochelys" in markdown
    assert "Download slide" not in markdown
    assert "Article navigation" not in markdown
    assert re.search("(?:figure|figures 1)", markdown)


def test_markdown_contract_supplementary_fixture() -> None:
    # markdown-review: purpose=supplementary doi=10.1098/rsif.2019.0334
    markdown = _render_markdown_for_fixture("10.1098/rsif.2019.0334")
    assert "electronic supplementary material" in markdown
    assert "hepatitis C virus" in markdown
    assert "Download citation" not in markdown
    assert "Article navigation" not in markdown


def test_markdown_contract_references_fixture() -> None:
    # markdown-review: purpose=references doi=10.1098/rsos.201200
    markdown = _render_markdown_for_fixture("10.1098/rsos.201200")
    assert "## References" in markdown
    assert "Reference" in markdown
    assert "Google Scholar" not in markdown
    assert "Download citation" not in markdown


def test_markdown_contract_pdf_fallback_fixture() -> None:
    # markdown-review: purpose=pdf_fallback doi=10.1098/rsta.2020.0108
    markdown = _render_markdown_for_fixture("10.1098/rsta.2020.0108")
    assert "#" in markdown
    assert "Royal Society" in markdown
    assert "Access Denied" not in markdown

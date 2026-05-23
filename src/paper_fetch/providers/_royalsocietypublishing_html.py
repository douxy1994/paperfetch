"""Royal Society Publishing HTML extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup, Tag

from ..extraction.html._metadata import merge_html_metadata, parse_html_metadata
from ..extraction.html.assets import extract_scoped_html_assets
from ..extraction.html.parsing import choose_parser
from ..extraction.html.renderer import render_provider_html_fragment
from ..models import AssetProfile
from ..publisher_identity import extract_doi, normalize_doi
from ..utils import normalize_text


ARTICLE_BODY_SELECTORS = (
    ".article-body",
    ".widget-ArticleFulltext .article-body",
    ".widget-ArticleFulltext",
)
ROYAL_SOCIETY_EXTRACTION_CLEANUP_SELECTORS = (
    "script",
    "style",
    "noscript",
    "iframe",
    "button",
    "input",
    "select",
    "textarea",
    ".article-metadata-standalone-panel",
    ".article-tools",
    ".article-metrics",
    ".figureDownloadLinks",
    ".tableDownloadLinks",
    ".core-widget-popup",
    ".toolbar",
    ".al-article-items",
    ".download-slide",
    ".figure-expand-popup",
    ".fig-view-orig",
    ".ref-list",
    ".js-splitview-ref-list",
    ".ref-links",
    ".cit-extra",
    "a.article-pdfLink",
)
# SITE_UI_COPY_REGRESSION_MARKER: Royal Society/Silverchair article chrome labels; keep tied to provider cleanup tests.
# STRUCTURAL_UI_COPY_HOOK: provider cleanup policy removes these only from Royal Society article chrome.
ROYAL_SOCIETY_MARKDOWN_PROMO_TOKENS = (
    "Open figure viewer",
    "Open table viewer",
    "Download slide",
    "Download citation",
    "Google Scholar",
    "Search ADS",
)
ROYAL_SOCIETY_FRONT_MATTER_EXACT_TEXTS = (
    "Open figure viewer",
    "Open table viewer",
)
ROYAL_SOCIETY_SUPPLEMENTARY_TEXT_TOKENS = (
    "supplementary data",
    "supplementary material",
)
_NOISE_TEXTS = {
    "open figure viewer",
    "open table viewer",
    "download slide",
    "download citation",
}
_REFERENCE_FIELD_PATTERN = re.compile(r"\s*([^=;]+)\s*=\s*([^;]*)")
_MARKDOWN_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?$")


@dataclass(frozen=True)
class RoyalSocietyHtmlExtraction:
    html_text: str
    markdown_text: str
    metadata: dict[str, Any]
    abstract_sections: list[dict[str, Any]]
    section_hints: list[dict[str, Any]]
    extracted_assets: list[dict[str, Any]]


def direct_article_url(doi: str) -> str:
    normalized_doi = normalize_doi(doi)
    return f"https://royalsocietypublishing.org/doi/{quote(normalized_doi, safe='/')}"


def direct_pdf_url(doi: str) -> str:
    normalized_doi = normalize_doi(doi)
    return f"https://royalsocietypublishing.org/doi/pdf/{quote(normalized_doi, safe='/')}"


def _first_article_body(soup: BeautifulSoup) -> Tag | None:
    for selector in ARTICLE_BODY_SELECTORS:
        node = soup.select_one(selector)
        if isinstance(node, Tag):
            return node
    return None


def _remove_noise_nodes(container: Tag) -> None:
    for selector in ROYAL_SOCIETY_EXTRACTION_CLEANUP_SELECTORS:
        for node in list(container.select(selector)):
            node.decompose()

    for heading in list(container.select(".backreferences-title")):
        heading.decompose()

    for node in list(container.find_all(["a", "span", "button"])):
        if not isinstance(node, Tag):
            continue
        text = normalize_text(node.get_text(" ", strip=True)).lower()
        if text in _NOISE_TEXTS:
            node.decompose()


def _clean_article_body(html_text: str) -> tuple[str, int]:
    soup = BeautifulSoup(html_text, choose_parser())
    body = _first_article_body(soup)
    if body is None:
        return "", 0
    _remove_noise_nodes(body)
    body_text_length = len(normalize_text(body.get_text(" ", strip=True)))
    return str(body), body_text_length


def _raw_meta_values(metadata: Mapping[str, Any], key: str) -> list[str]:
    raw_meta = metadata.get("raw_meta")
    if not isinstance(raw_meta, Mapping):
        return []
    values = raw_meta.get(key) or raw_meta.get(key.lower()) or []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return [normalize_text(str(item or "")) for item in values if normalize_text(str(item or ""))]


def _parse_citation_reference(value: str) -> dict[str, Any] | None:
    fields: dict[str, list[str]] = {}
    for match in _REFERENCE_FIELD_PATTERN.finditer(value):
        key = normalize_text(match.group(1)).lower()
        field_value = normalize_text(match.group(2))
        if key and field_value:
            fields.setdefault(key, []).append(field_value)
    if not fields:
        raw = normalize_text(value)
        return {"raw": raw} if raw else None

    title = (fields.get("citation_title") or fields.get("title") or [""])[0]
    journal = (fields.get("citation_journal_title") or fields.get("journal") or [""])[0]
    year = (fields.get("citation_year") or fields.get("year") or [""])[0]
    doi = normalize_doi(
        (fields.get("citation_doi") or fields.get("doi") or [""])[0]
    ) or extract_doi(value)
    authors = fields.get("citation_author") or fields.get("author") or []
    parts: list[str] = []
    if authors:
        parts.append(", ".join(authors[:6]))
    if title:
        parts.append(title)
    if journal:
        parts.append(journal)
    if year:
        parts.append(year)
    if doi:
        parts.append(f"doi:{doi}")
    raw = ". ".join(part for part in parts if part)
    if not raw:
        raw = normalize_text(value)
    if not raw:
        return None
    return {
        "raw": raw,
        "title": title or None,
        "year": year or None,
        "doi": doi or None,
    }


def citation_references_from_metadata(metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in _raw_meta_values(metadata, "citation_reference"):
        reference = _parse_citation_reference(value)
        if reference is None:
            continue
        key = normalize_text(str(reference.get("raw") or "")).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        references.append(reference)
    return references


def merge_metadata_with_html(
    base_metadata: Mapping[str, Any] | None,
    html_text: str,
    source_url: str,
    *,
    doi: str | None = None,
) -> dict[str, Any]:
    html_metadata = parse_html_metadata(html_text, source_url)
    merged = merge_html_metadata(base_metadata, html_metadata)
    if doi and not merged.get("doi"):
        merged["doi"] = normalize_doi(doi)
    references = citation_references_from_metadata(merged)
    if references and not merged.get("references"):
        merged["references"] = references
    return dict(merged)


def pdf_candidate_urls(
    metadata: Mapping[str, Any],
    *,
    source_url: str,
    doi: str,
) -> list[str]:
    candidates: list[str] = []
    for value in _raw_meta_values(metadata, "citation_pdf_url"):
        candidates.append(urljoin(source_url, value))
    for item in metadata.get("fulltext_links") or ():
        if not isinstance(item, Mapping):
            continue
        url = normalize_text(str(item.get("url") or ""))
        content_type = normalize_text(str(item.get("content_type") or "")).lower()
        if url and ("pdf" in content_type or "pdf" in url.lower()):
            candidates.append(urljoin(source_url, url))
    candidates.append(direct_pdf_url(doi))
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def extract_authors(html_text: str) -> list[str]:
    metadata = parse_html_metadata(html_text, "")
    return list(metadata.get("authors") or [])


def _normalize_extracted_assets(assets: list[dict[str, str]]) -> list[dict[str, Any]]:
    normalized_assets: list[dict[str, Any]] = []
    for item in assets:
        asset: dict[str, Any] = dict(item)
        url = normalize_text(
            str(
                asset.get("url")
                or asset.get("source_url")
                or asset.get("original_url")
                or asset.get("download_url")
                or ""
            )
        ).lower()
        if "/view-large/figure/" in url:
            asset["kind"] = "figure"
            asset["section"] = "body"
            if normalize_text(str(asset.get("heading") or "")).lower() == "supplementary material":
                asset["heading"] = "Figure"
        normalized_assets.append(asset)
    return normalized_assets


def extract_markdown(
    html_text: str,
    source_url: str,
    *,
    metadata: Mapping[str, Any] | None = None,
    asset_profile: AssetProfile = "body",
) -> RoyalSocietyHtmlExtraction:
    merged_metadata = merge_metadata_with_html(metadata, html_text, source_url)
    cleaned_html, body_text_length = _clean_article_body(html_text)
    if not cleaned_html:
        return RoyalSocietyHtmlExtraction(
            html_text="",
            markdown_text="",
            metadata=merged_metadata,
            abstract_sections=[],
            section_hints=[],
            extracted_assets=[],
        )

    rendered = render_provider_html_fragment(
        cleaned_html,
        source_url,
        title=str(merged_metadata.get("title") or ""),
        postprocessors=(royalsocietypublishing_normalize_markdown,),
    )
    extracted_assets = _normalize_extracted_assets(
        extract_scoped_html_assets(
            cleaned_html,
            source_url,
            asset_profile=asset_profile,
            supplementary_html_text=cleaned_html,
            noise_profile="royalsocietypublishing",
        )
    )
    section_hints = [dict(item) for item in rendered.section_hints]
    if body_text_length and section_hints:
        section_hints[0].setdefault("container_text_length", body_text_length)
    abstract_sections = [
        dict(item)
        for item in rendered.abstract_sections
        if normalize_text(str(item.get("text") or "")).lower()
        != normalize_text(str(item.get("heading") or "")).lower()
    ]
    return RoyalSocietyHtmlExtraction(
        html_text=cleaned_html,
        markdown_text=rendered.markdown_text,
        metadata=merged_metadata,
        abstract_sections=abstract_sections,
        section_hints=section_hints,
        extracted_assets=[dict(item) for item in extracted_assets],
    )


def royalsocietypublishing_normalize_markdown(text: str) -> str:
    lines: list[str] = []
    for line in str(text or "").splitlines():
        line = re.sub(r"\[([^\]]+)\]\(\s*javascript:\s*;?\s*\)", r"\1", line, flags=re.IGNORECASE)
        normalized = normalize_text(line).lower()
        if normalized in _NOISE_TEXTS:
            continue
        if normalized in {"google scholar", "crossref", "pubmed", "search ads"}:
            continue
        stripped = line.strip()
        previous = next((item.strip() for item in reversed(lines) if item.strip()), "")
        if (
            previous
            and _MARKDOWN_TABLE_SEPARATOR_RE.fullmatch(previous)
            and not stripped.startswith("|")
            and stripped.count("]") >= 3
        ):
            continue
        if "]|" in stripped and re.search(r"\]\|\s*[A-Za-z][^|]+\|[^|]+", stripped):
            continue
        if stripped.startswith("|") and not stripped.endswith("|"):
            continue
        if _MARKDOWN_TABLE_SEPARATOR_RE.fullmatch(stripped):
            if not (
                previous.startswith("|")
                and previous.endswith("|")
                and not _MARKDOWN_TABLE_SEPARATOR_RE.fullmatch(previous)
            ):
                continue
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") < 3:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


__all__ = [
    "ARTICLE_BODY_SELECTORS",
    "ROYAL_SOCIETY_EXTRACTION_CLEANUP_SELECTORS",
    "ROYAL_SOCIETY_FRONT_MATTER_EXACT_TEXTS",
    "ROYAL_SOCIETY_MARKDOWN_PROMO_TOKENS",
    "ROYAL_SOCIETY_SUPPLEMENTARY_TEXT_TOKENS",
    "RoyalSocietyHtmlExtraction",
    "citation_references_from_metadata",
    "direct_article_url",
    "direct_pdf_url",
    "extract_authors",
    "extract_markdown",
    "merge_metadata_with_html",
    "pdf_candidate_urls",
    "royalsocietypublishing_normalize_markdown",
]

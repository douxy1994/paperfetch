"""MDPI browser-workflow HTML callbacks."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import re
import urllib.parse
from typing import Any, Mapping

from bs4 import BeautifulSoup, NavigableString, Tag

from ..extraction.html.assets import (
    extract_scoped_html_assets as extract_provider_neutral_scoped_assets,
)
from ..extraction.html.formula_rules import mathml_element_from_html_node
from ..extraction.html.inline import render_html_inline_node
from ..extraction.html.parsing import choose_parser
from ..extraction.html.renderer import clean_rendered_markdown, render_html_markdown
from ..extraction.html.semantics import collect_html_section_hints
from ..extraction.html.shared import append_text_block, short_text, soup_root
from ..extraction.html.signals import HtmlExtractionFailure
from ..extraction.html.tables import render_table_markdown
from ..extraction.markdown_render.figures import (
    INLINE_FIGURE_ALT_ATTR,
    INLINE_FIGURE_SRC_ATTR,
)
from ..markdown.images import render_markdown_image
from ..models.markdown import (
    NUMBERED_REFERENCE_PATTERN,
    image_reference_candidates,
    image_references_match,
    iter_markdown_images,
)
from ..quality.html_availability import (
    HtmlQualityAssessor,
    availability_failure_message,
)
from ..utils import dedupe_authors, normalize_text
from ._article_markdown_math import (
    render_external_mathml_expression,
    render_mathml_expression,
)
from ._html_authors import extract_meta_authors
from ._html_section_markdown import render_container_markdown


MDPI_NOISE_PROFILE = "mdpi"

MDPI_SITE_RULE_OVERRIDES: dict[str, Any] = {
    "candidate_selectors": [
        ".html-article-content",
        "#article-contents",
        ".prose-article",
        "article",
    ],
    "remove_selectors": [
        ".profile-card-content",
        ".sciprofiles-link",
        ".article-menu",
        ".article__menu",
        ".article-sidebar",
        ".js-browse-figures",
        ".openpopupgallery",
        ".UI_BrowseArticleFigures",
        ".article-citation",
        ".article-metrics",
        ".altmetric-embed",
        ".social-share",
        ".share",
        "#Article_Metrics",
        "#table_of_contents",
        "ul.html-nav",
        "[data-reveal-id*='share']",
        "[data-reveal-id*='help']",
        "[id*='share-modal']",
        "[id*='recommended-articles']",
    ],
    "drop_keywords": {
        "article-menu",
        "article-toolbar",
        "browse-figures",
        "download-citation",
        "main-share",
        "metrics",
        "recommended-articles",
        "sciprofiles",
        "supplementary-modal",
    },
    "drop_text": {
        "Browse Figures",
        "Download PDF",
        "Download XML",
        "Download Citation",
        "Article Metrics",
        "Share and Cite",
        "Submit to this Journal",
    },
}

# SITE_UI_COPY_REGRESSION_MARKER: MDPI-owned article toolbar labels; keep tied to provider cleanup tests.
# STRUCTURAL_UI_COPY_HOOK: provider cleanup policy removes these only from MDPI article chrome.
MDPI_MARKDOWN_PROMO_TOKENS = (
    "browse figures",
    "download citation",
    "download pdf",
    "download xml",
    "share and cite",
    "submit to this journal",
    "article metrics",
    "sciprofiles",
)

MDPI_FRONT_MATTER_EXACT_TEXTS = (
    "article",
    "open access",
    "review",
    "communication",
)

MDPI_FRONT_MATTER_CONTAINS_TOKENS = (
    "academic editor",
    "check for updates",
    "received:",
    "revised:",
    "accepted:",
    "published:",
)

# SITE_UI_COPY_REGRESSION_MARKER: MDPI-owned post-content navigation labels.
# STRUCTURAL_UI_COPY_HOOK: provider cleanup policy uses these as post-body boundaries, not global denylist text.
MDPI_POST_CONTENT_BREAK_TOKENS = (
    "article metrics",
    "further information",
    "mdpi and acs style",
    "submit to this journal",
)

MDPI_EXTRACTION_CLEANUP_SELECTORS = (
    ".profile-card-content",
    ".sciprofiles-link",
    ".js-browse-figures",
    ".openpopupgallery",
    ".UI_BrowseArticleFigures",
    ".google-scholar",
    ".cross-ref",
    ".pub_med",
    "#table_of_contents",
    "ul.html-nav",
    "[data-reveal-id*='share']",
    "[data-reveal-id*='help']",
)

MDPI_SUPPLEMENTARY_TEXT_TOKENS = (
    "supplementary materials",
    "supplementary material",
    "table s",
    "figure s",
)

_ARTICLE_CONTAINER_SELECTORS = (
    ".html-article-content",
    "#article-contents",
    ".prose-article",
    "article",
)
_ABSTRACT_SELECTORS = (
    ".html-abstract",
    "section#html-abstract",
    "#html-abstract",
    "[id='Abstract']",
    ".art-abstract",
)
_REFERENCE_SELECTORS = (
    "#html-references_list li",
    "section#html-references_list li",
)
_SUPPLEMENTARY_SELECTORS = (
    "section[id*='supplement']",
    "div[id*='supplement']",
    "section[id^='app']",
)
_NOISY_ANCHOR_CLASSES = {
    "cross-ref",
    "google-scholar",
    "pub_med",
}
_NOISY_MARKDOWN_LINES = {
    "browse figures",
    "download pdf",
    "download supplementary material",
    "download xml",
    "google scholar",
    "crossref",
    "pubmed",
    "share",
    "cite",
    "need help?",
}
_REFERENCE_UI_BRACKET_TOKEN_RE = re.compile(
    r"\[\s*(?:Google Scholar|CrossRef|PubMed|Green Version)\s*\]",
    flags=re.IGNORECASE,
)
_MDPI_INLINE_IMAGE_ATTRS = (
    "data-original",
    "data-large",
    "data-full-size",
    "data-fullsize",
    "data-lg-src",
    "data-hi-res-src",
    "data-lsrc",
    "data-src",
    "src",
)
_MDPI_DISPLAY_LABEL_PATTERN = re.compile(
    r"^\s*(?P<kind>Fig(?:ure)?\.?|Table)\s*(?P<number>[A-Za-z]?\d+[A-Za-z]?(?:\.\d+[A-Za-z]?)*|[A-Za-z]\.\d+[A-Za-z]?)(?P<punct>[.:])?\s*(?P<caption>.*)$",
    flags=re.IGNORECASE | re.DOTALL,
)
_MDPI_DISPLAY_REF_TEMPLATE = r"\b(?:{kind})\s*\.?\s*{number}\b"
_MDPI_DISPLAY_BLOCK_ATTR = "data-paper-fetch-mdpi-display-object"
_MDPI_FORMULA_BLOCK_ATTR = "data-paper-fetch-mdpi-formula-block"
_MDPI_DISPLAY_SECTION_TYPES = {"display-objects"}
_MDPI_DISPLAY_SECTION_IDS = {"figures", "figuresandtables"}
_MDPI_INLINE_WRAPPER_NAMES = ("div", "span")
_MDPI_NON_INLINE_DESCENDANT_NAMES = {
    "article",
    "aside",
    "blockquote",
    "dd",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "form",
    "header",
    "li",
    "main",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}
_MDPI_NON_INLINE_WRAPPER_CLASSES = {
    "html-disp-formula-info",
    "html-fig-wrap",
    "html-fig_show",
    "html-table-wrap",
    "html-table_show",
    "html-array_table",
    "html-fn_group",
}


@dataclass
class _MdpiDisplayObject:
    kind: str
    key: str
    label: str
    caption: str
    node: Tag
    source_index: int
    ids: tuple[str, ...] = ()


def mark_inline_assets(markdown_text: str, assets: list[Any], source: str) -> None:
    if source != "mdpi_html" or not markdown_text or not assets:
        return
    inline_candidates = [
        image_reference_candidates(image.url)
        for image in iter_markdown_images(markdown_text)
        if image_reference_candidates(image.url)
    ]
    if not inline_candidates:
        return

    for asset in assets:
        kind = normalize_text(getattr(asset, "kind", None)).lower()
        if kind not in {"figure", "table", "formula", "equation"}:
            continue
        if normalize_text(getattr(asset, "section", None)).lower() in {
            "appendix",
            "supplementary",
        }:
            continue
        asset_candidates: set[str] = set()
        for field in (
            "path",
            "url",
            "original_url",
            "download_url",
            "source_url",
            "source_path",
            "source_href",
        ):
            asset_candidates |= image_reference_candidates(getattr(asset, field, None))
        if asset_candidates and any(
            image_references_match(asset_candidates, inline_candidate)
            for inline_candidate in inline_candidates
        ):
            asset.render_state = "inline"


def _append_unique(values: list[str], candidate: str | None) -> None:
    normalized = normalize_text(candidate)
    if normalized and normalized not in values:
        values.append(normalized)


def _remove_reference_ui_tokens(text: str) -> str:
    cleaned = _REFERENCE_UI_BRACKET_TOKEN_RE.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned


def _clean_reference_raw_text(text: str | None) -> str:
    return normalize_text(_remove_reference_ui_tokens(normalize_text(text)))


def _reference_label_from_node(node: Tag) -> str:
    label = normalize_text(str(node.get("data-content") or "")).strip()
    if not label:
        return ""
    if label.isdigit():
        return f"{label}."
    if NUMBERED_REFERENCE_PATTERN.match(f"{label} "):
        return label
    return ""


def _prepend_reference_label(text: str, label: str) -> str:
    if not text or not label or NUMBERED_REFERENCE_PATTERN.match(text):
        return text
    return f"{label} {text}"


def _class_tokens(node: Tag) -> set[str]:
    raw_classes = node.get("class") or []
    if isinstance(raw_classes, str):
        return {normalize_text(item).lower() for item in raw_classes.split() if normalize_text(item)}
    return {normalize_text(str(item)).lower() for item in raw_classes if normalize_text(str(item))}


def _has_class(node: Tag, class_name: str) -> bool:
    return class_name.lower() in _class_tokens(node)


def extract_authors(html_text: str) -> list[str]:
    authors = extract_meta_authors(
        html_text,
        keys={"citation_author", "dc.creator"},
    )
    if authors:
        return authors
    soup = BeautifulSoup(html_text, choose_parser())
    candidates: list[str] = []
    for selector in (".art-authors a", ".authors a", "[itemprop='author']"):
        for node in soup.select(selector):
            _append_unique(candidates, node.get_text(" ", strip=True))
    return dedupe_authors(candidates)


def extract_references(html_text: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html_text, choose_parser())
    references: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for selector in _REFERENCE_SELECTORS:
        for node in soup.select(selector):
            text = _clean_reference_raw_text(node.get_text(" ", strip=True))
            text = _prepend_reference_label(text, _reference_label_from_node(node))
            if not text or text in seen:
                continue
            seen.add(text)
            references.append({"raw": text})
    if references:
        return references
    for node in soup.select("meta[name='citation_reference']"):
        text = _clean_reference_raw_text(str(node.get("content") or ""))
        if text and text not in seen:
            seen.add(text)
            references.append({"raw": text})
    return references


def extract_keywords(html_text: str) -> list[str]:
    soup = BeautifulSoup(html_text, choose_parser())
    keywords: list[str] = []
    for container in soup.select("#html-keywords"):
        if not isinstance(container, Tag):
            continue
        for title_node in list(container.select("#html-keywords-title")):
            title_node.decompose()
        for node in container.find_all("a"):
            if isinstance(node, Tag):
                _append_unique(keywords, node.get_text(" ", strip=True))
        if keywords:
            continue
        text = normalize_text(container.get_text(" ", strip=True))
        text = re.sub(r"^Keywords\s*:?\s*", "", text, flags=re.IGNORECASE)
        for part in re.split(r"\s*;\s*", text):
            _append_unique(keywords, part)
    return keywords


def extract_pdf_urls(html_text: str, source_url: str | None = None) -> list[str]:
    soup = BeautifulSoup(html_text, choose_parser())
    urls: list[str] = []
    for selector, attr in (
        ("meta[name='citation_pdf_url']", "content"),
        ("link[type='application/pdf']", "href"),
        ("a[href$='/pdf']", "href"),
        ("a[href*='/pdf?']", "href"),
    ):
        for node in soup.select(selector):
            value = normalize_text(str(node.get(attr) or ""))
            if value:
                _append_unique(urls, urllib.parse.urljoin(source_url or "", value))
    return urls


def mdpi_pdf_url_from_landing_url(url: str | None) -> str | None:
    candidate = normalize_text(url)
    if not candidate:
        return None
    parsed = urllib.parse.urlparse(candidate)
    host = normalize_text(parsed.hostname or "").lower()
    if host not in {"www.mdpi.com", "mdpi.com"}:
        return None
    path = parsed.path.rstrip("/")
    if not path:
        return None
    if path.endswith("/pdf") or "/pdf/" in path:
        return candidate
    if re.fullmatch(r"/[0-9]{4}-[0-9Xx]{3,4}/[0-9]+/[0-9]+/[0-9]+", path):
        return urllib.parse.urlunparse(parsed._replace(path=f"{path}/pdf", query=""))
    return None


def _extract_title(soup: BeautifulSoup, metadata: Mapping[str, Any] | None) -> str | None:
    for selector, attr in (
        ("meta[name='citation_title']", "content"),
        ("meta[name='dc.title']", "content"),
        ("meta[property='og:title']", "content"),
    ):
        node = soup.select_one(selector)
        if node is not None:
            title = normalize_text(str(node.get(attr) or ""))
            if title:
                return title
    node = soup.select_one("h1")
    if node is not None:
        title = normalize_text(node.get_text(" ", strip=True))
        if title:
            return title
    title = normalize_text(str((metadata or {}).get("title") or ""))
    return title or None


def _select_article_container(soup: BeautifulSoup) -> Tag | None:
    for selector in _ARTICLE_CONTAINER_SELECTORS:
        node = soup.select_one(selector)
        if isinstance(node, Tag) and normalize_text(node.get_text(" ", strip=True)):
            return node
    return None


def _new_article_soup() -> tuple[BeautifulSoup, Tag]:
    soup = BeautifulSoup("<article></article>", choose_parser())
    article = soup.find("article")
    if not isinstance(article, Tag):
        raise HtmlExtractionFailure(
            "article_container_not_found",
            "Could not allocate MDPI article container.",
        )
    return soup, article


def _append_fragment(destination: Tag, html_text: str) -> None:
    fragment = BeautifulSoup(html_text, choose_parser())
    source = fragment.body if fragment.body is not None else fragment
    for child in list(source.contents):
        destination.append(child)


def _copy_node(node: Tag) -> Tag | None:
    copied = BeautifulSoup(str(node), choose_parser())
    found = copied.find(node.name)
    return found if isinstance(found, Tag) else None


def _article_container_html(
    html_text: str,
    metadata: Mapping[str, Any] | None,
) -> tuple[str, str | None, str | None, int]:
    soup = BeautifulSoup(html_text, choose_parser())
    title = _extract_title(soup, metadata)
    source_container = _select_article_container(soup)
    if source_container is None:
        raise HtmlExtractionFailure(
            "article_container_not_found",
            "Could not identify the main MDPI article container.",
        )

    article_soup, article = _new_article_soup()
    if title:
        title_node = article_soup.new_tag("h1")
        title_node.string = title
        article.append(title_node)

    old_style_body_nodes: list[Tag] = []
    old_style_display_nodes: list[Tag] = []
    seen_old_style_nodes: set[int] = set()
    for selector in (
        ".art-abstract",
        ".html-body",
    ):
        for node in source_container.select(selector):
            if not isinstance(node, Tag) or id(node) in seen_old_style_nodes:
                continue
            seen_old_style_nodes.add(id(node))
            old_style_body_nodes.append(node)
    for selector in (
        "section[type='display-objects']",
        "#Figures",
        "#FiguresandTables",
    ):
        for node in source_container.select(selector):
            if not isinstance(node, Tag) or id(node) in seen_old_style_nodes:
                continue
            seen_old_style_nodes.add(id(node))
            old_style_display_nodes.append(node)
    content_nodes = [*old_style_body_nodes, *old_style_display_nodes] if old_style_body_nodes else [source_container]
    for node in content_nodes:
        copied = _copy_node(node)
        if copied is None:
            continue
        _normalize_mdpi_dom(copied)
        _append_fragment(article, str(copied))
    if len(article.find_all(True)) <= 1:
        raise HtmlExtractionFailure(
            "article_container_not_found",
            "Could not copy the main MDPI article content.",
        )
    _normalize_mdpi_dom(article)
    article_text_length = len(" ".join(article.stripped_strings))
    abstract_text = _extract_abstract_text(article)
    return str(article), title, abstract_text, article_text_length


def _extract_abstract_text(container: Tag) -> str | None:
    for selector in _ABSTRACT_SELECTORS:
        node = container.select_one(selector)
        if isinstance(node, Tag):
            copied = _copy_node(node) or node
            for keyword_node in list(copied.select("#html-keywords, #html-keywords-title")):
                keyword_node.decompose()
            text = normalize_text(copied.get_text(" ", strip=True))
            if text:
                return normalize_text(
                    re.sub(r"^Abstract\s*:?\s*", "", text, flags=re.IGNORECASE)
                )
    return None


def _normalize_mdpi_dom(container: Tag) -> None:
    for selector in MDPI_EXTRACTION_CLEANUP_SELECTORS:
        for node in list(container.select(selector)):
            node.decompose()

    for node in list(container.select("#html-keywords")):
        node.decompose()

    for node in list(container.find_all(["script", "style", "noscript", "template", "iframe", "form", "button"])):
        node.decompose()

    for anchor in list(container.find_all("a")):
        if not isinstance(anchor, Tag):
            continue
        classes = {normalize_text(str(value)).lower() for value in anchor.get("class") or []}
        href = normalize_text(str(anchor.get("href") or "")).lower()
        text = normalize_text(anchor.get_text(" ", strip=True)).lower()
        if classes & _NOISY_ANCHOR_CLASSES or "scholar.google." in href:
            anchor.decompose()
            continue
        if "html-disp-formula" in classes and text:
            anchor.replace_with(NavigableString(text))
            continue
        if text in {"google scholar", "crossref", "pubmed"}:
            anchor.decompose()

    _remove_mdpi_abstract_title_colon(container)
    _normalize_mdpi_section_heading_levels(container)
    _normalize_mdpi_formula_dom(container)
    _split_mdpi_paragraph_display_blocks(container)
    _normalize_mdpi_display_objects(container)

    for node in list(container.select(".html-fig-wrap")):
        if isinstance(node, Tag):
            node.name = "figure"
            caption = node.select_one(".html-fig_description")
            if isinstance(caption, Tag):
                caption.name = "figcaption"

    for node in list(container.select(".html-p, div[role='paragraph']")):
        if isinstance(node, Tag) and normalize_text(node.name).lower() == "div":
            node.name = "p"

    _normalize_mdpi_inline_block_wrappers(container)

    for node in list(container.select(".html-italic")):
        if isinstance(node, Tag) and normalize_text(node.name).lower() == "span":
            node.name = "em"

    for node in list(container.select(".html-bold")):
        if isinstance(node, Tag) and normalize_text(node.name).lower() == "span":
            node.name = "strong"


def _is_mdpi_paragraph_context(node: Tag) -> bool:
    name = normalize_text(node.name or "").lower()
    role = normalize_text(str(node.get("role") or "")).lower()
    return name == "p" or _has_class(node, "html-p") or (name == "div" and role == "paragraph")


def _is_mdpi_non_inline_wrapper_node(node: Tag) -> bool:
    name = normalize_text(node.name or "").lower()
    if not name:
        return True
    if re.fullmatch(r"h[1-6]", name):
        return True
    if name in _MDPI_NON_INLINE_DESCENDANT_NAMES:
        return True
    if name == "img":
        return True
    if name == "math" and normalize_text(str(node.get("display") or "")).lower() == "block":
        return True
    if node.get(_MDPI_DISPLAY_BLOCK_ATTR):
        return True
    if _class_tokens(node) & _MDPI_NON_INLINE_WRAPPER_CLASSES:
        return True
    role = normalize_text(str(node.get("role") or "")).lower()
    return role in {"figure", "list", "listitem", "math", "table"}


def _is_mdpi_inline_block_wrapper(node: Tag) -> bool:
    name = normalize_text(node.name or "").lower()
    if name not in _MDPI_INLINE_WRAPPER_NAMES:
        return False
    if _is_mdpi_non_inline_wrapper_node(node):
        return False
    for descendant in node.find_all(True):
        if isinstance(descendant, Tag) and _is_mdpi_non_inline_wrapper_node(descendant):
            return False
    return bool(normalize_text(node.get_text(" ", strip=True)) or node.find("math"))


def _normalize_mdpi_inline_block_wrappers(container: Tag) -> None:
    paragraphs = [
        node
        for node in container.find_all(True)
        if isinstance(node, Tag) and _is_mdpi_paragraph_context(node)
    ]
    if _is_mdpi_paragraph_context(container):
        paragraphs.insert(0, container)

    for paragraph in paragraphs:
        wrappers = [
            node
            for node in paragraph.find_all(_MDPI_INLINE_WRAPPER_NAMES)
            if isinstance(node, Tag)
        ]
        for wrapper in reversed(wrappers):
            if _is_mdpi_inline_block_wrapper(wrapper):
                wrapper.name = "span"


def _render_mdpi_inline_text(node: Tag | None) -> str:
    if node is None:
        return ""
    return normalize_text(
        render_html_inline_node(
            node,
            policy="body",
            render_text_styles=False,
            break_render=" ",
        )
    )


def _render_mdpi_mathml_latex(node: Tag, *, display_mode: bool) -> str:
    element = mathml_element_from_html_node(node)
    if element is None:
        return ""
    latex = normalize_text(
        render_external_mathml_expression(element, display_mode=display_mode)
    )
    if latex:
        return latex
    return normalize_text(render_mathml_expression(element))


def _mdpi_formula_label(node: Tag) -> str:
    for selector in ("label", ".l", ".html-formula-number"):
        label_node = node.select_one(selector)
        if isinstance(label_node, Tag):
            label = short_text(label_node)
            if label:
                return label
    return ""


def _mdpi_markdown_formula_replacement(
    node: Tag,
    *,
    display_mode: bool,
    label: str = "",
) -> Tag | NavigableString | None:
    latex = _render_mdpi_mathml_latex(node, display_mode=display_mode)
    if not latex:
        return None
    if not display_mode:
        return NavigableString(f"${latex}$")

    soup = soup_root(node)
    if soup is None:
        return None
    replacement = soup.new_tag("div")
    replacement[_MDPI_FORMULA_BLOCK_ATTR] = "1"
    for line in ("$$", latex, "$$"):
        append_text_block(replacement, line, soup=soup)
    normalized_label = normalize_text(label)
    if normalized_label:
        append_text_block(replacement, normalized_label, soup=soup)
    return replacement


def _mdpi_formula_content_node(node: Tag) -> Tag:
    content = node.select_one(".f")
    if isinstance(content, Tag):
        return content
    return node


def _mdpi_html_formula_text(node: Tag) -> str:
    content_node = _mdpi_formula_content_node(node)
    rendered = _render_mdpi_inline_text(content_node)
    if rendered:
        return rendered
    copied = _copy_node(content_node)
    if copied is None:
        return ""
    for label_node in list(copied.select("label, .l, .html-formula-number")):
        label_node.decompose()
    return normalize_text(copied.get_text(" ", strip=True))


def _mdpi_formula_text_replacement(node: Tag, *, label: str = "") -> Tag | None:
    formula_text = _mdpi_html_formula_text(node)
    if not formula_text:
        return None
    soup = soup_root(node)
    if soup is None:
        return None
    replacement = soup.new_tag("div")
    replacement[_MDPI_FORMULA_BLOCK_ATTR] = "1"
    append_text_block(replacement, formula_text, soup=soup)
    normalized_label = normalize_text(label)
    if normalized_label:
        append_text_block(replacement, normalized_label, soup=soup)
    return replacement


def _normalize_mdpi_formula_dom(container: Tag) -> None:
    for formula in list(container.select(".html-disp-formula-info")):
        if not isinstance(formula, Tag) or formula.parent is None:
            continue
        replacement = _mdpi_markdown_formula_replacement(
            formula,
            display_mode=True,
            label=_mdpi_formula_label(formula),
        )
        if replacement is None:
            replacement = _mdpi_formula_text_replacement(
                formula,
                label=_mdpi_formula_label(formula),
            )
        if replacement is not None:
            formula.replace_with(replacement)

    for math_node in list(container.select("math[display='block']")):
        if not isinstance(math_node, Tag) or math_node.parent is None:
            continue
        replacement = _mdpi_markdown_formula_replacement(
            math_node,
            display_mode=True,
        )
        if replacement is not None:
            math_node.replace_with(replacement)

    for math_node in list(container.find_all("math")):
        if not isinstance(math_node, Tag) or math_node.parent is None:
            continue
        replacement = _mdpi_markdown_formula_replacement(
            math_node,
            display_mode=False,
        )
        if replacement is not None:
            math_node.replace_with(replacement)


def _copy_mdpi_paragraph_attrs(node: Tag) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for key, value in (getattr(node, "attrs", None) or {}).items():
        if key == "id":
            continue
        attrs[key] = copy.copy(value)
    return attrs


def _mdpi_node_has_renderable_content(node: Tag) -> bool:
    return bool(normalize_text(node.get_text(" ", strip=True)) or node.find("img") or node.find("math"))


def _new_mdpi_split_paragraph(source: Tag, soup: BeautifulSoup) -> Tag:
    paragraph = soup.new_tag("p")
    paragraph.attrs.update(_copy_mdpi_paragraph_attrs(source))
    return paragraph


def _flush_mdpi_split_paragraph(
    parts: list[Tag],
    paragraph: Tag,
    source: Tag,
    soup: BeautifulSoup,
) -> Tag:
    if _mdpi_node_has_renderable_content(paragraph):
        parts.append(paragraph)
    return _new_mdpi_split_paragraph(source, soup)


def _is_mdpi_formula_block_node(node: Tag) -> bool:
    return bool(node.get(_MDPI_FORMULA_BLOCK_ATTR))


def _split_mdpi_paragraph_display_blocks(container: Tag) -> None:
    soup = soup_root(container)
    if soup is None:
        return
    for paragraph in list(container.select(".html-p, div[role='paragraph'], p")):
        if not isinstance(paragraph, Tag) or paragraph.parent is None:
            continue
        formula_blocks = [
            child
            for child in paragraph.find_all(True, recursive=False)
            if isinstance(child, Tag) and _is_mdpi_formula_block_node(child)
        ]
        if not formula_blocks:
            continue

        parts: list[Tag] = []
        current = _new_mdpi_split_paragraph(paragraph, soup)
        for child in list(paragraph.contents):
            if isinstance(child, Tag) and _is_mdpi_formula_block_node(child):
                current = _flush_mdpi_split_paragraph(parts, current, paragraph, soup)
                parts.append(child.extract())
                continue
            current.append(child.extract())
        _flush_mdpi_split_paragraph(parts, current, paragraph, soup)

        if not parts:
            paragraph.decompose()
            continue
        for part in reversed(parts):
            paragraph.insert_after(part)
        paragraph.decompose()


def _display_label_kind(kind: str) -> str:
    return "Table" if normalize_text(kind).lower() == "table" else "Figure"


def _split_mdpi_display_label_caption(kind: str, text: str) -> tuple[str, str]:
    normalized = normalize_text(text)
    if not normalized:
        return "", ""
    match = _MDPI_DISPLAY_LABEL_PATTERN.match(normalized)
    if match is None:
        return "", normalized
    raw_kind = match.group("kind")
    label_kind = "Table" if raw_kind.lower().startswith("table") else "Figure"
    if label_kind.lower() != _display_label_kind(kind).lower():
        label_kind = _display_label_kind(kind)
    label = f"{label_kind} {match.group('number')}."
    caption = normalize_text(match.group("caption"))
    return label, caption


def _mdpi_display_label_number(label: str) -> str:
    match = _MDPI_DISPLAY_LABEL_PATTERN.match(label)
    return normalize_text(match.group("number")) if match is not None else ""


def _mdpi_display_label_from_id(kind: str, node_id: str) -> str:
    suffix = "t" if kind == "table" else "f"
    match = re.search(rf"[-_]{suffix}0*([1-9]\d*[A-Za-z]?)$", normalize_text(node_id), flags=re.IGNORECASE)
    if match is None:
        return ""
    return f"{_display_label_kind(kind)} {match.group(1)}."


def _mdpi_display_key(kind: str, label: str, node_id: str, index: int) -> str:
    if node_id:
        return node_id
    number = _mdpi_display_label_number(label)
    if number:
        return f"{kind}:{number.lower()}"
    return f"{kind}:source:{index}"


def _mdpi_caption_node_text(node: Tag | None) -> str:
    if not isinstance(node, Tag):
        return ""
    text = _render_mdpi_inline_text(node)
    return text or short_text(node)


def _figure_caption_node(wrapper: Tag) -> Tag | None:
    for selector in (".html-fig_description", "figcaption", ".html-caption"):
        node = wrapper.select_one(selector)
        if isinstance(node, Tag):
            return node
    return None


def _figure_display_object(wrapper: Tag, index: int) -> _MdpiDisplayObject | None:
    node_id = normalize_text(str(wrapper.get("id") or ""))
    caption_node = _figure_caption_node(wrapper)
    caption_text = _mdpi_caption_node_text(caption_node)
    label, caption = _split_mdpi_display_label_caption("figure", caption_text)
    if not label:
        label = _mdpi_display_label_from_id("figure", node_id)
    if not label and not wrapper.find("img"):
        return None
    return _MdpiDisplayObject(
        kind="figure",
        key=_mdpi_display_key("figure", label, node_id, index),
        label=label or "Figure",
        caption=caption,
        node=wrapper,
        source_index=index,
        ids=tuple(item for item in (node_id,) if item),
    )


def _href_fragment(value: str | None) -> str:
    href = normalize_text(str(value or ""))
    if not href.startswith("#"):
        return ""
    return urllib.parse.unquote(href[1:])


def _popup_for_wrapper(wrapper: Tag, popup_by_id: Mapping[str, Tag]) -> Tag | None:
    for node in wrapper.find_all(attrs={"href": True}):
        if not isinstance(node, Tag):
            continue
        fragment = _href_fragment(str(node.get("href") or ""))
        popup = popup_by_id.get(fragment)
        if isinstance(popup, Tag):
            return popup
    return None


def _table_caption_node(wrapper: Tag, popup: Tag | None) -> Tag | None:
    for root in (wrapper, popup):
        if not isinstance(root, Tag):
            continue
        for selector in (".html-table_wrap_discription", ".html-caption", "caption"):
            node = root.select_one(selector)
            if isinstance(node, Tag):
                return node
    return None


def _first_mdpi_image_url(node: Tag | None) -> str:
    if not isinstance(node, Tag):
        return ""
    if node.name == "img":
        return _mdpi_image_url(node, "")
    image = node.find("img")
    return _mdpi_image_url(image, "") if isinstance(image, Tag) else ""


def _dedupe_mdpi_text_lines(text: str) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for line in normalize_text(text).splitlines():
        normalized = normalize_text(line)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        lines.append(normalized)
    return lines


def _render_mdpi_table_object_markdown(
    wrapper: Tag,
    popup: Tag | None,
    *,
    label: str,
    caption: str,
) -> str:
    table = popup.find("table") if isinstance(popup, Tag) else None
    if not isinstance(table, Tag):
        table = wrapper.find("table")
    if isinstance(table, Tag):
        rendered = normalize_text(render_table_markdown(table, label=label, caption=caption))
        if rendered and ("|" in rendered or "\n- " in rendered):
            return rendered

    image_url = _first_mdpi_image_url(wrapper) or _first_mdpi_image_url(popup)
    if image_url:
        image_line = render_markdown_image("table", label or "Table", image_url)
        heading = f"**{label}** {caption}".strip() if label else caption
        return normalize_text("\n\n".join(part for part in (image_line, heading) if part))

    heading = f"**{label}** {caption}".strip() if label else caption
    fallback_text = short_text(popup) if isinstance(popup, Tag) else short_text(wrapper)
    lines = _dedupe_mdpi_text_lines(fallback_text)
    if heading:
        heading_plain = normalize_text(re.sub(r"[*_`]+", "", heading))
        lines = [line for line in lines if normalize_text(line) != heading_plain]
        return normalize_text("\n".join([heading, *lines]))
    return normalize_text("\n".join(lines))


def _markdown_display_block(reference: Tag, markdown_text: str, kind: str) -> Tag | None:
    soup = soup_root(reference)
    if soup is None:
        return None
    block = soup.new_tag("div")
    block[_MDPI_DISPLAY_BLOCK_ATTR] = kind
    block.append(NavigableString(markdown_text))
    return block


def _table_display_object(
    wrapper: Tag,
    popup_by_id: Mapping[str, Tag],
    index: int,
) -> _MdpiDisplayObject | None:
    node_id = normalize_text(str(wrapper.get("id") or ""))
    popup = _popup_for_wrapper(wrapper, popup_by_id)
    caption_text = _mdpi_caption_node_text(_table_caption_node(wrapper, popup))
    label, caption = _split_mdpi_display_label_caption("table", caption_text)
    if not label:
        label = _mdpi_display_label_from_id("table", node_id)
    markdown = _render_mdpi_table_object_markdown(
        wrapper,
        popup,
        label=label or "Table",
        caption=caption,
    )
    if not markdown:
        return None
    block = _markdown_display_block(wrapper, markdown, "table")
    if block is None:
        return None
    return _MdpiDisplayObject(
        kind="table",
        key=_mdpi_display_key("table", label, node_id, index),
        label=label or "Table",
        caption=caption,
        node=block,
        source_index=index,
        ids=tuple(item for item in (node_id,) if item),
    )


def _is_mdpi_display_section(node: Tag) -> bool:
    section_type = normalize_text(str(node.get("type") or "")).lower()
    node_id = normalize_text(str(node.get("id") or "")).lower()
    return section_type in _MDPI_DISPLAY_SECTION_TYPES or node_id in _MDPI_DISPLAY_SECTION_IDS


def _collect_mdpi_display_objects(container: Tag) -> list[_MdpiDisplayObject]:
    popup_by_id = {
        normalize_text(str(node.get("id") or "")): node
        for node in container.select(".html-fig_show, .html-table_show")
        if isinstance(node, Tag) and normalize_text(str(node.get("id") or ""))
    }
    display_objects: list[_MdpiDisplayObject] = []
    seen: set[tuple[str, str]] = set()
    for index, node in enumerate(list(container.select(".html-fig-wrap, .html-table-wrap"))):
        if not isinstance(node, Tag):
            continue
        if _has_class(node, "html-fig-wrap"):
            item = _figure_display_object(node, index)
        else:
            item = _table_display_object(node, popup_by_id, index)
            node.decompose()
        if item is None:
            continue
        dedupe_key = (
            item.kind,
            _mdpi_display_label_number(item.label).lower() or item.key,
        )
        if dedupe_key in seen:
            node.decompose()
            continue
        seen.add(dedupe_key)
        display_objects.append(item)
    for node in list(container.select(".html-fig_show, .html-table_show")):
        if isinstance(node, Tag):
            node.decompose()
    return display_objects


def _is_inside_mdpi_display_object(node: Tag) -> bool:
    current: Tag | None = node
    while isinstance(current, Tag):
        if current.get(_MDPI_DISPLAY_BLOCK_ATTR) or _has_class(current, "html-fig-wrap") or _has_class(current, "html-table-wrap"):
            return True
        if _is_mdpi_display_section(current):
            return True
        current = current.parent if isinstance(current.parent, Tag) else None
    return False


def _is_inside_references(node: Tag) -> bool:
    current: Tag | None = node
    while isinstance(current, Tag):
        node_id = normalize_text(str(current.get("id") or "")).lower()
        if node_id == "html-references_list":
            return True
        heading = current.find(re.compile(r"^h[1-6]$"), recursive=False)
        if isinstance(heading, Tag) and normalize_text(heading.get_text(" ", strip=True)).lower() == "references":
            return True
        current = current.parent if isinstance(current.parent, Tag) else None
    return False


def _display_insert_anchor(node: Tag) -> Tag:
    current = node
    while isinstance(current.parent, Tag) and current.parent.name in {"li", "ul", "ol"}:
        current = current.parent
    return current


def _iter_mdpi_reference_blocks(container: Tag) -> list[Tag]:
    blocks: list[Tag] = []
    seen: set[int] = set()
    for node in container.find_all(["p", "div", "li"]):
        if not isinstance(node, Tag):
            continue
        if id(node) in seen:
            continue
        if node.name == "div" and not _has_class(node, "html-p"):
            continue
        if node.get(_MDPI_DISPLAY_BLOCK_ATTR) or _is_inside_mdpi_display_object(node) or _is_inside_references(node):
            continue
        text = normalize_text(node.get_text(" ", strip=True))
        if not text:
            continue
        anchor = _display_insert_anchor(node)
        if id(anchor) in seen:
            continue
        seen.add(id(anchor))
        blocks.append(anchor)
    return blocks


def _display_objects_for_block(
    block: Tag,
    display_objects: list[_MdpiDisplayObject],
    used_keys: set[str],
) -> list[_MdpiDisplayObject]:
    matched_keys: set[str] = set()
    for anchor in block.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        fragment = _href_fragment(str(anchor.get("href") or ""))
        if not fragment:
            continue
        for item in display_objects:
            if item.key in used_keys:
                continue
            if fragment in item.ids:
                matched_keys.add(item.key)

    text = normalize_text(block.get_text(" ", strip=True))
    for item in display_objects:
        if item.key in used_keys or item.key in matched_keys:
            continue
        number = _mdpi_display_label_number(item.label)
        if not number:
            continue
        kind_pattern = "table" if item.kind == "table" else r"fig(?:ure)?"
        pattern = re.compile(
            _MDPI_DISPLAY_REF_TEMPLATE.format(
                kind=kind_pattern,
                number=re.escape(number),
            ),
            flags=re.IGNORECASE,
        )
        if pattern.search(text):
            matched_keys.add(item.key)
    return [item for item in display_objects if item.key in matched_keys and item.key not in used_keys]


def _references_anchor(container: Tag) -> Tag | None:
    references = container.select_one("#html-references_list")
    if isinstance(references, Tag):
        return references
    for heading in container.find_all(re.compile(r"^h[1-6]$")):
        if isinstance(heading, Tag) and normalize_text(heading.get_text(" ", strip=True)).lower() == "references":
            return heading.parent if isinstance(heading.parent, Tag) else heading
    return None


def _display_node_for_insert(node: Tag) -> Tag:
    return node.extract() if node.parent is not None else node


def _normalize_mdpi_display_objects(container: Tag) -> None:
    if normalize_text(container.name or "").lower() != "article":
        return
    display_objects = _collect_mdpi_display_objects(container)
    if not display_objects:
        return

    used_keys: set[str] = set()
    for block in _iter_mdpi_reference_blocks(container):
        matches = _display_objects_for_block(block, display_objects, used_keys)
        if not matches:
            continue
        cursor: Tag = block
        for item in matches:
            cursor.insert_after(_display_node_for_insert(item.node))
            cursor = item.node
            used_keys.add(item.key)

    unmatched = [item for item in display_objects if item.key not in used_keys]
    if unmatched:
        anchor = _references_anchor(container)
        if anchor is None:
            anchor = container
        for item in unmatched:
            if anchor is container:
                container.append(_display_node_for_insert(item.node))
                used_keys.add(item.key)
                continue
            anchor.insert_before(_display_node_for_insert(item.node))
            used_keys.add(item.key)

    for section in list(container.find_all(["section", "div"])):
        if not isinstance(section, Tag) or not _is_mdpi_display_section(section):
            continue
        if not normalize_text(section.get_text(" ", strip=True)) and not section.find("img"):
            section.decompose()


def _remove_mdpi_abstract_title_colon(container: Tag) -> None:
    for title_node in list(container.select("#html-abstract-title")):
        for sibling in list(title_node.next_siblings):
            if isinstance(sibling, NavigableString) and not normalize_text(str(sibling)):
                continue
            if isinstance(sibling, NavigableString) and normalize_text(str(sibling)) == ":":
                sibling.extract()
                continue
            if isinstance(sibling, Tag) and normalize_text(sibling.get_text(" ", strip=True)) == ":":
                sibling.decompose()
                continue
            break


def _normalize_mdpi_section_heading_levels(container: Tag) -> None:
    for heading in list(container.find_all(re.compile(r"^h[1-6]$"))):
        if not isinstance(heading, Tag):
            continue
        nested = normalize_text(str(heading.get("data-nested") or ""))
        if not nested.isdigit():
            continue
        target_level = min(max(int(nested) + 1, 2), 6)
        heading.name = f"h{target_level}"


def _mdpi_image_url(image: Tag, source_url: str) -> str:
    for attr in _MDPI_INLINE_IMAGE_ATTRS:
        candidate = normalize_text(str(image.get(attr) or ""))
        if candidate:
            return urllib.parse.urljoin(source_url, candidate)
    return ""


def _inject_mdpi_inline_figure_sources(container: Tag, source_url: str) -> None:
    for figure in container.find_all("figure"):
        if not isinstance(figure, Tag):
            continue
        caption_node = figure.find("figcaption")
        caption = short_text(caption_node) if isinstance(caption_node, Tag) else ""
        for image in figure.find_all("img"):
            if not isinstance(image, Tag):
                continue
            image_url = _mdpi_image_url(image, source_url)
            if not image_url:
                continue
            image[INLINE_FIGURE_SRC_ATTR] = image_url
            image[INLINE_FIGURE_ALT_ATTR] = caption or normalize_text(str(image.get("alt") or "Figure")) or "Figure"


def _render_mdpi_article_markdown(article_html: str, source_url: str) -> str:
    soup = BeautifulSoup(article_html, choose_parser())
    article = soup.find("article")
    if not isinstance(article, Tag):
        return ""
    _inject_mdpi_inline_figure_sources(article, source_url)
    title_node = article.find("h1")
    title = short_text(title_node) if isinstance(title_node, Tag) else ""
    lines: list[str] = []
    render_container_markdown(
        article,
        lines,
        level=2,
        skip_first_heading=title or None,
        section_content_selectors=(),
    )
    return "\n".join(lines)


def _abstract_section_payload(abstract_text: str | None) -> list[dict[str, str]]:
    normalized = normalize_text(abstract_text)
    if not normalized:
        return []
    return [{"heading": "Abstract", "text": normalized}]


def _normalize_mdpi_markdown(markdown_text: str) -> str:
    blocks = re.split(r"\n\s*\n", markdown_text)
    kept: list[str] = []
    for block in blocks:
        normalized = normalize_text(block)
        lowered = normalized.lower()
        if not normalized:
            continue
        if lowered in _NOISY_MARKDOWN_LINES:
            continue
        if any(token in lowered for token in MDPI_MARKDOWN_PROMO_TOKENS):
            if len(normalized) < 220:
                continue
        kept.append(block.strip())
    text = "\n\n".join(kept)
    text = _remove_reference_ui_tokens(text)
    return clean_rendered_markdown(text, noise_profile=MDPI_NOISE_PROFILE)


def extract_markdown(
    html_text: str,
    source_url: str,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    keywords = extract_keywords(html_text)
    article_html, title, abstract_text, container_text_length = _article_container_html(
        html_text,
        metadata,
    )
    article_soup = BeautifulSoup(article_html, choose_parser())
    article = article_soup.find("article")
    if not isinstance(article, Tag):
        raise HtmlExtractionFailure(
            "article_container_not_found",
            "Could not identify the normalized MDPI article container.",
        )
    section_hints = collect_html_section_hints(article, title=title)
    markdown = render_html_markdown(
        article_html,
        source_url,
        trafilatura_backend=None,
        noise_profile=MDPI_NOISE_PROFILE,
        renderer=_render_mdpi_article_markdown,
    )
    if title and f"# {title}" not in markdown:
        markdown = f"# {title}\n\n{markdown}".strip()
    markdown = _normalize_mdpi_markdown(markdown)

    quality_metadata = dict(metadata or {})
    if title and not quality_metadata.get("title"):
        quality_metadata["title"] = title
    diagnostics = HtmlQualityAssessor("mdpi").assess(
        markdown,
        quality_metadata,
        html_text=article_html,
        title=title,
        final_url=source_url,
        container_tag="article",
        container_text_length=container_text_length,
        section_hints=section_hints,
    )
    if not diagnostics.accepted:
        raise HtmlExtractionFailure(
            diagnostics.reason,
            availability_failure_message(diagnostics),
        )

    extraction_payload = {
        "title": title,
        "abstract_text": abstract_text,
        "abstract_sections": _abstract_section_payload(abstract_text),
        "section_hints": section_hints,
        "container_tag": "article",
        "container_text_length": container_text_length,
        "availability_diagnostics": diagnostics.to_dict(),
        "extracted_authors": extract_authors(html_text),
        "keywords": keywords,
        "references": extract_references(html_text),
    }
    return markdown, extraction_payload


def extract_asset_html_scopes(html_text: str, source_url: str) -> tuple[str, str]:
    del source_url
    soup = BeautifulSoup(html_text, choose_parser())
    container = _select_article_container(soup)
    if container is None:
        raise HtmlExtractionFailure(
            "article_container_not_found",
            "Could not identify the MDPI article container for assets.",
        )
    body_container = copy.deepcopy(container)
    supplementary_container = copy.deepcopy(container)
    _normalize_mdpi_dom(body_container)
    _normalize_mdpi_dom(supplementary_container)

    for node in list(body_container.select(", ".join(_SUPPLEMENTARY_SELECTORS))):
        if isinstance(node, Tag) and "supplement" in normalize_text(
            node.get_text(" ", strip=True)
        ).lower():
            node.decompose()

    supplementary_nodes: list[Tag] = []
    for selector in _SUPPLEMENTARY_SELECTORS:
        for node in supplementary_container.select(selector):
            if not isinstance(node, Tag):
                continue
            text = normalize_text(node.get_text(" ", strip=True)).lower()
            if "supplement" in text or "table s" in text or "figure s" in text:
                supplementary_nodes.append(node)
    supplementary_html = "\n".join(str(node) for node in supplementary_nodes)
    return str(body_container), supplementary_html


def extract_scoped_html_assets(
    html_text: str,
    source_url: str,
    *,
    asset_profile,
) -> list[dict[str, str]]:
    body_html, supplementary_html = extract_asset_html_scopes(html_text, source_url)
    assets = extract_provider_neutral_scoped_assets(
        body_html,
        source_url,
        asset_profile=asset_profile,
        supplementary_html_text=supplementary_html,
        noise_profile=MDPI_NOISE_PROFILE,
    )
    if asset_profile == "all":
        assets.extend(_extract_mdpi_supplementary_assets(supplementary_html, source_url))
    return _dedupe_assets(assets)


def _extract_mdpi_supplementary_assets(
    supplementary_html: str,
    source_url: str,
) -> list[dict[str, str]]:
    soup = BeautifulSoup(supplementary_html, choose_parser())
    assets: list[dict[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = normalize_text(str(anchor.get("href") or ""))
        if not href or href.startswith("#"):
            continue
        text = normalize_text(anchor.get_text(" ", strip=True))
        context = normalize_text(
            anchor.find_parent(["section", "div"]).get_text(" ", strip=True)
            if isinstance(anchor.find_parent(["section", "div"]), Tag)
            else ""
        )
        lowered = " ".join([href, text, context]).lower()
        if not any(token in lowered for token in ("supplement", "/s1", "table s", "figure s")):
            continue
        assets.append(
            {
                "kind": "supplementary",
                "heading": text or "Supplementary Material",
                "caption": context,
                "section": "supplementary",
                "url": urllib.parse.urljoin(source_url, href),
            }
        )
    return assets


def _dedupe_assets(assets: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for asset in assets:
        key = (
            normalize_text(str(asset.get("kind") or "")),
            normalize_text(str(asset.get("url") or asset.get("heading") or "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(asset)
    return deduped

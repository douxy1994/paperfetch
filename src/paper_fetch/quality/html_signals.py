"""HTML availability signal helpers and provider-owned signal callbacks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Pattern

from ..extraction.html.signals import ACCESS_GATE_PATTERNS
from ..utils import normalize_text

from bs4 import BeautifulSoup

def _attr_markers(name: str, value: str) -> tuple[str, str]:
    return (f'{name}="{value}"', f"{name}='{value}'")


def provider_datalayer_assignment_pattern(name: str) -> Pattern[str]:
    return re.compile(rf"\b{re.escape(name)}\s*=", flags=re.DOTALL)


HTML_STRONG_FULLTEXT_MARKERS = (
    *_attr_markers("property", "articleBody"),
    *_attr_markers("itemprop", "articleBody"),
)
HTML_STRUCTURE_MARKERS = (
    *_attr_markers("data-article-access", "full"),
    *_attr_markers("data-article-access-type", "full"),
    *_attr_markers("id", "bodymatter"),
)
# SITE_UI_COPY_REGRESSION_MARKER: site-owned UI copy; rerun extraction rules
# when publisher text changes.
NATURE_RESEARCH_BRIEFING_HEADING_SIGNATURE = (
    "the question",
    "the discovery",
    "the implications",
    "expert opinion",
    "behind the paper",
    "from the editor",
)
PROVIDER_AUTHORLESS_HEADING_SIGNATURES: Mapping[str, tuple[tuple[str, ...], ...]] = (
    MappingProxyType(
        {
            "springer": (NATURE_RESEARCH_BRIEFING_HEADING_SIGNATURE,),
            "springer_nature": (NATURE_RESEARCH_BRIEFING_HEADING_SIGNATURE,),
            "nature": (NATURE_RESEARCH_BRIEFING_HEADING_SIGNATURE,),
        }
    )
)
AAAS_DATALAYER_PATTERN = provider_datalayer_assignment_pattern("AAASdataLayer")
PNAS_DATALAYER_PATTERN = provider_datalayer_assignment_pattern("PNASdataLayer")
WILEY_DATALAYER_PATTERN = re.compile(
    r"\bwindow\.adobeDataLayer\.push\s*\(", flags=re.DOTALL
)


FieldPaths = tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class DatalayerSchema:
    provider: str
    pattern: Pattern[str]
    fields: Mapping[str, FieldPaths]
    required_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatalayerFieldMatch:
    field: str
    expected: str
    negate: bool = False


@dataclass(frozen=True)
class DatalayerSignalRule:
    match: DatalayerFieldMatch
    token: str


@dataclass(frozen=True)
class DatalayerSignalCombo:
    matches: tuple[DatalayerFieldMatch, ...]
    token: str


@dataclass(frozen=True)
class DatalayerContainsRule:
    field: str
    substring: str
    token: str


DatalayerRule = DatalayerSignalRule | DatalayerSignalCombo | DatalayerContainsRule


@dataclass(frozen=True)
class DatalayerSignalSet:
    schema: DatalayerSchema
    blocking_rules: tuple[DatalayerRule, ...] = ()
    strong_rules: tuple[DatalayerRule, ...] = ()
    soft_rules: tuple[DatalayerRule, ...] = ()
    abstract_only_rules: tuple[DatalayerRule, ...] = ()
    presence_rules: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ProviderDatalayer:
    schema: DatalayerSchema
    payload: Mapping[str, Any]

    def value(self, field_name: str) -> Any:
        for path in self.schema.fields.get(field_name, ()):
            value: Any = self.payload
            for key in path:
                if not isinstance(value, Mapping):
                    value = None
                    break
                value = value.get(key)
            if value is not None:
                return value
        return None

    def text(self, field_name: str) -> str:
        return normalize_text(self.value(field_name))

    def lowered(self, field_name: str) -> str:
        return self.text(field_name).lower()


AAAS_DATALAYER_SCHEMA = DatalayerSchema(
    provider="science",
    pattern=AAAS_DATALAYER_PATTERN,
    fields={
        "page_type": (("page", "pageInfo", "pageType"),),
        "view_type": (("page", "pageInfo", "viewType"),),
        "article_type": (("page", "pageInfo", "articleType"),),
        "user_entitled": (("user", "entitled"),),
        "user_access": (("user", "access"),),
    },
    required_fields=("page_type", "view_type", "user_entitled", "user_access"),
)
PNAS_DATALAYER_SCHEMA = DatalayerSchema(
    provider="pnas",
    pattern=PNAS_DATALAYER_PATTERN,
    fields={
        "access_type": (("page", "attributes", "accessType"),),
        "free_access": (("page", "attributes", "freeAccess"),),
        "user_access": (("user", "access"),),
    },
    required_fields=("access_type", "free_access", "user_access"),
)
WILEY_DATALAYER_SCHEMA = DatalayerSchema(
    provider="wiley",
    pattern=WILEY_DATALAYER_PATTERN,
    fields={
        "item_access": (("content", "item", "access"),),
        "format_viewed": (
            ("content", "item", "format-viewed"),
            ("content", "item", "format_viewed"),
        ),
        "page_tertiary_section": (
            ("page", "tertiary-section"),
            ("page", "tertiary_section"),
        ),
    },
    required_fields=("item_access", "format_viewed", "page_tertiary_section"),
)
DATALAYER_SCHEMAS: Mapping[str, DatalayerSchema] = {
    schema.provider: schema
    for schema in (
        AAAS_DATALAYER_SCHEMA,
        PNAS_DATALAYER_SCHEMA,
        WILEY_DATALAYER_SCHEMA,
    )
}
SCIENCE_SIGNAL_SET = DatalayerSignalSet(
    schema=AAAS_DATALAYER_SCHEMA,
    blocking_rules=(
        DatalayerSignalRule(
            DatalayerFieldMatch("page_type", "journal-article-denial"),
            "aaas_page_type_denial",
        ),
        DatalayerSignalRule(
            DatalayerFieldMatch("page_type", "journal-article-abstract"),
            "aaas_page_type_abstract",
        ),
        DatalayerSignalRule(
            DatalayerFieldMatch("view_type", "abs"),
            "aaas_view_abs",
        ),
        DatalayerSignalCombo(
            (
                DatalayerFieldMatch("user_entitled", "false"),
                DatalayerFieldMatch("user_access", "yes", negate=True),
            ),
            "aaas_entitlement_denied",
        ),
    ),
    strong_rules=(
        DatalayerSignalRule(
            DatalayerFieldMatch("user_entitled", "true"),
            "aaas_user_entitled",
        ),
        DatalayerSignalRule(
            DatalayerFieldMatch("user_access", "yes"),
            "aaas_user_access_yes",
        ),
    ),
    soft_rules=(
        DatalayerSignalRule(
            DatalayerFieldMatch("page_type", "journal-article-full-text"),
            "aaas_page_type_full_text",
        ),
        DatalayerSignalRule(
            DatalayerFieldMatch("view_type", "full"),
            "aaas_view_full",
        ),
    ),
    abstract_only_rules=(
        DatalayerContainsRule("page_type", "abstract", "aaas_page_type_abstract"),
        DatalayerContainsRule("view_type", "abstract", "aaas_view_abstract"),
    ),
    presence_rules=(("article_type", "aaas_article_type_present"),),
)
PNAS_SIGNAL_SET = DatalayerSignalSet(
    schema=PNAS_DATALAYER_SCHEMA,
    blocking_rules=(
        DatalayerSignalCombo(
            (
                DatalayerFieldMatch("access_type", "paywall"),
                DatalayerFieldMatch("free_access", "no"),
                DatalayerFieldMatch("user_access", "no"),
            ),
            "pnas_paywall_no_access",
        ),
    ),
)
WILEY_SIGNAL_SET = DatalayerSignalSet(
    schema=WILEY_DATALAYER_SCHEMA,
    blocking_rules=(
        DatalayerSignalRule(
            DatalayerFieldMatch("item_access", "no"),
            "wiley_access_no",
        ),
        DatalayerSignalRule(
            DatalayerFieldMatch("format_viewed", "abstract"),
            "wiley_format_viewed_abstract",
        ),
        DatalayerSignalRule(
            DatalayerFieldMatch("page_tertiary_section", "abs"),
            "wiley_page_tertiary_abs",
        ),
    ),
)


def _normalize_provider_signal_key(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", "_").split())


def authorless_heading_signatures_for_provider(
    provider_name: str | None,
) -> tuple[tuple[str, ...], ...]:
    return PROVIDER_AUTHORLESS_HEADING_SIGNATURES.get(
        _normalize_provider_signal_key(provider_name),
        (),
    )


def dedupe_signals(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _datalayer_rule_value(value: str) -> str:
    return normalize_text(value).lower()


def _matches_datalayer_field(
    datalayer: ProviderDatalayer, match: DatalayerFieldMatch
) -> bool:
    matched = datalayer.lowered(match.field) == _datalayer_rule_value(match.expected)
    return not matched if match.negate else matched


def _matches_datalayer_rule(
    datalayer: ProviderDatalayer, rule: DatalayerRule
) -> bool:
    if isinstance(rule, DatalayerSignalRule):
        return _matches_datalayer_field(datalayer, rule.match)
    if isinstance(rule, DatalayerSignalCombo):
        return all(_matches_datalayer_field(datalayer, match) for match in rule.matches)
    return _datalayer_rule_value(rule.substring) in datalayer.lowered(rule.field)


def _evaluate_datalayer_rules(
    datalayer: ProviderDatalayer, rules: tuple[DatalayerRule, ...]
) -> list[str]:
    return dedupe_signals(
        [rule.token for rule in rules if _matches_datalayer_rule(datalayer, rule)]
    )


def evaluate_datalayer_blocking_signals(
    html_text: str, signal_set: DatalayerSignalSet
) -> list[str]:
    datalayer = load_provider_datalayer(html_text, signal_set.schema)
    if datalayer is None:
        return []
    return _evaluate_datalayer_rules(datalayer, signal_set.blocking_rules)


def evaluate_datalayer_positive_signals(
    html_text: str, signal_set: DatalayerSignalSet
) -> tuple[list[str], list[str], list[str]]:
    strong, soft, abstract_only = default_positive_signals(html_text)
    datalayer = load_provider_datalayer(html_text, signal_set.schema)
    if datalayer is None:
        return strong, soft, abstract_only
    strong.extend(_evaluate_datalayer_rules(datalayer, signal_set.strong_rules))
    soft.extend(_evaluate_datalayer_rules(datalayer, signal_set.soft_rules))
    abstract_only.extend(
        _evaluate_datalayer_rules(datalayer, signal_set.abstract_only_rules)
    )
    soft.extend(
        token
        for field_name, token in signal_set.presence_rules
        if datalayer.text(field_name)
    )
    return dedupe_signals(strong), dedupe_signals(soft), dedupe_signals(abstract_only)


def default_positive_signals(html_text: str) -> tuple[list[str], list[str], list[str]]:
    strong: list[str] = []
    soft: list[str] = []
    lowered = html_text.lower()
    if any(marker in lowered for marker in HTML_STRONG_FULLTEXT_MARKERS):
        strong.append("article_body_marker")
    if any(marker in lowered for marker in HTML_STRUCTURE_MARKERS):
        soft.append("article_body_structure_marker")
    if "<article" in lowered:
        soft.append("article_tag_present")
    return dedupe_signals(strong), dedupe_signals(soft), []


def looks_like_abstract_redirect(
    requested_url: str | None, final_url: str | None
) -> bool:
    if not requested_url or not final_url:
        return False
    requested = requested_url.lower()
    final = final_url.lower()
    return "/doi/full/" in requested and "/doi/abs/" in final and requested != final


def _schema_field_is_present(
    payload: Mapping[str, Any], schema: DatalayerSchema, field_name: str
) -> bool:
    return ProviderDatalayer(schema, payload).value(field_name) is not None


def _payload_matches_schema(
    payload: Mapping[str, Any], schema: DatalayerSchema
) -> bool:
    if not schema.required_fields:
        return True
    return any(
        _schema_field_is_present(payload, schema, field_name)
        for field_name in schema.required_fields
    )


def _json_payload_after_match(html_text: str, match: re.Match[str]) -> Mapping[str, Any] | None:
    decoder = json.JSONDecoder()
    payload_text = html_text[match.end() :].lstrip()
    if not payload_text:
        return None
    try:
        payload, _end = decoder.raw_decode(payload_text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, Mapping) else None


def load_provider_datalayer(
    html_text: str, schema: DatalayerSchema
) -> ProviderDatalayer | None:
    for match in schema.pattern.finditer(html_text):
        payload = _json_payload_after_match(html_text, match)
        if payload is None:
            continue
        if _payload_matches_schema(payload, schema):
            return ProviderDatalayer(schema, payload)
    return None


def load_aaas_datalayer(html_text: str) -> Mapping[str, Any] | None:
    datalayer = load_provider_datalayer(html_text, AAAS_DATALAYER_SCHEMA)
    return datalayer.payload if datalayer is not None else None


def load_pnas_datalayer(html_text: str) -> Mapping[str, Any] | None:
    datalayer = load_provider_datalayer(html_text, PNAS_DATALAYER_SCHEMA)
    return datalayer.payload if datalayer is not None else None


def load_wiley_datalayer(html_text: str) -> Mapping[str, Any] | None:
    datalayer = load_provider_datalayer(html_text, WILEY_DATALAYER_SCHEMA)
    return datalayer.payload if datalayer is not None else None


def science_blocking_fallback_signals(html_text: str) -> list[str]:
    return evaluate_datalayer_blocking_signals(html_text, SCIENCE_SIGNAL_SET)


def science_positive_signals(html_text: str) -> tuple[list[str], list[str], list[str]]:
    return evaluate_datalayer_positive_signals(html_text, SCIENCE_SIGNAL_SET)


def pnas_blocking_fallback_signals(html_text: str) -> list[str]:
    return evaluate_datalayer_blocking_signals(html_text, PNAS_SIGNAL_SET)


def wiley_blocking_fallback_signals(html_text: str) -> list[str]:
    return evaluate_datalayer_blocking_signals(html_text, WILEY_SIGNAL_SET)


def ams_blocking_fallback_signals(html_text: str) -> list[str]:
    lowered = normalize_text(html_text).lower()
    signals: list[str] = []
    has_body_marker = any(
        token in lowered
        for token in (
            "id=\"bodymatter\"",
            "id='bodymatter'",
            "articlebody",
            "nlm_body",
            "articlefulltext",
        )
    )
    if not has_body_marker and "check access" in ACCESS_GATE_PATTERNS and "check access" in lowered:
        signals.append("ams_check_access_without_body")
    if not has_body_marker and "purchase this article" in ACCESS_GATE_PATTERNS and "purchase this article" in lowered:
        signals.append("ams_purchase_without_body")
    return dedupe_signals(signals)


def ams_positive_signals(html_text: str) -> tuple[list[str], list[str], list[str]]:
    strong, soft, abstract_only = default_positive_signals(html_text)
    lowered = html_text.lower()
    if "id=\"bodymatter\"" in lowered or "id='bodymatter'" in lowered:
        strong.append("ams_bodymatter")
    if "nlm_body" in lowered or "articlefulltext" in lowered:
        soft.append("ams_body_container")
    if "citation_fulltext_html_url" in lowered:
        soft.append("ams_fulltext_meta")
    if "citation_pdf_url" in lowered:
        soft.append("ams_pdf_meta")
    return dedupe_signals(strong), dedupe_signals(soft), dedupe_signals(abstract_only)


def ieee_blocking_fallback_signals(html_text: str) -> list[str]:
    from ..extraction.html.provider_rules import provider_html_rules

    lowered = normalize_text(html_text).lower()
    signals: list[str] = []
    if any(
        token in lowered
        for token in provider_html_rules("ieee").cleanup.access_block_text_tokens
    ):
        signals.append("ieee_access_or_challenge_page")
    soup = BeautifulSoup(html_text, "html.parser")
    article = soup.select_one("#article")
    if article is not None:
        text = normalize_text(article.get_text(" ", strip=True))
        has_body_nodes = bool(
            article.select(
                "p, h2, h3, div.section, div.section_2, figure, table, tex-math"
            )
        )
        if not text and not has_body_nodes:
            signals.append("ieee_empty_article_shell")
    return dedupe_signals(signals)


def ieee_positive_signals(html_text: str) -> tuple[list[str], list[str], list[str]]:
    strong, soft, abstract_only = default_positive_signals(html_text)
    lowered = html_text.lower()
    if 'id="article"' in lowered or "id='article'" in lowered:
        soft.append("ieee_article_container")
    if 'div class="section' in lowered or "div class='section" in lowered:
        strong.append("ieee_section_nodes")
    if "<tex-math" in lowered or "tex-math" in lowered:
        soft.append("ieee_formula_marker")
    if "<figure" in lowered or 'class="figure' in lowered or "class='figure" in lowered:
        soft.append("ieee_figure_marker")
    if "<table" in lowered:
        soft.append("ieee_table_marker")
    return dedupe_signals(strong), dedupe_signals(soft), dedupe_signals(abstract_only)


def no_availability_overrides(
    soup: Any,
    structure: Any,
    *,
    final_url: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    del soup, structure, final_url, metadata
    return [], [], []


def science_availability_overrides(
    soup: Any,
    structure: Any,
    *,
    final_url: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    del final_url, metadata
    if soup.select_one(".perspective, .article-type-perspective"):
        setattr(structure, "narrative_article_type", True)
    return [], [], []


def elsevier_availability_overrides(
    soup: Any,
    structure: Any,
    *,
    final_url: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    del structure, final_url, metadata
    canonical_node = soup.select_one("link[rel='canonical']")
    canonical_url = normalize_text(
        str((getattr(canonical_node, "attrs", None) or {}).get("href") or "")
    )
    if "/science/article/abs/" in canonical_url:
        return [], ["canonical_abstract_url"], ["canonical_abstract_url"]
    return [], [], []


def springer_availability_overrides(
    soup: Any,
    structure: Any,
    *,
    final_url: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    del final_url, metadata
    if getattr(structure, "post_abstract_body_run", False):
        return [], [], []
    if soup.select_one(
        ".app-article-access__heading, .c-preview-message__link, [data-test='access-via-institution']"
    ):
        return [], [], ["springer_access_preview_wall"]
    return [], [], []

"""Provider-owned HTML extraction, cleanup, and availability rule registry."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from ...common_patterns import EXTENDED_DATA_LABEL
from ...quality.html_signals import (
    ams_blocking_fallback_signals,
    ams_positive_signals,
    default_positive_signals,
    elsevier_availability_overrides,
    ieee_blocking_fallback_signals,
    ieee_positive_signals,
    no_availability_overrides,
    pnas_blocking_fallback_signals,
    science_availability_overrides,
    science_blocking_fallback_signals,
    science_positive_signals,
    springer_availability_overrides,
    wiley_blocking_fallback_signals,
)
from ...utils import normalize_text
from .html_tags import HTML_DROP_TAGS
from .signals import COMMON_ACCESS_BLOCK_TOKENS as SHARED_COMMON_ACCESS_BLOCK_TOKENS
from .ui_tokens import (
    CITATION_TOOL_CHROME_TOKENS,
    COMMON_NOISE_TOKENS,
    DOWNLOAD_PDF_LABEL,
    RELATED_CONTENT_CHROME_TOKENS,
    SPRINGER_NATURE_SOURCE_DATA_LABEL,
)
from .availability_policy import AvailabilityContainerRules, AvailabilityPolicy
from .cleanup_policy import (
    AVAILABILITY_DROP_TAGS,
    BROWSER_WORKFLOW_DROP_TAGS,
    BROWSER_WORKFLOW_SHORT_TEXT_PATTERNS,
    CleanupPolicy,
    build_cleanup_policy,
)


DEFAULT_NOISE_PROFILE = "generic"
COMMON_MARKDOWN_PROMO_TOKENS = ("learn more",)
COMMON_FRONT_MATTER_FOOTER_PREFIXES = (
    "all content on this site",
    "copyright",
)
GENERIC_FRONT_MATTER_EXACT_TEXTS = (
    "authors",
    "author information",
    # Generic cleanup only has exact matching. Atypon profiles use
    # ATYPON_FRONT_MATTER_CONTAINS_TOKENS for longer "Authors info &
    # affiliations" fragments, so this exact token is not a duplicate branch.
    "affiliations",
)

DEFAULT_SITE_RULE: dict[str, Any] = {
    "candidate_selectors": [
        "article",
        "main article",
        "[role='main'] article",
        "[itemprop='articleBody']",
        "[property='articleBody']",
        "[itemprop='mainEntity']",
        ".article",
        ".article__body",
        ".article__content",
        ".article-body",
        ".main-content",
        "#main-content",
        "main",
        "[role='main']",
        "body",
    ],
    "remove_selectors": [
        *(tag for tag in HTML_DROP_TAGS if tag != "template"),
        "iframe",
        ".social-share",
        ".article-tools",
        ".article-metrics",
        ".metrics-widget",
        ".recommended-articles",
        ".related-content",
        ".breadcrumbs",
        ".toc",
        ".tab__nav",
        ".accessDenialWidget",
        ".cookie-banner",
        ".cookie-consent",
    ],
    "drop_keywords": {
        *COMMON_NOISE_TOKENS,
        "download",
        "citation-tool",
        "nav",
        "access-widget",
    },
    "drop_text": {
        "Check for updates",
        "View Metrics",
        "Share",
        "Cite",
    },
}

SCIENCE_SITE_RULE_OVERRIDES: dict[str, Any] = {
    "candidate_selectors": [
        ".article__fulltext",
        ".article-view",
    ],
    "remove_selectors": [
        "header .social-share",
        ".jump-to-nav",
        ".article-access-info",
        ".references-tab",
        ".permissions",
        ".issue-item__citation",
        ".article-header__access",
        "#article_collateral_menu",
        "#core-collateral-fulltext-options",
        "#core-collateral-metrics",
        "#core-collateral-share",
        "#core-collateral-media",
        "#core-collateral-figures",
        "#core-collateral-tables",
    ],
    "drop_keywords": {"advert", "tab-nav", "jump-to"},
    "drop_text": {"Permissions"},
}

# SITE_UI_COPY_REGRESSION_MARKER: site-owned UI copy; rerun extraction rules
# when publisher text changes.
PNAS_MARKDOWN_PROMO_TOKENS = (
    "sign up for pnas alerts",
    "get alerts for new articles, or get an alert when an article is cited",
)
ATYPON_FRONT_MATTER_EXACT_TEXTS = (
    # These article-type labels are front-matter chrome for Atypon renderers.
    # html_availability.NARRATIVE_ARTICLE_TYPES is a separate quality heuristic
    # for short narrative papers and intentionally does not drive cleanup.
    "full access",
    "open access",
    "free access",
    "research article",
    "perspective",
    "review",
    "editorial",
    "commentary",
)
ATYPON_FRONT_MATTER_CONTAINS_TOKENS = (
    "authors info",
    "affiliations",
)
SCIENCE_MASTHEAD_TEXTS = ("science",)
PNAS_MASTHEAD_TEXTS = ("pnas",)
SCIENCE_FRONT_MATTER_PUBLICATION_KEYWORDS = SCIENCE_MASTHEAD_TEXTS
PNAS_FRONT_MATTER_PUBLICATION_KEYWORDS = PNAS_MASTHEAD_TEXTS
SCIENCE_FRONT_MATTER_EXACT_TEXTS = (
    *ATYPON_FRONT_MATTER_EXACT_TEXTS,
    *SCIENCE_MASTHEAD_TEXTS,
)
PNAS_FRONT_MATTER_EXACT_TEXTS = (
    *ATYPON_FRONT_MATTER_EXACT_TEXTS,
    *PNAS_MASTHEAD_TEXTS,
)
WILEY_FRONT_MATTER_EXACT_TEXTS = ATYPON_FRONT_MATTER_EXACT_TEXTS
PNAS_SITE_RULE_OVERRIDES: dict[str, Any] = {
    "candidate_selectors": [
        ".article__fulltext",
        ".core-container",
        ".article-content",
    ],
    "remove_selectors": [
        ".article__access",
        ".article__footer",
        ".article__reference-links",
        ".core-collateral",
        ".card",
        ".signup-alert-ad",
    ],
    "drop_keywords": {"tab-nav"},
}

# SITE_UI_COPY_REGRESSION_MARKER: site-owned UI copy; rerun extraction rules
# when publisher text changes.
SPRINGER_NATURE_MARKDOWN_PROMO_TOKENS = (
    "sign up for alerts",
    "download citation",
    "reprints and permissions",
    "similar content being viewed by others",
)
# SITE_UI_COPY_REGRESSION_MARKER: site-owned Springer/Nature chrome; rerun
# extraction rules when article action or license section labels change.
SPRINGER_NATURE_CHROME_SECTION_HEADINGS = (
    "about this article",
    "article information",
    "author information",
    "authors and affiliations",
    "cite this article",
    "open access",
    "permissions",
    "rights and permissions",
    "reprints and permissions",
)
# SITE_UI_COPY_REGRESSION_MARKER: site-owned Springer/Nature action chrome;
# rerun extraction rules when article action attributes change.
SPRINGER_NATURE_CHROME_ATTR_TOKENS = (
    "article-actions",
    "article-metrics",
    "saved-research",
    "save-article",
    "submit-manuscript",
)
SPRINGER_NATURE_LICENSE_LINK_HOSTS = ("creativecommons.org",)
SPRINGER_NATURE_LICENSE_LINK_PATH_PREFIXES = ("/licenses/",)
SPRINGER_NATURE_LICENSE_WORD_LIMIT = 180
SPRINGER_NATURE_FORMULA_CONTAINER_TOKENS = (
    "c-article-equation",
    "c-article-equation__content",
)
SPRINGER_NATURE_DISPLAY_FORMULA_SELECTORS = tuple(
    f".{token}" for token in SPRINGER_NATURE_FORMULA_CONTAINER_TOKENS
)
SPRINGER_NATURE_SUPPLEMENTARY_TEXT_TOKENS = (
    EXTENDED_DATA_LABEL,
    SPRINGER_NATURE_SOURCE_DATA_LABEL,
    "peer review",
)
WILEY_FORMULA_CONTAINER_TOKENS = ("fallback__mathequation",)

WILEY_SITE_RULE_OVERRIDES: dict[str, Any] = {
    "candidate_selectors": [
        ".article-section__content",
        ".issue-item__body",
        ".epub-section",
        ".doi-access",
    ],
    "remove_selectors": [
        ".citation-tools",
        ".epub-reference",
        ".article-section__tableofcontents",
        ".publicationHistory",
    ],
    "drop_text": {"Recommended articles"},
}

# SITE_UI_COPY_REGRESSION_MARKER: site-owned UI copy; rerun extraction rules
# when AMS toolbar / recommendation labels change.
AMS_MARKDOWN_PROMO_TOKENS = (
    DOWNLOAD_PDF_LABEL,
    "share this article",
    *CITATION_TOOL_CHROME_TOKENS,
    *RELATED_CONTENT_CHROME_TOKENS,
    "most read",
    "most cited",
)
AMS_MASTHEAD_TEXTS = ("ams", "bams")
AMS_FRONT_MATTER_EXACT_TEXTS = (
    *ATYPON_FRONT_MATTER_EXACT_TEXTS,
    "american meteorological society",
)
# Provider-scoped masthead keywords only; runtime publication-watermark helpers
# require short, punctuation-free, title-like text and must not match prose.
AMS_FRONT_MATTER_PUBLICATION_KEYWORDS = AMS_MASTHEAD_TEXTS
AMS_SITE_RULE_OVERRIDES: dict[str, Any] = {
    "candidate_selectors": [
        "#articleBody",
        "#contentRoot",
        ".component-content-item.component-container.container-fulltext-display",
        ".component-content-item.component-content-html",
        ".article__fulltext",
        ".articleFullText",
        ".NLM_article",
        ".NLM_body",
        "#bodymatter",
    ],
    "remove_selectors": [
        ".article__toolbar",
        ".article__metrics",
        ".core-collateral",
    ],
    # Defaults already cover download/metrics/related/toolbar; AMS adds the
    # broader citation token because its Atypon theme uses several variants.
    "drop_keywords": {"citation"},
}
# AMS DOM postprocess removes AMS-only interactive chrome that must survive
# generic cleanup until figure/gallery asset URLs have been normalized.
AMS_DOM_POSTPROCESS_CLEANUP_SELECTORS = (
    "button[data-xsl-identifier]",
    "[class*='popover']",
    ".citation",
    ".citationActions",
    ".debug",
    ".download-figure",
    ".ppt",
    ".gallery-link",
    ".component-image-gallery",
    ".gallery-overlay",
)

COMMON_ACCESS_BLOCK_TOKENS = SHARED_COMMON_ACCESS_BLOCK_TOKENS
IEEE_ACCESS_BLOCK_TEXT_TOKENS = (
    *COMMON_ACCESS_BLOCK_TOKENS,
    "institutional sign in",
    "purchase access",
)
# Generic script/style/noscript/iframe/button/input cleanup stays in
# DEFAULT_SITE_RULE and the browser workflow. These are IEEE REST fragment or
# Xplore-specific chrome selectors layered on top of those defaults.
IEEE_EXTRACTION_CLEANUP_SELECTORS = (
    "accesstype",
    "select",
    "textarea",
    ".zoom-container",
    ".document-actions",
    ".article-toolbar",
    ".stats-document-abstract-view",
    "button[data-docId]",
    "a[data-docId][href^='javascript:']",
    "[href^='javascript:']",
)
IEEE_AVAILABILITY_DROP_KEYWORDS = (
    "access-type",
    "document-actions",
    "references-modal",
    "show-all",
    "zoom",
)
IEEE_AVAILABILITY_DROP_TEXT = (
    "Show All",
    "View References",
    "Download PDF",
)
# SITE_UI_COPY_REGRESSION_MARKER: site-owned UI copy; rerun extraction rules
# when IEEE toolbar labels change.
IEEE_MARKDOWN_PROMO_TOKENS = (
    DOWNLOAD_PDF_LABEL,
    *CITATION_TOOL_CHROME_TOKENS,
    "show all",
    "view references",
    "view all authors",
)
IEEE_SITE_RULE_OVERRIDES: dict[str, Any] = {
    "candidate_selectors": [
        "#article",
        "#BodyWrapper",
        ".ArticlePage",
    ],
    "remove_selectors": list(IEEE_EXTRACTION_CLEANUP_SELECTORS),
    "drop_keywords": set(IEEE_AVAILABILITY_DROP_KEYWORDS),
    "drop_text": set(IEEE_AVAILABILITY_DROP_TEXT),
}


@dataclass(frozen=True)
class ProviderCleanupRules:
    markdown_promo_tokens: tuple[str, ...] = ()
    extraction_cleanup_selectors: tuple[str, ...] = ()
    dom_postprocess_cleanup_selectors: tuple[str, ...] = ()
    chrome_section_headings: tuple[str, ...] = ()
    chrome_attr_tokens: tuple[str, ...] = ()
    license_link_hosts: tuple[str, ...] = ()
    license_link_path_prefixes: tuple[str, ...] = ()
    license_word_limit: int = 0
    extraction_drop_keywords: tuple[str, ...] = ()
    access_block_text_tokens: tuple[str, ...] = ()
    post_content_break_tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderFrontMatterRules:
    exact_texts: tuple[str, ...] = GENERIC_FRONT_MATTER_EXACT_TEXTS
    contains_tokens: tuple[str, ...] = ()
    publication_keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderFormulaRules:
    container_tokens: tuple[str, ...] = ()
    display_selectors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderAssetRules:
    supplementary_text_tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderHeadingRules:
    normalizations: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DomHooks:
    pass


@dataclass(frozen=True)
class MarkdownHooks:
    pass


def _empty_blocking_fallback_signals(_html: str) -> list[str]:
    return []


def _empty_availability_policy() -> AvailabilityPolicy:
    return AvailabilityPolicy(name="")


def _merged_site_rule_from_overrides(
    site_rule_overrides: Mapping[str, Any],
) -> dict[str, Any]:
    merged = copy.deepcopy(DEFAULT_SITE_RULE)
    for key, value in site_rule_overrides.items():
        default_value = merged.get(key)
        if isinstance(default_value, list):
            merged[key] = [
                *default_value,
                *[item for item in value if item not in default_value],
            ]
            continue
        if isinstance(default_value, set):
            merged[key] = set(default_value) | set(value)
            continue
        merged[key] = copy.deepcopy(value)
    return merged


def _availability_container_rules_from_site_rule_overrides(
    site_rule_overrides: Mapping[str, Any],
) -> AvailabilityContainerRules:
    site_rule = _merged_site_rule_from_overrides(site_rule_overrides)
    return AvailabilityContainerRules(
        candidate_selectors=tuple(site_rule.get("candidate_selectors") or ()),
        remove_selectors=tuple(site_rule.get("remove_selectors") or ()),
        drop_keywords=tuple(site_rule.get("drop_keywords") or ()),
        drop_texts=tuple(site_rule.get("drop_text") or ()),
        drop_tags=AVAILABILITY_DROP_TAGS,
        browser_workflow_drop_tags=BROWSER_WORKFLOW_DROP_TAGS,
        browser_workflow_short_text_patterns=BROWSER_WORKFLOW_SHORT_TEXT_PATTERNS,
    )


def _availability_policy_with_defaults(
    provider_name: str,
    cleanup: ProviderCleanupRules,
    availability: AvailabilityPolicy,
) -> AvailabilityPolicy:
    empty_container_rules = AvailabilityContainerRules()
    container_rules = availability.container_rules
    if container_rules == empty_container_rules:
        container_rules = _availability_container_rules_from_site_rule_overrides(
            availability.site_rule_overrides
        )
    return AvailabilityPolicy(
        name=availability.name or provider_name,
        container_rules=container_rules,
        site_rule_overrides=availability.site_rule_overrides,
        positive_signals=availability.positive_signals or default_positive_signals,
        blocking_fallback_signals=(
            availability.blocking_fallback_signals
            or _empty_blocking_fallback_signals
        ),
        availability_overrides=(
            availability.availability_overrides or no_availability_overrides
        ),
        access_block_text_tokens=(
            availability.access_block_text_tokens or cleanup.access_block_text_tokens
        ),
    )


@dataclass(frozen=True)
class ProviderHtmlRules:
    name: str
    aliases: tuple[str, ...] = ()
    noise_profile: str = DEFAULT_NOISE_PROFILE
    cleanup: ProviderCleanupRules = field(default_factory=ProviderCleanupRules)
    front_matter: ProviderFrontMatterRules = field(
        default_factory=ProviderFrontMatterRules
    )
    formula: ProviderFormulaRules = field(default_factory=ProviderFormulaRules)
    assets: ProviderAssetRules = field(default_factory=ProviderAssetRules)
    heading: ProviderHeadingRules = field(default_factory=ProviderHeadingRules)
    availability: AvailabilityPolicy = field(default_factory=_empty_availability_policy)
    dom_hooks: DomHooks = field(default_factory=DomHooks)
    markdown_hooks: MarkdownHooks = field(default_factory=MarkdownHooks)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "availability",
            _availability_policy_with_defaults(
                self.name,
                self.cleanup,
                self.availability,
            ),
        )


GENERIC_HTML_RULES = ProviderHtmlRules(name=DEFAULT_NOISE_PROFILE)

PROVIDER_HTML_RULES: Mapping[str, ProviderHtmlRules] = MappingProxyType(
    {
        "science": ProviderHtmlRules(
            name="science",
            aliases=("aaas",),
            availability=AvailabilityPolicy(
                name="science",
                site_rule_overrides=SCIENCE_SITE_RULE_OVERRIDES,
                positive_signals=science_positive_signals,
                blocking_fallback_signals=science_blocking_fallback_signals,
                availability_overrides=science_availability_overrides,
            ),
            front_matter=ProviderFrontMatterRules(
                exact_texts=SCIENCE_FRONT_MATTER_EXACT_TEXTS,
                contains_tokens=ATYPON_FRONT_MATTER_CONTAINS_TOKENS,
                publication_keywords=SCIENCE_FRONT_MATTER_PUBLICATION_KEYWORDS,
            ),
        ),
        "pnas": ProviderHtmlRules(
            name="pnas",
            noise_profile="pnas",
            cleanup=ProviderCleanupRules(
                markdown_promo_tokens=PNAS_MARKDOWN_PROMO_TOKENS,
                extraction_drop_keywords=("signup-alert-ad", "tab-nav"),
            ),
            availability=AvailabilityPolicy(
                name="pnas",
                site_rule_overrides=PNAS_SITE_RULE_OVERRIDES,
                blocking_fallback_signals=pnas_blocking_fallback_signals,
            ),
            front_matter=ProviderFrontMatterRules(
                exact_texts=PNAS_FRONT_MATTER_EXACT_TEXTS,
                contains_tokens=ATYPON_FRONT_MATTER_CONTAINS_TOKENS,
                publication_keywords=PNAS_FRONT_MATTER_PUBLICATION_KEYWORDS,
            ),
        ),
        "elsevier": ProviderHtmlRules(
            name="elsevier",
            availability=AvailabilityPolicy(
                name="elsevier",
                availability_overrides=elsevier_availability_overrides,
            ),
        ),
        "springer_nature": ProviderHtmlRules(
            name="springer_nature",
            aliases=("springer", "nature"),
            noise_profile="springer_nature",
            cleanup=ProviderCleanupRules(
                markdown_promo_tokens=SPRINGER_NATURE_MARKDOWN_PROMO_TOKENS,
                chrome_section_headings=SPRINGER_NATURE_CHROME_SECTION_HEADINGS,
                chrome_attr_tokens=SPRINGER_NATURE_CHROME_ATTR_TOKENS,
                license_link_hosts=SPRINGER_NATURE_LICENSE_LINK_HOSTS,
                license_link_path_prefixes=SPRINGER_NATURE_LICENSE_LINK_PATH_PREFIXES,
                license_word_limit=SPRINGER_NATURE_LICENSE_WORD_LIMIT,
            ),
            formula=ProviderFormulaRules(
                container_tokens=SPRINGER_NATURE_FORMULA_CONTAINER_TOKENS,
                display_selectors=SPRINGER_NATURE_DISPLAY_FORMULA_SELECTORS,
            ),
            assets=ProviderAssetRules(
                supplementary_text_tokens=SPRINGER_NATURE_SUPPLEMENTARY_TEXT_TOKENS,
            ),
            heading=ProviderHeadingRules(normalizations={"online methods": "Methods"}),
            availability=AvailabilityPolicy(
                name="springer_nature",
                availability_overrides=springer_availability_overrides,
            ),
        ),
        "wiley": ProviderHtmlRules(
            name="wiley",
            cleanup=ProviderCleanupRules(
                extraction_drop_keywords=("citation-tools", "publicationhistory"),
            ),
            formula=ProviderFormulaRules(
                container_tokens=WILEY_FORMULA_CONTAINER_TOKENS,
            ),
            availability=AvailabilityPolicy(
                name="wiley",
                site_rule_overrides=WILEY_SITE_RULE_OVERRIDES,
                blocking_fallback_signals=wiley_blocking_fallback_signals,
            ),
            front_matter=ProviderFrontMatterRules(
                exact_texts=WILEY_FRONT_MATTER_EXACT_TEXTS,
                contains_tokens=ATYPON_FRONT_MATTER_CONTAINS_TOKENS,
            ),
        ),
        "ams": ProviderHtmlRules(
            name="ams",
            cleanup=ProviderCleanupRules(
                markdown_promo_tokens=AMS_MARKDOWN_PROMO_TOKENS,
                dom_postprocess_cleanup_selectors=AMS_DOM_POSTPROCESS_CLEANUP_SELECTORS,
            ),
            availability=AvailabilityPolicy(
                name="ams",
                site_rule_overrides=AMS_SITE_RULE_OVERRIDES,
                positive_signals=ams_positive_signals,
                blocking_fallback_signals=ams_blocking_fallback_signals,
            ),
            front_matter=ProviderFrontMatterRules(
                exact_texts=AMS_FRONT_MATTER_EXACT_TEXTS,
                contains_tokens=ATYPON_FRONT_MATTER_CONTAINS_TOKENS,
                publication_keywords=AMS_FRONT_MATTER_PUBLICATION_KEYWORDS,
            ),
        ),
        "ieee": ProviderHtmlRules(
            name="ieee",
            noise_profile="ieee",
            cleanup=ProviderCleanupRules(
                markdown_promo_tokens=IEEE_MARKDOWN_PROMO_TOKENS,
                extraction_cleanup_selectors=IEEE_EXTRACTION_CLEANUP_SELECTORS,
                extraction_drop_keywords=IEEE_AVAILABILITY_DROP_KEYWORDS,
                access_block_text_tokens=IEEE_ACCESS_BLOCK_TEXT_TOKENS,
            ),
            availability=AvailabilityPolicy(
                name="ieee",
                site_rule_overrides=IEEE_SITE_RULE_OVERRIDES,
                positive_signals=ieee_positive_signals,
                blocking_fallback_signals=ieee_blocking_fallback_signals,
            ),
        ),
    }
)


def _normalize_rule_key(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", "_").split())


def _build_rule_lookup() -> dict[str, ProviderHtmlRules]:
    lookup: dict[str, ProviderHtmlRules] = {DEFAULT_NOISE_PROFILE: GENERIC_HTML_RULES}
    for rules in PROVIDER_HTML_RULES.values():
        for key in (rules.name, rules.noise_profile, *rules.aliases):
            normalized = _normalize_rule_key(key)
            if normalized:
                lookup[normalized] = rules
    return lookup


_RULE_LOOKUP = MappingProxyType(_build_rule_lookup())
REGISTERED_NOISE_PROFILES = frozenset(
    {
        DEFAULT_NOISE_PROFILE,
        *(rules.noise_profile for rules in PROVIDER_HTML_RULES.values()),
    }
)


def provider_html_rules(name: str | None) -> ProviderHtmlRules:
    return _RULE_LOOKUP.get(_normalize_rule_key(name), GENERIC_HTML_RULES)


def merged_site_rule(rules: ProviderHtmlRules) -> dict[str, Any]:
    return _merged_site_rule_from_overrides(rules.availability.site_rule_overrides)


def _availability_container_rules_from_rules(
    rules: ProviderHtmlRules,
) -> AvailabilityContainerRules:
    return _availability_container_rules_from_site_rule_overrides(
        rules.availability.site_rule_overrides
    )


def _cleanup_policy_from_rules(rules: ProviderHtmlRules) -> CleanupPolicy:
    cleanup = rules.cleanup
    front_matter = rules.front_matter
    return build_cleanup_policy(
        rules.noise_profile,
        markdown_contains_tokens=(
            *COMMON_MARKDOWN_PROMO_TOKENS,
            *cleanup.markdown_promo_tokens,
        ),
        provider_markdown_promo_tokens=cleanup.markdown_promo_tokens,
        extraction_cleanup_selectors=cleanup.extraction_cleanup_selectors,
        dom_postprocess_cleanup_selectors=cleanup.dom_postprocess_cleanup_selectors,
        chrome_section_headings=cleanup.chrome_section_headings,
        chrome_attr_tokens=cleanup.chrome_attr_tokens,
        license_link_hosts=cleanup.license_link_hosts,
        license_link_path_prefixes=cleanup.license_link_path_prefixes,
        license_word_limit=cleanup.license_word_limit,
        extraction_drop_keywords=cleanup.extraction_drop_keywords,
        front_matter_exact_texts=front_matter.exact_texts,
        front_matter_contains_tokens=front_matter.contains_tokens,
        front_matter_publication_keywords=front_matter.publication_keywords,
        post_content_cutoff_tokens=cleanup.post_content_break_tokens,
    )


def cleanup_policy_for_profile(noise_profile: str | None) -> CleanupPolicy:
    return _cleanup_policy_from_rules(provider_html_rules(noise_profile))


def availability_rules_for_provider(provider: str | None) -> AvailabilityPolicy:
    return provider_html_rules(provider).availability


def front_matter_rules_for_profile(
    noise_profile: str | None,
) -> ProviderFrontMatterRules:
    return provider_html_rules(noise_profile).front_matter


def formula_rules_for_provider(provider: str | None) -> ProviderFormulaRules:
    return provider_html_rules(provider).formula


def asset_rules_for_provider(provider: str | None) -> ProviderAssetRules:
    return provider_html_rules(provider).assets


def normalize_noise_profile(noise_profile: str | None) -> str:
    return provider_html_rules(noise_profile).noise_profile


def markdown_promo_tokens_for_profile(noise_profile: str | None) -> tuple[str, ...]:
    return cleanup_policy_for_profile(noise_profile).markdown_contains_tokens


def front_matter_footer_prefixes() -> tuple[str, ...]:
    return COMMON_FRONT_MATTER_FOOTER_PREFIXES


def front_matter_exact_texts_for_profile(noise_profile: str | None) -> tuple[str, ...]:
    return front_matter_rules_for_profile(noise_profile).exact_texts


def front_matter_contains_tokens_for_profile(
    noise_profile: str | None,
) -> tuple[str, ...]:
    return front_matter_rules_for_profile(noise_profile).contains_tokens


def front_matter_publication_keywords_for_profile(
    noise_profile: str | None,
) -> tuple[str, ...]:
    return front_matter_rules_for_profile(noise_profile).publication_keywords


def extraction_cleanup_selectors_for_profile(
    noise_profile: str | None,
) -> tuple[str, ...]:
    return cleanup_policy_for_profile(noise_profile).extraction_cleanup_selectors


def extraction_drop_keywords_for_profile(noise_profile: str | None) -> tuple[str, ...]:
    return cleanup_policy_for_profile(noise_profile).extraction_drop_keywords


def normalize_provider_heading(provider_name: str | None, heading: str | None) -> str:
    normalized = normalize_text(heading)
    if not normalized:
        return ""
    replacement = provider_html_rules(provider_name).heading.normalizations.get(
        normalized.lower()
    )
    return replacement or normalized


def _dedupe_tuple(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def provider_formula_container_tokens(noise_profile: str | None) -> tuple[str, ...]:
    return formula_rules_for_provider(noise_profile).container_tokens


def provider_display_formula_selectors(noise_profile: str | None) -> tuple[str, ...]:
    return formula_rules_for_provider(noise_profile).display_selectors


def provider_supplementary_text_tokens(noise_profile: str | None) -> tuple[str, ...]:
    return asset_rules_for_provider(noise_profile).supplementary_text_tokens


def all_provider_formula_container_tokens() -> tuple[str, ...]:
    values: list[str] = []
    for rules in PROVIDER_HTML_RULES.values():
        values.extend(rules.formula.container_tokens)
    return _dedupe_tuple(values)


def all_provider_display_formula_selectors() -> tuple[str, ...]:
    values: list[str] = []
    for rules in PROVIDER_HTML_RULES.values():
        values.extend(rules.formula.display_selectors)
    return _dedupe_tuple(values)


__all__ = [
    "DEFAULT_NOISE_PROFILE",
    "DEFAULT_SITE_RULE",
    "GENERIC_HTML_RULES",
    "COMMON_ACCESS_BLOCK_TOKENS",
    "COMMON_MARKDOWN_PROMO_TOKENS",
    "COMMON_FRONT_MATTER_FOOTER_PREFIXES",
    "IEEE_ACCESS_BLOCK_TEXT_TOKENS",
    "IEEE_AVAILABILITY_DROP_KEYWORDS",
    "IEEE_AVAILABILITY_DROP_TEXT",
    "IEEE_EXTRACTION_CLEANUP_SELECTORS",
    "IEEE_MARKDOWN_PROMO_TOKENS",
    "IEEE_SITE_RULE_OVERRIDES",
    "DomHooks",
    "MarkdownHooks",
    "PNAS_MARKDOWN_PROMO_TOKENS",
    "PNAS_SITE_RULE_OVERRIDES",
    "PNAS_FRONT_MATTER_PUBLICATION_KEYWORDS",
    "AMS_DOM_POSTPROCESS_CLEANUP_SELECTORS",
    "AMS_FRONT_MATTER_PUBLICATION_KEYWORDS",
    "AMS_MARKDOWN_PROMO_TOKENS",
    "AMS_SITE_RULE_OVERRIDES",
    "PROVIDER_HTML_RULES",
    "ProviderAssetRules",
    "ProviderCleanupRules",
    "ProviderFormulaRules",
    "ProviderFrontMatterRules",
    "ProviderHeadingRules",
    "ProviderHtmlRules",
    "REGISTERED_NOISE_PROFILES",
    "SCIENCE_FRONT_MATTER_PUBLICATION_KEYWORDS",
    "SCIENCE_SITE_RULE_OVERRIDES",
    "SPRINGER_NATURE_CHROME_ATTR_TOKENS",
    "SPRINGER_NATURE_CHROME_SECTION_HEADINGS",
    "SPRINGER_NATURE_DISPLAY_FORMULA_SELECTORS",
    "SPRINGER_NATURE_FORMULA_CONTAINER_TOKENS",
    "SPRINGER_NATURE_LICENSE_LINK_HOSTS",
    "SPRINGER_NATURE_LICENSE_LINK_PATH_PREFIXES",
    "SPRINGER_NATURE_LICENSE_WORD_LIMIT",
    "SPRINGER_NATURE_MARKDOWN_PROMO_TOKENS",
    "SPRINGER_NATURE_SUPPLEMENTARY_TEXT_TOKENS",
    "WILEY_FORMULA_CONTAINER_TOKENS",
    "WILEY_SITE_RULE_OVERRIDES",
    "asset_rules_for_provider",
    "availability_rules_for_provider",
    "all_provider_display_formula_selectors",
    "all_provider_formula_container_tokens",
    "cleanup_policy_for_profile",
    "extraction_cleanup_selectors_for_profile",
    "extraction_drop_keywords_for_profile",
    "formula_rules_for_provider",
    "front_matter_contains_tokens_for_profile",
    "front_matter_exact_texts_for_profile",
    "front_matter_footer_prefixes",
    "front_matter_publication_keywords_for_profile",
    "front_matter_rules_for_profile",
    "markdown_promo_tokens_for_profile",
    "merged_site_rule",
    "normalize_noise_profile",
    "normalize_provider_heading",
    "provider_display_formula_selectors",
    "provider_formula_container_tokens",
    "provider_html_rules",
    "provider_supplementary_text_tokens",
]

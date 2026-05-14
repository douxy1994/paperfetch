from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from paper_fetch.extraction.html.availability_policy import AvailabilityPolicy
from paper_fetch.extraction.html.provider_rules import (
    GENERIC_HTML_RULES,
    PROVIDER_HTML_RULES,
    DomHooks,
    MarkdownHooks,
    ProviderAssetRules,
    ProviderCleanupRules,
    ProviderFormulaRules,
    ProviderFrontMatterRules,
    ProviderHeadingRules,
    ProviderHtmlRules,
    _availability_container_rules_from_rules,
    _cleanup_policy_from_rules,
    merged_site_rule,
)


def _all_registered_rules() -> tuple[ProviderHtmlRules, ...]:
    return (GENERIC_HTML_RULES, *PROVIDER_HTML_RULES.values())


@pytest.mark.parametrize(
    "rules",
    _all_registered_rules(),
    ids=lambda rules: rules.name,
)
def test_provider_html_rules_facets_are_present(rules: ProviderHtmlRules) -> None:
    assert isinstance(rules.cleanup, ProviderCleanupRules)
    assert isinstance(rules.front_matter, ProviderFrontMatterRules)
    assert isinstance(rules.formula, ProviderFormulaRules)
    assert isinstance(rules.assets, ProviderAssetRules)
    assert isinstance(rules.heading, ProviderHeadingRules)
    assert isinstance(rules.availability, AvailabilityPolicy)
    assert isinstance(rules.dom_hooks, DomHooks)
    assert isinstance(rules.markdown_hooks, MarkdownHooks)
    assert rules.availability.container_rules is not None


def test_provider_html_rules_does_not_expose_flat_rule_fields() -> None:
    field_names = {field.name for field in fields(ProviderHtmlRules)}

    assert field_names.isdisjoint(
        {
            "access_block_text_tokens",
            "availability_overrides",
            "availability_site_rule_overrides",
            "blocking_fallback_signals",
            "chrome_attr_tokens",
            "chrome_section_headings",
            "display_formula_selectors",
            "dom_postprocess_cleanup_selectors",
            "extraction_cleanup_selectors",
            "extraction_drop_keywords",
            "formula_container_tokens",
            "front_matter_contains_tokens",
            "front_matter_exact_texts",
            "front_matter_publication_keywords",
            "heading_normalizations",
            "license_link_hosts",
            "license_link_path_prefixes",
            "license_word_limit",
            "markdown_promo_tokens",
            "positive_signals",
            "supplementary_text_tokens",
        }
    )


def test_provider_html_rules_facets_are_frozen() -> None:
    rules = PROVIDER_HTML_RULES["ieee"]

    with pytest.raises(FrozenInstanceError):
        rules.cleanup.markdown_promo_tokens = ()
    with pytest.raises(FrozenInstanceError):
        rules.formula.container_tokens = ()
    with pytest.raises(FrozenInstanceError):
        rules.availability.site_rule_overrides = {}


def test_provider_html_rules_facets_round_trip_to_policies() -> None:
    rules = ProviderHtmlRules(
        name="custom",
        noise_profile="custom_noise",
        cleanup=ProviderCleanupRules(
            markdown_promo_tokens=("custom promo",),
            extraction_cleanup_selectors=(".custom-remove",),
            dom_postprocess_cleanup_selectors=(".custom-postprocess",),
            chrome_section_headings=("custom chrome",),
            chrome_attr_tokens=("custom-attr",),
            license_link_hosts=("licenses.example",),
            license_link_path_prefixes=("/licenses/",),
            license_word_limit=25,
            extraction_drop_keywords=("custom-drop",),
            access_block_text_tokens=("custom access wall",),
            post_content_break_tokens=("custom break",),
        ),
        front_matter=ProviderFrontMatterRules(
            exact_texts=("custom front",),
            contains_tokens=("custom contains",),
            publication_keywords=("custom journal",),
        ),
        formula=ProviderFormulaRules(
            container_tokens=("custom-equation",),
            display_selectors=(".custom-equation",),
        ),
        assets=ProviderAssetRules(supplementary_text_tokens=("custom data",)),
        heading=ProviderHeadingRules(normalizations={"custom methods": "Methods"}),
        availability=AvailabilityPolicy(
            name="custom",
            site_rule_overrides={
                "candidate_selectors": [".custom-article"],
                "remove_selectors": [".custom-remove"],
                "drop_keywords": {"custom-drop"},
                "drop_text": {"Custom action"},
            },
        ),
    )

    cleanup_policy = _cleanup_policy_from_rules(rules)
    container_rules = _availability_container_rules_from_rules(rules)
    merged = merged_site_rule(rules)

    assert cleanup_policy.name == "custom_noise"
    assert cleanup_policy.provider_markdown_promo_tokens == ("custom promo",)
    assert cleanup_policy.extraction_cleanup_selectors == (".custom-remove",)
    assert cleanup_policy.dom_postprocess_cleanup_selectors == (".custom-postprocess",)
    assert cleanup_policy.chrome_section_headings == frozenset({"custom chrome"})
    assert cleanup_policy.chrome_attr_tokens == ("custom-attr",)
    assert cleanup_policy.license_link_hosts == ("licenses.example",)
    assert cleanup_policy.license_link_path_prefixes == ("/licenses/",)
    assert cleanup_policy.license_word_limit == 25
    assert cleanup_policy.extraction_drop_keywords == ("custom-drop",)
    assert cleanup_policy.front_matter_exact_texts == ("custom front",)
    assert cleanup_policy.front_matter_contains_tokens == ("custom contains",)
    assert cleanup_policy.front_matter_publication_keywords == ("custom journal",)
    assert cleanup_policy.post_content_cutoff_tokens == ("custom break",)
    assert rules.formula.container_tokens == ("custom-equation",)
    assert rules.formula.display_selectors == (".custom-equation",)
    assert rules.assets.supplementary_text_tokens == ("custom data",)
    assert rules.heading.normalizations == {"custom methods": "Methods"}
    assert ".custom-article" in merged["candidate_selectors"]
    assert ".custom-remove" in container_rules.remove_selectors
    assert "custom-drop" in container_rules.drop_keywords
    assert "Custom action" in container_rules.drop_texts
    assert rules.availability.container_rules == container_rules
    assert rules.availability.access_block_text_tokens == ("custom access wall",)
    assert rules.availability.datalayer_signal_set is None
    assert rules.availability.text_marker_signal_set is None
    assert rules.availability.overrides is None

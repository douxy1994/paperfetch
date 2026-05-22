from __future__ import annotations

from tests.script_modules import load_script_module


def test_discover_brief_contains_required_search_contract() -> None:
    module = load_script_module("onboard_from_manifests")

    brief = module.build_discover_brief(
        provider="mdpi",
        domain="mdpi.com",
        doi_prefix="10.3390",
        output_manifest="onboarding/manifests/mdpi.yml",
    )

    assert brief["task_id"] == "mdpi-discover-manifest"
    assert brief["current_step"] == "discover-manifest"
    assert brief["runtime"] == "coding-agent-subagent"
    assert brief["schema"] == "onboarding/provider-manifest.schema.json"
    assert brief["hard_constraints"] == "onboarding/hard-constraints.md"
    assert brief["provider_seed"] == {
        "name": "mdpi",
        "domain": "mdpi.com",
        "doi_prefix_hint": "10.3390",
    }
    assert brief["output_manifest"] == "onboarding/manifests/mdpi.yml"
    assert brief["search_requirements"]["routing"] == [
        "doi_prefixes",
        "domains",
        "domain_suffixes",
        "crossref_publisher",
    ]
    assert brief["search_requirements"]["doi_sample_purposes"] == [
        "structure",
        "table",
        "formula",
        "figure",
        "supplementary",
        "references",
        "pdf_fallback",
        "abstract_only",
        "access_gate",
        "empty_shell",
    ]
    assert brief["files_allowed_to_modify"] == [
        "onboarding/manifests/mdpi.yml"
    ]
    assert {"src/", "tests/", "docs/providers.md", "CHANGELOG.md"}.issubset(
        set(brief["files_must_not_modify"])
    )
    assert brief["no_commit"] is True


def test_discover_brief_yaml_has_no_sensitive_collection_or_sdk_prompts() -> None:
    module = load_script_module("onboard_from_manifests")
    brief = module.build_discover_brief(
        provider="mdpi",
        domain="mdpi.com",
        doi_prefix=None,
        output_manifest="onboarding/manifests/mdpi.yml",
    )

    rendered = module.to_yaml(brief).lower()

    forbidden_fragments = [
        "secret",
        "api key",
        "apikey",
        "token",
        "env var",
        "environment variable",
        "anthropic",
        "openai",
        "llm sdk",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in rendered

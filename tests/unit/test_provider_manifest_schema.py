from __future__ import annotations

import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from ._manifest_sync import (
    MANIFESTS_DIR,
    load_manifest_schema,
    load_yaml,
)


REQUIRED_DOI_PURPOSES = {"structure", "figure", "references"}
PLACEHOLDER_PATTERN = re.compile(r"\b(?:todo|tbd|unknown)\b", re.IGNORECASE)


def load_schema():
    return load_manifest_schema()


def iter_manifest_paths() -> list[Path]:
    return sorted(MANIFESTS_DIR.glob("*.yml"))


def test_provider_manifest_schema_is_valid_json_schema() -> None:
    schema = load_schema()

    Draft202012Validator.check_schema(schema)


def test_all_provider_manifests_pass_schema_and_local_invariants() -> None:
    schema = load_schema()
    validator = Draft202012Validator(schema)
    manifest_paths = iter_manifest_paths()
    assert manifest_paths

    for manifest_path in manifest_paths:
        manifest = load_yaml(manifest_path)
        errors = sorted(validator.iter_errors(manifest), key=lambda error: error.json_path)
        assert not errors, [
            f"{manifest_path}: {error.json_path}: {error.message}" for error in errors
        ]

        assert manifest["name"] == manifest_path.stem
        assert isinstance(manifest["main_path"], list)
        assert manifest["main_path"], f"{manifest_path}: main_path must not be empty"
        route_sources = manifest.get("route_sources") or {}
        assert isinstance(route_sources, dict), f"{manifest_path}: route_sources must be an object"
        for step, source in route_sources.items():
            assert step in manifest["main_path"], (
                f"{manifest_path}: route_sources.{step} must reference "
                "a step from main_path"
            )
            assert source, f"{manifest_path}: route_sources.{step} must not be empty"
        if route_sources:
            assert manifest["display_source"] in set(route_sources.values()), (
                f"{manifest_path}: display_source must appear in route_sources values"
            )
        route_contract = manifest["route_contract"]
        for step in manifest["main_path"]:
            assert step in route_contract, (
                f"{manifest_path}: route_contract.{step} is required "
                "for every main_path step"
            )
            assert route_contract[step]["success_requires"], (
                f"{manifest_path}: route_contract.{step}.success_requires "
                "must not be empty"
            )
        assert isinstance(manifest["docs"], dict)
        assert manifest["docs"]["providers_md_capability_row"]
        assert manifest["docs"]["changelog_summary"]
        doi_samples = manifest["fixtures"]["doi_samples"]
        markdown_contract = manifest["markdown_contract"]
        for purpose in REQUIRED_DOI_PURPOSES:
            assert doi_samples[purpose]["doi"], f"{manifest_path}: {purpose} DOI is required"
        for purpose, sample in doi_samples.items():
            doi = sample.get("doi")
            if not doi:
                continue
            assert purpose in markdown_contract, (
                f"{manifest_path}: markdown_contract.{purpose} is required "
                "for every non-null DOI sample"
            )
            purpose_contract = markdown_contract[purpose]
            assert purpose_contract["doi"] == doi, (
                f"{manifest_path}: markdown_contract.{purpose}.doi must "
                "match fixtures.doi_samples"
            )
            assert purpose_contract["must_include"], (
                f"{manifest_path}: markdown_contract.{purpose}.must_include "
                "must not be empty"
            )
            assert purpose_contract["must_not_include"], (
                f"{manifest_path}: markdown_contract.{purpose}.must_not_include "
                "must not be empty"
            )
        for index, extra_fixture in enumerate(manifest.get("extra_fixtures") or []):
            assert extra_fixture["doi"], (
                f"{manifest_path}: extra_fixtures[{index}].doi is required"
            )
            assert extra_fixture["evidence_url"], (
                f"{manifest_path}: extra_fixtures[{index}].evidence_url is required"
            )
            assert extra_fixture["evidence_reason"], (
                f"{manifest_path}: extra_fixtures[{index}].evidence_reason is required"
            )
            assert extra_fixture["observed_signals"], (
                f"{manifest_path}: extra_fixtures[{index}].observed_signals "
                "must not be empty"
            )
            extra_contract = extra_fixture.get("markdown_contract")
            if extra_contract is None:
                continue
            assert extra_contract["doi"] == extra_fixture["doi"], (
                f"{manifest_path}: extra_fixtures[{index}].markdown_contract.doi "
                "must match extra fixture DOI"
            )
            assert extra_contract["must_include"], (
                f"{manifest_path}: extra_fixtures[{index}].markdown_contract."
                "must_include must not be empty"
            )
            assert extra_contract["must_not_include"], (
                f"{manifest_path}: extra_fixtures[{index}].markdown_contract."
                "must_not_include must not be empty"
            )

        rendered = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=True)
        assert not PLACEHOLDER_PATTERN.search(rendered), manifest_path

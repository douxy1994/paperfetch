from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFESTS_DIR = REPO_ROOT / "onboarding" / "manifests"
REVIEWS_DIR = REPO_ROOT / "onboarding" / "reviews"
REVIEW_SCHEMA_PATH = REPO_ROOT / "onboarding" / "provider-review.schema.json"
PROVIDER_TEST_GLOBS = {
    "ams": ("test_ams_provider.py",),
    "elsevier": ("test_elsevier_markdown.py", "test_provider_waterfalls.py"),
    "ieee": ("test_ieee_provider*.py",),
    "pnas": ("test_atypon_browser_workflow_provider*.py",),
    "science": ("test_atypon_browser_workflow_provider*.py",),
    "springer": (
        "test_springer_html*.py",
        "test_provider_waterfalls.py",
    ),
}

PLACEHOLDER_PATTERNS = (
    "test_provider_golden_replay_placeholder",
    "test_markdown_review_loop_contract_placeholder",
    "TODO: add recorded golden fixture assets before enabling replay",
)
REVIEW_PLACEHOLDER_PATTERN = re.compile(r"\b(?:todo|tbd|unknown)\b", re.IGNORECASE)
MARKDOWN_TARGET_PATTERN = re.compile(
    r"\b(markdown|rendered|to_ai_markdown|markdown_text)\b",
    re.IGNORECASE,
)
POSITIVE_ASSERTION_PATTERN = re.compile(
    r"\b(?:self\.)?assert(?:In|Regex|True)\s*\(|\bassert\s+.+\s+in\s+",
)
NEGATIVE_ASSERTION_PATTERN = re.compile(
    r"\b(?:self\.)?assertNot(?:In|Regex)\s*\(|\bassert\s+.+\s+not\s+in\s+",
)
COUNT_OR_REGEX_ASSERTION_PATTERN = re.compile(
    r"\b(?:assertEqual|assertRegex|assertNotRegex)\s*\(|"
    r"\bassert\s+.+(?:count\(|re\.search|re\.match)",
)
MARKDOWN_REVIEW_MARKER_TEMPLATE = "markdown-review: purpose={purpose} doi={doi}"


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path} must load as a mapping"
    return data


def _manifest_paths() -> tuple[Path, ...]:
    paths = tuple(sorted(MANIFESTS_DIR.glob("*.yml")))
    assert paths, "provider Markdown review contract needs manifest fixtures"
    return paths


def _doi_slug(doi: str) -> str:
    return doi.replace("/", "_")


def _load_review_schema() -> dict[str, Any]:
    data = yaml.safe_load(REVIEW_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{REVIEW_SCHEMA_PATH} must load as a mapping"
    Draft202012Validator.check_schema(data)
    return data


def _traceability_errors(review: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    provider = str(review.get("provider") or "<unknown>")
    for item in review.get("fixtures") or []:
        if not isinstance(item, dict):
            continue
        fixture_label = f"{provider}:{item.get('purpose')}:{item.get('doi')}"
        issue_ids: set[str] = set()
        for issue in item.get("issues") or []:
            issue_id = str(issue.get("id") or "") if isinstance(issue, dict) else ""
            if issue_id in issue_ids:
                errors.append(f"{fixture_label}: duplicate issue id {issue_id!r}")
            issue_ids.add(issue_id)
        for fix in item.get("fixes") or []:
            if not isinstance(fix, dict):
                continue
            fix_id = str(fix.get("id") or "<missing>")
            for issue_id in fix.get("issue_ids") or []:
                if str(issue_id) not in issue_ids:
                    errors.append(
                        f"{fixture_label}: fix {fix_id!r} references missing "
                        f"issue id {issue_id!r}"
                    )
            if not fix.get("test_names"):
                errors.append(f"{fixture_label}: fix {fix_id!r} has no test_names")
    return errors


def _expected_review_fixtures(manifest: dict[str, Any]) -> set[tuple[str, str]]:
    expected: set[tuple[str, str]] = set()
    doi_samples = manifest["fixtures"]["doi_samples"]
    assert isinstance(doi_samples, dict)
    for purpose, sample in doi_samples.items():
        if isinstance(sample, dict) and sample.get("doi"):
            expected.add((str(purpose), str(sample["doi"])))
    for extra_fixture in manifest.get("extra_fixtures") or []:
        if isinstance(extra_fixture, dict) and extra_fixture.get("doi"):
            expected.add((str(extra_fixture["purpose"]), str(extra_fixture["doi"])))
    return expected


def _assert_review_artifact(manifest_path: Path, manifest: dict[str, Any]) -> None:
    provider = str(manifest["name"])
    review_path = REVIEWS_DIR / f"{provider}.yml"
    assert review_path.is_file(), (
        f"{manifest_path}: expected persistent review artifact "
        f"{review_path.relative_to(REPO_ROOT)}"
    )
    review = _load_yaml(review_path)
    schema = _load_review_schema()
    errors = sorted(
        Draft202012Validator(schema).iter_errors(review),
        key=lambda error: error.json_path,
    )
    assert not errors, [
        f"{review_path}: {error.json_path}: {error.message}" for error in errors
    ]
    rendered = yaml.safe_dump(review, allow_unicode=True, sort_keys=True)
    assert not REVIEW_PLACEHOLDER_PATTERN.search(rendered), (
        f"{review_path} contains TODO/TBD/unknown placeholder text"
    )
    traceability_errors = _traceability_errors(review)
    assert not traceability_errors, [
        f"{review_path}: {error}" for error in traceability_errors
    ]
    assert review["provider"] == provider, (
        f"{review_path}: provider must match manifest name"
    )
    expected = _expected_review_fixtures(manifest)
    reviewed = {
        (str(item["purpose"]), str(item["doi"]))
        for item in review["fixtures"]
        if isinstance(item, dict)
    }
    assert expected <= reviewed, (
        f"{review_path}: missing fixture reviews for "
        f"{sorted(expected - reviewed)}"
    )
    for item in review["fixtures"]:
        key = (str(item["purpose"]), str(item["doi"]))
        assert key in expected, f"{review_path}: unexpected fixture review {key}"
        assert item["sample_representative"] is True, (
            f"{review_path}: {key} must be marked sample_representative: true"
        )
        assert item["markdown_semantic_reviewed"] is True, (
            f"{review_path}: {key} must be marked markdown_semantic_reviewed: true"
        )
        assert item["assertions"], (
            f"{review_path}: {key} must record semantic assertions"
        )
        baseline_path = REPO_ROOT / item["baseline_markdown_path"]
        assert baseline_path.is_file(), (
            f"{review_path}: {key} baseline_markdown_path must exist"
        )


def _provider_test_paths(provider: str) -> tuple[Path, ...]:
    test_root = REPO_ROOT / "tests" / "unit"
    paths: list[Path] = []
    default_path = test_root / f"test_{provider}_provider.py"
    if default_path.is_file():
        paths.append(default_path)
    for pattern in PROVIDER_TEST_GLOBS.get(provider, ()):
        paths.extend(sorted(test_root.glob(pattern)))
    unique_paths = tuple(dict.fromkeys(path for path in paths if path.is_file()))
    assert unique_paths, (
        f"{provider}: expected provider-local tests under "
        f"{test_root.relative_to(REPO_ROOT)}"
    )
    return unique_paths


def _assertion_mentions_markdown(text: str, pattern: re.Pattern[str]) -> bool:
    return any(
        pattern.search(line) and MARKDOWN_TARGET_PATTERN.search(line)
        for line in text.splitlines()
    )


def _marker_block(text: str, marker: str, *, line_count: int = 80) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if marker in line:
            return "\n".join(lines[index : index + line_count])
    return ""


def test_manifest_provider_tests_enforce_markdown_review_loop_contract() -> None:
    for manifest_path in _manifest_paths():
        manifest = _load_yaml(manifest_path)
        provider = str(manifest["name"])
        _assert_review_artifact(manifest_path, manifest)
        test_paths = _provider_test_paths(provider)

        test_text = "\n".join(path.read_text(encoding="utf-8") for path in test_paths)
        test_labels = ", ".join(path.relative_to(REPO_ROOT).as_posix() for path in test_paths)
        for placeholder in PLACEHOLDER_PATTERNS:
            assert placeholder not in test_text, (
                f"{test_labels} still contains scaffold "
                f"placeholder {placeholder!r}"
            )

        doi_samples = manifest["fixtures"]["doi_samples"]
        assert isinstance(doi_samples, dict)
        markdown_contract = manifest["markdown_contract"]
        assert isinstance(markdown_contract, dict)
        for purpose, sample in doi_samples.items():
            if not isinstance(sample, dict) or not sample.get("doi"):
                continue
            doi = str(sample["doi"])
            marker = MARKDOWN_REVIEW_MARKER_TEMPLATE.format(
                purpose=purpose,
                doi=doi,
            )
            accepted_markers = (marker, str(purpose), doi, _doi_slug(doi))
            assert any(marker in test_text for marker in accepted_markers), (
                f"{test_labels} must name non-null fixture purpose {purpose!r}, "
                f"DOI {doi!r}, or DOI slug {_doi_slug(doi)!r}"
            )
            contract = markdown_contract.get(purpose)
            assert isinstance(contract, dict), (
                f"{manifest_path}: markdown_contract.{purpose} is required "
                "for every non-null DOI sample"
            )
            assert contract.get("doi") == doi, (
                f"{manifest_path}: markdown_contract.{purpose}.doi must match "
                "fixtures.doi_samples"
            )
            assert contract.get("must_include"), (
                f"{manifest_path}: markdown_contract.{purpose}.must_include "
                "must not be empty"
            )
            assert contract.get("must_not_include"), (
                f"{manifest_path}: markdown_contract.{purpose}.must_not_include "
                "must not be empty"
            )

            block = _marker_block(test_text, marker)
            if block:
                assert _assertion_mentions_markdown(
                    block, POSITIVE_ASSERTION_PATTERN
                ), (
                    f"{test_labels} marker {marker!r} must be followed by "
                    "a positive Markdown assertion"
                )
                assert (
                    _assertion_mentions_markdown(block, NEGATIVE_ASSERTION_PATTERN)
                    or _assertion_mentions_markdown(
                        block, COUNT_OR_REGEX_ASSERTION_PATTERN
                    )
                ), (
                    f"{test_labels} marker {marker!r} must be followed by "
                    "a negative, regex, or count Markdown assertion"
                )

        assert _assertion_mentions_markdown(test_text, POSITIVE_ASSERTION_PATTERN), (
            f"{test_labels} must include a positive Markdown "
            "assertion such as assertIn(..., markdown)"
        )
        assert _assertion_mentions_markdown(test_text, NEGATIVE_ASSERTION_PATTERN), (
            f"{test_labels} must include a negative Markdown "
            "assertion such as assertNotIn(..., markdown)"
        )


def test_review_schema_requires_baseline_fields_and_notes() -> None:
    schema = _load_review_schema()
    review = {
        "schema_version": 1,
        "provider": "demo",
        "reviewed_at": "2026-05-20T00:00:00Z",
        "fixtures": [
            {
                "fixture": "tests/fixtures/golden_criteria/demo",
                "purpose": "structure",
                "doi": "10.1000/demo",
                "sample_representative": True,
                "markdown_semantic_reviewed": True,
                "issues": [],
                "assertions": ["must include ## Abstract"],
                "fixes": [],
            }
        ],
    }

    errors = sorted(
        Draft202012Validator(schema).iter_errors(review),
        key=lambda error: error.json_path,
    )

    messages = "\n".join(error.message for error in errors)
    assert "baseline_markdown_path" in messages
    assert "baseline_markdown_sha256" in messages
    assert "review_notes" in messages


def test_review_traceability_rejects_fix_with_missing_issue_id() -> None:
    review = {
        "provider": "demo",
        "fixtures": [
            {
                "purpose": "structure",
                "doi": "10.1000/demo",
                "issues": [{"id": "issue-1", "severity": "low", "summary": "Noise"}],
                "fixes": [
                    {
                        "id": "fix-1",
                        "issue_ids": ["issue-2"],
                        "summary": "Add cleanup",
                        "test_names": ["test_demo_cleanup"],
                    }
                ],
            }
        ],
    }

    assert _traceability_errors(review) == [
        "demo:structure:10.1000/demo: fix 'fix-1' references missing issue id 'issue-2'"
    ]


def test_review_schema_rejects_fix_without_test_names() -> None:
    schema = _load_review_schema()
    review = {
        "schema_version": 1,
        "provider": "demo",
        "reviewed_at": "2026-05-20T00:00:00Z",
        "fixtures": [
            {
                "fixture": "tests/fixtures/golden_criteria/demo",
                "purpose": "structure",
                "doi": "10.1000/demo",
                "baseline_markdown_path": "tests/fixtures/golden_criteria/demo/extracted.md",
                "baseline_markdown_sha256": "a" * 64,
                "review_notes": "Reviewed against fixture replay.",
                "sample_representative": True,
                "markdown_semantic_reviewed": True,
                "issues": [{"id": "issue-1", "severity": "low", "summary": "Noise"}],
                "assertions": ["must include ## Abstract"],
                "fixes": [
                    {
                        "id": "fix-1",
                        "issue_ids": ["issue-1"],
                        "summary": "Add cleanup",
                    }
                ],
            }
        ],
    }

    errors = sorted(
        Draft202012Validator(schema).iter_errors(review),
        key=lambda error: error.json_path,
    )

    assert any("test_names" in error.message for error in errors)

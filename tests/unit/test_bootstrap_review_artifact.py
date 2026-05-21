from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "bootstrap_review_artifact.py"
SCHEMA = REPO_ROOT / "docs" / "ai-onboarding" / "provider-review.schema.json"


def test_bootstrap_review_artifact_writes_schema_valid_draft(tmp_path: Path) -> None:
    manifest_path = tmp_path / "docs" / "ai-onboarding" / "manifests" / "newpub.yml"
    expected_path = (
        tmp_path
        / "tests"
        / "fixtures"
        / "golden_criteria"
        / "10.1234_sample"
        / "expected.json"
    )
    manifest_path.parent.mkdir(parents=True)
    expected_path.parent.mkdir(parents=True)
    expected_path.write_text(
        json.dumps({"markdown": "## Abstract\nBody\n"}) + "\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        """
name: newpub
fixtures:
  doi_samples:
    structure:
      doi: 10.1234/sample
markdown_contract:
  structure:
    doi: 10.1234/sample
    must_include:
      - "## Abstract"
    must_not_include:
      - "Download PDF"
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--provider",
            "newpub",
            "--manifest",
            str(manifest_path.relative_to(tmp_path)),
            "--output-dir",
            str(tmp_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)
    review_path = tmp_path / payload["review_path"]
    review = yaml.safe_load(review_path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    errors = sorted(
        Draft202012Validator(schema).iter_errors(review),
        key=lambda error: error.json_path,
    )
    assert not errors
    fixture = review["fixtures"][0]
    assert fixture["markdown_semantic_reviewed"] is False
    assert fixture["baseline_markdown_path"] == (
        "tests/fixtures/golden_criteria/10.1234_sample/expected.json"
    )
    assert fixture["baseline_markdown_sha256"]
    assert "must include ## Abstract" in fixture["assertions"]
    assert "must not include Download PDF" in fixture["assertions"]

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "onboard_from_manifests.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        check=True,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def test_help_includes_discover() -> None:
    result = run_cli("--help")

    assert "discover" in result.stdout


def test_start_provider_dry_run_writes_dag_and_discover_brief(tmp_path: Path) -> None:
    run_cli(
        "start",
        "--provider",
        "mdpi",
        "--domain",
        "mdpi.com",
        "--dry-run",
        "--output-dir",
        str(tmp_path),
    )

    dag_path = tmp_path / "task-dag.json"
    brief_path = tmp_path / "briefs" / "discover-manifest.yml"
    dag = json.loads(dag_path.read_text(encoding="utf-8"))
    brief = brief_path.read_text(encoding="utf-8")

    assert any(step["id"] == "discover-manifest" for step in dag["steps"])
    assert dag["manifest"] == "docs/ai-onboarding/manifests/mdpi.yml"
    assert brief_path.is_file()
    assert "current_step: discover-manifest" in brief
    assert "output_manifest: docs/ai-onboarding/manifests/mdpi.yml" in brief
    assert "domain: mdpi.com" in brief


def test_discover_prints_brief_with_requested_output_manifest() -> None:
    result = run_cli(
        "discover",
        "--provider",
        "mdpi",
        "--domain",
        "mdpi.com",
        "--output",
        "docs/ai-onboarding/manifests/mdpi.yml",
    )

    assert "task_id: mdpi-discover-manifest" in result.stdout
    assert "current_step: discover-manifest" in result.stdout
    assert "output_manifest: docs/ai-onboarding/manifests/mdpi.yml" in result.stdout


def test_start_manifest_replay_skips_discover_brief(tmp_path: Path) -> None:
    run_cli(
        "start",
        "--manifest",
        "docs/ai-onboarding/manifests/mdpi.yml",
        "--dry-run",
        "--output-dir",
        str(tmp_path),
    )

    dag = json.loads((tmp_path / "task-dag.json").read_text(encoding="utf-8"))
    assert all(step["id"] != "discover-manifest" for step in dag["steps"])
    assert not (tmp_path / "briefs" / "discover-manifest.yml").exists()


def test_onboard_script_does_not_import_llm_sdks() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8").lower()

    assert "anthropic" not in script
    assert "openai" not in script

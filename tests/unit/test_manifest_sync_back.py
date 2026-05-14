from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from ._manifest_sync import (
    REPO_ROOT,
    iter_manifest_cases,
    serialize_bundle_sync_back,
)


def test_manifest_sync_back_round_trips_runtime_bundle_fields(tmp_path: Path) -> None:
    case = next(case for case in iter_manifest_cases() if case.provider == "wiley")
    tmp_manifest = tmp_path / "wiley.yml"
    tmp_manifest.write_text(case.manifest_path.read_text(encoding="utf-8"), encoding="utf-8")

    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "manifest_sync_back.py"),
            "--provider",
            case.provider,
            "--manifest",
            str(tmp_manifest),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )

    summary = json.loads(result.stdout)
    assert summary["status"] == "OK"
    assert summary["provider"] == "wiley"
    assert summary["manifest_path"] == str(tmp_manifest)
    assert "extraction_hints.datalayer_signal_set" in summary["updated_fields"]

    updated = yaml.safe_load(tmp_manifest.read_text(encoding="utf-8"))
    assert isinstance(updated, dict)
    assert updated["extraction_hints"] == serialize_bundle_sync_back(case.bundle)
    assert set(case.manifest["main_path"]) <= set(updated["success_criteria"])
    for step in case.manifest["main_path"]:
        assert updated["success_criteria"][step] is not None

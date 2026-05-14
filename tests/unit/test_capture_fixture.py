from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    values = {
        "doi": "10.1234/example",
        "provider": "examplepub",
        "via": "http",
        "purpose": "structure",
        "dry_run": False,
        "output_dir": str(tmp_path),
        "force": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_capture_fixture_writes_fixture_manifest_and_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_script("capture_fixture")

    class FakeTransport:
        def request(self, method: str, url: str, **kwargs: object) -> dict[str, object]:
            assert method == "GET"
            assert url == "https://doi.org/10.1234/example"
            return {
                "headers": {"content-type": "text/html; charset=utf-8"},
                "body": b"<html><title>Fixture</title></html>",
                "url": "https://publisher.test/article",
                "status_code": 200,
            }

    monkeypatch.setattr(module, "HttpTransport", FakeTransport)

    summary = module.capture_fixture(_args(tmp_path))

    fixture_path = tmp_path / "tests" / "fixtures" / "golden_criteria" / "10.1234_example" / "original.html"
    manifest_path = tmp_path / "tests" / "fixtures" / "golden_criteria" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert fixture_path.read_bytes() == b"<html><title>Fixture</title></html>"
    assert summary["fixture_path"] == "tests/fixtures/golden_criteria/10.1234_example/original.html"
    assert summary["content_type"] == "text/html; charset=utf-8"
    assert summary["bytes"] == len(b"<html><title>Fixture</title></html>")
    assert manifest["samples"]["10.1234_example"]["expected_outcome"] == "pending"
    assert manifest["samples"]["10.1234_example"]["purpose"] == "structure"
    assert manifest["samples"]["10.1234_example"]["assets"]["original.html"] == summary["fixture_path"]


def test_capture_fixture_dry_run_does_not_fetch_or_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_script("capture_fixture")

    class FailingTransport:
        def request(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            raise AssertionError("dry-run must not fetch")

    monkeypatch.setattr(module, "HttpTransport", FailingTransport)

    summary = module.capture_fixture(_args(tmp_path, doi="10.0000/probe", dry_run=True))

    assert summary["dry_run"] is True
    assert summary["bytes"] == 0
    assert summary["would_write"]
    assert not (tmp_path / "tests").exists()


def test_capture_fixture_refuses_to_overwrite_without_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_script("capture_fixture")

    fixture_dir = tmp_path / "tests" / "fixtures" / "golden_criteria" / "10.1234_example"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "original.html").write_text("old", encoding="utf-8")

    class FakeTransport:
        def request(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            return {"headers": {"content-type": "text/html"}, "body": b"new", "url": "https://example.test"}

    monkeypatch.setattr(module, "HttpTransport", FakeTransport)

    with pytest.raises(FileExistsError):
        module.capture_fixture(_args(tmp_path))


def test_capture_fixture_routes_block_purpose_to_block_fixture_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_script("capture_fixture")

    class FakeTransport:
        def request(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            return {"headers": {"content-type": "text/html"}, "body": b"<html>gate</html>", "url": "https://example.test"}

    monkeypatch.setattr(module, "HttpTransport", FakeTransport)

    summary = module.capture_fixture(_args(tmp_path, purpose="access-gate"))

    assert summary["route"] == "block"
    assert (tmp_path / "tests" / "fixtures" / "block" / "10.1234_example" / "original.html").is_file()
    manifest = json.loads((tmp_path / "tests" / "fixtures" / "golden_criteria" / "manifest.json").read_text())
    assert manifest["samples"]["10.1234_example"]["fixture_family"] == "block"

#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
from pathlib import Path
from typing import Any

from paper_fetch.http import HttpTransport
from paper_fetch.publisher_identity import infer_provider_from_doi, normalize_doi


GOLDEN_PURPOSES = {
    "structure",
    "table",
    "formula",
    "figure",
    "supplementary",
    "references",
    "pdf-fallback",
}
BLOCK_PURPOSES = {"abstract-only", "access-gate", "empty-shell"}
PURPOSES = sorted(GOLDEN_PURPOSES | BLOCK_PURPOSES)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def doi_slug(doi: str) -> str:
    return normalize_doi(doi).replace("/", "_")


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"samples": {}}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"manifest root must be an object: {path}")
    samples = manifest.setdefault("samples", {})
    if not isinstance(samples, dict):
        raise ValueError(f"manifest samples must be an object: {path}")
    return manifest


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _content_type(response: dict[str, Any]) -> str:
    headers = response.get("headers") if isinstance(response.get("headers"), dict) else {}
    return str(headers.get("content-type") or headers.get("Content-Type") or "text/html")


def _body_bytes(response: dict[str, Any]) -> bytes:
    body = response.get("body", b"")
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    raise TypeError("HttpTransport response body must be bytes or str")


def _extension_for(content_type: str, purpose: str) -> str:
    normalized = content_type.lower()
    if purpose == "pdf-fallback" or "application/pdf" in normalized:
        return "pdf"
    if "xml" in normalized:
        return "xml"
    return "html"


def _fixture_family(purpose: str) -> str:
    return "block" if purpose in BLOCK_PURPOSES else "golden"


def _fixture_path(root: Path, slug: str, purpose: str, content_type: str) -> Path:
    family = _fixture_family(purpose)
    if family == "block":
        return root / "tests" / "fixtures" / "block" / slug / "original.html"
    filename = f"original.{_extension_for(content_type, purpose)}"
    return root / "tests" / "fixtures" / "golden_criteria" / slug / filename


def _manifest_entry(
    *,
    doi: str,
    provider: str,
    source_url: str,
    fetched_at: str,
    purpose: str,
    fixture_path: Path,
    root: Path,
    content_type: str,
) -> dict[str, Any]:
    family = _fixture_family(purpose)
    route_kind = "pdf_fallback" if purpose == "pdf-fallback" else ("block" if family == "block" else _extension_for(content_type, purpose))
    asset_name = fixture_path.name
    return {
        "doi": doi,
        "publisher": provider,
        "source_url": source_url,
        "fetched_at": fetched_at,
        "purpose": purpose,
        "expected_outcome": "pending",
        "fixture_family": family,
        "content_type": content_type,
        "route_kind": route_kind,
        "origin_kind": "real_replay",
        "usage_kind": "content",
        "assets": {
            asset_name: fixture_path.relative_to(root).as_posix(),
        },
    }


def _capture_http(doi: str) -> dict[str, Any]:
    url = f"https://doi.org/{doi}"
    return HttpTransport().request(
        "GET",
        url,
        headers={"Accept": "text/html,application/xhtml+xml,application/xml,application/pdf;q=0.9,*/*;q=0.8"},
        retry_on_transient=True,
    )


def capture_fixture(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.output_dir).resolve()
    doi = normalize_doi(args.doi)
    slug = doi_slug(doi)
    provider = args.provider or infer_provider_from_doi(doi) or "unknown"
    source_url = f"https://doi.org/{doi}"

    if args.via != "http":
        raise NotImplementedError(f"--via {args.via} is not implemented yet")

    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if args.dry_run:
        content_type = "text/html"
        body = b""
        final_url = source_url
    else:
        response = _capture_http(doi)
        content_type = _content_type(response)
        body = _body_bytes(response)
        final_url = str(response.get("url") or source_url)

    fixture_path = _fixture_path(root, slug, args.purpose, content_type)
    manifest_path = root / "tests" / "fixtures" / "golden_criteria" / "manifest.json"
    manifest = _load_manifest(manifest_path)
    samples = manifest["samples"]
    exists = fixture_path.exists() or slug in samples
    if exists and not args.force:
        raise FileExistsError(f"refusing to overwrite existing fixture or manifest sample: {slug}")

    entry = _manifest_entry(
        doi=doi,
        provider=provider,
        source_url=final_url,
        fetched_at=fetched_at,
        purpose=args.purpose,
        fixture_path=fixture_path,
        root=root,
        content_type=content_type,
    )
    summary = {
        "doi": doi,
        "dry_run": bool(args.dry_run),
        "fixture_path": fixture_path.relative_to(root).as_posix(),
        "manifest_sample_id": slug,
        "manifest_entry": entry,
        "content_type": content_type,
        "bytes": len(body),
        "route": entry["route_kind"],
        "purpose": args.purpose,
    }

    if args.dry_run:
        summary["would_write"] = [summary["fixture_path"], "tests/fixtures/golden_criteria/manifest.json"]
        return summary

    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_bytes(body)
    samples[slug] = entry
    _write_manifest(manifest_path, manifest)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture a DOI replay fixture and register it in the golden manifest.")
    parser.add_argument("--doi", required=True, help="DOI to capture, for example 10.1234/sample")
    parser.add_argument("--provider", help="provider name; defaults to DOI/catalog inference")
    parser.add_argument("--via", choices=("http", "playwright", "flaresolverr"), default="http")
    parser.add_argument("--purpose", choices=PURPOSES, required=True)
    parser.add_argument("--dry-run", action="store_true", help="print planned writes without fetching or writing")
    parser.add_argument("--output-dir", default=_repo_root(), help="repo root to write into; defaults to this checkout")
    parser.add_argument("--force", action="store_true", help="overwrite existing fixture and manifest sample")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        summary = capture_fixture(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

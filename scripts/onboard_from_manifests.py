#!/usr/bin/env python3
"""Generate provider onboarding task DAGs and worker briefs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PROVIDER_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
SCHEMA_PATH = "docs/ai-onboarding/provider-manifest.schema.json"
HARD_CONSTRAINTS_PATH = "docs/ai-onboarding/hard-constraints.md"
DISCOVER_STEP = "discover-manifest"
ROUTING_REQUIREMENTS = [
    "doi_prefixes",
    "domains",
    "domain_suffixes",
    "crossref_publisher",
]
DOI_SAMPLE_PURPOSES = [
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
FILES_MUST_NOT_MODIFY = [
    "src/",
    "tests/",
    "docs/providers.md",
    "CHANGELOG.md",
]


def _provider_slug(provider: str) -> str:
    slug = provider.strip().lower()
    if not slug:
        raise ValueError("provider must not be empty")
    if not PROVIDER_RE.fullmatch(slug):
        raise ValueError("provider must be snake_case starting with a lowercase letter")
    return slug


def default_manifest_path(provider: str) -> str:
    return f"docs/ai-onboarding/manifests/{_provider_slug(provider)}.yml"


def build_discover_brief(
    *,
    provider: str,
    domain: str | None,
    doi_prefix: str | None,
    output_manifest: str,
) -> dict[str, Any]:
    """Build the worker input for the manifest discovery task."""
    provider_name = _provider_slug(provider)
    return {
        "task_id": f"{provider_name}-{DISCOVER_STEP}",
        "current_step": DISCOVER_STEP,
        "runtime": "coding-agent-subagent",
        "provider_seed": {
            "name": provider_name,
            "domain": domain,
            "doi_prefix_hint": doi_prefix,
        },
        "output_manifest": output_manifest,
        "schema": SCHEMA_PATH,
        "hard_constraints": HARD_CONSTRAINTS_PATH,
        "search_requirements": {
            "routing": ROUTING_REQUIREMENTS,
            "doi_sample_purposes": DOI_SAMPLE_PURPOSES,
        },
        "output_requirements": {
            "generation_generated_by": "ai_discovery",
            "doi_sample_evidence_keys": [
                "doi",
                "evidence_url",
                "evidence_reason",
                "observed_signals",
                "confidence",
            ],
            "required_non_null_sample_purposes": [
                "structure",
                "figure",
                "references",
            ],
            "retry_error_code": "UNSUITABLE_DOI_SAMPLE",
        },
        "files_allowed_to_modify": [output_manifest],
        "files_must_not_modify": FILES_MUST_NOT_MODIFY,
        "no_commit": True,
    }


def build_dag(*, provider: str | None, manifest: str | None, include_discovery: bool) -> dict[str, Any]:
    provider_name = _provider_slug(provider) if provider else None
    steps: list[dict[str, Any]] = []
    if include_discovery:
        steps.append(
            {
                "id": DISCOVER_STEP,
                "type": "worker-brief",
                "brief": "briefs/discover-manifest.yml",
                "produces": [default_manifest_path(provider_name or "")],
            }
        )
    steps.extend(
        [
            {"id": "validate-manifest", "type": "coordinator-check"},
            {"id": "capture-fixtures", "type": "coordinator-action"},
            {"id": "scaffold", "type": "coordinator-action"},
            {"id": "implement-provider", "type": "worker-brief"},
            {"id": "merge-ready", "type": "coordinator-check"},
        ]
    )
    return {
        "provider": provider_name,
        "manifest": manifest,
        "dry_run": True,
        "steps": steps,
    }


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if any(char in text for char in [":", "#", "{", "}", "[", "]", ",", "&", "*", "!", "|", ">", "'", '"']):
        return json.dumps(text)
    if text.lower() in {"null", "true", "false", "yes", "no"}:
        return json.dumps(text)
    return text


def to_yaml(data: Any, *, indent: int = 0) -> str:
    lines: list[str] = []
    prefix = " " * indent
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.append(to_yaml(value, indent=indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(value)}")
    elif isinstance(data, list):
        if not data:
            lines.append(f"{prefix}[]")
        for item in data:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.append(to_yaml(item, indent=indent + 2))
            else:
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
    else:
        lines.append(f"{prefix}{_yaml_scalar(data)}")
    return "\n".join(lines)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_discover(args: argparse.Namespace) -> int:
    brief = build_discover_brief(
        provider=args.provider,
        domain=args.domain,
        doi_prefix=args.doi_prefix,
        output_manifest=args.output,
    )
    print(to_yaml(brief))
    return 0


def run_start(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    if not args.dry_run:
        raise SystemExit("start currently supports --dry-run only")

    if args.manifest:
        dag = build_dag(provider=None, manifest=args.manifest, include_discovery=False)
        write_text(output_dir / "task-dag.json", json.dumps(dag, indent=2, sort_keys=True) + "\n")
        return 0

    output_manifest = default_manifest_path(args.provider)
    brief = build_discover_brief(
        provider=args.provider,
        domain=args.domain,
        doi_prefix=args.doi_prefix,
        output_manifest=output_manifest,
    )
    dag = build_dag(provider=args.provider, manifest=output_manifest, include_discovery=True)
    write_text(output_dir / "task-dag.json", json.dumps(dag, indent=2, sort_keys=True) + "\n")
    write_text(output_dir / "briefs" / "discover-manifest.yml", to_yaml(brief) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate manifest-driven provider onboarding dry-run artifacts."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser(
        "discover",
        help="print a manifest discovery worker brief",
    )
    discover.add_argument("--provider", required=True, help="provider name seed")
    discover.add_argument("--domain", help="provider domain seed")
    discover.add_argument("--doi-prefix", help="DOI prefix seed")
    discover.add_argument(
        "--output",
        required=True,
        help="manifest path the discovery worker is allowed to write",
    )
    discover.set_defaults(func=run_discover)

    start = subparsers.add_parser(
        "start",
        help="write a dry-run onboarding DAG and worker briefs",
    )
    source = start.add_mutually_exclusive_group(required=True)
    source.add_argument("--provider", help="provider name seed")
    source.add_argument("--manifest", help="existing manifest path for replay mode")
    start.add_argument("--domain", help="provider domain seed")
    start.add_argument("--doi-prefix", help="DOI prefix seed")
    start.add_argument("--dry-run", action="store_true", help="write planned artifacts only")
    start.add_argument("--output-dir", required=True, help="directory for dry-run artifacts")
    start.set_defaults(func=run_start)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

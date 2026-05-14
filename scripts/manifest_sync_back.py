#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must load as a mapping")
    return data


def _known_manifest_path(root: Path, provider: str) -> Path:
    known_path = root / "docs" / "ai-onboarding" / "known-providers.yml"
    data = _load_yaml(known_path)
    providers = data.get("providers")
    if not isinstance(providers, list):
        raise ValueError(f"{known_path}: providers must be a list")
    for entry in providers:
        if not isinstance(entry, Mapping) or entry.get("name") != provider:
            continue
        manifest_path = entry.get("manifest_path")
        if manifest_path is None:
            raise ValueError(f"{provider}: known provider entry has no manifest_path")
        return root / str(manifest_path)
    raise ValueError(f"{provider}: provider is not listed in known-providers.yml")


def _provider_bundle(provider: str) -> Any:
    import paper_fetch.providers  # noqa: F401
    from paper_fetch.providers._registry import provider_bundle

    return provider_bundle(provider)


def serialize_bundle_sync_back(bundle: Any) -> dict[str, Any]:
    rules = bundle.html_rules
    availability = rules.availability if rules is not None else None
    return {
        "datalayer_signal_set": serialize_datalayer_signal_set(
            availability.datalayer_signal_set if availability is not None else None
        ),
        "text_marker_signal_set": serialize_text_marker_signal_set(
            availability.text_marker_signal_set if availability is not None else None
        ),
        "front_matter": serialize_front_matter_rules(
            rules.front_matter if rules is not None else None
        ),
        "asset_retry": serialize_asset_retry(bundle.asset_retry),
        "metadata_merge": serialize_metadata_merge(bundle.metadata_merge),
    }


def serialize_datalayer_signal_set(signal_set: Any) -> dict[str, Any] | None:
    if signal_set is None:
        return None
    schema = signal_set.schema
    return {
        "schema": {
            "provider": schema.provider,
            "pattern": schema.pattern.pattern,
            "fields": {
                field: [list(path) for path in paths]
                for field, paths in sorted(schema.fields.items())
            },
            "required_fields": list(schema.required_fields),
        },
        "blocking_rules": [
            _serialize_datalayer_rule(rule) for rule in signal_set.blocking_rules
        ],
        "strong_rules": [
            _serialize_datalayer_rule(rule) for rule in signal_set.strong_rules
        ],
        "soft_rules": [
            _serialize_datalayer_rule(rule) for rule in signal_set.soft_rules
        ],
        "abstract_only_rules": [
            _serialize_datalayer_rule(rule)
            for rule in signal_set.abstract_only_rules
        ],
        "presence_rules": [
            {"field": field, "token": token}
            for field, token in signal_set.presence_rules
        ],
    }


def _serialize_datalayer_rule(rule: Any) -> dict[str, Any]:
    if hasattr(rule, "match"):
        return {
            "kind": "field_match",
            "match": _serialize_datalayer_match(rule.match),
            "token": rule.token,
        }
    if hasattr(rule, "matches"):
        return {
            "kind": "combo",
            "matches": [_serialize_datalayer_match(match) for match in rule.matches],
            "token": rule.token,
        }
    return {
        "kind": "contains",
        "field": rule.field,
        "substring": rule.substring,
        "token": rule.token,
    }


def _serialize_datalayer_match(match: Any) -> dict[str, Any]:
    return {
        "field": match.field,
        "expected": match.expected,
        "negate": bool(match.negate),
    }


def serialize_text_marker_signal_set(signal_set: Any) -> dict[str, Any] | None:
    if signal_set is None:
        return None
    return {
        "blocking_markers": _sorted_marker_rules(signal_set.blocking_rules),
        "positive_strong": _sorted_marker_rules(signal_set.strong_rules),
        "positive_soft": _sorted_marker_rules(signal_set.soft_rules),
        "abstract_only": _sorted_marker_rules(signal_set.abstract_only_rules),
    }


def _sorted_marker_rules(rules: Any) -> list[dict[str, Any]]:
    serialized = [_serialize_text_marker_rule(rule) for rule in rules]
    return sorted(
        serialized,
        key=lambda item: (
            item["substring"],
            item["token"],
            item["negate"],
            item["contains"],
            item["absent"],
            item["access_gate_context"],
        ),
    )


def _serialize_text_marker_rule(rule: Any) -> dict[str, Any]:
    return {
        "substring": rule.substring,
        "token": rule.token,
        "negate": bool(rule.negate),
        "contains": list(rule.contains),
        "absent": list(rule.absent),
        "access_gate_context": bool(rule.access_gate_context),
    }


def serialize_front_matter_rules(rules: Any) -> dict[str, Any] | None:
    if rules is None:
        return None
    return {
        "exact_texts": list(rules.exact_texts),
        "contains_tokens": list(rules.contains_tokens),
        "publication_keywords": list(rules.publication_keywords),
    }


def serialize_asset_retry(policy: Any) -> dict[str, Any] | None:
    if policy is None:
        return None
    return {
        "name": policy.name,
        "key_fn": callable_path(policy.key_fn),
        "retryable_failure": callable_path(policy.retryable_failure),
        "failure_match": callable_path(policy.failure_match),
    }


def serialize_metadata_merge(rules: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index, rule in enumerate(rules or ()):
        for strategy in (
            "fill_empty",
            "overwrite",
            "concat_unique",
            "take_first_non_empty",
        ):
            for field in getattr(rule, strategy):
                entries.append(
                    {
                        "field": field,
                        "strategy": strategy,
                        "rule_index": index,
                    }
                )
    return sorted(
        entries,
        key=lambda item: (item["field"], item["strategy"], item["rule_index"]),
    )


def callable_path(value: Callable[..., Any] | None) -> str | None:
    if value is None:
        return None
    return f"{value.__module__}:{value.__qualname__}"


def sync_manifest(path: Path, *, provider: str) -> dict[str, Any]:
    manifest = _load_yaml(path)
    manifest_provider = str(manifest.get("name") or "")
    if manifest_provider != provider:
        raise ValueError(
            f"manifest provider mismatch: expected {provider!r}, got {manifest_provider!r}"
        )

    bundle = _provider_bundle(provider)
    sync_back = serialize_bundle_sync_back(bundle)
    extraction_hints = manifest.setdefault("extraction_hints", {})
    if not isinstance(extraction_hints, dict):
        raise ValueError("manifest extraction_hints must be a mapping")
    changed_fields: list[str] = []
    for field_name, value in sync_back.items():
        if extraction_hints.get(field_name) != value:
            changed_fields.append(f"extraction_hints.{field_name}")
        extraction_hints[field_name] = value

    success_criteria = manifest.setdefault("success_criteria", {})
    if not isinstance(success_criteria, dict):
        raise ValueError("manifest success_criteria must be a mapping")
    for step in manifest.get("main_path") or ():
        if success_criteria.get(step) is None:
            success_criteria[step] = {}
            changed_fields.append(f"success_criteria.{step}")

    path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return {
        "status": "OK",
        "provider": provider,
        "manifest_path": str(path),
        "updated_fields": changed_fields,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serialize runtime ProviderBundle sync-back fields into a manifest."
    )
    parser.add_argument("--provider", required=True, help="provider name")
    parser.add_argument("--manifest", help="manifest YAML path; defaults via known-providers.yml")
    parser.add_argument(
        "--output-dir",
        default=_repo_root(),
        help="repo root used to resolve known-providers.yml when --manifest is omitted",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.output_dir).resolve()
    manifest_path = (
        Path(args.manifest).resolve()
        if args.manifest
        else _known_manifest_path(root, args.provider)
    )
    try:
        summary = sync_manifest(manifest_path, provider=args.provider)
    except Exception as exc:
        print(
            json.dumps(
                {"status": "ERROR", "provider": args.provider, "reason": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

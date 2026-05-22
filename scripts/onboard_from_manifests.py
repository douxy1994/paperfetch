#!/usr/bin/env python3
"""Generate provider onboarding task DAGs and worker briefs."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, NamedTuple

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _structured_errors import ToolError, emit_error, error_payload  # noqa: E402


PROVIDER_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
SCHEMA_PATH = "onboarding/provider-manifest.schema.json"
ACCESS_REVIEW_SCHEMA_PATH = "onboarding/access-review.schema.json"
HARD_CONSTRAINTS_PATH = "onboarding/hard-constraints.md"
FAILURE_RECOVERY_PATH = "onboarding/failure-recovery.md"
STATE_SCHEMA_PATH = "onboarding/onboarding-state.schema.json"
DEFAULT_STATE_PATH = "onboarding/onboarding-state.json"
AGENT_CLI_ENV = "PROVIDER_ONBOARDING_AGENT_CLI"
ACCESS_PREFLIGHT_STEP = "operator-access-preflight"
DISCOVER_STEP = "discover-manifest"
IMPLEMENT_STEP = "implement-provider"
PROPOSE_CLEANING_STEP = "propose-cleaning-chain"
SHARED_INTEGRATION_STEP = "shared-integration"
SNAPSHOT_EXPECTED_STEP = "snapshot-expected"
CLEANING_PROPOSAL_DIR = "onboarding/cleaning-chain-proposals"
MAX_WORKER_RETRIES = 3
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
SHARED_FILES_MUST_NOT_MODIFY = [
    "onboarding/known-providers.yml",
    "docs/providers.md",
    "docs/extraction-rules.md",
    "CHANGELOG.md",
]
CENTRAL_PROVIDER_LOGIC_PATHS = [
    "src/paper_fetch/extraction/html/provider_rules.py",
    "src/paper_fetch/quality/html_signals.py",
    "src/paper_fetch/quality/html_availability.py",
]


class CoordinatorArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        emit_error(
            error_payload(
                "TASK_BRIEF_INVALID",
                message,
                provider=None,
                manifest=None,
                task_id="coordinator-parse-args",
                retryable=False,
                details={"reason": message},
            )
        )
        raise SystemExit(2)


class DagStep(NamedTuple):
    id: str
    type: str
    owner: str
    brief: str | None = None
    command: tuple[str, ...] = ()


TASK_DAG: tuple[DagStep, ...] = (
    DagStep(
        id=ACCESS_PREFLIGHT_STEP,
        type="operator-gate",
        owner="operator",
    ),
    DagStep(
        id=DISCOVER_STEP,
        type="worker-brief",
        owner="coordinator-subagent",
        brief="briefs/discover-manifest.yml",
    ),
    DagStep(id="validate-manifest", type="coordinator-check", owner="coordinator"),
    DagStep(id="capture-fixtures", type="coordinator-action", owner="coordinator"),
    DagStep(id=PROPOSE_CLEANING_STEP, type="coordinator-action", owner="coordinator"),
    DagStep(id="scaffold", type="coordinator-action", owner="coordinator"),
    DagStep(
        id=IMPLEMENT_STEP,
        type="worker-brief",
        owner="coordinator-subagent",
        brief="briefs/implement-provider.yml",
    ),
    DagStep(id=SHARED_INTEGRATION_STEP, type="coordinator-action", owner="coordinator"),
    DagStep(id=SNAPSHOT_EXPECTED_STEP, type="coordinator-action", owner="coordinator"),
    DagStep(id="manifest-sync-back", type="coordinator-action", owner="coordinator"),
    DagStep(id="provider-local-acceptance", type="coordinator-check", owner="coordinator"),
    DagStep(id="global-lint", type="coordinator-check", owner="coordinator"),
    DagStep(id="merge-ready", type="coordinator-action", owner="coordinator"),
)


class OnboardingSource(NamedTuple):
    provider: str
    manifest: str
    include_discovery: bool
    manifest_yaml: str | None


def _provider_slug(provider: str) -> str:
    slug = provider.strip().lower()
    if not slug:
        raise ValueError("provider must not be empty")
    if not PROVIDER_RE.fullmatch(slug):
        raise ValueError("provider must be snake_case starting with a lowercase letter")
    return slug


def default_manifest_path(provider: str) -> str:
    return f"onboarding/manifests/{_provider_slug(provider)}.yml"


def default_access_review_path(provider: str) -> str:
    return f"onboarding/access-reviews/{_provider_slug(provider)}.yml"


def default_cleaning_proposal_path(provider: str) -> str:
    return f"{CLEANING_PROPOSAL_DIR}/{_provider_slug(provider)}.yml"


def default_cleaning_evidence_path(provider: str) -> str:
    return f"{CLEANING_PROPOSAL_DIR}/{_provider_slug(provider)}.evidence.yml"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json_schema(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(
            "TASK_BRIEF_INVALID",
            f"schema cannot be loaded: {path}",
            retryable=False,
            task_id="coordinator-load-schema",
            details={"path": path.as_posix(), "reason": str(exc)},
        ) from exc
    if not isinstance(data, dict):
        raise ToolError(
            "TASK_BRIEF_INVALID",
            f"schema root must be an object: {path}",
            retryable=False,
            task_id="coordinator-load-schema",
            details={"path": path.as_posix()},
        )
    return data


def _load_access_review(provider: str) -> dict[str, Any]:
    provider_name = _provider_slug(provider)
    path = _repo_root() / default_access_review_path(provider_name)
    if not path.exists():
        raise ToolError(
            "ACCESS_REVIEW_NOT_FOUND",
            "Operator access review is required before discovery.",
            retryable=False,
            provider=provider_name,
            manifest=default_manifest_path(provider_name),
            task_id=f"{provider_name}-{ACCESS_PREFLIGHT_STEP}",
            details={
                "path": path.relative_to(_repo_root()).as_posix(),
                "required_before": DISCOVER_STEP,
            },
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ToolError(
            "ACCESS_REVIEW_SCHEMA_INVALID",
            "Access review YAML is invalid.",
            retryable=False,
            provider=provider_name,
            manifest=default_manifest_path(provider_name),
            task_id=f"{provider_name}-{ACCESS_PREFLIGHT_STEP}",
            details={"path": path.relative_to(_repo_root()).as_posix(), "reason": str(exc)},
        ) from exc
    if not isinstance(data, dict):
        raise ToolError(
            "ACCESS_REVIEW_SCHEMA_INVALID",
            "Access review root must be an object.",
            retryable=False,
            provider=provider_name,
            manifest=default_manifest_path(provider_name),
            task_id=f"{provider_name}-{ACCESS_PREFLIGHT_STEP}",
            details={"path": path.relative_to(_repo_root()).as_posix()},
        )
    return data


def validate_access_review(provider: str) -> dict[str, Any]:
    provider_name = _provider_slug(provider)
    review = _load_access_review(provider_name)
    schema_path = _repo_root() / ACCESS_REVIEW_SCHEMA_PATH
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise ToolError(
            "ACCESS_REVIEW_SCHEMA_INVALID",
            "Access review schema validation dependency is missing.",
            retryable=False,
            provider=provider_name,
            manifest=default_manifest_path(provider_name),
            task_id=f"{provider_name}-{ACCESS_PREFLIGHT_STEP}",
            details={"reason": str(exc)},
        ) from exc
    schema = _load_json_schema(schema_path)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(review), key=lambda error: error.json_path)
    if errors:
        error = errors[0]
        raise ToolError(
            "ACCESS_REVIEW_SCHEMA_INVALID",
            "Access review failed schema validation.",
            retryable=False,
            provider=provider_name,
            manifest=default_manifest_path(provider_name),
            task_id=f"{provider_name}-{ACCESS_PREFLIGHT_STEP}",
            details={
                "path": default_access_review_path(provider_name),
                "field": error.json_path,
                "reason": error.message,
            },
        )
    if review.get("provider") != provider_name:
        raise ToolError(
            "ACCESS_REVIEW_SCHEMA_INVALID",
            "Access review provider must match the onboarding provider.",
            retryable=False,
            provider=provider_name,
            manifest=default_manifest_path(provider_name),
            task_id=f"{provider_name}-{ACCESS_PREFLIGHT_STEP}",
            details={
                "path": default_access_review_path(provider_name),
                "field": "$.provider",
                "expected": provider_name,
                "actual": review.get("provider"),
            },
        )
    if review.get("status") == "blocked" or review.get("may_continue") is not True:
        raise ToolError(
            "ACCESS_REVIEW_NOT_APPROVED",
            "Operator access review does not allow provider onboarding to continue.",
            retryable=False,
            provider=provider_name,
            manifest=default_manifest_path(provider_name),
            task_id=f"{provider_name}-{ACCESS_PREFLIGHT_STEP}",
            details={
                "path": default_access_review_path(provider_name),
                "status": review.get("status"),
                "may_continue": review.get("may_continue"),
            },
        )
    return review


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ToolError(
            "MANIFEST_NOT_FOUND",
            "Provider manifest was not found.",
            retryable=False,
            manifest=path.as_posix(),
            task_id="start-validate-manifest",
            details={"path": path.as_posix()},
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ToolError(
            "MANIFEST_SCHEMA_INVALID",
            "Manifest YAML is invalid.",
            retryable=False,
            manifest=path.as_posix(),
            task_id="start-validate-manifest",
            details={"reason": str(exc)},
        ) from exc
    if not isinstance(data, dict):
        raise ToolError(
            "MANIFEST_SCHEMA_INVALID",
            "Manifest root must be a mapping.",
            retryable=False,
            manifest=path.as_posix(),
            task_id="start-validate-manifest",
            details={"path": path.as_posix()},
        )
    return data


def _manifest_source(path_value: str) -> OnboardingSource:
    manifest_path = Path(path_value)
    if not manifest_path.is_absolute():
        manifest_path = _repo_root() / manifest_path
    manifest = _read_manifest(manifest_path)
    provider_value = manifest.get("name")
    if not isinstance(provider_value, str):
        raise ToolError(
            "MANIFEST_SCHEMA_INVALID",
            "Manifest must contain string name.",
            retryable=False,
            manifest=path_value,
            task_id="start-validate-manifest",
            details={"field": "name", "expected": "string"},
        )
    provider = _provider_slug(provider_value)
    manifest_yaml = manifest_path.read_text(encoding="utf-8")
    return OnboardingSource(
        provider=provider,
        manifest=path_value,
        include_discovery=False,
        manifest_yaml=manifest_yaml,
    )


def _provider_source(
    *,
    provider: str,
    domain: str | None,
    doi_prefix: str | None,
) -> OnboardingSource:
    del domain, doi_prefix
    provider_name = _provider_slug(provider)
    return OnboardingSource(
        provider=provider_name,
        manifest=default_manifest_path(provider_name),
        include_discovery=True,
        manifest_yaml=None,
    )


def build_discover_brief(
    *,
    provider: str,
    domain: str | None,
    doi_prefix: str | None,
    output_manifest: str,
) -> dict[str, Any]:
    """Build the worker input for the manifest discovery task."""
    provider_name = _provider_slug(provider)
    access_review = default_access_review_path(provider_name)
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
        "access_review": access_review,
        "access_policy_constraints": {
            "source": access_review,
            "operator_gate": ACCESS_PREFLIGHT_STEP,
            "worker_must_not_infer_access_policy": True,
            "discovery_may_only_use_review_as_constraints": True,
        },
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


def _implementation_allowed_files(provider: str, manifest: str) -> list[str]:
    provider_name = _provider_slug(provider)
    return [
        manifest,
        f"src/paper_fetch/providers/{provider_name}.py",
        f"src/paper_fetch/providers/_{provider_name}_html.py",
        f"tests/unit/test_{provider_name}_provider.py",
        f"onboarding/reviews/{provider_name}.yml",
    ]


def _implementation_forbidden_files() -> list[str]:
    return [
        *SHARED_FILES_MUST_NOT_MODIFY,
        "src/paper_fetch/provider_catalog.py",
        *CENTRAL_PROVIDER_LOGIC_PATHS,
    ]


def _compact_cleaning_proposal_for_brief(provider: str) -> dict[str, Any]:
    provider_name = _provider_slug(provider)
    proposal_ref = default_cleaning_proposal_path(provider_name)
    evidence_ref = default_cleaning_evidence_path(provider_name)
    path = _repo_root() / proposal_ref
    base = {
        "artifact": proposal_ref,
        "evidence_artifact": evidence_ref,
        "producer_task": PROPOSE_CLEANING_STEP,
    }
    if not path.exists():
        return {
            **base,
            "status": "missing",
            "action": f"run python3 scripts/propose_cleaning_chain.py --provider {provider_name} --write",
        }
    try:
        proposal = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return {**base, "status": "invalid_yaml", "error": str(exc)}
    if not isinstance(proposal, dict):
        return {**base, "status": "invalid_shape", "error": "proposal root is not a mapping"}
    if proposal.get("schema_version") != 2:
        return {
            **base,
            "status": "legacy_schema",
            "schema_version": proposal.get("schema_version"),
            "action": f"rerun {PROPOSE_CLEANING_STEP} before implementation",
        }
    return {"status": "ready", "producer_task": PROPOSE_CLEANING_STEP, **proposal}


def build_implementation_brief(
    *,
    provider: str,
    manifest: str,
    manifest_yaml: str | None = None,
) -> dict[str, Any]:
    """Build the worker input for provider implementation."""
    provider_name = _provider_slug(provider)
    access_review = default_access_review_path(provider_name)
    brief: dict[str, Any] = {
        "task_id": f"{provider_name}-{IMPLEMENT_STEP}",
        "provider_manifest": manifest,
        "current_step": IMPLEMENT_STEP,
        "runtime": "coding-agent-subagent",
        "access_review": access_review,
        "access_policy_constraints": {
            "source": access_review,
            "must_follow_operator_review": True,
            "do_not_auto_login": True,
            "do_not_solve_captcha": True,
            "do_not_bypass_paywall_or_challenge": True,
            "challenge_or_permission_uncertainty": "stop_and_report",
        },
        "upstream_artifacts": {
            "task_dag": "task-dag.json",
            "capture_commands": f"onboarding/capture-commands/{provider_name}.txt",
            "cleaning_proposal": default_cleaning_proposal_path(provider_name),
            "cleaning_proposal_evidence": default_cleaning_evidence_path(provider_name),
            "scaffold_summary": f"onboarding/scaffold/{provider_name}.json",
        },
        "cleaning_proposal": _compact_cleaning_proposal_for_brief(provider_name),
        "hard_constraints": HARD_CONSTRAINTS_PATH,
        "markdown_review_loop": {
            "required": True,
            "fixture_source": (
                "provider_manifest.fixtures.doi_samples + "
                "provider_manifest.extra_fixtures"
            ),
            "route_contract_source": "provider_manifest.route_contract",
            "markdown_contract_source": "provider_manifest.markdown_contract",
            "require_each_non_null_purpose_asserted": True,
            "require_positive_and_negative_markdown_assertions": True,
            "forbid_skipped_scaffold_placeholder": True,
        },
        "coordinator_integration_scope": {
            "route_sources": (
                "provider_manifest.route_sources maps main_path steps to "
                "runtime sources."
            ),
            "extra_fixtures": (
                "provider_manifest.extra_fixtures extends capture and Markdown "
                "review beyond fixed purpose slots."
            ),
            "post_worker_integrations": [
                "golden corpus adapter wiring",
                "runtime source/schema registration",
                "manifest/bundle sync-back",
            ],
        },
        "output_requirements": {
            "review_artifact": f"onboarding/reviews/{provider_name}.yml",
            "reviewed_fixtures": (
                "one entry per non-null provider_manifest.fixtures.doi_samples "
                "purpose and per provider_manifest.extra_fixtures item"
            ),
            "reviewed_fixture_fields": [
                "fixture",
                "purpose",
                "issue",
                "assertion",
                "fix",
            ],
        },
        "acceptance": {
            "pytest": [
                f"PYTHONPATH=src python3 -m pytest tests/unit/test_{provider_name}_provider.py -q",
                "PYTHONPATH=src python3 -m pytest "
                "tests/unit/test_provider_markdown_review_contract.py -q",
                "PYTHONPATH=src python3 -m pytest "
                "tests/unit/test_provider_route_contract.py -q",
                "PYTHONPATH=src python3 -m pytest "
                "tests/unit/test_provider_bundle_completeness.py "
                "tests/unit/test_provider_owner_reuse.py -q",
            ],
            "grep_must_be_empty": [
                {
                    "pattern": provider_name,
                    "paths": CENTRAL_PROVIDER_LOGIC_PATHS,
                }
            ],
            "cleaning_contract_gate": [
                f"python3 scripts/onboard_from_manifests.py check-cleaning-proposal --provider {provider_name}",
                f"python3 scripts/propose_cleaning_chain.py --provider {provider_name} --check-contract",
            ],
            "live_review": {
                "required_for_browser_or_cdn_risk": _provider_requires_live_review(provider_name),
                "command": (
                    "PAPER_FETCH_RUN_LIVE=1 python3 "
                    f"scripts/run_golden_criteria_live_review.py --providers {provider_name}"
                ),
                "source_contract": "provider_manifest.route_sources",
                "markdown_contract": "provider_manifest.markdown_contract",
            },
        },
        "files_allowed_to_modify": _implementation_allowed_files(provider_name, manifest),
        "files_must_not_modify": _implementation_forbidden_files(),
        "failure_recovery": {
            "policy": FAILURE_RECOVERY_PATH,
            "max_retries": MAX_WORKER_RETRIES,
            "forbidden_write_code": "WORKER_MODIFIED_FORBIDDEN_FILE",
            "acceptance_failure_retry_task": IMPLEMENT_STEP,
            "blocked_after_retry_exhaustion": True,
        },
        "manifest_adjustment_policy": {
            "allowed_only_for_failure_code": "MARKDOWN_CONTRACT_DRIFT",
            "allowed_path": manifest,
            "allowed_fields": ["markdown_contract.<purpose>"],
            "forbidden_fields": [
                "routing",
                "main_path",
                "route_contract",
                "fixtures",
                "extra_fixtures",
                "probe",
                "access_policy",
            ],
            "must_match_current_provider": provider_name,
        },
        "no_commit": True,
    }
    if manifest_yaml is not None:
        brief["manifest_yaml"] = manifest_yaml
    return brief


def build_dag(
    *,
    provider: str | None,
    manifest: str | None,
    include_discovery: bool,
    dry_run: bool,
) -> dict[str, Any]:
    provider_name = _provider_slug(provider) if provider else None
    steps: list[dict[str, Any]] = []
    previous_step: str | None = None
    for step in TASK_DAG:
        if step.id == DISCOVER_STEP and not include_discovery:
            continue
        item: dict[str, Any] = {
            "id": step.id,
            "type": step.type,
            "owner": step.owner,
            "depends_on": [previous_step] if previous_step else [],
            "retry_limit": MAX_WORKER_RETRIES if step.type == "worker-brief" else 0,
        }
        if step.brief is not None:
            item["brief"] = step.brief
        if step.command:
            item["command"] = list(step.command)
        if step.id == ACCESS_PREFLIGHT_STEP and provider_name is not None:
            item["produces"] = [default_access_review_path(provider_name)]
        if step.id == DISCOVER_STEP and manifest is not None:
            item["produces"] = [manifest]
        if step.id == PROPOSE_CLEANING_STEP and provider_name is not None:
            item["produces"] = [
                default_cleaning_proposal_path(provider_name),
                default_cleaning_evidence_path(provider_name),
            ]
        steps.append(item)
        previous_step = step.id
    return {
        "provider": provider_name,
        "manifest": manifest,
        "dry_run": dry_run,
        "runtime": "coding-agent-subagent",
        "agent_cli_env": AGENT_CLI_ENV,
        "state_schema": STATE_SCHEMA_PATH,
        "serial": {
            "single_provider": True,
            "single_task": True,
            "no_matrix": True,
        },
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
    if "\n" in text or "\r" in text:
        return json.dumps(text)
    if text in {"-", "?", ":"} or text.startswith(("- ", "? ", ": ")):
        return json.dumps(text)
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


def _write_json(path: Path, data: dict[str, Any]) -> None:
    write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def _state_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return _repo_root() / path


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "agent_cli": os.environ.get(AGENT_CLI_ENV),
        "active_provider": None,
        "providers": {},
    }


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _default_state()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"state root must be an object: {path}")
    data.setdefault("schema_version", 1)
    data.setdefault("agent_cli", os.environ.get(AGENT_CLI_ENV))
    data.setdefault("active_provider", None)
    providers = data.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise ValueError(f"state providers must be an object: {path}")
    return data


def _dag_step_ids(include_discovery: bool) -> tuple[str, ...]:
    return tuple(
        step.id for step in TASK_DAG if include_discovery or step.id != DISCOVER_STEP
    )


def _task_statuses(step_ids: tuple[str, ...]) -> dict[str, str]:
    return {
        step_id: "in_progress" if index == 0 else "pending"
        for index, step_id in enumerate(step_ids)
    }


def _ensure_single_active_provider(state: dict[str, Any], provider: str) -> None:
    active_provider = state.get("active_provider")
    if active_provider not in {None, provider}:
        providers = state.get("providers", {})
        active_state = providers.get(active_provider, {})
        if active_state.get("status") == "in_progress":
            raise ToolError(
                "TASK_BRIEF_INVALID",
                "another provider is already in_progress: "
                f"{active_provider}; finish or block it before starting {provider}",
                retryable=False,
                provider=provider,
                task_id=f"{provider}-coordinator-state-conflict",
                details={"active_provider": active_provider},
            )


def _ensure_provider_state(
    state: dict[str, Any],
    *,
    provider: str,
    manifest: str | None = None,
    include_discovery: bool = True,
) -> dict[str, Any]:
    provider_name = _provider_slug(provider)
    _ensure_single_active_provider(state, provider_name)
    providers = state["providers"]
    current = providers.get(provider_name)
    if isinstance(current, dict):
        return current
    step_ids = _dag_step_ids(include_discovery)
    provider_state = {
        "provider": provider_name,
        "manifest": manifest or default_manifest_path(provider_name),
        "status": "in_progress",
        "current_step": step_ids[0],
        "steps": list(step_ids),
        "completed_steps": [],
        "task_statuses": _task_statuses(step_ids),
        "retry_counts": {step_id: 0 for step_id in step_ids},
        "verifications": {},
    }
    providers[provider_name] = provider_state
    state["active_provider"] = provider_name
    return provider_state


def _next_pending_step(provider_state: dict[str, Any]) -> str | None:
    task_statuses = provider_state["task_statuses"]
    for step_id in provider_state["steps"]:
        if task_statuses.get(step_id) == "in_progress":
            return str(step_id)
    for step_id in provider_state["steps"]:
        if task_statuses.get(step_id) == "pending":
            task_statuses[step_id] = "in_progress"
            provider_state["current_step"] = step_id
            return str(step_id)
    provider_state["current_step"] = None
    return None


def _provider_requires_live_review(provider: str) -> bool:
    manifest_path = _repo_root() / default_manifest_path(provider)
    if not manifest_path.exists():
        return provider == "mdpi"
    try:
        manifest = _read_manifest(manifest_path)
    except ToolError:
        return provider == "mdpi"
    probe = manifest.get("probe") if isinstance(manifest.get("probe"), dict) else {}
    return (
        provider == "mdpi"
        or bool(probe.get("requires_browser_runtime"))
        or bool(probe.get("requires_playwright"))
    )


def _manifest_path_for_provider(provider: str) -> Path:
    return _repo_root() / default_manifest_path(provider)


def _normalized_doi(value: str) -> str:
    doi = value.strip().lower()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:\s*", "", doi)
    return doi.strip()


def _doi_slug(value: str) -> str:
    return _normalized_doi(value).replace("/", "_")


def _manifest_dois(manifest: dict[str, Any]) -> list[str]:
    dois: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if not isinstance(value, str) or not value.strip():
            return
        doi = _normalized_doi(value)
        if doi and doi not in seen:
            seen.add(doi)
            dois.append(doi)

    fixtures = manifest.get("fixtures") if isinstance(manifest.get("fixtures"), dict) else {}
    doi_samples = fixtures.get("doi_samples") if isinstance(fixtures.get("doi_samples"), dict) else {}
    for sample in doi_samples.values():
        if isinstance(sample, dict):
            add(sample.get("doi"))

    extra_fixtures = manifest.get("extra_fixtures")
    if isinstance(extra_fixtures, list):
        for sample in extra_fixtures:
            if isinstance(sample, dict):
                add(sample.get("doi"))
    return dois


def _snapshot_expected_commands(provider: str, manifest_path: str | None = None) -> list[list[str]]:
    if manifest_path is None:
        path = _manifest_path_for_provider(provider)
    else:
        path = Path(manifest_path)
        if not path.is_absolute():
            path = _repo_root() / path
    manifest = _read_manifest(path)
    commands: list[list[str]] = []
    for doi in _manifest_dois(manifest):
        commands.append(
            [
                "PYTHONPATH=src",
                "python3",
                "scripts/snapshot_expected.py",
                "--doi",
                doi,
                "--review",
            ]
        )
        commands.append(
            [
                "PYTHONPATH=src",
                "python3",
                "scripts/snapshot_expected.py",
                "--doi",
                doi,
            ]
        )
        commands.append(
            [
                "PYTHONPATH=src",
                "python3",
                "scripts/onboard_from_manifests.py",
                "check-snapshot",
                "--provider",
                provider,
                "--doi",
                doi,
            ]
        )
    return commands


def _verify_commands(provider: str, task: str, *, include_live: bool = True) -> list[list[str]]:
    provider_name = _provider_slug(provider)
    command_map: dict[str, list[list[str]]] = {
        ACCESS_PREFLIGHT_STEP: [
            [
                "test",
                "-f",
                default_access_review_path(provider_name),
            ],
        ],
        "validate-manifest": [
            [
                "PYTHONPATH=src",
                "python3",
                "-m",
                "pytest",
                "tests/unit/test_provider_manifest_schema.py",
                "tests/unit/test_known_providers_sync.py",
                "-q",
            ]
        ],
        "capture-fixtures": [
            [
                "python3",
                "scripts/capture_fixture.py",
                "--from-manifest",
                default_manifest_path(provider_name),
                "--all",
                "--auto-via",
                "--fail-fast",
                "--dry-run",
            ]
        ],
        PROPOSE_CLEANING_STEP: [
            [
                "python3",
                "scripts/propose_cleaning_chain.py",
                "--provider",
                provider_name,
                "--write",
            ]
        ],
        "scaffold": [
            [
                "python3",
                "scripts/scaffold_provider.py",
                "--from-manifest",
                default_manifest_path(provider_name),
                "--merge-existing=safe",
            ]
        ],
        IMPLEMENT_STEP: [
            [
                "PYTHONPATH=src",
                "python3",
                "-m",
                "pytest",
                f"tests/unit/test_{provider_name}_provider.py",
                "-q",
            ],
            [
                "PYTHONPATH=src",
                "python3",
                "-m",
                "pytest",
                "tests/unit/test_provider_markdown_review_contract.py",
                "-q",
            ],
            [
                "PYTHONPATH=src",
                "python3",
                "-m",
                "pytest",
                "tests/unit/test_provider_route_contract.py",
                "-q",
            ],
            [
                "git",
                "grep",
                "-n",
                provider_name,
                "--",
                *CENTRAL_PROVIDER_LOGIC_PATHS,
            ],
        ],
        SHARED_INTEGRATION_STEP: [
            [
                "PYTHONPATH=src",
                "python3",
                "-m",
                "pytest",
                "tests/unit/test_manifest_bundle_sync.py",
                "tests/unit/test_golden_corpus_adapters.py",
                "tests/unit/test_provider_benchmark_samples.py",
                "tests/devtools/test_golden_criteria_live.py",
                "-q",
            ]
        ],
        SNAPSHOT_EXPECTED_STEP: _snapshot_expected_commands(provider_name),
        "manifest-sync-back": [
            [
                "python3",
                "scripts/manifest_sync_back.py",
                "--provider",
                provider_name,
                "--manifest",
                default_manifest_path(provider_name),
                "--sync-docs",
            ]
        ],
        "provider-local-acceptance": [
            [
                "python3",
                "scripts/onboard_from_manifests.py",
                "check-cleaning-proposal",
                "--provider",
                provider_name,
            ],
            [
                "python3",
                "scripts/propose_cleaning_chain.py",
                "--provider",
                provider_name,
                "--check-contract",
            ],
            [
                "PYTHONPATH=src",
                "python3",
                "-m",
                "pytest",
                f"tests/unit/test_{provider_name}_provider.py",
                "-q",
            ],
            [
                "PYTHONPATH=src",
                "python3",
                "-m",
                "pytest",
                "tests/unit/test_provider_markdown_review_contract.py",
                "-q",
            ],
            [
                "PYTHONPATH=src",
                "python3",
                "-m",
                "pytest",
                "tests/unit/test_provider_route_contract.py",
                "-q",
            ],
            [
                "git",
                "grep",
                "-n",
                provider_name,
                "--",
                *CENTRAL_PROVIDER_LOGIC_PATHS,
            ],
        ],
        "global-lint": [
            [
                "PYTHONPATH=src",
                "python3",
                "-m",
                "pytest",
                "tests/unit/test_manifest_bundle_sync.py",
                "tests/unit/test_provider_owner_reuse.py",
                "tests/unit/test_provider_bundle_completeness.py",
                "tests/unit/test_import_boundaries.py",
                "tests/unit/test_extraction_rules_validator.py",
                "-q",
            ]
        ],
        "merge-ready": [
            [
                "git",
                "diff",
                "--",
                default_manifest_path(provider_name),
                "onboarding/known-providers.yml",
                "docs/providers.md",
                "CHANGELOG.md",
            ]
        ],
    }
    if include_live and task == "provider-local-acceptance" and _provider_requires_live_review(provider_name):
        command_map["provider-local-acceptance"].append(
            [
                "PAPER_FETCH_RUN_LIVE=1",
                "python3",
                "scripts/run_golden_criteria_live_review.py",
                "--providers",
                provider_name,
            ]
        )
    return command_map.get(task, [])


def _load_golden_manifest() -> dict[str, Any]:
    path = _repo_root() / "tests" / "fixtures" / "golden_criteria" / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(
            "EXPECTED_SNAPSHOT_FAILED",
            "golden criteria manifest cannot be loaded.",
            retryable=True,
            task_id=SNAPSHOT_EXPECTED_STEP,
            details={"path": path.relative_to(_repo_root()).as_posix(), "reason": str(exc)},
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("samples"), dict):
        raise ToolError(
            "EXPECTED_SNAPSHOT_FAILED",
            "golden criteria manifest must contain samples.",
            retryable=True,
            task_id=SNAPSHOT_EXPECTED_STEP,
            details={"path": path.relative_to(_repo_root()).as_posix()},
        )
    return data


def _golden_sample_for_doi(doi: str, manifest: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    slug = _doi_slug(doi)
    samples = manifest.get("samples", {})
    sample = samples.get(slug)
    if isinstance(sample, dict):
        return slug, sample
    normalized = _normalized_doi(doi)
    for sample_id, item in samples.items():
        if isinstance(item, dict) and _normalized_doi(str(item.get("doi") or "")) == normalized:
            return str(sample_id), item
    return None


def _fixture_root_for_sample(sample_id: str, sample: dict[str, Any]) -> Path:
    family = str(sample.get("fixture_family") or "golden")
    if family == "block":
        return _repo_root() / "tests" / "fixtures" / "block" / sample_id
    return _repo_root() / "tests" / "fixtures" / "golden_criteria" / sample_id


def _run_env_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    argv = list(command)
    while argv and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", argv[0]):
        key, value = argv.pop(0).split("=", 1)
        env[key] = value
    if not argv:
        raise ValueError("command must contain an executable")
    return subprocess.run(
        argv,
        cwd=_repo_root(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else _repo_root() / path


def check_cleaning_proposal_freshness(
    provider: str,
    *,
    proposal_path: Path | None = None,
) -> dict[str, Any]:
    provider_name = _provider_slug(provider)
    proposal_ref = default_cleaning_proposal_path(provider_name)
    path = proposal_path or (_repo_root() / proposal_ref)
    if not path.exists():
        raise ToolError(
            "MARKDOWN_CONTRACT_DRIFT",
            "Cleaning proposal is missing; rerun propose-cleaning-chain.",
            retryable=True,
            provider=provider_name,
            manifest=default_manifest_path(provider_name),
            task_id=f"{provider_name}-{PROPOSE_CLEANING_STEP}",
            details={
                "proposal": path.as_posix(),
                "recovery_task": PROPOSE_CLEANING_STEP,
                "reason": "missing_proposal",
            },
        )
    try:
        proposal = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ToolError(
            "MARKDOWN_CONTRACT_DRIFT",
            "Cleaning proposal YAML is invalid; rerun propose-cleaning-chain.",
            retryable=True,
            provider=provider_name,
            manifest=default_manifest_path(provider_name),
            task_id=f"{provider_name}-{PROPOSE_CLEANING_STEP}",
            details={
                "proposal": path.as_posix(),
                "recovery_task": PROPOSE_CLEANING_STEP,
                "reason": str(exc),
            },
        ) from exc
    if not isinstance(proposal, dict) or proposal.get("schema_version") != 2:
        raise ToolError(
            "MARKDOWN_CONTRACT_DRIFT",
            "Cleaning proposal is stale or legacy; rerun propose-cleaning-chain.",
            retryable=True,
            provider=provider_name,
            manifest=default_manifest_path(provider_name),
            task_id=f"{provider_name}-{PROPOSE_CLEANING_STEP}",
            details={
                "proposal": path.as_posix(),
                "schema_version": proposal.get("schema_version") if isinstance(proposal, dict) else None,
                "recovery_task": PROPOSE_CLEANING_STEP,
                "reason": "proposal_schema_not_compact",
            },
        )
    digest_items = proposal.get("fixtures_digest")
    if not isinstance(digest_items, list) or not digest_items:
        raise ToolError(
            "MARKDOWN_CONTRACT_DRIFT",
            "Cleaning proposal has no fixture digest; rerun propose-cleaning-chain.",
            retryable=True,
            provider=provider_name,
            manifest=default_manifest_path(provider_name),
            task_id=f"{provider_name}-{PROPOSE_CLEANING_STEP}",
            details={
                "proposal": path.as_posix(),
                "recovery_task": PROPOSE_CLEANING_STEP,
                "reason": "missing_fixtures_digest",
            },
        )

    stale: list[dict[str, Any]] = []
    checked = 0
    for item in digest_items:
        if not isinstance(item, dict):
            stale.append({"reason": "invalid_digest_item", "item": item})
            continue
        raw_path = item.get("raw_path")
        expected_sha = item.get("sha256")
        if not raw_path or not expected_sha:
            stale.append(
                {
                    "purpose": item.get("purpose"),
                    "doi": item.get("doi"),
                    "raw_path": raw_path,
                    "reason": "missing_digest_path_or_sha256",
                }
            )
            continue
        fixture_path = _resolve_repo_path(str(raw_path))
        if not fixture_path.exists():
            stale.append(
                {
                    "purpose": item.get("purpose"),
                    "doi": item.get("doi"),
                    "raw_path": raw_path,
                    "reason": "fixture_missing",
                }
            )
            continue
        actual_sha = _sha256_file(fixture_path)
        checked += 1
        if actual_sha != str(expected_sha):
            stale.append(
                {
                    "purpose": item.get("purpose"),
                    "doi": item.get("doi"),
                    "raw_path": raw_path,
                    "expected_sha256": expected_sha,
                    "actual_sha256": actual_sha,
                    "reason": "sha256_mismatch",
                }
            )
    if stale:
        raise ToolError(
            "MARKDOWN_CONTRACT_DRIFT",
            "Cleaning proposal fixture digest is stale; rerun propose-cleaning-chain.",
            retryable=True,
            provider=provider_name,
            manifest=default_manifest_path(provider_name),
            task_id=f"{provider_name}-{PROPOSE_CLEANING_STEP}",
            details={
                "proposal": path.as_posix(),
                "recovery_task": PROPOSE_CLEANING_STEP,
                "stale_fixtures_digest": stale,
            },
        )
    return {
        "provider": provider_name,
        "proposal": path.as_posix(),
        "fixtures_checked": checked,
        "result": "passed",
    }


def _command_failed(command: list[str], completed: subprocess.CompletedProcess[str]) -> bool:
    argv = _command_argv(command)
    if len(argv) >= 2 and argv[0] == "git" and argv[1] == "grep":
        return completed.returncode != 1
    return completed.returncode != 0


def _tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _command_argv(command: list[str]) -> list[str]:
    return [part for part in command if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", part)]


def _is_cleaning_contract_command(command: list[str]) -> bool:
    argv = _command_argv(command)
    return (
        len(argv) >= 3
        and argv[0] == "python3"
        and argv[1] == "scripts/propose_cleaning_chain.py"
        and "--check-contract" in argv
    )


def _failure_code_for_task(task: str, command: list[str] | None = None) -> str:
    if command is not None and _is_cleaning_contract_command(command):
        return "MARKDOWN_CONTRACT_DRIFT"
    if task == SNAPSHOT_EXPECTED_STEP:
        return "EXPECTED_SNAPSHOT_FAILED"
    if task == "global-lint":
        return "GLOBAL_LINT_FAILED"
    if task == SHARED_INTEGRATION_STEP:
        return "SHARED_INTEGRATION_FAILED"
    if task == "provider-local-acceptance":
        return "PROVIDER_LOCAL_ACCEPTANCE_FAILED"
    if task == "validate-manifest":
        return "MANIFEST_SCHEMA_INVALID"
    if task == ACCESS_PREFLIGHT_STEP:
        return "ACCESS_REVIEW_NOT_FOUND"
    return "LOCAL_CHECK_FAILED"


def _load_failure_recovery_entries() -> dict[str, dict[str, Any]]:
    path = _repo_root() / FAILURE_RECOVERY_PATH
    entries: dict[str, dict[str, Any]] = {}
    current_code: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("## Signal: "):
            current_code = line.removeprefix("## Signal: ").strip()
            entries[current_code] = {}
            continue
        if current_code is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in {"diagnosis", "action", "retryable"}:
            entries[current_code][key] = value
    for entry in entries.values():
        retryable = entry.get("retryable")
        if isinstance(retryable, str):
            entry["retryable"] = retryable.lower() == "true"
    return entries


def _latest_failure(provider_state: dict[str, Any]) -> dict[str, Any] | None:
    runs = provider_state.get("runs")
    if not isinstance(runs, dict):
        return None
    ordered_tasks: list[str] = []
    current_step = provider_state.get("current_step")
    if isinstance(current_step, str):
        ordered_tasks.append(current_step)
    steps = provider_state.get("steps")
    if isinstance(steps, list):
        ordered_tasks.extend(str(step) for step in reversed(steps))
    task_statuses = provider_state.get("task_statuses")
    if isinstance(task_statuses, dict):
        ordered_tasks.extend(
            str(task) for task, status in task_statuses.items() if status in {"failed", "blocked"}
        )
    seen: set[str] = set()
    for task in ordered_tasks:
        if task in seen:
            continue
        seen.add(task)
        run = runs.get(task)
        if not isinstance(run, dict):
            continue
        failure = run.get("failure")
        if isinstance(failure, dict):
            return {"task": task, **failure}
    return None


def _access_review_summary(provider: str) -> dict[str, Any]:
    provider_name = _provider_slug(provider)
    path = _repo_root() / default_access_review_path(provider_name)
    if not path.exists():
        return {
            "status": "missing",
            "path": default_access_review_path(provider_name),
            "may_continue": False,
            "approved": False,
        }
    try:
        review = _load_access_review(provider_name)
    except ToolError as exc:
        return {
            "status": "schema_invalid",
            "path": default_access_review_path(provider_name),
            "may_continue": False,
            "approved": False,
            "error_code": exc.code,
        }
    status = str(review.get("status") or "unknown")
    may_continue = review.get("may_continue") is True
    approved = status == "approved" and may_continue
    if not approved and review.get("reviewed_by") == "operator-required":
        status_label = "draft"
    else:
        status_label = "approved" if approved else status
    return {
        "status": status_label,
        "path": default_access_review_path(provider_name),
        "may_continue": may_continue,
        "approved": approved,
        "reviewed_by": review.get("reviewed_by"),
        "legal_access_mode": (
            review.get("legal_access", {}).get("mode")
            if isinstance(review.get("legal_access"), dict)
            else None
        ),
        "allowed_runtimes": review.get("allowed_runtimes"),
    }


OPERATOR_REQUIRED_FAILURE_CODES = {
    "ACCESS_REVIEW_NOT_FOUND",
    "ACCESS_REVIEW_SCHEMA_INVALID",
    "ACCESS_REVIEW_NOT_APPROVED",
    "BROWSER_RUNTIME_REQUIRED",
    "CHALLENGE_DETECTED",
    "WORKER_MODIFIED_FORBIDDEN_FILE",
    "MANIFEST_PROVIDER_CONFLICT",
    "DISCOVERY_RETRY_EXHAUSTED",
    "TASK_RETRY_EXHAUSTED",
}


def diagnose_provider_state(provider_state: dict[str, Any]) -> dict[str, Any]:
    provider = _provider_slug(str(provider_state.get("provider") or "unknown"))
    recovery_entries = _load_failure_recovery_entries()
    failure = _latest_failure(provider_state)
    failure_code = str(failure.get("code")) if failure and failure.get("code") else None
    recovery = recovery_entries.get(failure_code or "", {})
    retryable = bool(recovery.get("retryable")) if failure_code in recovery_entries else None
    operator_required = (
        failure_code in OPERATOR_REQUIRED_FAILURE_CODES
        if failure_code is not None
        else False
    )
    access = _access_review_summary(provider)
    if not access["approved"] and provider_state.get("status") == "blocked":
        operator_required = True
    return {
        "provider": provider,
        "status": provider_state.get("status"),
        "current_step": provider_state.get("current_step"),
        "failure": {
            "task": failure.get("task") if failure else None,
            "code": failure_code,
            "retryable": retryable,
            "diagnosis": recovery.get("diagnosis"),
            "action": recovery.get("action"),
        },
        "access_review": access,
        "operator_required": operator_required,
    }


def plan_resume_blocked(provider_state: dict[str, Any]) -> dict[str, Any]:
    diagnosis = diagnose_provider_state(provider_state)
    provider = diagnosis["provider"]
    failure = diagnosis["failure"]
    code = failure.get("code")
    task = failure.get("task") or provider_state.get("current_step")
    blockers: list[str] = []
    if provider_state.get("status") != "blocked":
        blockers.append("provider status is not blocked")
    if not isinstance(task, str) or not task:
        blockers.append("no failed or current task is recorded")
    if failure.get("retryable") is not True:
        blockers.append(f"failure code is not retryable: {code}")
    access = diagnosis["access_review"]
    if not access.get("approved"):
        blockers.append(
            f"access review is not approved: {access.get('status')}"
        )
    if code in OPERATOR_REQUIRED_FAILURE_CODES:
        blockers.append(f"operator action required for failure code: {code}")
    if code == "UNSUITABLE_DOI_SAMPLE":
        blockers.append("failed DOI purpose must be replaced or explicitly approved before retry")
    if code == "BROWSER_RUNTIME_REQUIRED":
        blockers.append("browser runtime must be configured and approved before retry")
    resumable = not blockers
    next_task = IMPLEMENT_STEP if code == "MARKDOWN_CONTRACT_DRIFT" else task
    return {
        "provider": provider,
        "resumable": resumable,
        "next_task": next_task if isinstance(next_task, str) else None,
        "operator_required": bool(blockers),
        "blockers": blockers,
        "diagnosis": diagnosis,
    }


def _source_from_provider_state(provider_state: dict[str, Any]) -> OnboardingSource:
    provider = _provider_slug(str(provider_state["provider"]))
    manifest = str(provider_state.get("manifest") or default_manifest_path(provider))
    include_discovery = DISCOVER_STEP in set(provider_state.get("steps") or [])
    manifest_yaml: str | None = None
    if not include_discovery:
        manifest_path = _repo_root() / manifest
        if manifest_path.exists():
            manifest_yaml = manifest_path.read_text(encoding="utf-8")
    return OnboardingSource(
        provider=provider,
        manifest=manifest,
        include_discovery=include_discovery,
        manifest_yaml=manifest_yaml,
    )


def _execute_run_loop(
    *,
    source: OnboardingSource,
    output_dir: Path,
    state_path: Path,
    state: dict[str, Any],
    provider_state: dict[str, Any],
    until: str,
    domain: str | None,
    doi_prefix: str | None,
) -> dict[str, Any]:
    _run_artifacts(
        source=source,
        output_dir=output_dir,
        domain=domain,
        doi_prefix=doi_prefix,
    )
    executed: list[str] = []
    try:
        while True:
            task = _next_pending_step(provider_state)
            if task is None:
                break
            if task in {DISCOVER_STEP, IMPLEMENT_STEP}:
                brief_name = (
                    "discover-manifest.yml"
                    if task == DISCOVER_STEP
                    else "implement-provider.yml"
                )
                _dispatch_worker(
                    provider=source.provider,
                    task=task,
                    brief_path=output_dir / "briefs" / brief_name,
                    output_dir=output_dir,
                    provider_state=provider_state,
                )
            else:
                _execute_local_task(
                    provider=source.provider,
                    task=task,
                    provider_state=provider_state,
                )
                if task == PROPOSE_CLEANING_STEP:
                    _write_implementation_brief(output_dir=output_dir, source=source)
            executed.append(task)
            _mark_step_completed(
                state,
                provider_state,
                provider=source.provider,
                task=task,
            )
            _write_json(state_path, state)
            if task == until:
                break
    except ToolError:
        failed_task = provider_state.get("current_step")
        if isinstance(failed_task, str):
            _mark_step_failed(
                state,
                provider_state,
                provider=source.provider,
                task=failed_task,
            )
            _write_json(state_path, state)
        raise

    _write_json(state_path, state)
    return {
        "provider": source.provider,
        "manifest": source.manifest,
        "executed": executed,
        "until": until,
        "status": provider_state["status"],
        "current_step": provider_state.get("current_step"),
        "state": str(state_path),
        "output_dir": str(output_dir),
    }


def _record_run(
    provider_state: dict[str, Any],
    *,
    task: str,
    commands: list[list[str]],
    result: str,
    failure: dict[str, Any] | None = None,
) -> None:
    runs = provider_state.setdefault("runs", {})
    entry: dict[str, Any] = {
        "dry_run": False,
        "commands": commands,
        "result": result,
    }
    if failure is not None:
        entry["failure"] = failure
    runs[task] = entry


def _mark_step_failed(
    state: dict[str, Any],
    provider_state: dict[str, Any],
    *,
    provider: str,
    task: str,
) -> None:
    provider_state["task_statuses"][task] = "failed"
    provider_state["current_step"] = task
    provider_state["status"] = "blocked"
    state["active_provider"] = provider


def _mark_step_completed(
    state: dict[str, Any],
    provider_state: dict[str, Any],
    *,
    provider: str,
    task: str,
) -> str | None:
    task_statuses = provider_state["task_statuses"]
    task_statuses[task] = "completed"
    completed_steps = provider_state["completed_steps"]
    if task not in completed_steps:
        completed_steps.append(task)
    provider_state["current_step"] = None
    next_step = _next_pending_step(provider_state)
    if next_step is None:
        provider_state["status"] = "merge_ready"
        state["active_provider"] = None
    else:
        provider_state["status"] = "in_progress"
        state["active_provider"] = provider
    return next_step


def _write_implementation_brief(*, output_dir: Path, source: OnboardingSource) -> None:
    manifest_yaml = source.manifest_yaml
    manifest_path = _repo_root() / source.manifest
    if manifest_yaml is None and manifest_path.exists():
        manifest_yaml = manifest_path.read_text(encoding="utf-8")
    implementation_brief = build_implementation_brief(
        provider=source.provider,
        manifest=source.manifest,
        manifest_yaml=manifest_yaml,
    )
    write_text(
        output_dir / "briefs" / "implement-provider.yml",
        to_yaml(implementation_brief) + "\n",
    )


def _run_artifacts(
    *,
    source: OnboardingSource,
    output_dir: Path,
    domain: str | None,
    doi_prefix: str | None,
) -> None:
    dag = build_dag(
        provider=source.provider,
        manifest=source.manifest,
        include_discovery=source.include_discovery,
        dry_run=False,
    )
    write_text(
        output_dir / "task-dag.json",
        json.dumps(dag, indent=2, sort_keys=True) + "\n",
    )
    if source.include_discovery:
        discover_brief = build_discover_brief(
            provider=source.provider,
            domain=domain,
            doi_prefix=doi_prefix,
            output_manifest=source.manifest,
        )
        write_text(
            output_dir / "briefs" / "discover-manifest.yml",
            to_yaml(discover_brief) + "\n",
        )
    _write_implementation_brief(output_dir=output_dir, source=source)


def _workspace_changed_paths() -> set[str]:
    root = _repo_root()
    paths: set[str] = set()
    diff = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if diff.returncode == 0:
        paths.update(line.strip() for line in diff.stdout.splitlines() if line.strip())
    status = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode == 0:
        for line in status.stdout.splitlines():
            if not line.strip():
                continue
            path = line[3:].strip() if len(line) > 3 else line.strip()
            if " -> " in path:
                path = path.rsplit(" -> ", 1)[-1]
            if path:
                paths.add(path)
    return paths


def _matches_forbidden(path: str, forbidden: list[str]) -> bool:
    normalized = path.strip("/")
    for item in forbidden:
        pattern = item.strip()
        if not pattern:
            continue
        if pattern.endswith("/"):
            base = pattern.strip("/")
            if normalized == base or normalized.startswith(base + "/"):
                return True
            continue
        if normalized == pattern.strip("/") or normalized.startswith(pattern.strip("/") + "/"):
            return True
    return False


def _forbidden_changes(before: set[str], after: set[str], forbidden: list[str]) -> list[str]:
    return sorted(path for path in after - before if _matches_forbidden(path, forbidden))


def _load_brief(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"worker brief must load as a mapping: {path}")
    return data


def _worker_prompt(
    *,
    provider: str,
    task: str,
    brief: dict[str, Any],
) -> str:
    root = _repo_root()
    parts = [
        f"# Provider onboarding worker task: {provider} / {task}",
        "",
        "Follow the YAML task brief exactly. Do not commit changes.",
        "",
        "## Task Brief",
        "```yaml",
        to_yaml(brief),
        "```",
    ]
    access_path = root / default_access_review_path(provider)
    if access_path.exists():
        parts.extend(
            [
                "",
                "## Access Review",
                "```yaml",
                access_path.read_text(encoding="utf-8"),
                "```",
            ]
        )
    hard_constraints = root / HARD_CONSTRAINTS_PATH
    if hard_constraints.exists():
        parts.extend(
            [
                "",
                "## Hard Constraints",
                "```markdown",
                hard_constraints.read_text(encoding="utf-8"),
                "```",
            ]
        )
    if task == DISCOVER_STEP:
        schema = root / SCHEMA_PATH
        if schema.exists():
            parts.extend(
                [
                    "",
                    "## Provider Manifest Schema",
                    "```json",
                    schema.read_text(encoding="utf-8"),
                    "```",
                ]
            )
    if task == IMPLEMENT_STEP:
        manifest_path = root / str(brief.get("provider_manifest") or default_manifest_path(provider))
        if manifest_path.exists():
            parts.extend(
                [
                    "",
                    "## Provider Manifest",
                    "```yaml",
                    manifest_path.read_text(encoding="utf-8"),
                    "```",
                ]
            )
        proposal_path = root / default_cleaning_proposal_path(provider)
        if proposal_path.exists():
            parts.extend(
                [
                    "",
                    "## Compact Cleaning Proposal",
                    "```yaml",
                    proposal_path.read_text(encoding="utf-8"),
                    "```",
                ]
            )
    return "\n".join(parts) + "\n"


def _dispatch_worker(
    *,
    provider: str,
    task: str,
    brief_path: Path,
    output_dir: Path,
    provider_state: dict[str, Any],
) -> None:
    agent_cli = os.environ.get(AGENT_CLI_ENV)
    if not agent_cli:
        raise ToolError(
            "WORKER_AGENT_CLI_MISSING",
            f"{AGENT_CLI_ENV} is required to dispatch onboarding worker tasks.",
            retryable=False,
            provider=provider,
            manifest=provider_state.get("manifest"),
            task_id=f"{provider}-{task}",
            details={"env": AGENT_CLI_ENV},
        )
    brief = _load_brief(brief_path)
    prompt = _worker_prompt(provider=provider, task=task, brief=brief)
    forbidden = [str(value) for value in brief.get("files_must_not_modify") or ()]
    worker_dir = output_dir / "workers"
    worker_dir.mkdir(parents=True, exist_ok=True)
    argv = shlex.split(agent_cli)
    if not argv:
        raise ToolError(
            "WORKER_AGENT_CLI_MISSING",
            f"{AGENT_CLI_ENV} did not contain an executable command.",
            retryable=False,
            provider=provider,
            manifest=provider_state.get("manifest"),
            task_id=f"{provider}-{task}",
            details={"env": AGENT_CLI_ENV},
        )

    retry_counts = provider_state.setdefault("retry_counts", {})
    attempt_start = int(retry_counts.get(task, 0)) + 1
    commands = [argv]
    last_failure: dict[str, Any] | None = None
    for attempt in range(attempt_start, MAX_WORKER_RETRIES + 1):
        before = _workspace_changed_paths()
        completed = subprocess.run(
            argv,
            cwd=_repo_root(),
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
        )
        prefix = worker_dir / f"{task}-attempt-{attempt}"
        write_text(prefix.with_suffix(".prompt.md"), prompt)
        write_text(prefix.with_suffix(".stdout.log"), completed.stdout)
        write_text(prefix.with_suffix(".stderr.log"), completed.stderr)
        after = _workspace_changed_paths()
        forbidden_paths = _forbidden_changes(before, after, forbidden)
        if forbidden_paths:
            retry_counts[task] = attempt
            last_failure = {
                "code": "WORKER_MODIFIED_FORBIDDEN_FILE",
                "attempt": attempt,
                "forbidden_paths": forbidden_paths,
                "stdout_tail": _tail(completed.stdout),
                "stderr_tail": _tail(completed.stderr),
            }
            _record_run(
                provider_state,
                task=task,
                commands=commands,
                result="failed",
                failure=last_failure,
            )
            raise ToolError(
                "WORKER_MODIFIED_FORBIDDEN_FILE",
                "worker modified files outside its allowed scope.",
                retryable=True,
                provider=provider,
                manifest=provider_state.get("manifest"),
                task_id=f"{provider}-{task}",
                details=last_failure,
            )
        if completed.returncode == 0:
            _record_run(provider_state, task=task, commands=commands, result="passed")
            return
        retry_counts[task] = attempt
        last_failure = {
            "code": "WORKER_AGENT_FAILED",
            "attempt": attempt,
            "returncode": completed.returncode,
            "stdout_tail": _tail(completed.stdout),
            "stderr_tail": _tail(completed.stderr),
        }
    _record_run(
        provider_state,
        task=task,
        commands=commands,
        result="failed",
        failure=last_failure,
    )
    raise ToolError(
        "TASK_RETRY_EXHAUSTED",
        f"worker task {task} failed after {MAX_WORKER_RETRIES} attempts.",
        retryable=False,
        provider=provider,
        manifest=provider_state.get("manifest"),
        task_id=f"{provider}-{task}",
        details=last_failure or {"task": task},
    )


def _run_task_commands(
    provider: str,
    task: str,
    *,
    manifest: str | None = None,
) -> list[list[str]]:
    provider_name = _provider_slug(provider)
    manifest_path = manifest or default_manifest_path(provider_name)
    if task == "validate-manifest":
        return [
            [
                "PYTHONPATH=src",
                "python3",
                "-m",
                "pytest",
                "tests/unit/test_provider_manifest_schema.py",
                "-q",
            ]
        ]
    if task == "capture-fixtures":
        return [
            [
                "python3",
                "scripts/capture_fixture.py",
                "--from-manifest",
                manifest_path,
                "--all",
                "--auto-via",
                "--fail-fast",
            ]
        ]
    if task == PROPOSE_CLEANING_STEP:
        return [
            [
                "python3",
                "scripts/propose_cleaning_chain.py",
                "--provider",
                provider_name,
                "--write",
            ]
        ]
    if task == "scaffold":
        return [
            [
                "python3",
                "scripts/scaffold_provider.py",
                "--from-manifest",
                manifest_path,
                "--merge-existing=safe",
            ]
        ]
    if task == "manifest-sync-back":
        return [
            [
                "python3",
                "scripts/manifest_sync_back.py",
                "--provider",
                provider_name,
                "--manifest",
                manifest_path,
                "--sync-docs",
            ]
        ]
    if task == SNAPSHOT_EXPECTED_STEP:
        commands = _snapshot_expected_commands(provider_name, manifest_path)
        commands.append(
            [
                "python3",
                "scripts/bootstrap_review_artifact.py",
                "--provider",
                provider_name,
                "--manifest",
                manifest_path,
            ]
        )
        return commands
    return _verify_commands(provider_name, task)


def _payload_from_stderr(stderr: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(stderr)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _payload_from_stdout_yaml(stdout: str) -> dict[str, Any] | None:
    try:
        payload = yaml.safe_load(stdout)
    except yaml.YAMLError:
        return None
    return payload if isinstance(payload, dict) else None


def _execute_local_task(
    *,
    provider: str,
    task: str,
    provider_state: dict[str, Any],
) -> None:
    if task in {ACCESS_PREFLIGHT_STEP, DISCOVER_STEP}:
        validate_access_review(provider)
    manifest_path = str(provider_state.get("manifest") or default_manifest_path(provider))
    commands = _run_task_commands(provider, task, manifest=manifest_path)
    for command in commands:
        completed = _run_env_command(command)
        if _command_failed(command, completed):
            failure_code = _failure_code_for_task(task, command)
            structured = _payload_from_stderr(completed.stderr)
            if structured and isinstance(structured.get("code"), str):
                failure_code = str(structured["code"])
            failure = {
                "code": failure_code,
                "command": command,
                "returncode": completed.returncode,
                "stdout_tail": _tail(completed.stdout),
                "stderr_tail": _tail(completed.stderr),
            }
            if structured:
                failure["structured_error"] = structured
            if _is_cleaning_contract_command(command):
                contract_payload = _payload_from_stdout_yaml(completed.stdout)
                if contract_payload is not None:
                    failure["contract_check"] = contract_payload
            _record_run(provider_state, task=task, commands=commands, result="failed", failure=failure)
            raise ToolError(
                failure_code,
                f"onboarding run failed for task {task}.",
                retryable=bool(structured.get("retryable")) if structured else True,
                provider=provider,
                manifest=manifest_path,
                task_id=f"{provider}-run-{task}",
                details=failure,
            )
    _record_run(provider_state, task=task, commands=commands, result="passed")


def run_run(args: argparse.Namespace) -> int:
    if args.manifest:
        source = _manifest_source(args.manifest)
    else:
        source = _provider_source(
            provider=args.provider,
            domain=args.domain,
            doi_prefix=args.doi_prefix,
        )
    output_dir = Path(args.output_dir or f".paper-fetch-runs/{source.provider}-onboarding")
    if not output_dir.is_absolute():
        output_dir = _repo_root() / output_dir
    step_ids = _dag_step_ids(source.include_discovery)
    if args.until not in step_ids:
        raise ToolError(
            "TASK_BRIEF_INVALID",
            f"--until must name a task in the active DAG: {args.until}",
            retryable=False,
            provider=source.provider,
            manifest=source.manifest,
            task_id=f"{source.provider}-run",
            details={"until": args.until, "steps": list(step_ids)},
        )
    state_path = _state_path(args.state)
    state = _load_state(state_path)
    provider_state = _ensure_provider_state(
        state,
        provider=source.provider,
        manifest=source.manifest,
        include_discovery=source.include_discovery,
    )
    print(
        json.dumps(
            _execute_run_loop(
                source=source,
                output_dir=output_dir,
                state_path=state_path,
                state=state,
                provider_state=provider_state,
                until=args.until,
                domain=args.domain,
                doi_prefix=args.doi_prefix,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


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
    if args.manifest:
        source = _manifest_source(args.manifest)
    else:
        source = _provider_source(
            provider=args.provider,
            domain=args.domain,
            doi_prefix=args.doi_prefix,
        )

    dag = build_dag(
        provider=source.provider,
        manifest=source.manifest,
        include_discovery=source.include_discovery,
        dry_run=args.dry_run,
    )
    implementation_brief = build_implementation_brief(
        provider=source.provider,
        manifest=source.manifest,
        manifest_yaml=source.manifest_yaml,
    )
    write_text(
        output_dir / "task-dag.json",
        json.dumps(dag, indent=2, sort_keys=True) + "\n",
    )
    write_text(
        output_dir / "briefs" / "implement-provider.yml",
        to_yaml(implementation_brief) + "\n",
    )

    if source.include_discovery:
        discover_brief = build_discover_brief(
            provider=source.provider,
            domain=args.domain,
            doi_prefix=args.doi_prefix,
            output_manifest=source.manifest,
        )
        write_text(
            output_dir / "briefs" / "discover-manifest.yml",
            to_yaml(discover_brief) + "\n",
        )
    if args.dry_run:
        return 0

    state_path = _state_path(args.state)
    state = _load_state(state_path)
    _ensure_provider_state(
        state,
        provider=source.provider,
        manifest=source.manifest,
        include_discovery=source.include_discovery,
    )
    _write_json(state_path, state)
    return 0


def run_next(args: argparse.Namespace) -> int:
    provider = _provider_slug(args.provider)
    state_path = _state_path(args.state)
    state = _load_state(state_path)
    provider_state = _ensure_provider_state(state, provider=provider)
    step_id = _next_pending_step(provider_state)
    _write_json(state_path, state)
    print(
        json.dumps(
            {
                "provider": provider,
                "status": provider_state["status"],
                "current_step": step_id,
                "state": str(state_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def run_verify(args: argparse.Namespace) -> int:
    provider = _provider_slug(args.provider)
    if args.task not in _dag_step_ids(include_discovery=True):
        raise ToolError(
            "TASK_BRIEF_INVALID",
            f"unknown task for provider {provider}: {args.task}",
            retryable=False,
            provider=provider,
            task_id=f"{provider}-verify-{args.task}",
            details={"task": args.task},
        )
    state_path = _state_path(args.state)
    state = _load_state(state_path)
    provider_state = _ensure_provider_state(state, provider=provider)
    if args.task in {ACCESS_PREFLIGHT_STEP, DISCOVER_STEP}:
        validate_access_review(provider)
    commands = _verify_commands(provider, args.task)
    verifications = provider_state.setdefault("verifications", {})
    verifications[args.task] = {
        "dry_run": True,
        "commands": commands,
        "result": "planned",
    }
    _write_json(state_path, state)
    print(
        json.dumps(
            {
                "provider": provider,
                "task": args.task,
                "dry_run": True,
                "commands": commands,
                "result": "planned",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def run_check_snapshot(args: argparse.Namespace) -> int:
    provider = _provider_slug(args.provider)
    doi = _normalized_doi(args.doi)
    provider_manifest = _read_manifest(_manifest_path_for_provider(provider))
    if doi not in _manifest_dois(provider_manifest):
        raise ToolError(
            "FIXTURE_NOT_FOUND",
            "DOI is not registered in provider manifest fixtures.",
            retryable=True,
            provider=provider,
            manifest=default_manifest_path(provider),
            task_id=f"{provider}-{SNAPSHOT_EXPECTED_STEP}",
            details={"doi": doi},
        )
    golden_manifest = _load_golden_manifest()
    sample_entry = _golden_sample_for_doi(doi, golden_manifest)
    if sample_entry is None:
        raise ToolError(
            "FIXTURE_NOT_FOUND",
            "DOI is missing from golden criteria manifest.",
            retryable=True,
            provider=provider,
            manifest=default_manifest_path(provider),
            task_id=f"{provider}-{SNAPSHOT_EXPECTED_STEP}",
            details={"doi": doi, "sample_id": _doi_slug(doi)},
        )
    sample_id, sample = sample_entry
    fixture_root = _fixture_root_for_sample(sample_id, sample)
    expected_path = fixture_root / "expected.json"
    if not fixture_root.is_dir():
        raise ToolError(
            "FIXTURE_NOT_FOUND",
            "fixture directory is missing.",
            retryable=True,
            provider=provider,
            manifest=default_manifest_path(provider),
            task_id=f"{provider}-{SNAPSHOT_EXPECTED_STEP}",
            details={"doi": doi, "fixture_dir": fixture_root.relative_to(_repo_root()).as_posix()},
        )
    if not expected_path.is_file():
        raise ToolError(
            "EXPECTED_SNAPSHOT_FAILED",
            "expected snapshot file is missing.",
            retryable=True,
            provider=provider,
            manifest=default_manifest_path(provider),
            task_id=f"{provider}-{SNAPSHOT_EXPECTED_STEP}",
            details={"doi": doi, "expected_path": expected_path.relative_to(_repo_root()).as_posix()},
        )
    if sample.get("expected_outcome") == "pending":
        raise ToolError(
            "EXPECTED_OUTCOME_PENDING",
            "fixture manifest expected_outcome is still pending.",
            retryable=True,
            provider=provider,
            manifest=default_manifest_path(provider),
            task_id=f"{provider}-{SNAPSHOT_EXPECTED_STEP}",
            details={"doi": doi, "sample_id": sample_id},
        )
    print(
        json.dumps(
            {
                "provider": provider,
                "doi": doi,
                "sample_id": sample_id,
                "expected_path": expected_path.relative_to(_repo_root()).as_posix(),
                "expected_outcome": sample.get("expected_outcome"),
                "result": "passed",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def run_check_cleaning_proposal(args: argparse.Namespace) -> int:
    proposal_path = Path(args.proposal) if args.proposal else None
    if proposal_path is not None and not proposal_path.is_absolute():
        proposal_path = _repo_root() / proposal_path
    print(
        json.dumps(
            check_cleaning_proposal_freshness(args.provider, proposal_path=proposal_path),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def run_run_checks(args: argparse.Namespace) -> int:
    provider = _provider_slug(args.provider)
    if bool(args.task) == bool(args.all_local):
        raise ToolError(
            "TASK_BRIEF_INVALID",
            "run-checks requires exactly one of --task or --all-local.",
            retryable=True,
            provider=provider,
            task_id=f"{provider}-run-checks",
            details={"task": args.task, "all_local": args.all_local},
        )
    all_step_ids = _dag_step_ids(include_discovery=True)
    if args.task and args.task not in all_step_ids:
        raise ToolError(
            "TASK_BRIEF_INVALID",
            f"unknown task for provider {provider}: {args.task}",
            retryable=False,
            provider=provider,
            task_id=f"{provider}-run-checks-{args.task}",
            details={"task": args.task},
        )

    tasks = (
        [
            ACCESS_PREFLIGHT_STEP,
            "validate-manifest",
            "provider-local-acceptance",
            SHARED_INTEGRATION_STEP,
            "global-lint",
        ]
        if args.all_local
        else [args.task]
    )
    state_path = _state_path(args.state)
    state = _load_state(state_path)
    provider_state = _ensure_provider_state(state, provider=provider)
    completed_tasks: list[str] = []

    for task in tasks:
        if task == ACCESS_PREFLIGHT_STEP:
            validate_access_review(provider)
        commands = _verify_commands(provider, task, include_live=not args.all_local)
        for command in commands:
            completed = _run_env_command(command)
            if _command_failed(command, completed):
                failure_code = _failure_code_for_task(task, command)
                structured = _payload_from_stderr(completed.stderr)
                if structured and isinstance(structured.get("code"), str):
                    failure_code = str(structured["code"])
                failure = {
                    "code": failure_code,
                    "command": command,
                    "returncode": completed.returncode,
                    "stdout_tail": _tail(completed.stdout),
                    "stderr_tail": _tail(completed.stderr),
                }
                if structured:
                    failure["structured_error"] = structured
                if _is_cleaning_contract_command(command):
                    contract_payload = _payload_from_stdout_yaml(completed.stdout)
                    if contract_payload is not None:
                        failure["contract_check"] = contract_payload
                _record_run(provider_state, task=task, commands=commands, result="failed", failure=failure)
                _write_json(state_path, state)
                raise ToolError(
                    failure_code,
                    f"onboarding local check failed for task {task}.",
                    retryable=bool(structured.get("retryable")) if structured else True,
                    provider=provider,
                    manifest=default_manifest_path(provider),
                    task_id=f"{provider}-run-checks-{task}",
                    details=failure,
                )
        _record_run(provider_state, task=task, commands=commands, result="passed")
        completed_tasks.append(task)

    _write_json(state_path, state)
    print(
        json.dumps(
            {
                "provider": provider,
                "tasks": completed_tasks,
                "result": "passed",
                "state": str(state_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _fixture_path_for_doi(doi: str) -> str | None:
    try:
        golden_manifest = _load_golden_manifest()
    except ToolError:
        return None
    sample_entry = _golden_sample_for_doi(doi, golden_manifest)
    if sample_entry is None:
        return None
    sample_id, sample = sample_entry
    return _fixture_root_for_sample(sample_id, sample).relative_to(_repo_root()).as_posix()


def _manifest_fixture_summary(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    fixtures: list[dict[str, Any]] = []
    manifest_fixtures = manifest.get("fixtures") if isinstance(manifest.get("fixtures"), dict) else {}
    doi_samples = (
        manifest_fixtures.get("doi_samples")
        if isinstance(manifest_fixtures.get("doi_samples"), dict)
        else {}
    )
    for purpose, sample in doi_samples.items():
        if not isinstance(sample, dict):
            continue
        doi = sample.get("doi")
        item = {
            "purpose": purpose,
            "doi": doi,
            "fixture_path": _fixture_path_for_doi(str(doi)) if doi else None,
            "expected_outcome": None,
            "null_reason": None if doi else sample.get("evidence_reason"),
        }
        if doi:
            try:
                golden_manifest = _load_golden_manifest()
                sample_entry = _golden_sample_for_doi(str(doi), golden_manifest)
            except ToolError:
                sample_entry = None
            if sample_entry is not None:
                item["expected_outcome"] = sample_entry[1].get("expected_outcome")
        fixtures.append(item)
    extra_fixtures = manifest.get("extra_fixtures")
    if isinstance(extra_fixtures, list):
        for index, sample in enumerate(extra_fixtures):
            if not isinstance(sample, dict):
                continue
            doi = sample.get("doi")
            fixtures.append(
                {
                    "purpose": sample.get("purpose") or f"extra_fixtures[{index}]",
                    "doi": doi,
                    "fixture_path": _fixture_path_for_doi(str(doi)) if doi else None,
                    "expected_outcome": sample.get("expected_outcome"),
                    "null_reason": None if doi else sample.get("evidence_reason"),
                }
            )
    return fixtures


def _review_artifact_summary(provider: str) -> dict[str, Any]:
    path = _repo_root() / "onboarding" / "reviews" / f"{provider}.yml"
    if not path.exists():
        return {"status": "missing", "path": path.relative_to(_repo_root()).as_posix(), "fixtures": []}
    try:
        review = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return {
            "status": "invalid_yaml",
            "path": path.relative_to(_repo_root()).as_posix(),
            "error": str(exc),
            "fixtures": [],
        }
    fixtures = review.get("fixtures") if isinstance(review, dict) else None
    summaries: list[dict[str, Any]] = []
    if isinstance(fixtures, list):
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            fixes = fixture.get("fixes") if isinstance(fixture.get("fixes"), list) else []
            issues = fixture.get("issues") if isinstance(fixture.get("issues"), list) else []
            summaries.append(
                {
                    "fixture": fixture.get("fixture"),
                    "purpose": fixture.get("purpose"),
                    "doi": fixture.get("doi"),
                    "issue_ids": [
                        issue.get("id")
                        for issue in issues
                        if isinstance(issue, dict) and issue.get("id")
                    ],
                    "fix_ids": [
                        fix.get("id")
                        for fix in fixes
                        if isinstance(fix, dict) and fix.get("id")
                    ],
                    "test_names": sorted(
                        {
                            str(test_name)
                            for fix in fixes
                            if isinstance(fix, dict)
                            for test_name in (fix.get("test_names") or [])
                        }
                    ),
                    "markdown_semantic_reviewed": fixture.get("markdown_semantic_reviewed"),
                }
            )
    return {
        "status": "present",
        "path": path.relative_to(_repo_root()).as_posix(),
        "fixtures": summaries,
    }


def build_provider_summary(
    *,
    provider: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    provider_name = _provider_slug(provider)
    providers = state.get("providers") if isinstance(state.get("providers"), dict) else {}
    provider_state = providers.get(provider_name) if isinstance(providers, dict) else None
    if not isinstance(provider_state, dict):
        provider_state = {
            "provider": provider_name,
            "manifest": default_manifest_path(provider_name),
            "status": "not_started",
            "current_step": None,
        }
    manifest_path = _repo_root() / str(provider_state.get("manifest") or default_manifest_path(provider_name))
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        manifest = _read_manifest(manifest_path)
    runs = provider_state.get("runs") if isinstance(provider_state.get("runs"), dict) else {}
    verifications = (
        provider_state.get("verifications")
        if isinstance(provider_state.get("verifications"), dict)
        else {}
    )
    diagnosis = diagnose_provider_state(provider_state)
    summary: dict[str, Any] = {
        "provider": provider_name,
        "status": provider_state.get("status"),
        "current_step": provider_state.get("current_step"),
        "failed_task": diagnosis["failure"].get("task"),
        "failure_code": diagnosis["failure"].get("code"),
        "failure_recovery_action": diagnosis["failure"].get("action"),
        "access_review": diagnosis["access_review"],
        "manifest": {
            "path": manifest_path.relative_to(_repo_root()).as_posix(),
            "main_path": manifest.get("main_path"),
            "route_sources": manifest.get("route_sources"),
            "display_source": manifest.get("display_source"),
        },
        "fixture_coverage": _manifest_fixture_summary(manifest) if manifest else [],
        "review_artifact": _review_artifact_summary(provider_name),
        "run_checks": [
            {
                "task": task,
                "result": run.get("result"),
                "commands": run.get("commands"),
                "failure_code": (
                    run.get("failure", {}).get("code")
                    if isinstance(run.get("failure"), dict)
                    else None
                ),
            }
            for task, run in runs.items()
            if isinstance(run, dict)
        ],
        "verification_plans": [
            {
                "task": task,
                "result": plan.get("result"),
                "commands": plan.get("commands"),
            }
            for task, plan in verifications.items()
            if isinstance(plan, dict)
        ],
        "operator_action": None,
        "merge_ready_pr_draft": None,
    }
    if provider_state.get("status") == "blocked":
        plan = plan_resume_blocked(provider_state)
        summary["operator_action"] = (
            diagnosis["failure"].get("action")
            or "; ".join(plan["blockers"])
            or "inspect blocked provider state"
        )
    if provider_state.get("status") == "merge_ready":
        summary["merge_ready_pr_draft"] = (
            f"Add {provider_name} provider onboarding artifacts and local verification summary."
        )
    return summary


def _markdown_scalar(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _markdown_command(command: Any) -> str:
    if isinstance(command, list):
        return shlex.join(str(part) for part in command)
    if isinstance(command, str):
        return command
    return _markdown_scalar(command)


def _append_markdown_commands(lines: list[str], commands: Any) -> None:
    if not isinstance(commands, list) or not commands:
        lines.append("  - commands: []")
        return
    for command in commands:
        lines.append(f"  - command: `{_markdown_command(command)}`")


def render_provider_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# {summary['provider']} onboarding summary",
        "",
        f"- status: {summary.get('status')}",
        f"- current_step: {summary.get('current_step')}",
        f"- failed_task: {summary.get('failed_task')}",
        f"- failure_code: {summary.get('failure_code')}",
        f"- failure_recovery_action: {summary.get('failure_recovery_action')}",
        f"- access_review: {summary['access_review'].get('status')}",
        "",
        "## Manifest",
        "",
        f"- path: {summary['manifest'].get('path')}",
        f"- display_source: {summary['manifest'].get('display_source')}",
        f"- main_path: {summary['manifest'].get('main_path')}",
        f"- route_sources: {summary['manifest'].get('route_sources')}",
        "",
        "## Fixture Coverage",
        "",
    ]
    for fixture in summary.get("fixture_coverage", []):
        lines.append(
            "- "
            f"{fixture.get('purpose')}: doi={fixture.get('doi')} "
            f"fixture={fixture.get('fixture_path')} "
            f"expected={fixture.get('expected_outcome')}"
        )

    review = summary.get("review_artifact")
    lines.extend(["", "## Review Artifact", ""])
    if not isinstance(review, dict):
        lines.append("- missing review artifact summary")
    else:
        lines.append(f"- status: {review.get('status')}")
        lines.append(f"- path: {review.get('path')}")
        fixtures = review.get("fixtures") if isinstance(review.get("fixtures"), list) else []
        if not fixtures:
            lines.append("- no review fixture summaries")
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            lines.append(
                "- "
                f"{fixture.get('fixture')}/{fixture.get('purpose')}: "
                f"doi={fixture.get('doi')} "
                f"reviewed={fixture.get('markdown_semantic_reviewed')} "
                f"issue_ids={_markdown_scalar(fixture.get('issue_ids') or [])} "
                f"fix_ids={_markdown_scalar(fixture.get('fix_ids') or [])} "
                f"tests={_markdown_scalar(fixture.get('test_names') or [])}"
            )

    lines.extend(["", "## Run Checks", ""])
    run_checks = summary.get("run_checks") or []
    if not run_checks:
        lines.append("- no recorded run-check results")
    for run in run_checks:
        lines.append(
            f"- {run.get('task')}: result={run.get('result')} failure_code={run.get('failure_code')}"
        )
        _append_markdown_commands(lines, run.get("commands"))

    lines.extend(["", "## Verification Plans", ""])
    verification_plans = summary.get("verification_plans") or []
    if not verification_plans:
        lines.append("- no recorded verification plans")
    for plan in verification_plans:
        lines.append(f"- {plan.get('task')}: result={plan.get('result')}")
        _append_markdown_commands(lines, plan.get("commands"))

    lines.extend(["", "## Operator Action", ""])
    lines.append(f"- {summary.get('operator_action') or 'none recorded'}")
    if summary.get("merge_ready_pr_draft"):
        lines.extend(["", "## PR Draft", "", str(summary["merge_ready_pr_draft"])])
    return "\n".join(lines) + "\n"


def run_diagnose(args: argparse.Namespace) -> int:
    state_path = _state_path(args.state)
    state = _load_state(state_path)
    providers = state.get("providers") if isinstance(state.get("providers"), dict) else {}
    if args.provider:
        provider_name = _provider_slug(args.provider)
        provider_state = providers.get(provider_name)
        if not isinstance(provider_state, dict):
            raise ToolError(
                "TASK_BRIEF_INVALID",
                f"provider is missing from state: {provider_name}",
                retryable=False,
                provider=provider_name,
                task_id=f"{provider_name}-diagnose",
            )
        diagnoses = [diagnose_provider_state(provider_state)]
    else:
        diagnoses = [
            diagnose_provider_state(provider_state)
            for provider_state in providers.values()
            if isinstance(provider_state, dict)
        ]
    print(
        json.dumps(
            {
                "state": str(state_path),
                "providers": diagnoses,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def run_resume_blocked(args: argparse.Namespace) -> int:
    provider = _provider_slug(args.provider)
    state_path = _state_path(args.state)
    state = _load_state(state_path)
    providers = state.get("providers") if isinstance(state.get("providers"), dict) else {}
    provider_state = providers.get(provider)
    if not isinstance(provider_state, dict):
        raise ToolError(
            "TASK_BRIEF_INVALID",
            f"provider is missing from state: {provider}",
            retryable=False,
            provider=provider,
            task_id=f"{provider}-resume-blocked",
        )
    plan = plan_resume_blocked(provider_state)
    payload = {"resume_plan": {**plan, "until": args.until}, "state": str(state_path)}
    if args.dry_run:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if not plan["resumable"]:
        raise ToolError(
            "TASK_BRIEF_INVALID",
            "blocked provider is not resumable without operator action.",
            retryable=False,
            provider=provider,
            manifest=provider_state.get("manifest"),
            task_id=f"{provider}-resume-blocked",
            details=payload,
        )
    steps = provider_state.get("steps") if isinstance(provider_state.get("steps"), list) else []
    if args.until not in steps:
        raise ToolError(
            "TASK_BRIEF_INVALID",
            f"--until must name a task in the provider state DAG: {args.until}",
            retryable=False,
            provider=provider,
            manifest=provider_state.get("manifest"),
            task_id=f"{provider}-resume-blocked",
            details={"until": args.until, "steps": steps},
        )
    next_task = str(plan["next_task"])
    task_statuses = provider_state.setdefault("task_statuses", {})
    task_statuses[next_task] = "in_progress"
    provider_state["current_step"] = next_task
    provider_state["status"] = "in_progress"
    state["active_provider"] = provider
    _write_json(state_path, state)
    source = _source_from_provider_state(provider_state)
    output_dir = Path(args.output_dir or f".paper-fetch-runs/{provider}-onboarding")
    if not output_dir.is_absolute():
        output_dir = _repo_root() / output_dir
    run_payload = _execute_run_loop(
        source=source,
        output_dir=output_dir,
        state_path=state_path,
        state=state,
        provider_state=provider_state,
        until=args.until,
        domain=None,
        doi_prefix=None,
    )
    print(json.dumps({**payload, "run": run_payload}, indent=2, sort_keys=True))
    return 0


def run_summarize(args: argparse.Namespace) -> int:
    provider = _provider_slug(args.provider)
    state_path = _state_path(args.state)
    state = _load_state(state_path)
    summary = build_provider_summary(provider=provider, state=state)
    if args.format == "json":
        content = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    else:
        content = render_provider_summary_markdown(summary)
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = _repo_root() / output_path
        write_text(output_path, content)
    else:
        print(content, end="")
    return 0


def run_advance(args: argparse.Namespace) -> int:
    provider = _provider_slug(args.provider)
    state_path = _state_path(args.state)
    state = _load_state(state_path)
    provider_state = _ensure_provider_state(state, provider=provider)
    task_statuses = provider_state["task_statuses"]
    if args.task not in task_statuses:
        raise ToolError(
            "TASK_BRIEF_INVALID",
            f"unknown task for provider {provider}: {args.task}",
            retryable=False,
            provider=provider,
            task_id=f"{provider}-advance-{args.task}",
            details={"task": args.task},
        )
    if args.task == ACCESS_PREFLIGHT_STEP:
        validate_access_review(provider)
    elif args.task == DISCOVER_STEP and ACCESS_PREFLIGHT_STEP not in provider_state["completed_steps"]:
        validate_access_review(provider)
        raise ToolError(
            "ACCESS_REVIEW_NOT_APPROVED",
            "operator-access-preflight must be completed before discover-manifest.",
            retryable=False,
            provider=provider,
            manifest=provider_state.get("manifest"),
            task_id=f"{provider}-advance-{args.task}",
            details={
                "required_completed_step": ACCESS_PREFLIGHT_STEP,
                "task": args.task,
            },
        )
    task_statuses[args.task] = "completed"
    completed_steps = provider_state["completed_steps"]
    if args.task not in completed_steps:
        completed_steps.append(args.task)
    provider_state["current_step"] = None
    next_step = _next_pending_step(provider_state)
    if next_step is None:
        provider_state["status"] = "merge_ready"
        state["active_provider"] = None
    else:
        provider_state["status"] = "in_progress"
        state["active_provider"] = provider
    _write_json(state_path, state)
    print(
        json.dumps(
            {
                "provider": provider,
                "advanced": args.task,
                "status": provider_state["status"],
                "next_step": next_step,
                "state": str(state_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = CoordinatorArgumentParser(
        description="Generate manifest-driven provider onboarding dry-run artifacts."
    )
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=CoordinatorArgumentParser)

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
    start.add_argument(
        "--state",
        default=DEFAULT_STATE_PATH,
        help="coordinator state JSON path",
    )
    start.set_defaults(func=run_start)

    run = subparsers.add_parser(
        "run",
        help="execute the serial onboarding DAG for one provider",
    )
    run_source = run.add_mutually_exclusive_group(required=True)
    run_source.add_argument("--provider", help="provider name seed")
    run_source.add_argument("--manifest", help="existing manifest path for replay mode")
    run.add_argument("--domain", help="provider domain seed")
    run.add_argument("--doi-prefix", help="DOI prefix seed")
    run.add_argument(
        "--until",
        default="merge-ready",
        help="inclusive task id to stop after; defaults to merge-ready",
    )
    run.add_argument(
        "--output-dir",
        help="directory for DAG, briefs, and worker logs",
    )
    run.add_argument(
        "--state",
        default=DEFAULT_STATE_PATH,
        help="coordinator state JSON path",
    )
    run.set_defaults(func=run_run)

    diagnose = subparsers.add_parser(
        "diagnose",
        help="summarize blocked provider failures from coordinator state",
    )
    diagnose.add_argument("--provider", help="optional provider name")
    diagnose.add_argument(
        "--state",
        default=DEFAULT_STATE_PATH,
        help="coordinator state JSON path",
    )
    diagnose.set_defaults(func=run_diagnose)

    resume_blocked = subparsers.add_parser(
        "resume-blocked",
        help="resume one retryable blocked provider after preconditions are satisfied",
    )
    resume_blocked.add_argument("--provider", required=True, help="provider name")
    resume_blocked.add_argument("--dry-run", action="store_true", help="print resume plan only")
    resume_blocked.add_argument(
        "--until",
        default="provider-local-acceptance",
        help="inclusive task id to stop after; defaults to provider-local-acceptance",
    )
    resume_blocked.add_argument(
        "--output-dir",
        help="directory for DAG, briefs, and worker logs",
    )
    resume_blocked.add_argument(
        "--state",
        default=DEFAULT_STATE_PATH,
        help="coordinator state JSON path",
    )
    resume_blocked.set_defaults(func=run_resume_blocked)

    summarize = subparsers.add_parser(
        "summarize",
        help="render an operator-facing provider onboarding summary",
    )
    summarize.add_argument("--provider", required=True, help="provider name")
    summarize.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="summary output format",
    )
    summarize.add_argument("--output", help="optional output path")
    summarize.add_argument(
        "--state",
        default=DEFAULT_STATE_PATH,
        help="coordinator state JSON path",
    )
    summarize.set_defaults(func=run_summarize)

    next_task = subparsers.add_parser(
        "next",
        help="print and persist the next serial task for one provider",
    )
    next_task.add_argument("--provider", required=True, help="provider name")
    next_task.add_argument(
        "--state",
        default=DEFAULT_STATE_PATH,
        help="coordinator state JSON path",
    )
    next_task.set_defaults(func=run_next)

    verify = subparsers.add_parser(
        "verify",
        help="write dry-run verification plan for a provider task",
    )
    verify.add_argument("--provider", required=True, help="provider name")
    verify.add_argument("--task", required=True, help="task id to verify")
    verify.add_argument(
        "--state",
        default=DEFAULT_STATE_PATH,
        help="coordinator state JSON path",
    )
    verify.set_defaults(func=run_verify)

    run_checks = subparsers.add_parser(
        "run-checks",
        help="execute local verification commands for a provider task",
    )
    run_checks.add_argument("--provider", required=True, help="provider name")
    task_group = run_checks.add_mutually_exclusive_group(required=True)
    task_group.add_argument("--task", help="single task id to execute")
    task_group.add_argument(
        "--all-local",
        action="store_true",
        help="run access, manifest, review, shared integration, and global lint gates",
    )
    run_checks.add_argument(
        "--state",
        default=DEFAULT_STATE_PATH,
        help="coordinator state JSON path",
    )
    run_checks.set_defaults(func=run_run_checks)

    check_snapshot = subparsers.add_parser(
        "check-snapshot",
        help="check that a DOI fixture has an expected snapshot",
    )
    check_snapshot.add_argument("--provider", required=True, help="provider name")
    check_snapshot.add_argument("--doi", required=True, help="DOI to check")
    check_snapshot.set_defaults(func=run_check_snapshot)

    check_cleaning = subparsers.add_parser(
        "check-cleaning-proposal",
        help="check cleaning proposal fixture digest freshness",
    )
    check_cleaning.add_argument("--provider", required=True, help="provider name")
    check_cleaning.add_argument("--proposal", help="optional compact proposal path")
    check_cleaning.set_defaults(func=run_check_cleaning_proposal)

    advance = subparsers.add_parser(
        "advance",
        help="mark a task complete and persist the next serial task",
    )
    advance.add_argument("--provider", required=True, help="provider name")
    advance.add_argument("--task", required=True, help="task id to mark complete")
    advance.add_argument(
        "--state",
        default=DEFAULT_STATE_PATH,
        help="coordinator state JSON path",
    )
    advance.set_defaults(func=run_advance)

    return parser


def _provider_from_args(args: argparse.Namespace) -> str | None:
    provider = getattr(args, "provider", None)
    if isinstance(provider, str):
        try:
            return _provider_slug(provider)
        except ValueError:
            return provider
    return None


def _manifest_from_args(args: argparse.Namespace) -> str | None:
    manifest = getattr(args, "manifest", None)
    return manifest if isinstance(manifest, str) else None


def _task_id_from_args(args: argparse.Namespace) -> str:
    provider = _provider_from_args(args)
    command = getattr(args, "command", None) or "coordinator"
    task = getattr(args, "task", None)
    if provider and task:
        return f"{provider}-{command}-{task}"
    if provider:
        return f"{provider}-{command}"
    return str(command)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ToolError as exc:
        emit_error(
            error_payload(
                exc.code,
                exc.message,
                provider=exc.provider or _provider_from_args(args),
                manifest=exc.manifest or _manifest_from_args(args),
                task_id=exc.task_id or _task_id_from_args(args),
                retryable=exc.retryable,
                details=exc.details,
            )
        )
        return 1
    except ValueError as exc:
        emit_error(
            error_payload(
                "TASK_BRIEF_INVALID",
                str(exc),
                provider=_provider_from_args(args),
                manifest=_manifest_from_args(args),
                task_id=_task_id_from_args(args),
                retryable=False,
                details={"reason": str(exc)},
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

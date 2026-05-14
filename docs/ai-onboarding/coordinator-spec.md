# Coordinator Spec

本文定义 S14 coordinator 的机器可验证编排规则。

## Invocation

`/onboard <name>` 对应的本地入口是：

```bash
python3 scripts/onboard_from_manifests.py start --provider <name> --domain <domain> --dry-run --output-dir <dir>
python3 scripts/onboard_from_manifests.py start --manifest docs/ai-onboarding/manifests/<name>.yml --dry-run --output-dir <dir>
python3 scripts/onboard_from_manifests.py next --provider <name>
python3 scripts/onboard_from_manifests.py verify --provider <name> --task <task-id>
python3 scripts/onboard_from_manifests.py advance --provider <name> --task <task-id>
```

`PROVIDER_ONBOARDING_AGENT_CLI` records the operator-selected coding agent CLI. `scripts/onboard_from_manifests.py` only writes task DAG, task brief, verification plan, and coordinator state. It must not generate CLI-specific commands for worker dispatch.

## Runtime

- Coordinator is one long-running coding agent CLI session.
- Worker is one child agent task with isolated context and no commit right.
- Worker dispatch uses the selected coding agent CLI outside `scripts/onboard_from_manifests.py`.
- The script must not call any LLM SDK or vendor client.
- The script must not run a GitHub Actions matrix.
- Provider onboarding is serial across providers.
- Task execution is serial inside one provider.
- One coordinator state file may contain at most one provider with `status: in_progress`.
- Worker output remains in the workspace; coordinator owns verification, shared-file updates, and commit preparation.

## Task DAG

The provider DAG is ordered:

1. `discover-manifest`
2. `validate-manifest`
3. `capture-fixtures`
4. `scaffold`
5. `implement-provider`
6. `snapshot-expected`
7. `manifest-sync-back`
8. `provider-local-acceptance`
9. `global-lint`
10. `merge-ready`

`start --provider` includes all 10 tasks and writes `briefs/discover-manifest.yml` plus `briefs/implement-provider.yml`.

`start --manifest` skips `discover-manifest`, reads the provider name from the manifest YAML, and writes `briefs/implement-provider.yml`.

## Task Ownership

- `discover-manifest`: coordinator dispatches discovery worker.
- `validate-manifest`: coordinator validates schema, known-provider conflict, draft state, and DOI sample evidence.
- `capture-fixtures`: coordinator runs `scripts/capture_fixture.py` from manifest DOI samples.
- `scaffold`: coordinator runs `scripts/scaffold_provider.py --from-manifest`.
- `implement-provider`: coordinator dispatches implementation worker.
- `snapshot-expected`: coordinator runs `scripts/snapshot_expected.py`.
- `manifest-sync-back`: coordinator runs `scripts/manifest_sync_back.py`.
- `provider-local-acceptance`: coordinator runs provider-local pytest and hard-constraint grep.
- `global-lint`: coordinator runs manifest sync, owner reuse, bundle completeness, import boundary, and docs validation checks.
- `merge-ready`: coordinator updates manifest readiness, known provider index, shared docs, and PR summary.

## State Machine

State file path defaults to `docs/ai-onboarding/onboarding-state.json`. The schema is `docs/ai-onboarding/onboarding-state.schema.json`.

Provider status values:

- `in_progress`
- `blocked`
- `merge_ready`
- `completed`

Task status values:

- `pending`
- `in_progress`
- `completed`
- `failed`
- `blocked`

Rules:

- `next` initializes missing provider state and marks the first pending task `in_progress`.
- `verify` writes a dry-run verification plan under `verifications.<task-id>` and does not modify provider code or docs.
- `advance` marks the requested task `completed` and moves exactly one next task to `in_progress`.
- Completing the final task clears `active_provider` and sets provider status to `merge_ready`.
- A second provider cannot become `in_progress` while another provider is active.
- Retry counters are stored per task.

## Retry

- Worker retry limit is 3.
- `WORKER_MODIFIED_FORBIDDEN_FILE` requires coordinator to discard or revert forbidden-path changes before retry.
- `UNSUITABLE_DOI_SAMPLE` from fixture capture routes back to `discover-manifest` and only replaces the failed `fixtures.doi_samples.<purpose>` object.
- Provider-local acceptance failure routes back to `implement-provider`.
- Retry count 3 sets provider status to `blocked` and stops the pipeline.

## Worker Isolation

Worker brief must include:

- `files_allowed_to_modify`
- `files_must_not_modify`
- `no_commit: true`

Shared files are coordinator-only at `merge-ready`:

- `docs/ai-onboarding/known-providers.yml`
- `docs/providers.md`
- `docs/extraction-rules.md`
- `CHANGELOG.md`

Forbidden central provider logic files for implementation worker:

- `src/paper_fetch/provider_catalog.py`
- `src/paper_fetch/extraction/html/provider_rules.py`
- `src/paper_fetch/quality/html_signals.py`
- `src/paper_fetch/quality/html_availability.py`

## Worker Prompt Input

Discovery worker prompt must inline:

- discovery brief YAML
- `docs/ai-onboarding/provider-manifest.schema.json`
- `docs/ai-onboarding/hard-constraints.md`

Implementation worker prompt must inline:

- implementation brief YAML
- `docs/ai-onboarding/hard-constraints.md`
- current provider manifest YAML

Worker must not read README, audit documents, or chat history as provider behavior input.

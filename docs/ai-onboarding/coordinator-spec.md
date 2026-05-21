# Coordinator Spec

本文定义 S14 coordinator 的机器可验证编排规则。

## Invocation

`/onboard <name>` 对应的本地入口是：

```bash
python3 scripts/onboard_from_manifests.py start --provider <name> --domain <domain> --dry-run --output-dir <dir>
python3 scripts/onboard_from_manifests.py start --manifest docs/ai-onboarding/manifests/<name>.yml --dry-run --output-dir <dir>
python3 scripts/onboard_from_manifests.py run --provider <name> --domain <domain> --output-dir <dir>
python3 scripts/onboard_from_manifests.py run --manifest docs/ai-onboarding/manifests/<name>.yml --until merge-ready
python3 scripts/onboard_from_manifests.py next --provider <name>
python3 scripts/onboard_from_manifests.py verify --provider <name> --task <task-id>
python3 scripts/onboard_from_manifests.py run-checks --provider <name> --task <task-id>
python3 scripts/onboard_from_manifests.py run-checks --provider <name> --all-local
python3 scripts/onboard_from_manifests.py advance --provider <name> --task <task-id>
```

`PROVIDER_ONBOARDING_AGENT_CLI` records the operator-selected coding agent CLI. `start` only writes task DAG, task brief, verification plan, and coordinator state. `run` may call that local CLI through subprocess with prompt stdin, but must not call an LLM SDK or vendor client.

## Runtime

- Coordinator is one long-running coding agent CLI session.
- Worker is one child agent task with isolated context and no commit right.
- Worker dispatch uses the selected coding agent CLI; `run` invokes only `PROVIDER_ONBOARDING_AGENT_CLI` and stores prompt/stdout/stderr logs under `<output-dir>/workers/`.
- The script must not call any LLM SDK or vendor client.
- The script must not run a GitHub Actions matrix.
- Provider onboarding is serial across providers.
- Task execution is serial inside one provider.
- One coordinator state file may contain at most one provider with `status: in_progress`.
- Worker output remains in the workspace; coordinator owns verification, shared-file updates, and commit preparation.

## Task DAG

The provider DAG is ordered:

1. `operator-access-preflight`
2. `discover-manifest`
3. `validate-manifest`
4. `capture-fixtures`
5. `scaffold`
6. `implement-provider`
7. `shared-integration`
8. `snapshot-expected`
9. `manifest-sync-back`
10. `provider-local-acceptance`
11. `global-lint`
12. `merge-ready`

`operator-access-preflight` validates `docs/ai-onboarding/access-reviews/<provider>.yml` against `docs/ai-onboarding/access-review.schema.json`. Required operator decisions are legal access mode, allowed runtime, forbidden behaviors, CAPTCHA/challenge policy, temporary site policy, and `may_continue: true`. Missing, blocked, or schema-invalid access review prevents discovery worker dispatch.

`start --provider` includes all 12 tasks and writes `briefs/discover-manifest.yml` plus `briefs/implement-provider.yml`.

`start --manifest` skips `discover-manifest`, reads the provider name from the manifest YAML, and writes `briefs/implement-provider.yml`; it does not skip `operator-access-preflight`.

## Task Ownership

- `operator-access-preflight`: operator writes and approves `docs/ai-onboarding/access-reviews/<provider>.yml`; coordinator validates it before discovery.
- `discover-manifest`: coordinator dispatches discovery worker with the access review as constraints only.
- `validate-manifest`: coordinator validates schema, known-provider conflict, draft state, and DOI sample evidence.
- `capture-fixtures`: coordinator runs `scripts/capture_fixture.py --from-manifest <manifest> --all --auto-via --fail-fast`.
- `scaffold`: coordinator runs `scripts/scaffold_provider.py --from-manifest --merge-existing=safe`; existing outputs are reused when safe, otherwise produce a merge plan JSON instead of deleting user work.
- `implement-provider`: coordinator dispatches implementation worker with access review constraints.
- `shared-integration`: coordinator integrates shared surfaces after provider-owned implementation, including `provider_catalog`, MCP status/instructions/schema, golden/live review, benchmark samples, shared renderer/workflow gaps, shared docs, and changelog entries. Each shared edit must trace to manifest facts, bundle sync-back, fixture replay, or provider-local test evidence.
- `snapshot-expected`: coordinator enumerates every non-null manifest DOI sample and `extra_fixtures[].doi`, runs `scripts/snapshot_expected.py --doi <doi> --review`, runs `scripts/snapshot_expected.py --doi <doi>`, and checks fixture directory, `expected.json`, and non-pending `expected_outcome`.
- `manifest-sync-back`: coordinator runs `scripts/manifest_sync_back.py --sync-docs`.
- `provider-local-acceptance`: coordinator runs provider-local pytest, review artifact validation, hard-constraint grep, and provider subset live review for browser/CDN-risk providers.
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
- `run-checks --task` executes the same local command plan for one task and records result details under `runs.<task-id>`.
- `run-checks --all-local` runs access review, manifest, review/provider-local acceptance, shared integration, and global lint gates without triggering GitHub CI or the live review command.
- `verify --task operator-access-preflight` and `verify --task discover-manifest` require an approved access review.
- `advance` marks the requested task `completed` and moves exactly one next task to `in_progress`.
- `advance --task operator-access-preflight` validates access review approval before moving to `discover-manifest`.
- Completing the final task clears `active_provider` and sets provider status to `merge_ready`.
- A second provider cannot become `in_progress` while another provider is active.
- Retry counters are stored per task.
- `run --until <task>` executes the same DAG inclusively through `<task>` and leaves the next task in state for continuation.

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

Shared files are coordinator-only at `shared-integration` or `merge-ready`:

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
- approved access review YAML
- `docs/ai-onboarding/provider-manifest.schema.json`
- `docs/ai-onboarding/hard-constraints.md`

Implementation worker prompt must inline:

- implementation brief YAML
- approved access review YAML
- `docs/ai-onboarding/hard-constraints.md`
- current provider manifest YAML

Worker must not read README, audit documents, or chat history as provider behavior input.

`run` checks git changed paths before and after each worker attempt. A new changed path matching `files_must_not_modify` fails the task with `WORKER_MODIFIED_FORBIDDEN_FILE`.

# Agent Task Brief

Task brief 是 coordinator 派给 worker 的唯一输入。Worker 必须只按 brief 中的字段执行，不从 README、audit 文档或临时聊天记录推断额外写入范围。

## discover-manifest

`discover-manifest` brief 必须是 YAML object，并且必须包含下列 required keys：

```yaml
task_id: mdpi-discover-manifest
current_step: discover-manifest
runtime: coding-agent-subagent
provider_seed:
  name: mdpi
  domain: mdpi.com
  doi_prefix_hint: null
output_manifest: docs/ai-onboarding/manifests/mdpi.yml
schema: docs/ai-onboarding/provider-manifest.schema.json
hard_constraints: docs/ai-onboarding/hard-constraints.md
search_requirements:
  routing:
    - doi_prefixes
    - domains
    - domain_suffixes
    - crossref_publisher
  doi_sample_purposes:
    - structure
    - table
    - formula
    - figure
    - supplementary
    - references
    - pdf_fallback
    - abstract_only
    - access_gate
    - empty_shell
files_allowed_to_modify:
  - docs/ai-onboarding/manifests/mdpi.yml
files_must_not_modify:
  - src/
  - tests/
  - docs/providers.md
  - CHANGELOG.md
no_commit: true
```

### Required Keys

- `task_id` must be `<provider>-discover-manifest`.
- `current_step` must be `discover-manifest`.
- `runtime` must be `coding-agent-subagent`.
- `provider_seed.name` must be the normalized provider id.
- `provider_seed.domain` may be null, but the key must exist.
- `provider_seed.doi_prefix_hint` may be null, but the key must exist.
- `output_manifest` must be the exact manifest path the worker may write.
- `schema` must be `docs/ai-onboarding/provider-manifest.schema.json`.
- `hard_constraints` must be `docs/ai-onboarding/hard-constraints.md`.
- `search_requirements.routing` must contain `doi_prefixes`, `domains`, `domain_suffixes`, and `crossref_publisher`.
- `search_requirements.doi_sample_purposes` must contain `structure`, `table`, `formula`, `figure`, `supplementary`, `references`, `pdf_fallback`, `abstract_only`, `access_gate`, and `empty_shell`.
- `files_allowed_to_modify` must contain exactly one path, equal to `output_manifest`.
- `files_must_not_modify` must contain `src/`, `tests/`, `docs/providers.md`, and `CHANGELOG.md`.
- `no_commit` must be `true`.

### Forbidden Writes

Discovery worker must not write any path outside `output_manifest`.

Forbidden paths include:

- `src/`
- `tests/`
- `docs/providers.md`
- `CHANGELOG.md`
- fixture directories
- provider implementation modules
- shared onboarding docs

Coordinator must treat any forbidden write as `WORKER_MODIFIED_FORBIDDEN_FILE` and discard that worker result before retrying.

## implement-provider

`implement-provider` brief 必须是 YAML object。Provider manifest 是唯一 provider 行为输入源。Worker 不得从 README、audit 文档、临时聊天记录或共享 docs 推断 provider 行为。

```yaml
task_id: mdpi-implement-provider
provider_manifest: docs/ai-onboarding/manifests/mdpi.yml
current_step: implement-provider
runtime: coding-agent-subagent
upstream_artifacts:
  task_dag: task-dag.json
  capture_commands: docs/ai-onboarding/capture-commands/mdpi.txt
  scaffold_summary: docs/ai-onboarding/scaffold/mdpi.json
hard_constraints: docs/ai-onboarding/hard-constraints.md
acceptance:
  pytest:
    - PYTHONPATH=src python3 -m pytest tests/unit/test_mdpi_provider.py -q
    - PYTHONPATH=src python3 -m pytest tests/unit/test_provider_bundle_completeness.py tests/unit/test_provider_owner_reuse.py -q
  grep_must_be_empty:
    - pattern: mdpi
      paths:
        - src/paper_fetch/extraction/html/provider_rules.py
        - src/paper_fetch/quality/html_signals.py
        - src/paper_fetch/quality/html_availability.py
files_allowed_to_modify:
  - src/paper_fetch/providers/mdpi.py
  - src/paper_fetch/providers/_mdpi_html.py
  - tests/unit/test_mdpi_provider.py
files_must_not_modify:
  - docs/ai-onboarding/manifests/mdpi.yml
  - docs/ai-onboarding/known-providers.yml
  - docs/providers.md
  - docs/extraction-rules.md
  - CHANGELOG.md
  - src/paper_fetch/provider_catalog.py
  - src/paper_fetch/extraction/html/provider_rules.py
  - src/paper_fetch/quality/html_signals.py
  - src/paper_fetch/quality/html_availability.py
failure_recovery:
  policy: docs/ai-onboarding/failure-recovery.md
  max_retries: 3
  forbidden_write_code: WORKER_MODIFIED_FORBIDDEN_FILE
  acceptance_failure_retry_task: implement-provider
  blocked_after_retry_exhaustion: true
no_commit: true
```

### implement-provider Required Keys

- `task_id` must be `<provider>-implement-provider`.
- `provider_manifest` must be the manifest path for the provider.
- `current_step` must be `implement-provider`.
- `runtime` must be `coding-agent-subagent`.
- `upstream_artifacts` must include `task_dag`, `capture_commands`, and `scaffold_summary`.
- `hard_constraints` must be `docs/ai-onboarding/hard-constraints.md`.
- `acceptance.pytest` must contain provider-local pytest.
- `acceptance.grep_must_be_empty` must contain central provider-logic grep checks.
- `files_allowed_to_modify` must only contain provider-specific implementation and provider-specific tests.
- `files_must_not_modify` must include manifest, shared docs, known provider index, and central provider logic files.
- `failure_recovery.policy` must be `docs/ai-onboarding/failure-recovery.md`.
- `failure_recovery.max_retries` must be `3`.
- `failure_recovery.acceptance_failure_retry_task` must be `implement-provider`.
- `no_commit` must be `true`.

### implement-provider Prompt

Coordinator must inline these inputs when dispatching the worker through the selected coding agent CLI:

- implementation brief YAML
- `docs/ai-onboarding/hard-constraints.md`
- current provider manifest YAML

The worker must return a structured summary containing changed files, tests run, grep checks run, and unresolved failures.

## coordinator-only scaffold/from-manifest

`scaffold` is a coordinator action. Coordinator must run:

```bash
python3 scripts/scaffold_provider.py --from-manifest docs/ai-onboarding/manifests/mdpi.yml
```

Rules:

- `--from-manifest` must not be combined with legacy scaffold inputs including `--name`, `--doi`, `--source`, `--fulltext-client`, or `--html-capable`.
- Command stdout is JSON artifact summary.
- Coordinator records `generated_files` and `docs_files` as upstream artifacts for `implement-provider`.
- If scaffold exits with `MANIFEST_SCHEMA_INVALID`, coordinator routes the JSON stderr to manifest repair.

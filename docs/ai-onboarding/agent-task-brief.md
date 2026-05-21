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
access_review: docs/ai-onboarding/access-reviews/mdpi.yml
access_policy_constraints:
  source: docs/ai-onboarding/access-reviews/mdpi.yml
  operator_gate: operator-access-preflight
  worker_must_not_infer_access_policy: true
  discovery_may_only_use_review_as_constraints: true
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
- `access_review` must point to `docs/ai-onboarding/access-reviews/<provider>.yml`.
- `access_policy_constraints.worker_must_not_infer_access_policy` must be `true`.
- Discovery may use the access review only as operator constraints. It must not decide that login, CAPTCHA handling, challenge bypass, paywall bypass, or temporary site policy is acceptable.
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
access_review: docs/ai-onboarding/access-reviews/mdpi.yml
access_policy_constraints:
  source: docs/ai-onboarding/access-reviews/mdpi.yml
  must_follow_operator_review: true
  do_not_auto_login: true
  do_not_solve_captcha: true
  do_not_bypass_paywall_or_challenge: true
  challenge_or_permission_uncertainty: stop_and_report
upstream_artifacts:
  task_dag: task-dag.json
  capture_commands: docs/ai-onboarding/capture-commands/mdpi.txt
  scaffold_summary: docs/ai-onboarding/scaffold/mdpi.json
hard_constraints: docs/ai-onboarding/hard-constraints.md
markdown_review_loop:
  required: true
  fixture_source: provider_manifest.fixtures.doi_samples + provider_manifest.extra_fixtures
  route_contract_source: provider_manifest.route_contract
  markdown_contract_source: provider_manifest.markdown_contract
  require_each_non_null_purpose_asserted: true
  require_positive_and_negative_markdown_assertions: true
  forbid_skipped_scaffold_placeholder: true
coordinator_integration_scope:
  route_sources: provider_manifest.route_sources maps main_path steps to runtime sources.
  extra_fixtures: provider_manifest.extra_fixtures extends capture and Markdown review beyond fixed purpose slots.
  post_worker_integrations:
    - golden corpus adapter wiring
    - runtime source/schema registration
    - manifest/bundle sync-back
output_requirements:
  review_artifact: docs/ai-onboarding/reviews/mdpi.yml
  reviewed_fixtures: one entry per non-null provider_manifest.fixtures.doi_samples purpose and per provider_manifest.extra_fixtures item
  reviewed_fixture_fields:
    - fixture
    - purpose
    - issue
    - assertion
    - fix
acceptance:
  pytest:
    - PYTHONPATH=src python3 -m pytest tests/unit/test_mdpi_provider.py -q
    - PYTHONPATH=src python3 -m pytest tests/unit/test_provider_markdown_review_contract.py -q
    - PYTHONPATH=src python3 -m pytest tests/unit/test_provider_route_contract.py -q
    - PYTHONPATH=src python3 -m pytest tests/unit/test_provider_bundle_completeness.py tests/unit/test_provider_owner_reuse.py -q
  grep_must_be_empty:
    - pattern: mdpi
      paths:
        - src/paper_fetch/extraction/html/provider_rules.py
        - src/paper_fetch/quality/html_signals.py
        - src/paper_fetch/quality/html_availability.py
  live_review:
    required_for_browser_or_cdn_risk: true
    command: PAPER_FETCH_RUN_LIVE=1 python3 scripts/run_golden_criteria_live_review.py --providers mdpi
    source_contract: provider_manifest.route_sources
    markdown_contract: provider_manifest.markdown_contract
files_allowed_to_modify:
  - src/paper_fetch/providers/mdpi.py
  - src/paper_fetch/providers/_mdpi_html.py
  - tests/unit/test_mdpi_provider.py
  - docs/ai-onboarding/reviews/mdpi.yml
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
- `access_review` must point to the approved operator access review.
- `access_policy_constraints` must require no automatic login, no CAPTCHA solving, no paywall/challenge bypass, and stop/report on challenge or permission uncertainty.
- `upstream_artifacts` must include `task_dag`, `capture_commands`, and `scaffold_summary`.
- `hard_constraints` must be `docs/ai-onboarding/hard-constraints.md`.
- `markdown_review_loop.required` must be `true`.
- `markdown_review_loop.fixture_source` must be `provider_manifest.fixtures.doi_samples + provider_manifest.extra_fixtures`.
- `markdown_review_loop.route_contract_source` must be `provider_manifest.route_contract`.
- `markdown_review_loop.markdown_contract_source` must be `provider_manifest.markdown_contract`.
- `markdown_review_loop.require_each_non_null_purpose_asserted` must be `true`.
- `markdown_review_loop.require_positive_and_negative_markdown_assertions` must be `true`.
- `markdown_review_loop.forbid_skipped_scaffold_placeholder` must be `true`.
- `coordinator_integration_scope` must identify route source mapping, extra fixtures, golden corpus adapter wiring, runtime source/schema registration, and manifest/bundle sync-back as coordinator integration scope when they exceed provider-owned worker files.
- `output_requirements.review_artifact` must be `docs/ai-onboarding/reviews/<provider>.yml`.
- `output_requirements.reviewed_fixtures` must require one entry per non-null manifest fixture purpose and per `extra_fixtures` item.
- `output_requirements.reviewed_fixture_fields` must contain `fixture`, `purpose`, `issue`, `assertion`, and `fix`.
- `acceptance.pytest` must contain provider-local pytest.
- `acceptance.pytest` must contain `tests/unit/test_provider_markdown_review_contract.py`.
- `acceptance.pytest` must contain `tests/unit/test_provider_route_contract.py`.
- `acceptance.grep_must_be_empty` must contain central provider-logic grep checks.
- `acceptance.live_review` must declare whether provider subset live review is required for browser/CDN risk and must point to `route_sources` plus `markdown_contract`.
- `files_allowed_to_modify` must only contain provider-specific implementation, provider-specific tests, and the provider review artifact.
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
It must also write `docs/ai-onboarding/reviews/<provider>.yml`: one entry per non-null `fixtures.doi_samples.<purpose>` and per `extra_fixtures` item, with `sample_representative`, `markdown_semantic_reviewed`, `issues`, `assertions`, and `fixes`. If a fixture has no finding, the entry must still name the fixture and purpose and state that baseline Markdown was reviewed. The worker must turn every `markdown_contract.<purpose>` and every extra fixture `markdown_contract` item into provider-local assertions before changing extraction code, and must turn every `route_contract.<step>` rejection rule into a route or fallback test before accepting that route as implemented.

## coordinator-only scaffold/from-manifest

`scaffold` is a coordinator action. Coordinator must run:

```bash
python3 scripts/scaffold_provider.py --from-manifest docs/ai-onboarding/manifests/mdpi.yml --merge-existing=safe
```

Rules:

- `--from-manifest` must not be combined with legacy scaffold inputs including `--name`, `--doi`, `--source`, `--fulltext-client`, or `--html-capable`.
- Command stdout is JSON artifact summary.
- If outputs already exist, `--merge-existing=safe` reuses identical files and complete existing provider files. Real conflicts still return `status: MERGE_PLAN` with existing paths, manifest sample conflicts, and diff previews.
- Coordinator records `generated_files` and `docs_files` as upstream artifacts for `implement-provider`.
- If scaffold exits with `MANIFEST_SCHEMA_INVALID`, coordinator routes the JSON stderr to manifest repair.

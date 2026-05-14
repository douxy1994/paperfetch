# AI Onboarding Hard Constraints

Worker 和 coordinator 必须满足下列机器可判约束。

## Worker Scope

- `runtime` must be `coding-agent-subagent`.
- Worker must not commit.
- Worker may only modify paths listed in `files_allowed_to_modify`.
- Worker must not modify paths listed in `files_must_not_modify`.
- Worker must not edit `docs/ai-onboarding/known-providers.yml`.
- Worker must not edit shared docs: `docs/providers.md`, `docs/extraction-rules.md`, `CHANGELOG.md`.
- Worker must not write API keys, tokens, FlareSolverr endpoint URLs, or local secret file paths into manifest, docs, tests, or task brief output.

## Provider Logic

- Provider-specific implementation belongs under `src/paper_fetch/providers/`.
- Provider-specific tests belong under `tests/unit/test_<provider>_provider.py`.
- Provider-specific functions must not be added to `src/paper_fetch/extraction/html/provider_rules.py`.
- Provider-specific functions must not be added to `src/paper_fetch/quality/html_signals.py`.
- Provider-specific functions must not be added to `src/paper_fetch/quality/html_availability.py`.
- Provider routing, asset profile, probe requirements, fixture purposes, and docs source name must come from the provider manifest.
- Worker must not infer provider behavior from `docs/provider-development.md`, `docs/adding-a-provider.md`, README files, audit files, or chat history.

## Acceptance

- Provider-local pytest listed in the task brief must pass.
- `python3 scripts/validate_extraction_rules.py` must pass before merge-ready.
- `PYTHONPATH=src python3 -m pytest tests/unit/test_manifest_bundle_sync.py -q` must pass before merge-ready.
- `PYTHONPATH=src python3 -m pytest tests/unit/test_provider_bundle_completeness.py tests/unit/test_provider_owner_reuse.py -q` must pass before merge-ready.
- `manifest_sync_back.py` is the only allowed writer for sync-back fields in `extraction_hints` and `success_criteria`.

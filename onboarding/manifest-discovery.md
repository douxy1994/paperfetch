# Manifest Discovery

`discover-manifest` 是 AI onboarding 的第一个 worker step。它必须等 `operator-access-preflight` 通过后运行，把 provider 种子转换成带证据的 `ProviderManifest`，供后续 `validate-manifest`、`capture-fixtures`、`propose-cleaning-chain`、`scaffold` 和 `implement-provider` 使用。Coordinator DAG 和状态机规则见 `onboarding/coordinator-spec.md`。

## Worker Input

Coordinator 给 discovery worker 的输入必须是 task brief，不是自然语言 onboarding 文档：

```yaml
task_id: mdpi-discover-manifest
current_step: discover-manifest
runtime: coding-agent-subagent
provider_seed:
  name: mdpi
  domain: mdpi.com
  doi_prefix_hint: null
output_manifest: onboarding/manifests/mdpi.yml
access_review: onboarding/access-reviews/mdpi.yml
access_policy_constraints:
  source: onboarding/access-reviews/mdpi.yml
  operator_gate: operator-access-preflight
  worker_must_not_infer_access_policy: true
  discovery_may_only_use_review_as_constraints: true
schema: onboarding/provider-manifest.schema.json
hard_constraints: onboarding/hard-constraints.md
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
  - onboarding/manifests/mdpi.yml
files_must_not_modify:
  - src/
  - tests/
  - docs/providers.md
  - CHANGELOG.md
no_commit: true
```

Discovery worker 只能写 `output_manifest`。它不能写代码、fixture、tests、shared docs，也不能 commit。它只能把 access review 当作 operator 约束输入，不能自行推断自动登录、CAPTCHA 处理、challenge/paywall 绕过或临时站点策略可行。

机器可判规则：

- `task_id` must equal `<provider>-discover-manifest`.
- `current_step` must equal `discover-manifest`.
- `runtime` must equal `coding-agent-subagent`.
- `access_review` must point to `onboarding/access-reviews/<provider>.yml`.
- `access_policy_constraints.worker_must_not_infer_access_policy` must be `true`.
- `files_allowed_to_modify` must contain exactly one path, equal to `output_manifest`.
- `files_must_not_modify` must contain `src/`, `tests/`, `docs/providers.md`, and `CHANGELOG.md`.
- `no_commit` must be `true`.

## Search Evidence Requirements

Discovery worker 必须为这些字段找公开证据：

- `routing.doi_prefixes`
- `routing.domains`
- `routing.domain_suffixes`
- `routing.crossref_publisher`
- `main_path`
- `route_contract`
- `markdown_contract`
- `asset_profile`
- `supplementary_scope`
- `abstract_only_strategy`
- `probe`
- `fixtures.doi_samples`

可用证据包括 publisher article pages、DOI landing pages、Crossref/OpenAlex 结果、公开 PDF/HTML 链接和页面中可观察到的 DOM/text signal。

每个 evidence 必须满足：

- `evidence_url` is an HTTP(S) URL or a stable DOI landing URL.
- `evidence_reason` explains which observed signal supports the manifest field.
- `observed_signals` is a non-empty list for every DOI sample with a DOI.
- Crossref/OpenAlex evidence must identify the publisher or DOI prefix it supports.
- Publisher article page evidence must identify whether it supports HTML structure, assets, supplementary material, references, gated access, abstract-only behavior, or PDF fallback.
- Search notes must be represented in manifest fields; do not write separate scratch files.

## DOI Sample Evidence

`fixtures.doi_samples` 的每个 purpose 必须是对象：

```yaml
structure:
  doi: "10.3390/membranes15030093"
  evidence_url: "https://www.mdpi.com/..."
  evidence_reason: "Landing page exposes a normal article body with headings and figures."
  observed_signals: ["html_body", "figures", "references"]
  confidence: high
```

固定 purpose 集合：

- `structure`
- `table`
- `formula`
- `figure`
- `supplementary`
- `references`
- `pdf_fallback`
- `abstract_only`
- `access_gate`
- `empty_shell`

`structure`、`figure`、`references` 在 draft 状态也必须有 DOI。其他 purpose 找不到样本时允许 `doi: null`，但 `evidence_reason` 必须说明搜索失败原因。

## Output Schema

Discovery worker 必须写一个 `ProviderManifest` YAML 到 `output_manifest`，并且必须通过 `onboarding/provider-manifest.schema.json`。

输出必须满足：

- No `TODO`, `TBD`, or `unknown` placeholder values.
- `routing.doi_prefixes`, `routing.domains`, `routing.domain_suffixes`, and `routing.crossref_publisher` are evidence-backed.
- `fixtures.doi_samples` contains all fixed purpose keys listed above.
- `route_contract` contains every `main_path` step and describes success/rejection signals.
- `markdown_contract` contains every non-null DOI sample purpose and gives positive/negative Markdown assertions.
- Each sample object contains `doi`, `evidence_url`, `evidence_reason`, `observed_signals`, and `confidence`.
- `confidence` values are only `high`, `medium`, or `low`.
- `doi: null` is allowed only when evidence explains the failed search for that purpose.
- `structure`, `figure`, and `references` must not use `doi: null` while the manifest is draft.

## Generation Metadata

Discovery worker 必须写 `generation`：

```yaml
generation:
  generated_by: ai_discovery
  generated_at: "2026-05-14T00:00:00Z"
  source_queries:
    - "MDPI DOI prefix articles supplementary materials"
  confidence: high
```

`source_queries` 记录实际搜索 query。`confidence` 只能是 `high`、`medium`、`low`。

## Retry Rules

Discovery 阶段只使用结构化错误：

- `MANIFEST_DISCOVERY_FAILED`
- `MANIFEST_SCHEMA_INVALID`
- `MANIFEST_PROVIDER_CONFLICT`
- `UNSUITABLE_DOI_SAMPLE`

`UNSUITABLE_DOI_SAMPLE` 由后续 `capture-fixtures` 返回时，coordinator 必须重新派 discovery worker，只替换失败 purpose 的 DOI sample 和 evidence。

Retry 必须遵守：

- `MANIFEST_DISCOVERY_FAILED`: rerun discovery from the same provider seed or mark the provider blocked after retry budget is exhausted.
- `MANIFEST_SCHEMA_INVALID`: keep `output_manifest` as the only writable file and repair schema-invalid fields only.
- `MANIFEST_PROVIDER_CONFLICT`: stop before fixture capture and require coordinator review.
- `UNSUITABLE_DOI_SAMPLE`: replace only the failed `fixtures.doi_samples.<purpose>` object and keep unrelated samples unchanged.
- Retry output must still pass the same `files_allowed_to_modify`, `files_must_not_modify`, and `no_commit` checks.

## Acceptance

Discovery 输出完成后必须满足：

- Manifest 通过 `provider-manifest.schema.json`
- 没有 `TODO`、`TBD`、`unknown`
- 每个 DOI sample 有 evidence object
- Worker 没有修改 `files_must_not_modify`
- `scripts/onboard_from_manifests.py start --provider <name> --domain <domain> --dry-run` 生成的 DAG 含 `discover-manifest`
- DAG 中 `operator-access-preflight` 位于 `discover-manifest` 之前
- `scripts/onboard_from_manifests.py start --provider <name> --domain <domain> --dry-run` 写 `briefs/discover-manifest.yml` 和 `briefs/implement-provider.yml`
- `scripts/onboard_from_manifests.py start --manifest <manifest> --dry-run` 跳过 `discover-manifest`，并从 manifest YAML 读取 provider name

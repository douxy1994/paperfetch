# Failure Recovery

Coordinator 必须按结构化 error code 决定恢复动作。

| Code | Source Step | Retry Target | Coordinator Action |
|---|---|---|---|
| `MANIFEST_DISCOVERY_FAILED` | `discover-manifest` | `discover-manifest` | 重新派 discovery worker；retry 用尽后标记 provider `blocked`。 |
| `MANIFEST_SCHEMA_INVALID` | `validate-manifest` / `scaffold` | `discover-manifest` | 把 JSON stderr 回派给 discovery worker，只修 manifest schema 字段。 |
| `MANIFEST_PROVIDER_CONFLICT` | `validate-manifest` | none | 停在当前 provider，等待 coordinator 裁决。 |
| `UNSUITABLE_DOI_SAMPLE` | `capture-fixtures` | `discover-manifest` | 只替换失败 purpose 的 `fixtures.doi_samples.<purpose>` 对象。 |
| `HTTP_FORBIDDEN` | `capture-fixtures` | `capture-fixtures` with `--retry-via=flaresolverr` when allowed | 如果 manifest `probe.requires_flaresolverr=true` 或 coordinator policy 允许 challenge retry，则用 FlareSolverr 路线重跑；否则回派 discovery worker 替换该 purpose DOI。 |
| `HTTP_RATE_LIMITED` | `capture-fixtures` | `capture-fixtures` | 等待 provider backoff 后有限重跑；retry 用尽后标记 provider `blocked`，不要让 worker 手写 URL 绕过 manifest。 |
| `CHALLENGE_DETECTED` | `capture-fixtures` | `capture-fixtures` with `--retry-via=flaresolverr` | 只在 manifest 允许或 first attempt 已结构化识别 challenge 时启用 FlareSolverr；不可进入人工 fallback。 |
| `FLARESOLVERR_REQUIRED` | `capture-fixtures` | environment setup | 当前非交互 capture 无法完成 FlareSolverr 路线；coordinator 应检查运行环境或将 provider 暂停为 `blocked`。 |
| `BROWSER_RUNTIME_REQUIRED` | `capture-fixtures` | environment setup | 当前非交互 capture 需要 Playwright/browser runtime；coordinator 应修复环境后重跑，不派 worker LLM。 |
| `NON_PDF_FALLBACK_CONTENT` | `capture-fixtures` | `discover-manifest` | `pdf_fallback` DOI 返回 HTML wrapper 或非 PDF 内容，替换该 purpose DOI/evidence。 |
| `ACCESS_GATE_CAPTURED` | `capture-fixtures` | `discover-manifest` | 普通内容 purpose 捕获到 access gate，替换该 purpose DOI；只有 `access_gate` purpose 可接受 access gate fixture。 |
| `EMPTY_ARTICLE_SHELL` | `capture-fixtures` | `discover-manifest` | 普通内容 purpose 捕获到空壳 HTML，替换该 purpose DOI；只有 `empty_shell` purpose 可接受空壳 fixture。 |
| `NETWORK_TRANSIENT` | `capture-fixtures` | `capture-fixtures` | DNS/TLS/timeout/5xx 等 transient 失败按 provider retry budget 重跑；用尽后 `TASK_RETRY_EXHAUSTED`。 |
| `WORKER_MODIFIED_FORBIDDEN_FILE` | any worker step | current worker step | coordinator 丢弃或 revert forbidden-path diff 后重派 worker。 |
| `MANIFEST_CODE_DRIFT` | `global-lint` | `implement-provider` | 重派 implementation worker 修代码；sync-back 字段只能由 `manifest_sync_back.py` 写入。 |
| `TASK_RETRY_EXHAUSTED` | any retryable step | none | provider 状态置为 `blocked`，pipeline 停止在当前 provider。 |

Retry count is stored in `docs/ai-onboarding/onboarding-state.json` and must not exceed `3` for worker tasks.

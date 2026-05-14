# Failure Recovery

Coordinator 必须按结构化 error code 决定恢复动作。

| Code | Source Step | Retry Target | Coordinator Action |
|---|---|---|---|
| `MANIFEST_DISCOVERY_FAILED` | `discover-manifest` | `discover-manifest` | 重新派 discovery worker；retry 用尽后标记 provider `blocked`。 |
| `MANIFEST_SCHEMA_INVALID` | `validate-manifest` / `scaffold` | `discover-manifest` | 把 JSON stderr 回派给 discovery worker，只修 manifest schema 字段。 |
| `MANIFEST_PROVIDER_CONFLICT` | `validate-manifest` | none | 停在当前 provider，等待 coordinator 裁决。 |
| `UNSUITABLE_DOI_SAMPLE` | `capture-fixtures` | `discover-manifest` | 只替换失败 purpose 的 `fixtures.doi_samples.<purpose>` 对象。 |
| `WORKER_MODIFIED_FORBIDDEN_FILE` | any worker step | current worker step | coordinator 丢弃或 revert forbidden-path diff 后重派 worker。 |
| `MANIFEST_CODE_DRIFT` | `global-lint` | `implement-provider` | 重派 implementation worker 修代码；sync-back 字段只能由 `manifest_sync_back.py` 写入。 |
| `TASK_RETRY_EXHAUSTED` | any retryable step | none | provider 状态置为 `blocked`，pipeline 停止在当前 provider。 |

Retry count is stored in `docs/ai-onboarding/onboarding-state.json` and must not exceed `3` for worker tasks.

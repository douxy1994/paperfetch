# AI Onboarding Automation Roadmap

本文记录 provider onboarding 中可以由脚本 / agent 自动完成的部分，以及必须由 operator 保留的人工边界。它补充 [`README.md`](./README.md)、[`coordinator-spec.md`](./coordinator-spec.md) 和 [`acceptance.md`](./acceptance.md)，不替代 manifest、access review 或 provider review schema。

## 可自动化项

- `scripts/onboard_from_manifests.py run` 串行执行 provider DAG，并持久化 state、DAG、worker brief、worker stdout/stderr/prompt 日志。
- `scripts/capture_fixture.py --auto-via` 根据 manifest `probe.requires_browser_runtime` / `probe.requires_playwright` 和 access review `allowed_runtimes` 选择 `http` 或 `browser`。
- fixture capture 对 `HTTP_FORBIDDEN`、`HTTP_RATE_LIMITED`、`CHALLENGE_DETECTED` 可在 access review 允许 browser runtime 时自动 retry 到 browser route；否则返回 structured JSON。
- `scripts/scaffold_provider.py --from-manifest --merge-existing=safe` 复用相同内容，保留完整已有 provider 文件，并继续生成 fixture/capture/scaffold summary。
- `scripts/bootstrap_review_artifact.py` 从 manifest non-null fixtures 和 `extra_fixtures` 生成 review 草稿，填入 `expected.json` 路径、sha256、manifest assertions 和初始问题分类。
- `scripts/manifest_sync_back.py --sync-docs` 从 manifest docs facts 同步 `known-providers.yml`、provider matrix、extraction rules marker row 和 changelog marker entry。

## 不可自动化边界

- access approval 不能由脚本伪造；`docs/ai-onboarding/access-reviews/<provider>.yml` 必须由 operator 批准，且 `may_continue: true`。
- CAPTCHA、paywall、challenge、登录和权限不确定时，脚本不得绕过；只能按 access review 和 [`failure-recovery.md`](./failure-recovery.md) stop / retry / report。
- `markdown_semantic_reviewed: true` 不能由 bootstrap 自动设置；最终 Markdown 语义审查签字必须来自 worker/operator 的真实阅读结论。
- worker 不得修改 shared docs、central provider logic 或未授权路径；runner 会用 git changed-path diff 检测 forbidden writes。
- GitHub CI 不由 onboarding runner 触发；本地 gate 只运行 repo-local commands。

## Runner 命令

```bash
python3 scripts/onboard_from_manifests.py run \
  --provider mdpi \
  --domain mdpi.com \
  --output-dir .paper-fetch-runs/mdpi-onboarding

python3 scripts/onboard_from_manifests.py run \
  --manifest docs/ai-onboarding/manifests/mdpi.yml \
  --until merge-ready
```

`--until <task>` 是 inclusive cutoff；完成该 task 后停止，并把下一步保留在 state 中。`--state` 默认写 `docs/ai-onboarding/onboarding-state.json`。

## Worker Dispatch 契约

- runner 只通过 `PROVIDER_ONBOARDING_AGENT_CLI` 调用外部本地 agent CLI，不接入 LLM SDK。
- prompt 通过 stdin 输入，内容包含 worker brief、access review、hard constraints，以及 discovery schema 或当前 manifest。
- 日志写入 `<output-dir>/workers/<task>-attempt-N.{prompt.md,stdout.log,stderr.log}`。
- 调用前后读取 git changed paths；新增 forbidden path 变更会以 `WORKER_MODIFIED_FORBIDDEN_FILE` 失败。
- worker retry limit 是 3；CLI 非零退出耗尽后返回 `TASK_RETRY_EXHAUSTED`。

## Live 策略

- browser/CDN-risk provider 默认需要 provider subset live review，例如：

```bash
PAPER_FETCH_RUN_LIVE=1 python3 scripts/run_golden_criteria_live_review.py --providers mdpi
```

- runner 的 `provider-local-acceptance` 会在 `_provider_requires_live_review()` 为 true 时包含 live review command。
- live review 必须比较 `FetchEnvelope.source` 与 manifest `route_sources`，并复用 `markdown_contract` 做自动内容 / 噪声分类。

## Failure Recovery 映射

- `ACCESS_REVIEW_NOT_FOUND` / `ACCESS_REVIEW_NOT_APPROVED`：停在 operator gate。
- `UNSUITABLE_DOI_SAMPLE`：回到 `discover-manifest`，只替换失败 purpose 的 DOI sample。
- `HTTP_FORBIDDEN` / `HTTP_RATE_LIMITED` / `CHALLENGE_DETECTED`：若 access review 允许 browser，capture 可自动 retry；否则 stop/report。
- `BROWSER_RUNTIME_REQUIRED`：operator 配置合法 browser runtime，或更新 access review / manifest。
- `WORKER_MODIFIED_FORBIDDEN_FILE`：coordinator 处理 forbidden path diff 后才能重派 worker。
- `PROVIDER_LOCAL_ACCEPTANCE_FAILED` / `GLOBAL_LINT_FAILED`：回到实现或 shared integration 修复；不靠 narrative waiver 通过。

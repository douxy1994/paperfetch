# Provider Onboarding Runbook

本文说明不同使用场景下如何选择 `/goal` runbook 和本地 coordinator 命令。权威输入仍是 `onboarding/` 目录；本文只做入口索引，不替代 manifest、access review、task brief、hard constraints 或 acceptance contract。

## Quick Decision Table

| 场景 | 使用入口 | 适用条件 |
|---|---|---|
| 从零添加 provider | `/goal follow onboarding/instruction.md 添加 <provider> provider` | 只有 provider 名称、domain 或 DOI prefix，需要 discovery、capture、scaffold、实现、验收全链路 |
| 已有 manifest 继续实现 | `python3 scripts/onboard_from_manifests.py run --manifest onboarding/manifests/<provider>.yml --until merge-ready` | manifest 已存在，想从当前 state 继续推进到 merge-ready |
| 已有 provider 查漏补缺 | `summarize` + `diagnose` + `run-checks --all-local` | provider 已有实现，需要找缺失 fixture、review、snapshot、contract 或 acceptance 缺口 |
| 单 DOI snapshot/quality 修复 | `check-snapshot`、`snapshot_expected.py`、`repair-markdown-quality` | 某个 DOI 的 `expected.json`、`extracted.md` 或 `markdown-quality.json` 缺失、过期或 fail |
| blocked state 恢复 | `diagnose` + `resume-blocked --dry-run` | state 中 provider 已 blocked，需要按 failure code 决定能否续跑 |
| 只做本地验收 | `python3 scripts/onboard_from_manifests.py run-checks --provider <provider> --all-local` | 不想推进 DAG，只想验证当前工作区状态 |

## Codex Goal Templates

从零实现：

```text
/goal follow onboarding/instruction.md 添加 <provider> provider，domain 是 <domain>。
使用 PROVIDER_ONBOARDING_AGENT_CLI 派发 worker，不触发 GitHub CI，不提交 commit。
遇到 access review、challenge、captcha、样本不可用或 retry exhaustion 时停止并报告 structured error code。
```

已有 manifest 继续实现：

```text
/goal follow onboarding/instruction.md 继续实现 provider <provider>。
优先运行 python3 scripts/onboard_from_manifests.py run --manifest onboarding/manifests/<provider>.yml --until merge-ready。
只使用 onboarding/ 权威输入和项目脚本；不要触发 GitHub CI，不要自动批准 access review。
```

查漏补缺：

```text
/goal 对已有 provider <provider> 做 onboarding 查漏补缺。
先运行 summarize、diagnose、run-checks --all-local 找缺口；按缺口使用 check-snapshot、snapshot_expected.py、repair-markdown-quality 或 resume-blocked。
不要自动把 markdown_semantic_reviewed 改为 true，不要改 access approval，不触发 GitHub CI。
```

Markdown quality repair：

```text
/goal 修复 provider <provider> 的 DOI <doi> Markdown quality failure。
先确认 markdown-quality.json 是 agent_prompt schema v2 的 fail 或含 blocking issue；pending report 只报告 MARKDOWN_QUALITY_REVIEW_PENDING。
使用 python3 scripts/onboard_from_manifests.py repair-markdown-quality --provider <provider> --doi <doi>。
```

## Command Recipes

从零或继续跑全链路：

```bash
python3 scripts/onboard_from_manifests.py run \
  --provider <provider> \
  --domain <domain> \
  --output-dir .paper-fetch-runs/<provider>-onboarding

python3 scripts/onboard_from_manifests.py run \
  --manifest onboarding/manifests/<provider>.yml \
  --until merge-ready
```

查漏补缺和恢复：

```bash
python3 scripts/onboard_from_manifests.py summarize \
  --provider <provider> \
  --format markdown \
  --output .paper-fetch-runs/<provider>-onboarding/summary.md

python3 scripts/onboard_from_manifests.py diagnose --provider <provider>
python3 scripts/onboard_from_manifests.py resume-blocked --provider <provider> --dry-run
python3 scripts/onboard_from_manifests.py run-checks --provider <provider> --all-local
```

单 DOI snapshot 和 quality：

```bash
PYTHONPATH=src python3 scripts/snapshot_expected.py --doi "<doi>" --review
PYTHONPATH=src python3 scripts/snapshot_expected.py --doi "<doi>"
python3 scripts/onboard_from_manifests.py check-snapshot --provider <provider> --doi "<doi>"

python3 scripts/onboard_from_manifests.py repair-markdown-quality \
  --provider <provider> \
  --doi "<doi>" \
  --output-dir .paper-fetch-runs/<provider>-markdown-repair
```

## Guardrails

- `PROVIDER_ONBOARDING_AGENT_CLI` 是唯一 worker dispatch 通道；不要从脚本里接入 LLM SDK。
- coordinator 负责 state、验证、snapshot、changed-path scope 检查和 failure recovery；worker 只做 brief 允许的窄范围任务。
- access review 必须由 operator 批准；脚本和 worker 不得把 blocked 草稿升级为 approved。
- `markdown_semantic_reviewed: true` 只能来自真实语义签字；bootstrap 和 repair 都不能自动设置。
- 不触发 GitHub CI；本地验收使用 repo-local commands。
- 多 provider 或多 DOI repair 不要在同一个工作区并发写入；需要并行时使用独立 worktree 后由 coordinator 串行合并。

## Expected Outputs

- Coordinator state：`onboarding/onboarding-state.json`，包含 runs、verifications 和 repairs 摘要。
- DAG/worker logs：`.paper-fetch-runs/<provider>-onboarding/`。
- Markdown repair logs：`.paper-fetch-runs/<provider>-markdown-repair/markdown-quality/<doi_slug>/attempt-N/`。
- Operator digest：`.paper-fetch-runs/<provider>-onboarding/summary.md`。
- Review artifact：`onboarding/reviews/<provider>.yml`，acceptance 不接受只写在 worker 回复里的审查结论。

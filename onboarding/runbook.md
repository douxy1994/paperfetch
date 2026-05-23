# Provider Onboarding Runbook

本文说明不同使用场景下如何选择 `/goal` runbook 和本地 coordinator 命令。权威输入仍是 `onboarding/` 目录；本文只做入口索引，不替代 manifest、access review、task brief、hard constraints 或 acceptance contract。

## Quick Decision Table

| 场景 | 使用入口 | 适用条件 |
|---|---|---|
| 从零添加 provider | `/goal follow onboarding/instruction.md 添加 <provider> provider` | 只有 provider 名称、domain 或 DOI prefix，需要 discovery、capture、scaffold、实现、验收全链路 |
| 已有 manifest 继续实现 | `python3 scripts/onboard_from_manifests.py run --manifest onboarding/manifests/<provider>.yml --until merge-ready` | manifest 已存在，想从当前 state 继续推进到 merge-ready |
| 已有 provider 查漏补缺 | `summarize` + `diagnose` + `run-checks --all-local` | provider 已有实现，需要找缺失 fixture、review、snapshot、contract 或 acceptance 缺口 |
| 单 DOI snapshot/quality 修复 | `check-snapshot`、`snapshot_expected.py`、`repair-markdown-quality` | 某个 DOI 的 `expected.json`、`extracted.md`、正文 figure 内联、fresh Markdown review 或 `markdown-quality.json` 缺失、过期或 fail |
| blocked state 恢复 | `diagnose` + `resume-blocked --dry-run` | state 中 provider 已 blocked，需要按 failure code 决定能否续跑 |
| 只做本地验收 | `python3 scripts/onboard_from_manifests.py run-checks --provider <provider> --all-local` | 不想推进 DAG，只想验证当前工作区状态 |

## Codex Goal Templates

从零实现：

```text
/goal follow onboarding/instruction.md 添加 <provider> provider，domain 是 <domain>。
默认用本机 codex exec 派发 worker；只有需要 override 时才设置 PROVIDER_ONBOARDING_AGENT_CLI。不触发 GitHub CI，不提交 commit。
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
先运行 check-snapshot 或 repair-markdown-quality；链路会通过默认 codex exec 或 PROVIDER_ONBOARDING_AGENT_CLI override 重新读取当前 extracted.md 做 fresh review，不再只信旧 markdown-quality.json。
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

`check-snapshot` 每次都会派发 fresh Markdown quality worker 读取当前 `extracted.md`，临时报告写入 `.paper-fetch-runs/<provider>-markdown-quality-audit/<doi_slug>/attempt-N/`。full `run` 在 `snapshot-expected` 阶段遇到 fresh blocking issue 时会自动调 `repair-markdown-quality`，单独运行 `check-snapshot` 只负责阻断并报告问题。

有 `asset_contract.figures.inline: body` 的 provider，snapshot/quality 修复必须确认 `extracted.md` 正文中有 `![Figure ...](...)`，且图片出现在 References/Figures/Supplementary 等尾部 section 之前。`download: required` 还必须由 provider-local marker `asset-download-contract: provider=<provider>` 覆盖本地文件落盘、字节数和最终 Markdown 本地路径 rewrite。

## Guardrails

- 默认 worker dispatch 是本机 `codex exec --cd <repo-root> --sandbox workspace-write -c approval_policy="never" -`；`PROVIDER_ONBOARDING_AGENT_CLI` 仅用于 operator override。不要从脚本里接入 LLM SDK。
- `markdown-quality.json` 是持久审查记录，不是唯一 gate；fresh review 和持久报告都必须无 blocking issue。
- figure asset contract 是 blocking gate；caption-only `## Figures`、远程-only 图片链接或缺少 provider-local 下载断言都不能作为通过依据。
- coordinator 负责 state、验证、snapshot、changed-path scope 检查和 failure recovery；worker 只做 brief 允许的窄范围任务。
- access review 必须由 operator 批准；脚本和 worker 不得把 blocked 草稿升级为 approved。
- `markdown_semantic_reviewed: true` 只能来自真实语义签字；bootstrap 和 repair 都不能自动设置。
- 不触发 GitHub CI；本地验收使用 repo-local commands。
- 多 provider 或多 DOI repair 不要在同一个工作区并发写入；需要并行时使用独立 worktree 后由 coordinator 串行合并。

## Expected Outputs

- Coordinator state：`onboarding/onboarding-state.json`，包含 runs、verifications 和 repairs 摘要。
- DAG/worker logs：`.paper-fetch-runs/<provider>-onboarding/`。
- Markdown repair logs：`.paper-fetch-runs/<provider>-markdown-repair/markdown-quality/<doi_slug>/attempt-N/`。
- Fresh Markdown quality audit logs：`.paper-fetch-runs/<provider>-markdown-quality-audit/<doi_slug>/attempt-N/`。
- Operator digest：`.paper-fetch-runs/<provider>-onboarding/summary.md`。
- Review artifact：`onboarding/reviews/<provider>.yml`，acceptance 不接受只写在 worker 回复里的审查结论。

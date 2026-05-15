# CloakBrowser 迁移执行 Runbook

> 你（运行 `/goal` 的 orchestrator）正在阅读这份 runbook。**严格按编号顺序执行**，不要跳步、不要并行、不要自创流程；遇到失败时先按本文对应恢复策略处理，恢复耗尽或被标记为不可恢复时才停止。
>
> 配套文件:
> - `./CLOAKBROWSER_FULL_MIGRATION_PLAN.md` — 9 个 Phase 的细化操作步骤（你**只**读其中的 §3 和当前 Phase 的 §5）。
> - `./MIGRATION_DECISIONS.md` — 跨 Phase 的命名/签名决策日志（每个 sub-agent 完成后追加）。

---

## 0. Orchestrator 角色边界

你在本 runbook 中扮演 **orchestrator**：

- **你做的事**：执行 §1 启动准备；按 §3 的循环为每个 Phase 派发 code sub-agent 与（必要时）smoke sub-agent；运行验收命令；管理分支与合并。
- **你不做的事**：不亲自实施 Phase 内的代码改动（那是 code sub-agent 的工作）；不亲自跑 live 测试（那是 smoke sub-agent 的工作）；不修改 `./CLOAKBROWSER_FULL_MIGRATION_PLAN.md`；不 push 到 remote。

工作目录：`/home/dictation/paper-fetch-skill`。所有命令在此目录运行。

---

## 1. 启动前的准备

按顺序执行以下子步骤；任一步失败时先按本节自动修复策略处理。若该步骤标记为不可自动修复，或自动修复后仍失败，立即停止并把失败原因报告给用户。

### 1.1 环境检查（带自动修复）

按顺序执行以下检查，**每条检查带自动修复策略**：

#### 1.1.1 仓库状态必须干净

```bash
git status --porcelain
```

期待：空输出。
**不可自动修复**：若不空，停止并请用户处理（auto-stash 会隐藏状态，禁止）。

#### 1.1.2 Python 可用

```bash
python3 --version
```

**不可自动修复**：失败则停止。

#### 1.1.3 cloakbrowser / playwright 包可用

用 `importlib.metadata` 探测版本（避免依赖包是否暴露 `__version__` 属性）：

```bash
python3 -c "from importlib.metadata import version; print('cloakbrowser', version('cloakbrowser'))"
python3 -c "from importlib.metadata import version; print('playwright', version('playwright'))"
```

**自动修复一次**：任一命令失败（`PackageNotFoundError` / `ModuleNotFoundError`）→

```bash
python3 -m pip install --upgrade 'cloakbrowser>=0.3.28,<0.4' 'playwright>=1.40'
```

修复完成后**重跑**对应版本探测命令。第二次仍失败 → 停止并把 pip 与 import 的完整 stderr 报告给用户。

#### 1.1.4 记录修复痕迹

若 §1.1.3 触发过自动修复：在当前 shell 里记录 `CLOAKBROWSER_PREFLIGHT_AUTO_FIXED=1`，不要在创建集成分支前写入任何仓库文件。该记录会在 §1.3 写入 `MIGRATION_DECISIONS.md` 的 `## Pre-flight notes` 节，并随初始化 commit 一起提交。

### 1.2 baseline 单测必须通过

```bash
PYTHONPATH=src python3 -m pytest tests/unit -q
```

不通过则停止——baseline 失败说明仓库起点已坏，先让用户修复。

### 1.3 创建集成分支与决策日志

```bash
git switch -c cloakbrowser-migration
```

创建或更新决策日志。此步骤必须幂等：如果 `MIGRATION_DECISIONS.md` 已存在且没有新增内容，不要强行 commit。

```bash
if [ ! -f MIGRATION_DECISIONS.md ]; then
  cat > MIGRATION_DECISIONS.md <<'EOF'
# CloakBrowser Migration Decisions Log

每个 Phase 完成后由对应 sub-agent 追加。后续 sub-agent 必须先读取本文件，以沿用前序命名与签名决定。

EOF
fi

if [ "${CLOAKBROWSER_PREFLIGHT_AUTO_FIXED:-}" = "1" ]; then
  if ! grep -q '^## Pre-flight notes$' MIGRATION_DECISIONS.md; then
    tmp="$(mktemp)"
    awk 'NR==1 {print; print ""; print "## Pre-flight notes"; print ""; print "- auto-fixed cloakbrowser/playwright install"; next} {print}' MIGRATION_DECISIONS.md > "$tmp"
    mv "$tmp" MIGRATION_DECISIONS.md
  elif ! grep -q 'auto-fixed cloakbrowser/playwright install' MIGRATION_DECISIONS.md; then
    tmp="$(mktemp)"
    awk '/^## Pre-flight notes$/ {print; getline; print; print "- auto-fixed cloakbrowser/playwright install"; next} {print}' MIGRATION_DECISIONS.md > "$tmp"
    mv "$tmp" MIGRATION_DECISIONS.md
  fi
fi

git add MIGRATION_DECISIONS.md
if ! git diff --cached --quiet -- MIGRATION_DECISIONS.md; then
  git commit -m "Init CloakBrowser migration decisions log"
else
  echo "MIGRATION_DECISIONS.md unchanged; no init commit needed"
fi
```

### 1.4 锁定计划版本

```bash
git log -1 --oneline -- CLOAKBROWSER_FULL_MIGRATION_PLAN.md
```

记录该 commit hash，整条 mega-goal 期间不得有其他人修改计划文件。

后续每个 Phase 进入 §3.1 前都必须重新运行同一命令，并与本步骤记录的 hash 比对；hash 改变属于不可恢复失败，立即走 §3.7。

---

## 2. 全局不变量

每个 Phase 验收时除该 Phase 自带的 acceptance 命令外，**额外**检查以下不变量：

| 不变量 | 检查命令 | 期望 |
| --- | --- | --- |
| 不破坏 CLAUDE/计划文件 | `git diff --name-only main..HEAD -- CLOAKBROWSER_FULL_MIGRATION_PLAN.md` | 空 |
| 测试不用 skip/xfail 绕过 | `git diff main..HEAD -- 'tests/**/*.py' \| grep -E "^\+.*(pytest\.skip\|pytest\.mark\.xfail)"` | 空 |
| 直接启动 stock Chromium 数 | `git grep -nE "sync_playwright\(\)\.start\|chromium\.launch" src/paper_fetch/ \| wc -l` | 见下表 |

`sync_playwright().start()` / `chromium.launch()` 命中数随 Phase 单调递减：

| Phase 完成后 | 允许命中数 |
| --- | --- |
| Phase 1 | ≤ 4 (runtime_playwright + _pdf_fallback + fetchers/context + html_extraction) |
| Phase 2 | ≤ 3 |
| Phase 3 | ≤ 2 |
| Phase 4 | ≤ 1 |
| Phase 5 起 | 0 |

grep 类不变量以**输出内容**为准：命令 exit code 为 1 但输出为空时视为通过。任一不变量失败 → 视为该 Phase 验收失败，进入 §3.4b 分类；若该失败在 §3.4b 标记为不可恢复，则走 §3.7。

---

## 3. 主循环：Phase 1..9

对 N in [1, 2, 3, 4, 5, 6, 7, 8, 9]，依次执行 §3.1 → §3.5；若需要再执行 §3.6；失败先按 §3.4b / §3.6 的恢复策略处理，恢复耗尽后走 §3.7。

### 3.1 Phase 间硬约束

- 重新运行 `git log -1 --oneline -- CLOAKBROWSER_FULL_MIGRATION_PLAN.md`，必须与 §1.4 锁定的 hash 完全一致；否则立即走 §3.7，失败原因写 "计划文件被外部修改"。
- 若 N == 9 且 `MIGRATION_DECISIONS.md` 中未出现 `## Phase 6` 节，**停止 mega-goal** 并报错 "Phase 6 未完成，禁止进入 Phase 9"。

### 3.2 创建 Phase 分支

```bash
git switch cloakbrowser-migration
git switch -c cloakbrowser-migration-phase-${N}
```

### 3.3 派发 code sub-agent

用 §4.1 的 `CODE_AGENT_PROMPT` 模板，把 `{N}` 替换为当前 Phase 编号，作为 prompt 启动一个 code sub-agent。

**等待 code sub-agent 返回**。它的返回值应是一份 ≤200 字的简短报告。

若 code agent 自己声明 yes（验收通过）→ §3.4 二次验证。
若 code agent 自己声明 no → 收集当前分支结构状态并进入 §3.4b 自动恢复分类；不要仅凭自报失败直接停止。

### 3.4 验收（单测 + 不变量）

**不要信任 code sub-agent 自报的"通过"**。你自己跑一遍：

1. 打开 `./CLOAKBROWSER_FULL_MIGRATION_PLAN.md`，定位 `### Phase ${N} · ...` 小节。
2. 找到该小节的 **"验收命令"** 子节。
3. 逐条运行其中的 shell 命令，捕获 exit code 和 stdout 末尾 30 行。
4. 再额外跑 §2 全局不变量检查。
5. 检查 `git log --oneline cloakbrowser-migration..HEAD`：必须恰好有 1 个 commit，message 以 `Phase ${N}:` 开头。
6. 检查 `MIGRATION_DECISIONS.md` 末尾新增了 `## Phase ${N}` 小节。

**全部通过 → §3.5 合并**；**任一失败 → §3.4b 自动恢复分类**（不要直接跳 §3.7）。

### 3.4b 自动恢复分类

每个 Phase 的自动恢复预算：

- `repair` 最多 **1 次**：用于 code agent 没有形成合法单 commit、漏写 `MIGRATION_DECISIONS.md` Phase 节、commit message 不合规、或留下未提交改动。
- `fixup` 最多 **2 次**：用于已有合法单 commit 后，验收命令或可修复不变量失败。

每次进入本节，先收集失败诊断：

   - 失败命令完整路径
   - exit code
   - stdout / stderr 末尾 60 行（取大者）
   - 当前 `git status --short`
   - 当前 `git log --oneline cloakbrowser-migration..HEAD`
   - 当前 `git diff --stat cloakbrowser-migration..HEAD`
   - sub-agent 上一次返回的 ≤200 字报告

按以下顺序分类：

1. **不可恢复，直接 §3.7**：
   - §1.4 计划文件 hash 改变。
   - `git diff --name-only main..HEAD -- CLOAKBROWSER_FULL_MIGRATION_PLAN.md` 非空。
   - skip/xfail 不变量输出非空。
   - stock Chromium 命中数超过当前 Phase 允许值。
   - `git log --oneline cloakbrowser-migration..HEAD` 超过 1 个 commit。
   - 自动恢复预算已耗尽。
2. **repair 路径**：若 Phase commit 数为 0、commit message 不以 `Phase ${N}:` 开头、`MIGRATION_DECISIONS.md` 缺少 `## Phase ${N}`、或 `git status --short` 显示有未提交改动，且 repair 尚未使用：
   - 用 §4.3 `REPAIR_AGENT_PROMPT` 派发 repair agent，把失败诊断作为 `{FAILURE_REPORT}` 输入。
   - repair agent 返回后，重新跑 §3.4 完整验收。
   - 若仍失败，重新进入 §3.4b 分类；repair 不得第二次派发。
3. **fixup 路径**：若 Phase commit 数恰好为 1，commit message 合规，且失败来自验收命令或可修复的不变量，且 fixup 次数 < 2：
   - 用 §4.2 `FIXUP_AGENT_PROMPT` 派发 fixup agent，把失败诊断作为 `{FAILURE_REPORT}` 输入。
   - fixup agent 返回后，重新跑 §3.4 完整验收。
   - 若仍失败，重新进入 §3.4b 分类；最多派发 2 次 fixup。
4. **无法分类**：走 §3.7，并在失败报告中写明 "自动恢复分类失败"。

每次 repair/fixup agent 都必须把尝试记录追加到 `MIGRATION_DECISIONS.md` 对应 Phase 节，并纳入同一个 Phase commit。orchestrator 不亲自修改 Phase 代码或 Phase 决策日志。

### 3.5 合并到集成分支

```bash
git switch cloakbrowser-migration
git merge --no-ff cloakbrowser-migration-phase-${N} -m "Merge Phase ${N}"
```

输出给用户：
```
Phase ${N} 单测验收通过，已合并到 cloakbrowser-migration。
```

若 N ∈ {4, 5, 6, 9}：进入 §3.6 自动 live smoke。
否则：直接进入 Phase N+1，跳过 §3.6。

### 3.6 自动 live smoke（仅 N ∈ {4, 5, 6, 9}）

用 §4.4 的 `SMOKE_AGENT_PROMPT` 模板派发一个独立的 smoke sub-agent，传入 `{N}`。

**smoke sub-agent 不修改任何代码**，只跑 live 测试并报告结果。允许 1 次失败重试以过滤 publisher 端 transient（429 / Cloudflare challenge 等）。

等待 smoke sub-agent 返回，它的返回字段固定为以下三种之一：

| 返回 | orchestrator 行为 |
| --- | --- |
| `pass` | 进入 Phase N+1。 |
| `pass_with_retry` | 把 smoke 报告（含重试细节）追加到 `MIGRATION_DECISIONS.md` 该 Phase 节末尾，commit `"chore: Phase ${N} smoke notes"`，进入 Phase N+1。 |
| `fail` | 走 §3.7 失败分支。**已合并到 `cloakbrowser-migration` 的代码不自动回滚**——live 失败可能是 publisher transient 或真实回归，需要人工判断。 |

注意：smoke sub-agent **不创建任何代码 commit**；任何来自 smoke 的笔记由 orchestrator 自己 commit（避免 sub-agent 互相争抢 git 状态）。

### 3.7 失败：停止并交还

```bash
git switch cloakbrowser-migration
# 保留 phase-${N} 分支以便人工调试；不要 delete 也不要 reset。
```

输出给用户：
```
✗ Phase ${N} 验收失败。
失败命令: <列出每条失败命令>
exit code: <每条的 exit code>
stderr 末尾 30 行: <粘贴>
分支 cloakbrowser-migration-phase-${N} 已保留供人工调试。
mega-goal 已停止。
```

**结束 mega-goal**。只有在前文恢复预算已经耗尽或该失败明确标记为不可恢复时才进入本节；进入本节后不要再尝试自动修复。

---

## 4. Sub-agent prompt 模板

派发时把 `{N}` 替换为具体 Phase 编号。code / fixup / repair agent 可以改代码并 commit 或 amend；smoke agent 只跑测试不 commit。

### 4.1 CODE_AGENT_PROMPT（每个 Phase 都用）

```text
你是 CloakBrowser 迁移的 Phase {N} 代码执行 agent。工作目录 /home/dictation/paper-fetch-skill。

前置阅读（按顺序，全部必读，不读完不要动手）:
  1. ./CLOAKBROWSER_FULL_MIGRATION_PLAN.md §3 "通用约束"（共 8 条硬规则）
  2. ./CLOAKBROWSER_FULL_MIGRATION_PLAN.md §5 中的 "### Phase {N} · ..." 整节
  3. ./MIGRATION_DECISIONS.md 全文（前序 Phase 的命名/签名决定，本 Phase 必须沿用）

任务:
  1. 严格按 Phase {N} 的"细化操作步骤"逐条实施改动。仅修改该 Phase "输入文件"小节列出的文件。
  2. 跑完该 Phase "验收命令"全部条目，全部通过；任一失败先修，不要绕过。
  3. git add 仅暂存本 Phase 涉及的文件（git status 检查无误后再 add）。
  4. git commit -m "Phase {N}: <一句概述本 Phase 的核心改动>"
  5. 在 ./MIGRATION_DECISIONS.md 末尾追加一节，**严格按以下格式**:

     ## Phase {N}

     ### 命名决定
     - <新增/重命名的类、函数、常量名，逐行列出>

     ### 签名决定
     - <新增公开函数的完整签名，逐行列出>

     ### 判断性偏差
     - <如果偏离了计划文本，说明为什么；若无偏差写 "无"。>

     把这次对 MIGRATION_DECISIONS.md 的追加包含在同一个 commit 中。

返回给 orchestrator（≤200 字）:
  - 修改文件总数
  - 关键命名决定 3 条以内
  - 验收命令是否全部通过 (yes/no)

绝对禁止:
  - 触碰其他 Phase 范围内的文件
  - 删除任何 alias（除非本 Phase 明确为 Phase 9）
  - 用 pytest.skip / pytest.mark.xfail 绕过失败
  - 修改 CLOAKBROWSER_FULL_MIGRATION_PLAN.md 本身
  - git push / 创建多个 commit / amend 已有 commit
  - 自行决定 "保留旧路径以防万一" —— 按计划文本执行，不另加 fallback。
```

### 4.2 FIXUP_AGENT_PROMPT（每次 §3.4 验收失败时派发）

```text
你是 CloakBrowser 迁移的 Phase {N} 代码修复 agent。工作目录 /home/dictation/paper-fetch-skill。

当前状态:
- 已存在分支 cloakbrowser-migration-phase-{N}，并已有 1 个 Phase {N} commit。
- 上一次 code agent 完成后，orchestrator 跑验收时出现失败。

你看到的失败诊断（orchestrator 注入，不要无视）:
{FAILURE_REPORT}
  - failed_commands: 失败命令逐条
  - exit_codes: 每条 exit code
  - output_tail: stdout / stderr 末尾 60 行
  - git_status: 当前 git status --short
  - phase_commits: git log --oneline cloakbrowser-migration..HEAD
  - git_diff_stat: 当前分支相对 cloakbrowser-migration 的 diff 摘要
  - prior_agent_report: 前一个 code agent 的 ≤200 字报告

前置阅读:
  1. ./CLOAKBROWSER_FULL_MIGRATION_PLAN.md §3 "通用约束"
  2. ./CLOAKBROWSER_FULL_MIGRATION_PLAN.md §5 中的 "### Phase {N} · ..." 整节
  3. ./MIGRATION_DECISIONS.md 全文（含本 Phase 已有的命名决定）

任务:
  1. 阅读失败诊断，定位根因（不要重头实现整个 Phase）。
  2. 仅修复诊断中指出的问题。不要扩大改动范围。
  3. 跑完该 Phase "验收命令"全部条目，全部通过。
  4. 用 `git commit --amend --no-edit` 把修复合并进**已有**的 Phase {N} commit；
     不允许创建新 commit（orchestrator 依赖每个 Phase 仅一个 commit）。
  5. 在 ./MIGRATION_DECISIONS.md 该 Phase 节末尾追加一行:
     - fixup #X: <一句概述本次修复的根因与改动>
     其中 X 由 orchestrator 在 prompt 中按本 Phase fixup 次数替换。
     并把这次对决策日志的修改 `git add` 后再 `git commit --amend --no-edit`。

返回给 orchestrator（≤200 字）:
  - 根因诊断 1-2 句
  - 改动文件清单
  - 是否所有验收命令通过 (yes/no)

绝对禁止:
  - 创建新 commit（必须 amend）
  - 触碰其他 Phase 范围内的文件
  - 修改 CLOAKBROWSER_FULL_MIGRATION_PLAN.md / CLOAKBROWSER_MIGRATION_RUNBOOK.md
  - 用 pytest.skip / pytest.mark.xfail / pytest -k 排除来"绕过"失败
  - 通过弱化断言、删除测试、放宽 grep 命令来通过验收
  - git push / branch 切换 / reset / stash
  - 若你判断根因超出 fixup 范围（例如需要重新设计），返回 yes/no=no 并在报告中说明，
    不要硬撑——orchestrator 会重派或最终走 §3.7。
```

### 4.3 REPAIR_AGENT_PROMPT（Phase 结构修复时派发）

```text
你是 CloakBrowser 迁移的 Phase {N} 结构修复 agent。工作目录 /home/dictation/paper-fetch-skill。

当前状态:
- 已存在分支 cloakbrowser-migration-phase-{N}。
- 上一次 code agent 没有形成可验收的 Phase 结构，可能表现为: 没有 Phase commit、commit message 不合规、MIGRATION_DECISIONS.md 缺少 Phase 节、或工作树有未提交改动。
- 你的目标不是重做整个 Phase，而是把当前分支修复到 orchestrator 可继续验收的结构。

你看到的失败诊断（orchestrator 注入，不要无视）:
{FAILURE_REPORT}
  - failed_commands: 失败命令逐条
  - exit_codes: 每条 exit code
  - output_tail: stdout / stderr 末尾 60 行
  - git_status: 当前 git status --short
  - phase_commits: git log --oneline cloakbrowser-migration..HEAD
  - git_diff_stat: 当前分支相对 cloakbrowser-migration 的 diff 摘要
  - prior_agent_report: 前一个 agent 的 ≤200 字报告

前置阅读:
  1. ./CLOAKBROWSER_FULL_MIGRATION_PLAN.md §3 "通用约束"
  2. ./CLOAKBROWSER_FULL_MIGRATION_PLAN.md §5 中的 "### Phase {N} · ..." 整节
  3. ./MIGRATION_DECISIONS.md 全文（若本 Phase 节缺失，你负责补齐）

任务:
  1. 只做结构修复和必要的最小代码修复，不扩大 Phase 范围。
  2. 确保 `MIGRATION_DECISIONS.md` 存在 `## Phase {N}` 节；若缺失，按 CODE_AGENT_PROMPT 的格式补齐。无论该节原本是否存在，都要在该 Phase 节末尾追加:
     - repair #1: <一句概述修复了什么结构问题>
  3. 确保 `git log --oneline cloakbrowser-migration..HEAD` 恰好只有 1 个 commit，且 message 以 `Phase {N}:` 开头：
     - 若没有 commit：`git add` 本 Phase 允许的文件与 `MIGRATION_DECISIONS.md` 后创建 `git commit -m "Phase {N}: <一句概述本 Phase 的核心改动>"`。
     - 若已有 1 个 commit 但 message 不合规：修正文件后用 `git commit --amend -m "Phase {N}: <一句概述本 Phase 的核心改动>"`。
     - 若已有超过 1 个 commit：立即返回 yes/no=no，不要 reset、rebase、squash 或删除 commit。
  4. 若工作树有未提交改动，确认它们只属于本 Phase 输入文件或 `MIGRATION_DECISIONS.md`，再纳入上述 commit 或 amend。
  5. 跑完该 Phase "验收命令"全部条目，全部通过；若失败且根因不是结构问题，返回 yes/no=no，把失败摘要交回 orchestrator 进入 fixup。

返回给 orchestrator（≤200 字）:
  - 修复的结构问题
  - 当前 Phase commit 数与 commit message
  - 是否所有验收命令通过 (yes/no)

绝对禁止:
  - 创建超过 1 个 Phase commit
  - 触碰其他 Phase 范围内的文件
  - 修改 CLOAKBROWSER_FULL_MIGRATION_PLAN.md / CLOAKBROWSER_MIGRATION_RUNBOOK.md
  - 用 pytest.skip / pytest.mark.xfail / pytest -k 排除来"绕过"失败
  - 通过弱化断言、删除测试、放宽 grep 命令来通过验收
  - git push / branch 切换 / reset / stash / rebase
```

### 4.4 SMOKE_AGENT_PROMPT（仅 Phase 4/5/6/9 派发）

```text
你是 CloakBrowser 迁移的 Phase {N} live smoke agent。工作目录 /home/dictation/paper-fetch-skill。

你的唯一职责是跑 live 测试并报告结果。**绝对不要修改任何代码、不要 git add / commit / push、不要修改 MIGRATION_DECISIONS.md**。当前 HEAD 已经在 cloakbrowser-migration 分支上包含 Phase {N} 的代码改动。

测试范围（根据 N 选择）:
  - N == 4 → PDF/ePDF fallback 路径，跑:
      tests/live/test_live_publishers.py::LivePublisherTests::test_wiley_doi_live_fulltext
      tests/live/test_live_atypon_browser_workflow.py::test_science_doi_live_fulltext_via_html
      tests/live/test_live_atypon_browser_workflow.py::test_pnas_doi_live_fulltext_uses_a_stable_provider_path
  - N == 5 → 正文资产 + supplementary，跑:
      tests/live/test_live_atypon_browser_workflow.py (整个文件，含 asset / supplementary 断言)
      tests/live/test_live_publishers.py::LivePublisherTests::test_wiley_doi_live_fulltext
  - N == 6 → imagePayload 等价能力，跑:
      tests/live/test_live_atypon_browser_workflow.py (整个文件)
      tests/live/test_live_publishers.py::LivePublisherTests::test_wiley_doi_live_fulltext
      重点关注 figure / table 图片下载与 challenge recovery 路径。
  - N == 9 → 全量回归，跑:
      tests/live/test_live_atypon_browser_workflow.py
      tests/live/test_live_publishers.py

执行流程:
  1. 确认 CloakBrowser binary 可用（首次运行会触发下载）:
       python3 -c "import cloakbrowser; cloakbrowser.ensure_runtime() if hasattr(cloakbrowser, 'ensure_runtime') else None"
     （如果 ensure_runtime 不存在则跳过，binary 会在测试启动时按需下载。）
  2. 第一遍跑目标测试集（串行，必须 -n 0）:
       CROSSREF_MAILTO=paper-fetch-skill@example.invalid \
       PAPER_FETCH_RUN_LIVE=1 \
       CLOAKBROWSER_HEADLESS=true \
       PYTHONPATH=src python3 -m pytest -n 0 <目标测试> -q
  3. 若第一遍全部通过 → 返回 "pass" 与简短摘要。
  4. 若第一遍有失败:
     a. 收集失败 test id 列表与 stderr 末尾 40 行。
     b. **只**重跑失败的 test id（单次重试，仍 -n 0）。
     c. 如果重试全部通过 → 返回 "pass_with_retry"，附:
        - 首次失败 test id
        - 失败 stderr 末尾 20 行
        - 重试通过证据
     d. 如果重试仍失败 → 返回 "fail"，附:
        - 失败 test id 列表
        - 每个失败的 stderr 末尾 30 行
        - 你对失败性质的初步判断（regression / publisher transient / network / cloakbrowser binary）

返回给 orchestrator 的格式（严格 YAML）:
  status: pass | pass_with_retry | fail
  phase: {N}
  tests_run: <count>
  tests_failed_first_pass: <count>
  tests_failed_after_retry: <count>
  diagnosis: <≤200 字的人话>
  failure_details: |
    <仅 fail 或 pass_with_retry 时填，多行 raw stderr 摘录>

绝对禁止:
  - 修改任何源代码、测试代码、配置文件
  - git add / commit / push / branch 切换 / reset / stash
  - 修改 MIGRATION_DECISIONS.md 或 CLOAKBROWSER_FULL_MIGRATION_PLAN.md
  - 用 pytest -k 跳过子集来"绕过"失败
  - 超过 1 次重试（避免无限循环消耗）
  - 跑超出目标测试范围的测试（节省时间和外部请求）
```

---

## 5. 完成判定

Phase 9 通过 §3.5 合并 + §3.6 smoke 验证之后，输出给用户：

```
全部 9 个 Phase 已完成并合并到 cloakbrowser-migration。
Phase 4/5/6/9 自动 live smoke 全部通过（见 MIGRATION_DECISIONS.md 中各 Phase 节的 smoke notes）。

建议人工再确认:
  PYTHONPATH=src python3 -m pytest tests/unit tests/integration -q
  git grep -nE "sync_playwright\(\)\.start|chromium\.launch" src/paper_fetch/   # 期待空
  PAPER_FETCH_RUN_LIVE=1 CLOAKBROWSER_HEADLESS=true PYTHONPATH=src python3 -m pytest -n 0 \
    tests/live/test_live_publishers.py -q

确认无误后可执行:
  git switch main
  git merge --no-ff cloakbrowser-migration
```

不要自行合并到 main，不要 push。结束 mega-goal。

---

## 6. 失败处理速查

| 场景 | 处理 |
| --- | --- |
| §1.1.3 包探测失败（首次） | 触发 §1.1.3 自动 pip install 修复一次，再重试 |
| §1.1.3 修复后仍失败 | 停止 mega-goal，附 pip + import 完整 stderr |
| §1.1.1 工作树不干净 | 停止；禁止 auto-stash（隐藏状态风险） |
| §1.2 baseline 单测失败 | 停止；不要尝试自动修复（说明起点已坏） |
| code sub-agent 报告 "no" | 进入 §3.4b 自动恢复分类；可能 repair 1 次或 fixup 最多 2 次 |
| Phase commit 数为 0 / message 不合规 / 缺 `## Phase N` / 有未提交改动 | 进入 §4.3 repair，最多 1 次 |
| §3.4 验收命令失败且已有合法单 commit | 进入 §4.2 fixup，最多 2 次 |
| §3.4b 恢复预算耗尽 | 走 §3.7 |
| §2 不变量 "sync_playwright/chromium.launch 命中数" 超额 | 直接 §3.7，不可恢复（真实回归） |
| §3.4 git log commit 数 > 1 | 直接 §3.7，不可恢复（保留现场，避免自动 reset/rebase） |
| skip/xfail 不变量输出非空 | 直接 §3.7，不可恢复 |
| smoke sub-agent 返回 `fail` | 走 §3.7。代码已合并，不自动回滚——把失败诊断完整交还人工 |
| smoke sub-agent 返回 `pass_with_retry` | 视为通过，继续 Phase N+1，把 smoke notes commit 到集成分支 |
| smoke sub-agent 返回 transient 嫌疑但被分类为 fail | 仍走 §3.7；交人工决定是否重新派发 smoke agent |
| sub-agent（任意类型）卡住超时 | 报告给用户决定是否重试；不要自动重试 |
| 计划文件被外部修改（hash 变了） | 立即停止；不可恢复 |

---

## 7. Phase 摘要（仅供 orchestrator 快速定位）

| Phase | 一句话目标 | 影响 live? | 自动 live smoke? |
| --- | --- | --- | --- |
| 1 | 引入 browser-neutral 类型与依赖字段命名 | 否 | 否 |
| 2 | `runtime_playwright` → `runtime_browser`，统一启动器为 CloakBrowser | 否 | 否 |
| 3 | PNAS fast preflight 改为 CloakBrowser 实现 | 是（轻） | 否（合并到 Phase 4 一并 smoke） |
| 4 | PDF/ePDF fallback 改为 CloakBrowser 实现 | 是 | **是**（Wiley + Science + PNAS） |
| 5 | 正文资产 / supplementary 下载改为 CloakBrowser context | 是 | **是**（atypon 全套 + Wiley） |
| 6 | 实现 CloakBrowser imagePayload 等价能力（Phase 9 硬阻塞） | 是 | **是**（atypon 全套 + Wiley，重点 challenge recovery） |
| 7 | provider catalog / config / manifest / MCP 文案清理 | 否 | 否 |
| 8 | 安装器 / 离线包 / CI 不再围绕 FlareSolverr | 否 | 否 |
| 9 | 删除或归档 FlareSolverr 正式路径（不可逆） | 是 | **是**（全量 live） |

各 Phase 详细操作步骤、输入文件、单测验收命令一律在 `./CLOAKBROWSER_FULL_MIGRATION_PLAN.md` §5 中。本表仅用于判断 §3.6 自动 smoke 是否触发；具体 smoke 测试集见 §4.4 SMOKE_AGENT_PROMPT。

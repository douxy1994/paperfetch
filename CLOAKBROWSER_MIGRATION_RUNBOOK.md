# CloakBrowser 迁移执行 Runbook

> 你（运行 `/goal` 的 orchestrator）正在阅读这份 runbook。**严格按编号顺序执行**，不要跳步、不要并行、不要自创流程。
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

按顺序执行以下子步骤，**任何一步失败立即停止并把失败原因报告给用户**。

### 1.1 环境检查

```bash
# 仓库状态干净
git status --porcelain
# 期待：空输出。若不空，停止并请用户处理。

# Python 与 CloakBrowser 可用
python3 --version
python3 -c "import cloakbrowser; print('cloakbrowser', cloakbrowser.__version__)"
python3 -c "import playwright; print('playwright', playwright.__version__)"
```

### 1.2 baseline 单测必须通过

```bash
PYTHONPATH=src python3 -m pytest tests/unit -q
```

不通过则停止——baseline 失败说明仓库起点已坏，先让用户修复。

### 1.3 创建集成分支与决策日志

```bash
git switch -c cloakbrowser-migration
```

创建空决策日志（如果文件已存在则跳过 commit）：

```bash
[ -f MIGRATION_DECISIONS.md ] || cat > MIGRATION_DECISIONS.md <<'EOF'
# CloakBrowser Migration Decisions Log

每个 Phase 完成后由对应 sub-agent 追加。后续 sub-agent 必须先读取本文件，以沿用前序命名与签名决定。

EOF
git add MIGRATION_DECISIONS.md
git commit -m "Init CloakBrowser migration decisions log"
```

### 1.4 锁定计划版本

```bash
git log -1 --oneline -- CLOAKBROWSER_FULL_MIGRATION_PLAN.md
```

记录该 commit hash，整条 mega-goal 期间不得有其他人修改计划文件。

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

任一不变量失败 → 视为该 Phase 验收失败，按 §3.7 处理。

---

## 3. 主循环：Phase 1..9

对 N in [1, 2, 3, 4, 5, 6, 7, 8, 9]，依次执行 §3.1 → §3.5；若需要再执行 §3.6；失败则走 §3.7。

### 3.1 Phase 间硬约束

- 若 N == 9 且 `MIGRATION_DECISIONS.md` 中未出现 `## Phase 6` 节，**停止 mega-goal** 并报错 "Phase 6 未完成，禁止进入 Phase 9"。

### 3.2 创建 Phase 分支

```bash
git switch cloakbrowser-migration
git switch -c cloakbrowser-migration-phase-${N}
```

### 3.3 派发 code sub-agent

用 §4.1 的 `CODE_AGENT_PROMPT` 模板，把 `{N}` 替换为当前 Phase 编号，作为 prompt 启动一个 code sub-agent。

**等待 code sub-agent 返回**。它的返回值应是一份 ≤200 字的简短报告。

### 3.4 验收（单测 + 不变量）

**不要信任 code sub-agent 自报的"通过"**。你自己跑一遍：

1. 打开 `./CLOAKBROWSER_FULL_MIGRATION_PLAN.md`，定位 `### Phase ${N} · ...` 小节。
2. 找到该小节的 **"验收命令"** 子节。
3. 逐条运行其中的 shell 命令，捕获 exit code 和 stdout 末尾 30 行。
4. 再额外跑 §2 全局不变量检查。
5. 检查 `git log --oneline cloakbrowser-migration..HEAD`：必须恰好有 1 个 commit，message 以 `Phase ${N}:` 开头。
6. 检查 `MIGRATION_DECISIONS.md` 末尾新增了 `## Phase ${N}` 小节。

**全部通过 → §3.5 合并**；**任一失败 → §3.7 走"失败"分支**。

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

用 §4.2 的 `SMOKE_AGENT_PROMPT` 模板派发一个独立的 smoke sub-agent，传入 `{N}`。

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

**结束 mega-goal**。不要尝试自动修复。

---

## 4. Sub-agent prompt 模板

派发时把 `{N}` 替换为具体 Phase 编号。两类 sub-agent 互相独立——code agent 改代码并 commit，smoke agent 只跑测试不 commit。

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

### 4.2 SMOKE_AGENT_PROMPT（仅 Phase 4/5/6/9 派发）

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
| §1 任一步失败 | 停止 mega-goal，原样报告 |
| code sub-agent 报告 "no" | 视为验收失败，走 §3.7 |
| §3.4 验收命令失败 | 走 §3.7 |
| §3.4 不变量失败 | 走 §3.7 |
| smoke sub-agent 返回 `fail` | 走 §3.7。注意代码已合并，不自动回滚——把失败诊断完整交还人工 |
| smoke sub-agent 返回 `pass_with_retry` | 视为通过，继续 Phase N+1，把 smoke notes commit 到集成分支 |
| smoke sub-agent 返回 transient 嫌疑但被分类为 fail | 仍走 §3.7；交人工决定是否重新派发 smoke agent |
| sub-agent（任意类型）卡住超时 | 报告给用户决定是否重试；不要自动重试 |
| 计划文件被外部修改（hash 变了） | 立即停止；提示用户重新锁定版本 |

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

各 Phase 详细操作步骤、输入文件、单测验收命令一律在 `./CLOAKBROWSER_FULL_MIGRATION_PLAN.md` §5 中。本表仅用于判断 §3.6 自动 smoke 是否触发；具体 smoke 测试集见 §4.2 SMOKE_AGENT_PROMPT。

# AI Onboarding 清洗链路优化执行指南

> 状态：**/goal 可执行实施指南**。
> 日期：2026-05-21。
> 目标：把 fixture 驱动的 cleaning proposal 接入 AI onboarding DAG、provider-local gate 和 9 个存量 provider 清账流程。
> 执行入口：`/goal follow AI_ONBOARDING_OPTIMIZATION.md 执行清洗链路优化`。
> 约束：默认中文汇报；使用项目代码和项目脚本；不使用 Agent 自带 paper-fetch MCP/Skill/环境 CLI 替代项目实现；不触发 GitHub CI；不提交 commit。

本文不是 provider 行为事实源。执行 provider onboarding 时仍以 `docs/ai-onboarding/` 下的 manifest、schema、brief、hard constraints、acceptance 和 failure recovery 为准。本文只定义本次清洗链路优化如何被 `/goal` 串行拆给 subagent 执行。

---

## 1. 已拍板决策

1. **清洗 proposer 进入 DAG 闭环（L3）**
   在 `capture-fixtures` 后、`scaffold` 前新增 `propose-cleaning-chain` coordinator action。它运行 `scripts/propose_cleaning_chain.py --provider <p> --write`，生成 implementation worker 可消费的紧凑 proposal。

2. **contract delta 强制拦截，但必须带分类**
   provider-local acceptance 调用 `--check-contract`。只有真实不可解释的 drift 阻塞；sentinel 和跨 route 守护不应制造误报。

3. **contract drift 在 implement 阶段就地调和**
   gate 发现 `markdown_contract` 与真实清洗结果不一致时，恢复目标是 `implement-provider`，不是退回 `discover-manifest`。implementation worker 可以在受限范围内修改 `docs/ai-onboarding/manifests/<provider>.yml` 的相关 `markdown_contract` purpose；不得顺手改 routing、fixtures、access policy、docs facts 或无关契约。

4. **`cross_route_guard` 告警即可**
   站点 chrome 类负断言如果只是当前 fixture route 没覆盖，例如 HTML chrome 断言遇到 XML/API/PDF route，不阻塞 gate，也不强制要求 route 归属标注。可在 proposal 中记录 warning/provenance，供后续人工巡检。

5. **9 个存量 provider 先全部清账再开 gate**
   强制拦截正式上线前，elsevier、springer、wiley、science、pnas、ieee、arxiv、copernicus、ams 必须逐个消化 §5 的 dead/missing：有效守护要分类豁免或告警，无效契约要删除或改写，真实清洗漏洞要修 provider-owned 实现。

---

## 2. 目标状态

### 2.1 DAG

最终 provider DAG 为 13 个串行 task：

```text
1 operator-access-preflight -> 2 discover-manifest -> 3 validate-manifest ->
4 capture-fixtures -> 5 propose-cleaning-chain -> 6 scaffold ->
7 implement-provider -> 8 shared-integration -> 9 snapshot-expected ->
10 manifest-sync-back -> 11 provider-local-acceptance ->
12 global-lint -> 13 merge-ready
```

`propose-cleaning-chain` 是 coordinator action，不派 worker，不调 LLM。它只依赖已捕获 fixture，不依赖 scaffold。

### 2.2 Proposal 产物

`scripts/propose_cleaning_chain.py --provider <p> --write` 生成两类文件：

| 文件 | 内容 | 用途 |
|---|---|---|
| `docs/ai-onboarding/cleaning-chain-proposals/<p>.yml` | 紧凑决策：contract delta、分类后的 dead/missing、选定 drop token/selector、probe/conflict 摘要、`fixtures_digest` | inline 给 implementation worker，目标 < 3KB |
| `docs/ai-onboarding/cleaning-chain-proposals/<p>.evidence.yml` | 全量证据：selector candidates、content anchors、boilerplate、over-cleaning probes、token conflict report | 人工复核和 provider 清账 |

两文件都必须绑定当前 fixture digest。acceptance 发现 digest 与当前 `original.html` 不一致时，应报告 proposal 过期并要求重跑 proposer。

### 2.3 Contract Drift 分类

| 分类 | 例子 | Gate 行为 | 处理方式 |
|---|---|---|---|
| `sentinel` | `[Formula unavailable]`、`Access Denied` | 不阻塞 | 标为豁免，保留防御性断言 |
| `cross_route_guard` | `Google Scholar`、`Download PDF`、`Article Metrics`、`Download Citation`、`Subscribe` 在当前 fixture route 中空转 | 不阻塞，只告警 | 记录 warning/provenance，不强制 route 标注 |
| `truly_vacuous` | 非 sentinel、非跨 route 守护，且所有 fixture 都从不出现 | 阻塞 | implement 阶段调和契约或删除无效断言 |
| `missing_must_include` | 契约要求 token，但生产清洗链输出缺失 | 阻塞，除非复核证明契约本身过激 | 修 provider-owned 实现，或在 manifest 中就地调和该 purpose 的 `markdown_contract` |

---

## 3. /goal 执行方式

顶层执行：

```text
/goal follow AI_ONBOARDING_OPTIMIZATION.md 执行清洗链路优化
```

单阶段执行：

```text
/goal follow AI_ONBOARDING_OPTIMIZATION.md 执行 Phase A
/goal follow AI_ONBOARDING_OPTIMIZATION.md 执行 Phase B
/goal follow AI_ONBOARDING_OPTIMIZATION.md 执行 Phase C
/goal follow AI_ONBOARDING_OPTIMIZATION.md 执行 Phase D
/goal follow AI_ONBOARDING_OPTIMIZATION.md 执行 Phase E
```

单 provider 清账：

```text
/goal follow AI_ONBOARDING_OPTIMIZATION.md 清账 provider wiley
```

单任务执行：

```text
/goal follow AI_ONBOARDING_OPTIMIZATION.md 执行 Task A1
/goal follow AI_ONBOARDING_OPTIMIZATION.md 执行 Task B-wiley
/goal follow AI_ONBOARDING_OPTIMIZATION.md 执行 Task C3
```

执行规则：

- Phase 必须串行推进：A -> B -> C -> D -> E。
- Phase 内 task 必须按编号串行推进，除非 task 明确写了可并行；本文件默认不并行写同一类文件。
- Phase B 的 9 个 provider 必须逐个执行；同一时间不要让两个 subagent 修改 manifest/proposal/provider tests。
- 每个 subagent 只按本文件列出的 allowed files 工作。若必须越界，先停止并在最终汇报中说明原因。
- subagent 不提交 commit，不触发 GitHub CI，不使用 Agent 自带 paper-fetch MCP/Skill 替代项目脚本。
- 若工作树已有用户改动，读取并兼容；不得回滚非本任务改动。

### 3.1 总任务图

| Task | 名称 | 依赖 | 产出 |
|---|---|---|---|
| A1 | 生产清洗链 baseline 接入 | 无 | proposer 使用真实 provider 清洗输出 |
| A2 | proposal 拆分与 digest | A1 | `<p>.yml` / `<p>.evidence.yml` + `fixtures_digest` |
| A3 | anchor 归一化与 dead 分类 | A2 | `sentinel` / `cross_route_guard` / `truly_vacuous` 分类 |
| A4 | `--check-contract` 语义收敛 | A3 | warning/failure 行为符合 §2.3 |
| A5 | proposer 单测与兼容检查 | A4 | focused tests 通过 |
| B0 | 清账准备和队列校验 | A5 | 9-provider 清账状态表初始化 |
| B-wiley | wiley 清账 | B0 | wiley proposal/contract 清账 |
| B-science | science 清账 | B-wiley | science proposal/contract 清账 |
| B-pnas | pnas 清账 | B-science | pnas proposal/contract 清账 |
| B-springer | springer 清账 | B-pnas | springer proposal/contract 清账 |
| B-ams | ams 清账 | B-springer | ams proposal/contract 清账 |
| B-arxiv | arxiv 清账 | B-ams | arxiv proposal/contract 清账 |
| B-copernicus | copernicus 清账 | B-arxiv | copernicus proposal/contract 清账 |
| B-elsevier | elsevier 清账 | B-copernicus | elsevier proposal/contract 清账 |
| B-ieee | ieee 清账 | B-elsevier | ieee proposal/contract 清账 |
| C1 | DAG/task/schema 接入 | B-ieee | 13-task DAG 和 state schema |
| C2 | run/verify/checks 行为接入 | C1 | coordinator 可执行 proposer task |
| C3 | implementation brief inline proposal | C2 | worker 输入含紧凑 proposal |
| C4 | onboarding docs 同步 | C3 | README/spec/instruction/roadmap 同步 |
| C5 | coordinator focused tests | C4 | coordinator tests 通过 |
| D1 | provider-local contract gate | C5 | acceptance 调用 `--check-contract` |
| D2 | digest freshness gate | D1 | 过期 proposal 被拦截 |
| D3 | `MARKDOWN_CONTRACT_DRIFT` recovery | D2 | retryable failure code 和恢复路由 |
| D4 | implement 阶段调和规则 | D3 | brief/hard constraints 允许受限 manifest contract 调和 |
| D5 | gate focused tests | D4 | gate/recovery tests 通过 |
| E1 | focused 验证 | D5 | 关键单测与 docs checks 通过 |
| E2 | full unit 验证 | E1 | `tests/unit` 通过 |
| E3 | 最终摘要和完成检查 | E2 | provider 清账表、风险和命令结果完整 |

---

## 4. Phase A：修 proposer 基础能力

**目标**：让 proposer 产出的 contract delta 基于 provider 真实清洗链，而不是通用 baseline；同时把产物拆小、绑定 fixture digest、降低 anchor 噪声。

**Subagent brief**

- Goal：更新 `scripts/propose_cleaning_chain.py`，使 proposal 可被 gate 和 implementation worker 稳定消费。
- Allowed files：
  - `scripts/propose_cleaning_chain.py`
  - `tests/unit/test_propose_cleaning_chain.py`
- Forbidden files：
  - provider implementation files
  - provider manifests
  - shared docs
  - generated proposal files
- Inputs to read：
  - `docs/ai-onboarding/README.md`
  - `docs/ai-onboarding/provider-manifest.schema.json`
  - existing `docs/ai-onboarding/cleaning-chain-proposals/mdpi.yml`
  - provider real cleaning entrypoints under `src/paper_fetch/providers/`

### 4.1 Phase A 任务卡

| Task | 目标 | 具体执行内容 | 完成标准 |
|---|---|---|---|
| A1 | 让 proposer baseline 使用生产清洗链 | 找到当前 `calibrate_markdown_contract` 的 baseline 生成路径；梳理 provider 真实 HTML/XML/PDF 清洗入口；增加一个统一调用层，让 proposer 对已捕获 fixture 调用 provider 生产转换逻辑；保留无法调用生产链时的明确错误，不静默退回通用转换器 | `## Abstract` / `Equation` 类缺失不再由通用 baseline 差异制造；单测覆盖“生产链被调用” |
| A2 | 拆分 proposal 并绑定 fixture digest | 将 `--write` 输出拆为紧凑 `<provider>.yml` 和全量 `<provider>.evidence.yml`；计算每个参与 fixture 的 `original.html` sha256；两个文件都写 `fixtures_digest`；保持旧 mdpi fixture 的可读性 | 写盘后两个文件都存在；紧凑文件只含 brief 所需字段；digest 字段可被测试断言 |
| A3 | 清理 anchor 噪声并分类 dead 负断言 | 对 `suggested_must_include_from_fixtures` 做大小写、空白、换行归一化；实现 dead token 分类器；内置 sentinel 列表；用 manifest route/source 识别 cross-route guard；其余才进入 truly vacuous | 重复 anchor 合并；`[Formula unavailable]`/`Access Denied` 不进入 blocking dead；站点 chrome 进入 warning |
| A4 | 收敛 `--check-contract` 行为 | 调整 `--check-contract` 输出，使 blocking 与 warning 分开；exit code 只受 `truly_vacuous` 和未解释 missing 影响；输出保留机器可读字段供 coordinator gate 消费 | `sentinel` 和 `cross_route_guard` 不导致失败；blocking drift 有稳定字段和非零退出 |
| A5 | 补单测和兼容检查 | 为 A1-A4 增加或更新单测；覆盖拆分写盘、digest、anchor 去重、dead 分类、check-contract exit 行为；确认没有写 provider 产物作为测试副作用 | `tests/unit/test_propose_cleaning_chain.py` 通过；`mdpi --check-contract` 可作为 smoke check |

每个 A 任务的 subagent final report 必须包含：涉及函数、行为前后差异、测试命令、是否影响旧 proposal 格式读取。

**Required edits**

1. `calibrate_markdown_contract` 使用 provider 生产清洗链输出作为 baseline，避免 `## Abstract`、`Equation` 等由通用转换器差异导致的假 missing。
2. `--write` 输出 `<provider>.yml` 和 `<provider>.evidence.yml` 两个文件。
3. 两个文件都写入 `fixtures_digest`，覆盖每个参与 fixture 的 `original.html` sha256。
4. `suggested_must_include_from_fixtures` 做大小写、空白、换行归一化去重。
5. `dead_must_not_include` 分类为 `sentinel`、`cross_route_guard`、`truly_vacuous`。
6. `--check-contract` 对 `sentinel` 和 `cross_route_guard` 不返回失败；对 `truly_vacuous` 和未解释的 `missing_must_include` 返回可机读失败。

**Acceptance commands**

```bash
PYTHONPATH=src python3 -m pytest tests/unit/test_propose_cleaning_chain.py -q
python3 scripts/propose_cleaning_chain.py --provider mdpi --check-contract
```

**Final report format**

- changed files
- new proposal schema shape
- classification behavior
- acceptance command results
- unresolved provider-specific risks

---

## 5. Phase B：9 个存量 provider 回填并清账

**目标**：在强制 gate 上线前，逐个 provider 消化现有 dead/missing，避免 gate 一上线就卡住存量 provider。

**执行顺序**

1. `wiley`
2. `science`
3. `pnas`
4. `springer`
5. `ams`
6. `arxiv`
7. `copernicus`
8. `elsevier`
9. `ieee`

优先级依据：先处理 token conflict 高的 provider，再处理 missing 非空 provider，最后用 copernicus/ams 做健康基线和对照。

### 5.1 Provider 清账队列

| provider | 初始 missing | 初始 dead | token_conflict | 清账重点 |
|---|---|---|---:|---|
| wiley | supplementary:`Supplementary` | `[Formula unavailable]`, Access Denied | 34 | 复核 supplementary 是否真实应出现；sentinel 豁免 |
| science | formula:`Equation`, figure:`Figure`, references:`Reference`, abstract_only/access_gate:`## Abstract` | `[Formula unavailable]`, Access Denied | 27 | 用生产链复核 Abstract/Equation/Figure/Reference |
| pnas | references:`Reference`, abstract_only/access_gate:`## Abstract` | Article Metrics, Access Denied | 21 | 区分 route chrome 告警与真实 reference 缺失 |
| springer | formula:`Equation`, references:`Reference`, abstract_only/access_gate:`## Abstract` | `[Formula unavailable]`, Article Metrics, Subscribe | 19 | 复核 Equation/Reference，chrome 走 warning |
| ams | 无 | `[Formula unavailable]`, Article Metrics, Access Denied | 17 | 作为零 missing 健康对照，验证分类不误拦 |
| arxiv | structure:`## Abstract`, table:`Table`, formula:`Equation`, figure:`Figure`, references:`Reference`, pdf_fallback:`#` | Google Scholar, `[Formula unavailable]`, Article Metrics, Access Denied | 15 | PDF/HTML/API route 分开复核，避免把 route 差异当漏洞 |
| copernicus | 无 | Download PDF, Article Metrics, Google Scholar, Access Denied | 7 | 作为零 missing 健康对照，确认 cross-route 告警 |
| elsevier | formula:`Equation`, figure:`Figure`, supplementary:`Supplementary` | Download PDF, Google Scholar, `[Formula unavailable]`, Article Metrics, Download Citation | 5 | 复核 XML 生产链中的 formula/figure/supplementary |
| ieee | structure/abstract_only:`## Abstract`, formula:`Equation`, supplementary:`Supplementary`, pdf_fallback:`#` | Download PDF, Google Scholar, `[Formula unavailable]`, Article Metrics, Download Citation | 3 | PDF fallback 与 HTML route 分开复核 |

### 5.2 Task B0：清账准备和队列校验

- Goal：在开始 9-provider 清账前确认 Phase A 行为稳定，并建立统一记录方式。
- Allowed files：
  - `AI_ONBOARDING_OPTIMIZATION.md`
  - `docs/ai-onboarding/cleaning-chain-proposals/*.yml`
  - `docs/ai-onboarding/cleaning-chain-proposals/*.evidence.yml`
- Required steps：
  1. 确认 `python3 scripts/propose_cleaning_chain.py --provider mdpi --check-contract` 的 warning/failure 语义符合 §2.3。
  2. 对 9 个 provider 逐个 dry check 当前状态，记录 blocking missing、blocking truly vacuous、warning-only 项。
  3. 不修 provider，只更新执行摘要或 task 状态记录；若发现 Phase A 基础行为仍错误，停止并退回 A 任务。
- Acceptance：
  - 9 个 provider 都有初始清账记录。
  - 后续 `B-<provider>` subagent 能从记录中知道本 provider 要处理哪些 blocking 项和 warning 项。
- Final report：
  - provider queue
  - 每个 provider 当前 blocking count / warning count
  - 是否允许进入 `B-wiley`

### 5.3 单 Provider Subagent Brief

把 `<provider>` 替换为当前 provider。

- Goal：清账 `<provider>` 的 cleaning proposal、manifest contract 和 provider-owned implementation，使 `--check-contract` 不再产生未解释阻塞。
- Allowed files：
  - `docs/ai-onboarding/cleaning-chain-proposals/<provider>.yml`
  - `docs/ai-onboarding/cleaning-chain-proposals/<provider>.evidence.yml`
  - `docs/ai-onboarding/manifests/<provider>.yml`
  - `docs/ai-onboarding/reviews/<provider>.yml`
  - `src/paper_fetch/providers/<provider>.py`
  - `src/paper_fetch/providers/_<provider>_*.py`
  - §5.4 中列出的当前 provider 专属 helper 和 provider-local tests
  - `tests/unit/test_<provider>*`
  - provider-specific fixture `expected.json` only if a real implementation fix changes expected output and snapshot tooling is run
- Forbidden files：
  - `src/paper_fetch/provider_catalog.py`
  - `src/paper_fetch/extraction/html/provider_rules.py`
  - `src/paper_fetch/quality/html_signals.py`
  - `src/paper_fetch/quality/html_availability.py`
  - `docs/providers.md`
  - `docs/extraction-rules.md`
  - `CHANGELOG.md`
  - unrelated provider files
- Inputs to read：
  - `docs/ai-onboarding/manifests/<provider>.yml`
  - `docs/ai-onboarding/reviews/<provider>.yml`
  - current proposal/evidence if present
  - provider-owned implementation and provider-local tests

### 5.4 Provider-Owned 文件索引

Phase B subagent 只能修改当前 provider 这一行列出的 provider-owned 文件；不能修改其他 provider。

| provider | provider-owned implementation files | provider-local tests |
|---|---|---|
| wiley | `src/paper_fetch/providers/wiley.py`, `src/paper_fetch/providers/_wiley_html.py` | `tests/unit/test_wiley*` |
| science | `src/paper_fetch/providers/science.py`, `src/paper_fetch/providers/_science_html.py` | `tests/unit/test_science*` |
| pnas | `src/paper_fetch/providers/pnas.py`, `src/paper_fetch/providers/_pnas_html.py` | `tests/unit/test_pnas*` |
| springer | `src/paper_fetch/providers/springer.py`, `src/paper_fetch/providers/_springer_html.py`, `src/paper_fetch/providers/html_springer_nature.py` | `tests/unit/test_springer*` |
| ams | `src/paper_fetch/providers/ams.py`, `src/paper_fetch/providers/_ams_html.py` | `tests/unit/test_ams*` |
| arxiv | `src/paper_fetch/providers/arxiv.py`, `src/paper_fetch/providers/_arxiv_*.py`, `src/paper_fetch/arxiv_id.py` | `tests/unit/test_arxiv*` |
| copernicus | `src/paper_fetch/providers/copernicus.py`, `src/paper_fetch/providers/_article_markdown_copernicus.py` | `tests/unit/test_copernicus*`, `tests/unit/test_provider_catalog_copernicus.py` |
| elsevier | `src/paper_fetch/providers/elsevier.py`, `src/paper_fetch/providers/_elsevier_*.py`, `src/paper_fetch/providers/_article_markdown_elsevier*.py` | `tests/unit/test_elsevier*` |
| ieee | `src/paper_fetch/providers/ieee.py`, `src/paper_fetch/providers/_ieee_*.py` | `tests/unit/test_ieee*`, `tests/unit/_ieee_provider_support.py` |

### 5.5 单 Provider 任务细化

每个 `B-<provider>` 都按下表执行。除 provider 名称和关注点不同外，不允许自行改变流程。

| Step | 目标 | 具体执行内容 | 完成标准 |
|---|---|---|---|
| Bx.1 | 生成最新 proposal | 运行 `python3 scripts/propose_cleaning_chain.py --provider <provider> --write`；检查紧凑文件和 evidence 文件都更新；确认 `fixtures_digest` 覆盖所有参与 fixture | proposal 可读，digest 存在，未写无关 provider |
| Bx.2 | 获取 blocking/warning 清单 | 运行 `--check-contract`；把输出拆成 `missing_must_include`、`truly_vacuous`、`sentinel`、`cross_route_guard` 四类 | 清单明确，warning 不当作 blocker |
| Bx.3 | 复核每个 missing | 用生产清洗输出和 provider-local tests 判断 token 缺失原因；真实实现漏内容则先加失败测试再修实现；契约过激则只改对应 `markdown_contract.<purpose>`；无法覆盖则写明 evidence | 每个 missing 有 `implementation_fix` / `contract_adjustment` / `explained` 结论 |
| Bx.4 | 复核每个 dead | `sentinel` 保留并豁免；`cross_route_guard` 保留 warning；`truly_vacuous` 删除或改写契约；如果 dead 暴露实现缺口则补测试和实现 | 没有未分类 dead；只有 truly vacuous 能阻塞 |
| Bx.5 | 回归 provider-local 行为 | 运行 provider focused tests；如实现影响 expected output，用项目 snapshot 工具更新 provider-specific expected，并说明原因 | provider focused tests 通过或失败原因明确 |
| Bx.6 | 最终 contract check | 再跑 `--check-contract`；确认无 blocking drift，warning-only 项记录在 final report | `B-<provider>` 可交付给下一个 provider |

**Required workflow**

1. Run `python3 scripts/propose_cleaning_chain.py --provider <provider> --write`.
2. Run `python3 scripts/propose_cleaning_chain.py --provider <provider> --check-contract`.
3. For every `missing_must_include`, verify against production cleaning output:
   - if implementation lost real content, add/adjust provider-local test and fix provider-owned implementation;
   - if contract is too strict or token wording is wrong, update only the relevant `markdown_contract.<purpose>`;
   - if purpose route is intentionally null or not represented, document the reason in proposal/review as appropriate.
4. For every `dead_must_not_include`, classify:
   - `sentinel`: keep and mark exempt;
   - `cross_route_guard`: keep as warning, do not block, route annotation optional;
   - `truly_vacuous`: remove or rewrite the manifest assertion, unless it reveals a real implementation gap.
5. Rerun `--check-contract` and provider-local focused tests.

**Acceptance commands**

```bash
python3 scripts/propose_cleaning_chain.py --provider <provider> --check-contract
PYTHONPATH=src python3 -m pytest tests/unit/test_<provider>* -q
PYTHONPATH=src python3 -m pytest tests/unit/test_propose_cleaning_chain.py -q
```

**Final report format**

- provider
- proposal files written
- missing items resolved, with outcome `implementation_fix` / `contract_adjustment` / `explained`
- dead items classified, with counts by `sentinel` / `cross_route_guard` / `truly_vacuous`
- tests run and results
- remaining warnings that intentionally do not block

---

## 6. Phase C：接入 DAG

**目标**：把 `propose-cleaning-chain` 变成 coordinator 的固定 task，而不是 implementation 阶段的可选手动步骤。

**Subagent brief**

- Goal：更新 coordinator DAG、state schema、brief generation 和 onboarding docs。
- Allowed files：
  - `scripts/onboard_from_manifests.py`
  - `docs/ai-onboarding/onboarding-state.schema.json`
  - `docs/ai-onboarding/README.md`
  - `docs/ai-onboarding/coordinator-spec.md`
  - `docs/ai-onboarding/automation-roadmap.md`
  - `docs/ai-onboarding/instruction.md`
  - `docs/ai-onboarding/agent-task-brief.md`
  - `tests/unit/test_onboard_from_manifests.py`
- Forbidden files：
  - provider implementation files
  - provider manifests
  - proposal artifacts

### 6.1 Phase C 任务卡

| Task | 目标 | 具体执行内容 | 完成标准 |
|---|---|---|---|
| C1 | DAG/task/schema 接入 | 在 coordinator DAG 中插入 `propose-cleaning-chain`；更新 task 顺序、task id 常量、state schema enum、start 生成的 task 列表；确认 `start --provider` 和 `start --manifest` 的行为一致 | dry-run task 列表为 13 步，新 task 位于 capture 后 scaffold 前 |
| C2 | run/verify/checks 行为接入 | 为新 task 增加 `run` 分支，执行 `scripts/propose_cleaning_chain.py --provider <p> --write`；更新 `verify`、`run-checks`、`advance`、`next`、`summarize` 中的 task 识别和状态推进 | coordinator 能单独 verify/run/check/advance 新 task |
| C3 | implementation brief inline proposal | 更新 implementation brief 构造逻辑：读取 `<provider>.yml` 紧凑 proposal 并 inline；不得 inline `.evidence.yml`；proposal 缺失时给出明确前置 task 提示 | generated `briefs/implement-provider.yml` 含 proposal 摘要且不含全量 evidence |
| C4 | onboarding docs 同步 | 更新 `README.md`、`coordinator-spec.md`、`automation-roadmap.md`、`instruction.md`、`agent-task-brief.md` 中的 DAG、固定步骤、worker prompt 输入和自动化边界 | 文档不再把 proposer 描述为可选手动步骤 |
| C5 | coordinator focused tests | 更新/新增 `test_onboard_from_manifests.py` 覆盖 13-task DAG、new task run command、brief inline、state schema、summarize/advance 行为 | focused tests 通过 |

每个 C 任务 final report 必须说明是否修改了 task 顺序、state schema、brief 文件格式；如果没有改某项，要说明原因。

**Required edits**

1. 在 DAG 中新增 `propose-cleaning-chain`，位于 `capture-fixtures` 和 `scaffold` 之间。
2. `run` 对该 task 调用 `scripts/propose_cleaning_chain.py --provider <p> --write`。
3. `start`/brief generation 让 implementation prompt inline 紧凑 proposal 文件；不得 inline `.evidence.yml` 全量证据。
4. `verify`、`run-checks`、`advance`、`next`、`summarize` 等 task 枚举全部识别新 task。
5. docs 中把旧的“capture 后可先运行 proposer”改成固定步骤。

**Acceptance commands**

```bash
PYTHONPATH=src python3 -m pytest tests/unit/test_onboard_from_manifests.py -q
PYTHONPATH=src python3 -m pytest tests/unit/test_provider_manifest_schema.py -q
```

**Final report format**

- DAG before/after
- coordinator behavior changed
- docs changed
- tests run and results

---

## 7. Phase D：接入 Contract Gate 和 Failure Recovery

**目标**：在 provider-local acceptance 增加 contract drift gate，并把失败恢复到 implement 阶段就地调和。

**Subagent brief**

- Goal：实现 `MARKDOWN_CONTRACT_DRIFT` gate、retryable recovery 和 implement 阶段受限调和规则。
- Allowed files：
  - `scripts/onboard_from_manifests.py`
  - `scripts/propose_cleaning_chain.py`
  - `docs/ai-onboarding/failure-recovery.md`
  - `docs/ai-onboarding/coordinator-spec.md`
  - `docs/ai-onboarding/hard-constraints.md`
  - `docs/ai-onboarding/agent-task-brief.md`
  - `docs/ai-onboarding/acceptance.md`
  - `tests/unit/test_onboard_from_manifests.py`
  - `tests/unit/test_propose_cleaning_chain.py`
- Forbidden files：
  - provider implementation files
  - provider manifests
  - generated proposal artifacts

### 7.1 Phase D 任务卡

| Task | 目标 | 具体执行内容 | 完成标准 |
|---|---|---|---|
| D1 | provider-local contract gate | 在 provider-local acceptance/run-checks 中加入 `propose_cleaning_chain.py --provider <p> --check-contract`；保证命令失败时 coordinator 捕获 structured failure | acceptance 会消费 proposal contract delta |
| D2 | digest freshness gate | 在 gate 中读取 proposal `fixtures_digest` 并与当前 fixture sha256 比对；过期时提示重跑 `propose-cleaning-chain`，不要误报为 provider 实现失败 | fixture 改动后旧 proposal 会被拦截 |
| D3 | `MARKDOWN_CONTRACT_DRIFT` recovery | 新增 structured code，`retryable: true`；更新 failure recovery 文档和 coordinator routing；失败恢复目标为 `implement-provider` | diagnose/resume-blocked 能显示稳定恢复动作 |
| D4 | implement 阶段调和规则 | 更新 implementation brief/hard constraints：只有 `MARKDOWN_CONTRACT_DRIFT` 场景允许修改当前 provider manifest 的相关 `markdown_contract` purpose；禁止改 routing、fixtures、access policy、docs facts 和无关 purpose | worker 边界清楚，不把 manifest 全量开放 |
| D5 | gate focused tests | 单测覆盖 warning-only 不失败、sentinel 不失败、truly vacuous 失败、missing 失败、digest stale 失败、recovery target 为 implement | focused tests 通过 |

每个 D 任务 final report 必须说明 blocking/warning 判定是否与 §2.3 一致。

**Required edits**

1. provider-local acceptance 调用 `propose_cleaning_chain.py --provider <p> --check-contract`。
2. gate 同时检查 `fixtures_digest` freshness。
3. 新增 structured code `MARKDOWN_CONTRACT_DRIFT`，`retryable: true`。
4. recovery target 为 `implement-provider`。
5. implementation brief/hard constraints 增加受限例外：只在 `MARKDOWN_CONTRACT_DRIFT` 场景下，允许修改当前 provider manifest 的相关 `markdown_contract` purpose；其他 manifest 字段仍禁止。
6. `cross_route_guard` warning 不阻塞 acceptance；`sentinel` 不阻塞；`truly_vacuous` 和未解释 missing 阻塞。

**Acceptance commands**

```bash
PYTHONPATH=src python3 -m pytest tests/unit/test_onboard_from_manifests.py -q
PYTHONPATH=src python3 -m pytest tests/unit/test_propose_cleaning_chain.py -q
PYTHONPATH=src python3 -m pytest tests/unit/test_provider_markdown_review_contract.py -q
```

**Final report format**

- new failure code and recovery target
- gate behavior by classification
- implement-stage manifest edit exception
- tests run and results

---

## 8. Phase E：全量验证和最终文档同步

**目标**：确认 Phase A-D 与 provider 清账结果没有破坏现有 onboarding、manifest、docs 和 unit gates。

**Subagent brief**

- Goal：运行收尾验证，修复遗漏的 docs drift 或 schema/test drift。
- Allowed files：
  - docs touched by Phase C/D
  - tests touched by Phase A/C/D
  - `AI_ONBOARDING_OPTIMIZATION.md`
- Forbidden files：
  - provider implementation files，除非 Phase B 留下明确未收尾失败
  - unrelated generated artifacts

### 8.1 Phase E 任务卡

| Task | 目标 | 具体执行内容 | 完成标准 |
|---|---|---|---|
| E1 | focused 验证 | 运行 proposer、coordinator、manifest、review contract、docs drift 的 focused tests；只修与本优化直接相关的失败 | focused commands 通过，或失败有明确阻塞原因 |
| E2 | full unit 验证 | 运行 `PYTHONPATH=src python3 -m pytest tests/unit -q`；若失败，先判断是否由本优化引入；只修本优化引入的失败 | full unit 通过，或列出非本任务遗留失败 |
| E3 | 最终摘要和完成检查 | 汇总 A-D 的改动、每个 provider 清账结果、warning-only 项、测试命令、未触发 GitHub CI；确认 §10 完成定义逐项满足 | 最终报告可直接交给 operator 审阅 |

E 阶段不新增功能；只做验证、文档 drift 收敛和最终报告。

**Required workflow**

1. 运行 focused checks。
2. 运行 full unit。
3. 运行 extraction rules validation。
4. 若 docs drift 失败，只修与本优化相关的 docs。
5. 生成最终执行摘要，列出每个 provider 清账状态。

**Acceptance commands**

```bash
PYTHONPATH=src python3 -m pytest tests/unit/test_propose_cleaning_chain.py -q
PYTHONPATH=src python3 -m pytest tests/unit/test_onboard_from_manifests.py -q
PYTHONPATH=src python3 -m pytest tests/unit/test_provider_manifest_schema.py -q
PYTHONPATH=src python3 -m pytest tests/unit/test_manifest_bundle_sync.py -q
PYTHONPATH=src python3 -m pytest tests/unit/test_human_docs_drift.py -q
python3 scripts/validate_extraction_rules.py
PYTHONPATH=src python3 -m pytest tests/unit -q
```

**Final report format**

- all tests run and results
- provider clearing table
- remaining non-blocking warnings
- files changed by phase
- explicit note that GitHub CI was not triggered

---

## 9. 背景数据和判断依据

以下数据来自对 9 个已实现 provider 执行只读命令：

```bash
python3 scripts/propose_cleaning_chain.py --provider <provider> --check-contract
```

当时未写盘、未污染仓库。该数据用于指导清账优先级，不代表 Phase A 修复生产链 baseline 后的最终 gate 结果。

| provider | missing_must_include (purpose:token) | dead_must_not_include | overcleaning_probes | token_conflict |
|---|---|---|---:|---:|
| elsevier | formula:`Equation`, figure:`Figure`, supplementary:`Supplementary` | Download PDF, Google Scholar, `[Formula unavailable]`, Article Metrics, Download Citation | 20 | 5 |
| springer | formula:`Equation`, references:`Reference`, abstract_only/access_gate:`## Abstract` | `[Formula unavailable]`, Article Metrics, Subscribe | 80 | 19 |
| wiley | supplementary:`Supplementary` | `[Formula unavailable]`, Access Denied | 80 | 34 |
| science | formula:`Equation`, figure:`Figure`, references:`Reference`, abstract_only/access_gate:`## Abstract` | `[Formula unavailable]`, Access Denied | 80 | 27 |
| pnas | references:`Reference`, abstract_only/access_gate:`## Abstract` | Article Metrics, Access Denied | 41 | 21 |
| ieee | structure/abstract_only:`## Abstract`, formula:`Equation`, supplementary:`Supplementary`, pdf_fallback:`#` | Download PDF, Google Scholar, `[Formula unavailable]`, Article Metrics, Download Citation | 80 | 3 |
| arxiv | structure:`## Abstract`, table:`Table`, formula:`Equation`, figure:`Figure`, references:`Reference`, pdf_fallback:`#` | Google Scholar, `[Formula unavailable]`, Article Metrics, Access Denied | 80 | 15 |
| copernicus | 无 | Download PDF, Article Metrics, Google Scholar, Access Denied | 80 | 7 |
| ams | 无 | `[Formula unavailable]`, Article Metrics, Access Denied | 80 | 17 |

跨 provider 结论：

- `## Abstract` 和 `Equation` 的普遍 missing 高度疑似 proposer baseline 与生产清洗链不一致，Phase A 必须先修。
- `[Formula unavailable]` 是转换器 fallback sentinel，不应因原始 HTML 中不存在而要求删除。
- `Access Denied` 在 PDF fallback 中常是防御性 sentinel，当前 fixture 干净时空转但仍有守护价值。
- `Google Scholar`、`Download PDF`、`Article Metrics`、`Download Citation`、`Subscribe` 多数属于站点 chrome 或跨 route guard，按已拍板决策只告警。
- `Supplementary`、`Reference`、`Figure`、`Table` 可能是真实契约过激或真实清洗缺口，必须逐 provider 用生产链复核。

---

## 10. 完成定义

本优化完成必须同时满足：

- `propose-cleaning-chain` 已是固定 DAG task。
- implementation worker prompt 可读取紧凑 proposal，但不 inline 全量 evidence。
- proposal 拆分、digest、分类、去重已实现并有单测。
- provider-local acceptance 已接 `--check-contract` 和 digest freshness gate。
- `MARKDOWN_CONTRACT_DRIFT` 已写入 failure recovery，且恢复到 `implement-provider`。
- implement 阶段受限调和 `markdown_contract` 的规则已写入 coordinator/docs/brief/hard constraints。
- 9 个存量 provider 已逐个清账，强制 gate 打开后不会因历史 dead/missing 被无谓卡住。
- focused tests、docs drift、extraction rules validation 和完整 unit 验证通过。
- 最终汇报明确列出未触发 GitHub CI。

# CloakBrowser 全链路迁移计划（细化版 · Codex `/goal` 友好）

日期：2026-05-15
作者：paper-fetch-skill 维护者
迭代版本：v2（在 v1 基础上将每个阶段细化到可由 Codex `/goal` 单步执行）

---

## 0. 如何用 Codex `/goal` 推进本计划

本计划被设计为一份 **可串行执行的工单集合**。每个 Phase 是一个完整的 `/goal` 单元：包含明确的输入文件、需要新增/重命名/删除的符号、最小可行实现细节、单元/集成验收命令、以及回滚锚点。建议执行顺序如下：

1. 在 Codex 中开启工作分支：`git switch -c cloakbrowser-migration-phase-N`。
2. 把对应 Phase 完整粘贴给 `/goal`，要求按"先改实现再改测试再跑测试"的顺序推进。
3. 每个 Phase 末尾的"验收命令"必须全部通过才可进入下一 Phase。
4. 验收失败时优先回到本 Phase 的"风险与回滚锚点"，不要跨 Phase 修补。

Codex `/goal` 单次输入建议：
- 直接复制"Phase N · 细化操作步骤"小节作为 prompt。
- 把当前仓库根目录 `/home/dictation/paper-fetch-skill` 作为工作目录。
- 必要时附上"通用约束"和"依赖关系图"两节作为前置上下文。

---

## 1. 当前状态快照（2026-05-15）

```text
src/paper_fetch/providers/_cloakbrowser.py        # 最小实现，无 imagePayload、无 disable_media 精细控制以外能力
src/paper_fetch/providers/_flaresolverr.py        # 1021 行，仍是 FetchedPublisherHtml / FlareSolverrFailure / merge_browser_context_seeds 的事实定义点
src/paper_fetch/runtime_playwright.py             # PlaywrightContextManager 直接 sync_playwright().start() + chromium.launch()
src/paper_fetch/providers/_pdf_fallback.py:255    # fetch_pdf_with_playwright 在无 runtime 时直接启动 stock Chromium
src/paper_fetch/providers/browser_workflow/
  fetchers/context.py:44                          # _new_playwright_context 在无 runtime 时直接 sync_playwright().start()
  html_extraction.py:173                          # fetch_html_with_direct_playwright 同样直接启动 stock Chromium
  shared.py:23                                    # BrowserWorkflowDeps 18 个字段仍含 *_with_flaresolverr / *_playwright 命名
  __init__.py:9                                   # 重导出表中 fetch_html_with_flaresolverr -> fetch_html_with_cloakbrowser alias
src/paper_fetch/provider_catalog.py:62            # ProviderSpec.requires_flaresolverr: bool = False
src/paper_fetch/providers/base.py:754             # ProviderBase 仍按 requires_flaresolverr 校验 FLARESOLVERR_ENV_FILE
src/paper_fetch/config.py:20-42                   # DEFAULT_VENDOR_FLARESOLVERR_DIR / FLARESOLVERR_* 仍在生产 config
src/paper_fetch/mcp/_instructions.py:30-32        # MCP 操作员说明仍把 FLARESOLVERR_* 列为必备
```

已完成的最小接入：
- `cloakbrowser>=0.3.28,<0.4` 进入 `pyproject.toml` / `requirements.txt`。
- `wiley / science / pnas / ams` 的 `default_browser_workflow_deps()` 将 `fetch_html_with_flaresolverr` 字段指向 `fetch_html_with_cloakbrowser`。
- `provider_status` 不再依赖 FlareSolverr 服务健康检查（已切到 `probe_runtime_status`，但仍通过 alias 名字暴露 FlareSolverr 字段）。
- Science 已经在未设置 `FLARESOLVERR_ENV_FILE` 时 live smoke 通过。

剩余的全链路工作集中在：直接 Playwright 启动点、PDF/ePDF fallback、资产下载（含 imagePayload 替代）、命名契约清理、状态/配置/manifest 同步、安装器/离线包/CI、最后归档或删除 FlareSolverr 正式路径。

---

## 2. 目标契约

最终判定：

- 生产代码（`src/paper_fetch/**`，不含 `legacy/**`）：
  - `git grep -nE "sync_playwright\(\)\.start|chromium\.launch" src/` 返回为空。
  - `git grep -nE "fetch_html_with_flaresolverr|warm_browser_context_with_flaresolverr|fetch_html_with_direct_playwright|_new_playwright_context|requires_flaresolverr|FLARESOLVERR_" src/` 仅在 `legacy/` 子树或显式 alias re-export 行命中。
- `python3 -c "from paper_fetch.providers.browser_workflow.shared import default_browser_workflow_deps; default_browser_workflow_deps()"` 不再 import `_flaresolverr.py`。
- `provider_status({"wiley", "science", "pnas", "ams"})` 在仅有 `CLOAKBROWSER_HEADLESS=true` 的 env 下报告 `READY`。
- 单元测试全部通过：`PYTHONPATH=src python3 -m pytest tests/unit -q`。
- 至少一个 live smoke 通过：`PAPER_FETCH_RUN_LIVE=1 PYTHONPATH=src python3 -m pytest -n 0 tests/live/test_live_publishers.py::LivePublisherTests::test_wiley_doi_live_fulltext -q`。
- 离线包构建脚本 / Windows installer / CI release workflow 不再要求 `vendor/flaresolverr` 或 FlareSolverr wheelhouse。

**不在本计划范围**：
- 完全从依赖树移除 `playwright` 包（CloakBrowser Python wrapper 内部仍依赖）。
- 默认随安装包重分发 CloakBrowser binary（需先解决 Binary License）。
- 处理人工 CAPTCHA 或无授权 access gate。

---

## 3. 通用约束（每个 Phase 都要遵守）

1. **不破坏外部 contract**：`FetchedPublisherHtml` 字段、`browser_context_seed` 三键（`browser_cookies`/`browser_user_agent`/`browser_final_url`）、`html_fetcher` 诊断字段在迁移期间保持向后兼容。新增字段允许，删除/改名旧字段不允许（直到 Phase 9）。
2. **每个 Phase 必须保留 compatibility alias 一轮**：旧名通过 `__init__.py` re-export 指向新实现；测试单独覆盖 alias 仍可工作。
3. **不引入两个并行 backend**：本次目标是 CloakBrowser-only。`/goal` 不应建议保留 `flaresolverr|cloakbrowser` 双选项开关。
4. **artifact 目录结构保持**：`artifact_dir / "cloakbrowser"` 用于 CloakBrowser 产物；`artifact_dir / "flaresolverr"` 在 Phase 9 之前可以保留为空。
5. **诊断字段命名**：HTML 成功路径标记 `html_fetcher="cloakbrowser"`；fast preflight 成功路径标记 `html_fetcher="cloakbrowser_fast"`。**不再** 使用 `html_fetcher="flaresolverr"` 作为默认值。
6. **不修改测试断言以遮蔽迁移问题**：测试如果失败，要么修迁移代码，要么改测试逻辑反映新行为；不要靠 `pytest.skip` 或 `xfail` 跳过。
7. **生产代码不能 `try: import playwright`**：导入 stock Playwright API 的入口必须收敛到 `runtime_playwright.py`（Phase 2 后改名为 `runtime_browser.py`）内部。
8. **关于 Playwright 类型**：CloakBrowser 返回的对象是 Playwright `Browser` / `BrowserContext`，因此 `from playwright.sync_api import ...` 仍允许出现在 **类型注释 / 异常捕获 / 接收对象的下游代码**，只是不能用来启动浏览器。

---

## 4. 依赖关系图

```text
Phase 1 (browser-neutral types & aliases)
    │
    └─► Phase 2 (runtime_playwright -> runtime_browser，统一启动器)
            │
            ├─► Phase 3 (PNAS fast preflight)
            │
            ├─► Phase 4 (PDF/ePDF fallback)
            │       │
            │       └─► Phase 5 (asset & supplementary downloads)
            │               │
            │               └─► Phase 6 (imagePayload 等价实现)
            │
            └─► Phase 7 (status / config / manifest 清理)
                    │
                    └─► Phase 8 (安装器 / 离线包 / CI)
                            │
                            └─► Phase 9 (删除或归档 FlareSolverr)
```

Phase 1 是所有后续阶段的语义基础；Phase 6 是 Phase 9 的硬阻塞依赖（不实现 imagePayload 等价能力，FlareSolverr patch 不能下线）。Phase 7 不依赖 Phase 4/5/6，可在 Phase 2 完成后并行推进，但建议放在 Phase 6 之后以减少回滚噪声。

---

## 5. Phase 详细操作步骤

### Phase 1 · 稳定 browser-neutral runtime contract

**目标**：从依赖字段、失败异常类型、诊断字段名上把 "FlareSolverr" 命名抽离出来，建立 browser-neutral 契约。所有调用方继续工作，但语义上不再绑死 FlareSolverr。

**输入文件**：
- `src/paper_fetch/providers/_flaresolverr.py`
- `src/paper_fetch/providers/_cloakbrowser.py`
- `src/paper_fetch/providers/browser_workflow/shared.py`
- `src/paper_fetch/providers/browser_workflow/__init__.py`
- `src/paper_fetch/providers/browser_workflow/bootstrap.py`
- `src/paper_fetch/providers/browser_workflow/html_extraction.py`
- `src/paper_fetch/providers/browser_workflow/asset_download.py`
- `src/paper_fetch/providers/browser_workflow/pdf_fallback.py`
- `tests/unit/test_browser_workflow_deps.py`
- `tests/unit/test_cloakbrowser_backend.py`

**细化操作步骤**：

1. 新增 `src/paper_fetch/providers/browser_runtime/__init__.py`，导出 browser-neutral 类型与协议：

   ```python
   # browser_runtime/__init__.py
   from .types import (
       BrowserRuntimeConfig,
       BrowserRuntimeFailure,
       BrowserFetchedHtml,
       BrowserImagePayload,
   )
   from .api import (
       load_runtime_config,
       ensure_runtime_ready,
       probe_runtime_status,
       fetch_html_with_browser,
       warm_browser_context,
   )
   ```

   - `types.py`：
     - `BrowserRuntimeConfig`：迁移期间是 `CloakBrowserRuntimeConfig` 的别名（`BrowserRuntimeConfig = CloakBrowserRuntimeConfig`），后续直接用前者。
     - `BrowserRuntimeFailure`：`CloakBrowserFailure` 的别名（同上）。注意保留 `FlareSolverrFailure` 作为基类以兼容旧 `isinstance` 检查。
     - `BrowserFetchedHtml`：`FetchedPublisherHtml` 的别名（同上）。
     - `BrowserImagePayload`：新 `TypedDict`，字段同 `_payload_from_flaresolverr_image_payload()` 的输出（`bodyB64` / `contentType` / `url` / `status` / `width` / `height`）。

   - `api.py`：
     - `load_runtime_config(env, *, provider, doi) -> BrowserRuntimeConfig`：转发 `_cloakbrowser.load_runtime_config`。
     - `ensure_runtime_ready(config)`：转发 `_cloakbrowser.ensure_runtime_ready`。
     - `probe_runtime_status(env, *, provider, doi="probe://browser/status")`：转发 `_cloakbrowser.probe_runtime_status`。
     - `fetch_html_with_browser(candidate_urls, *, publisher, config, **kwargs)`：转发 `_cloakbrowser.fetch_html_with_cloakbrowser`，并把 `paper_fetch_html_fetcher_name` 属性置为 `"cloakbrowser"`。
     - `warm_browser_context(...)`：转发 `_cloakbrowser.warm_browser_context_with_cloakbrowser`。

2. 改造 `_cloakbrowser.py`：
   - 把 `from ._flaresolverr import DEFAULT_FLARESOLVERR_MAX_TIMEOUT_MS, DEFAULT_FLARESOLVERR_WAIT_SECONDS, DEFAULT_FLARESOLVERR_WARM_WAIT_SECONDS` 中的常量在本模块内重新命名：
     ```python
     DEFAULT_BROWSER_RUNTIME_MAX_TIMEOUT_MS = 120000
     DEFAULT_BROWSER_RUNTIME_WAIT_SECONDS = 8
     DEFAULT_BROWSER_RUNTIME_WARM_WAIT_SECONDS = 1
     ```
   - 把 `fetch_html_with_cloakbrowser.paper_fetch_html_fetcher_name` 改为 `"cloakbrowser"`（不变），并新增 `fetch_html_with_cloakbrowser_fast = ...`（同函数对象但 `paper_fetch_html_fetcher_name = "cloakbrowser_fast"`，供 Phase 3 重用）。
   - **保留** `from ._flaresolverr import FetchedPublisherHtml, FlareSolverrFailure, merge_browser_context_seeds, normalize_browser_cookies_for_playwright, parse_optional_int`：这些函数尚未迁移，本阶段仅做命名层抽象。

3. 改造 `browser_workflow/shared.py:BrowserWorkflowDeps`：
   - 把 18 个字段重新命名为 browser-neutral 名称：

     | 旧字段 | 新字段 |
     | --- | --- |
     | `fetch_html_with_flaresolverr` | `fetch_html_with_browser` |
     | `warm_browser_context_with_flaresolverr` | `warm_browser_context` |
     | `fetch_pdf_with_playwright` | `fetch_pdf_with_browser` |
     | `fetch_html_with_direct_playwright` | `fetch_html_with_fast_browser` |
     | `_build_shared_playwright_file_fetcher` | `_build_shared_browser_file_fetcher` |
     | `_build_shared_playwright_image_fetcher` | `_build_shared_browser_image_fetcher` |

   - 其余字段（`fetch_seeded_browser_pdf_payload` / `pdf_browser_context_seed` / `refresh_browser_context_seed` / `download_assets` / `bootstrap_browser_workflow` / 各 `_cached_*` / `_assets_matching_download_failures` / `_browser_workflow_image_download_candidates` / `extract_atypon_browser_workflow_markdown` / `split_body_and_supplementary_assets` / `load_runtime_config` / `ensure_runtime_ready` / `probe_runtime_status`）名称不变。
   - 在同一文件末尾增加 deprecation-tolerant 工厂函数 `default_browser_workflow_deps_with_legacy_aliases()`，仅供旧测试使用（**不让生产代码引用**）。
   - 修改 `default_browser_workflow_deps()` 的 import 改为：

     ```python
     from ..browser_runtime import (
         ensure_runtime_ready,
         fetch_html_with_browser,
         load_runtime_config,
         probe_runtime_status,
         warm_browser_context,
     )
     ```

4. 把所有 `deps.fetch_html_with_flaresolverr(...)` 调用改为 `deps.fetch_html_with_browser(...)`：
   - `browser_workflow/asset_download.py` 共 3 处（行 225 / 407 / 482）。
   - `browser_workflow/bootstrap.py` 共 2 处（行 40 / 53）。
   - `browser_workflow/html_extraction.py:_fetch_flaresolverr_html_payload` 改名为 `_fetch_browser_html_payload`，保留旧名作为本模块内的 alias：
     ```python
     _fetch_flaresolverr_html_payload = _fetch_browser_html_payload  # legacy alias
     _fetch_flaresolverr_html_payload_with_fast_path = _fetch_browser_html_payload_with_fast_path
     ```
   - `bootstrap.py` 内的 `deps.fetch_html_with_flaresolverr` 同步改名为 `deps.fetch_html_with_browser`。
   - `pdf_fallback.py:fetch_seeded_browser_pdf_payload` 内的 `deps.fetch_pdf_with_playwright` 改名为 `deps.fetch_pdf_with_browser`。

5. 改造 `browser_workflow/__init__.py:_EXPORTS`：
   - 对每个 browser-neutral 新名增加一行：
     ```python
     "fetch_html_with_browser": ("paper_fetch.providers.browser_runtime", "fetch_html_with_browser"),
     "warm_browser_context": ("paper_fetch.providers.browser_runtime", "warm_browser_context"),
     "fetch_pdf_with_browser": ("paper_fetch.providers._pdf_fallback", "fetch_pdf_with_playwright"),  # Phase 4 才会改名 _pdf_fallback 内部函数
     "fetch_html_with_fast_browser": (".html_extraction", "fetch_html_with_direct_playwright"),  # Phase 3 才会改名
     ```
   - **保留** 旧名行（`fetch_html_with_flaresolverr` / `warm_browser_context_with_flaresolverr` / `fetch_pdf_with_playwright` / `fetch_html_with_direct_playwright`）作为 compatibility alias，指向同一目标。

6. 改造 `tests/unit/test_browser_workflow_deps.py`：
   - 把所有 fixture 中的旧字段名替换为新名。
   - 单独新增一组 alias 测试 `test_legacy_aliases_still_resolve`，断言 `default_browser_workflow_deps_with_legacy_aliases()` 返回的对象在 `fetch_html_with_flaresolverr` 字段下仍可调用 → CloakBrowser 实现。

7. 改造 `tests/unit/test_cloakbrowser_backend.py`：
   - 增加 `test_fetch_html_with_browser_marks_diagnostic("cloakbrowser")`：mock CloakBrowser launch，确认 `RawFulltextPayload.content.diagnostics["html_fetcher"] == "cloakbrowser"`。
   - 增加 `test_browser_runtime_module_imports`：确认 `paper_fetch.providers.browser_runtime` 公开 `BrowserRuntimeConfig` / `BrowserRuntimeFailure` / `BrowserFetchedHtml` / `BrowserImagePayload` / `fetch_html_with_browser` / `warm_browser_context` / `load_runtime_config` / `ensure_runtime_ready` / `probe_runtime_status`。

**验收命令**：

```bash
PYTHONPATH=src python3 -m pytest \
  tests/unit/test_browser_workflow_deps.py \
  tests/unit/test_cloakbrowser_backend.py \
  tests/unit/test_provider_request_options.py \
  -q
git grep -nE "fetch_html_with_flaresolverr|warm_browser_context_with_flaresolverr" src/paper_fetch/providers/browser_workflow/ \
  | grep -v "__init__.py" \
  | grep -v "# legacy alias"   # 期待为空
```

**风险与回滚锚点**：
- 旧测试若大量依赖字段名 `fetch_html_with_flaresolverr`，可先在 Phase 1 末尾保留 alias，不强制大改测试。
- 如果 `_EXPORTS` 表里同时有 `fetch_html_with_browser` 和 `fetch_html_with_flaresolverr` 指向同一目标，注意 `__getattr__` 缓存：第一次访问后会写入 `globals()`，因此重名风险低，但需要在 docstring 中注释。
- 回滚锚点：保留 v1 计划文件 + `git revert` 单个 commit 即可，因为本阶段没有删除任何运行时函数。

---

### Phase 2 · 统一 RuntimeContext 浏览器生命周期

**目标**：所有 shared browser/context 由 CloakBrowser 创建。生产代码不再直接 `sync_playwright().start()` 启动 stock Chromium。

**输入文件**：
- `src/paper_fetch/runtime_playwright.py`
- `src/paper_fetch/runtime.py`（持有 `RuntimeContext` 并暴露 `new_playwright_context`）
- `tests/unit/test_runtime_playwright.py`（如不存在，新建）

**细化操作步骤**：

1. 把 `src/paper_fetch/runtime_playwright.py` 改为 `runtime_browser.py`：
   - `git mv src/paper_fetch/runtime_playwright.py src/paper_fetch/runtime_browser.py`
   - 保留 `runtime_playwright.py` 作为 compatibility re-export：
     ```python
     # runtime_playwright.py (1 行 alias，本 Phase 末尾保留)
     from .runtime_browser import PlaywrightContextManager  # noqa: F401  -- legacy alias
     ```

2. 在 `runtime_browser.py` 中重写 `PlaywrightContextManager`：
   - 重命名类为 `BrowserContextManager`，保留 `PlaywrightContextManager = BrowserContextManager` 作为 alias。
   - `browser()` 内部从：
     ```python
     from playwright.sync_api import sync_playwright
     manager = sync_playwright().start()
     browser = manager.chromium.launch(headless=active_headless)
     ```
     改为：
     ```python
     import cloakbrowser
     browser = cloakbrowser.launch(headless=active_headless, locale="en-US")
     ```
   - 移除 `_playwright_manager` 字段（CloakBrowser launch 返回的 `Browser` 自身已包含生命周期）。
   - `close()` 仅 `self._browser.close()`，不再调用 `manager.stop()`。
   - 在文件顶部加 module docstring：
     > "Browser lifecycle manager. All Playwright-typed objects returned by this module are launched by CloakBrowser, not stock Playwright."

3. 改造 `runtime.py`：
   - 找到 `RuntimeContext.new_playwright_context(...)`：将其内部委托改为 `BrowserContextManager.new_context(...)`，但保留 **方法名** `new_playwright_context` 作为 alias。
   - 新增 `RuntimeContext.new_browser_context(...)`，签名相同，作为推荐入口。所有 Phase 4/5 的新调用方使用新名。
   - 在 `RuntimeContext.__del__` / `close()` 中调用 `BrowserContextManager.close()`。

4. 增加 `tests/unit/test_runtime_browser.py`：
   - `test_browser_reused_across_calls`：mock `cloakbrowser.launch`，连续两次相同 `headless` 调用 `new_context` 应只 launch 一次。
   - `test_headless_change_restarts_browser`：headless True→False 应触发 `close()` + 重新 launch。
   - `test_legacy_playwright_alias_still_works`：`from paper_fetch.runtime_playwright import PlaywrightContextManager` 应等同 `BrowserContextManager`。
   - `test_no_direct_sync_playwright_usage`：通过 `inspect.getsource()` 断言 `runtime_browser.py` 源码不出现 `sync_playwright(`。

**验收命令**：

```bash
PYTHONPATH=src python3 -m pytest tests/unit/test_runtime_browser.py -q
git grep -nE "sync_playwright\(\)\.start|chromium\.launch" src/paper_fetch/runtime_browser.py src/paper_fetch/runtime.py
# 期待：以上 grep 输出为空。
git grep -nE "sync_playwright\(\)\.start|chromium\.launch" src/paper_fetch/   # 仍可能在 _pdf_fallback.py / fetchers/context.py / html_extraction.py 出现，Phase 3-5 处理
```

**风险与回滚锚点**：
- CloakBrowser binary 首次运行需要联网下载；`tests/unit/test_runtime_browser.py` 必须用 `monkeypatch.setattr("cloakbrowser.launch", ...)` 避免真实启动。
- 如果发现 `RuntimeContext.new_playwright_context` 在测试 fixture 中被广泛调用，先保留 alias，下游测试不必全部改名。
- 回滚锚点：`git mv` 反向操作 + 还原 `runtime_browser.py` 为 `runtime_playwright.py` 原内容。

---

### Phase 3 · 迁移 PNAS fast preflight

**目标**：`fetch_html_with_direct_playwright()` 改名 `fetch_html_with_fast_browser()`，底层从直接 stock Chromium launch 切到 CloakBrowser，并复用 Phase 2 的统一 lifecycle。

**输入文件**：
- `src/paper_fetch/providers/browser_workflow/html_extraction.py`
- `src/paper_fetch/providers/browser_workflow/bootstrap.py`
- `src/paper_fetch/providers/browser_workflow/__init__.py`
- `src/paper_fetch/providers/pnas.py`（如直接 import）
- `tests/unit/test_atypon_browser_workflow_provider_html.py`
- `tests/unit/test_atypon_browser_workflow_provider_fallbacks.py`

**细化操作步骤**：

1. 重写 `html_extraction.py:fetch_html_with_direct_playwright`（行 173-288）：
   - 在文件中保留旧名作为单行 alias：
     ```python
     fetch_html_with_direct_playwright = fetch_html_with_fast_browser  # legacy alias
     ```
   - 新函数 `fetch_html_with_fast_browser(candidate_urls, *, publisher, user_agent, headless=True, timeout_ms=_FAST_BROWSER_HTML_TIMEOUT_MS, context=None) -> BrowserFetchedHtml`：
     - 删除 `from playwright.sync_api import sync_playwright`。
     - 若 `context is not None`：`browser_context = context.new_browser_context(headless=headless, **context_kwargs)`；否则 `browser_context = BrowserContextManager().new_context(headless=headless, **context_kwargs)`，并在 `finally` 中关闭。
     - 保留 `domcontentloaded`、阻断 `image|font|stylesheet|media` 的 route handler、`detect_html_block`、`looks_like_abstract_redirect`。
     - 成功路径返回的 `BrowserFetchedHtml` 中 **不直接** 写 fetcher name 字段（fetcher name 通过 `paper_fetch_html_fetcher_name` 属性注入）。
   - 把 `_FAST_FLARESOLVERR_HTML_*` 常量重命名为 `_FAST_BROWSER_HTML_*`：
     - `_FAST_FLARESOLVERR_HTML_WAIT_SECONDS` → `_FAST_BROWSER_HTML_WAIT_SECONDS`
     - `_FAST_FLARESOLVERR_HTML_WARM_WAIT_SECONDS` → `_FAST_BROWSER_HTML_WARM_WAIT_SECONDS`
     - `_FAST_FLARESOLVERR_RETRY_KINDS` → `_FAST_BROWSER_HTML_RETRY_KINDS`
     - 保留旧名作为文件级 alias。
   - 给 `fetch_html_with_fast_browser` 加属性 `paper_fetch_html_fetcher_name = "cloakbrowser_fast"`。
   - `_fetch_browser_html_payload` 函数（Phase 1 重命名后的版本）中读取 `paper_fetch_html_fetcher_name`，因此 PNAS preflight 成功后 `RawFulltextPayload.content.diagnostics["html_fetcher"] == "cloakbrowser_fast"`。

2. 改造 `bootstrap.py`：找到 `deps.fetch_html_with_direct_playwright(...)`（约第 109 行），改名为 `deps.fetch_html_with_fast_browser(...)`。

3. 更新 `browser_workflow/__init__.py:_EXPORTS`：
   ```python
   "fetch_html_with_fast_browser": (".html_extraction", "fetch_html_with_fast_browser"),
   # 保留：
   "fetch_html_with_direct_playwright": (".html_extraction", "fetch_html_with_direct_playwright"),
   ```

4. 改造 PNAS provider：
   - `src/paper_fetch/providers/pnas.py` 中如果直接 import `fetch_html_with_direct_playwright`，统一改为 `fetch_html_with_fast_browser`。
   - 失败诊断字符串 `playwright_direct_failed` 改为 `fast_browser_failed`；保留旧 reason code 作为 alias 通过 `quality.reason_codes`（如果它已经是命名常量）。
   - `playwright_unavailable` 失败 reason 改名为 `browser_runtime_unavailable`，同样保留 alias。

5. 单测改造：
   - `tests/unit/test_atypon_browser_workflow_provider_html.py` 中所有 mock fetcher 名字段从 `flaresolverr` 改为 `cloakbrowser`，从 `playwright_direct` 改为 `cloakbrowser_fast`。
   - 新增 `test_pnas_fast_preflight_uses_cloakbrowser`：mock `cloakbrowser.launch`，断言 fast preflight 路径完全不进入 `sync_playwright()`。
   - 新增 `test_pnas_fast_failure_triggers_full_path`：fast preflight 失败时应 fallback 到 `fetch_html_with_browser`（cold path）。

**验收命令**：

```bash
PYTHONPATH=src python3 -m pytest \
  tests/unit/test_atypon_browser_workflow_provider_html.py \
  tests/unit/test_atypon_browser_workflow_provider_fallbacks.py \
  -q
git grep -nE "sync_playwright\(\)" src/paper_fetch/providers/browser_workflow/html_extraction.py
# 期待：空。
git grep -nE "fetch_html_with_direct_playwright" src/paper_fetch/   # 仅在 alias 行和 __init__ 重导出中出现
```

**风险与回滚锚点**：
- `_FAST_FLARESOLVERR_RETRY_KINDS` 是一个 set，重命名时必须更新所有 `import ... from ._flaresolverr` 的使用点（如果有）。
- PNAS live smoke 期间 fast preflight 经常以 challenge 失败再 fallback；保证 fallback 链 `fast -> full` 的 reason code 仍能命中现有 `_FAST_BROWSER_HTML_RETRY_KINDS`。
- 回滚：保留旧函数为一段独立 git commit，方便 `git revert`。

---

### Phase 4 · 迁移 PDF/ePDF fallback

**目标**：Wiley / Science / PNAS / AMS / IEEE 的 browser PDF fallback 使用 CloakBrowser-created context。`fetch_pdf_with_playwright()` 内部不再直接 `sync_playwright().start()`。

**输入文件**：
- `src/paper_fetch/providers/_pdf_fallback.py`（行 255-468）
- `src/paper_fetch/providers/browser_workflow/pdf_fallback.py`
- `src/paper_fetch/providers/ieee.py`（行 403 直接调用 `fetch_pdf_with_playwright`）
- `tests/unit/test_pdf_fallback_helpers.py`
- `tests/unit/test_atypon_browser_workflow_provider_fallbacks.py`

**细化操作步骤**：

1. 改造 `_pdf_fallback.py:fetch_pdf_with_playwright`（行 255）：
   - 新增 browser-neutral 入口 `fetch_pdf_with_browser(...)`，签名与旧函数完全一致。
   - 旧名保留为 alias：`fetch_pdf_with_playwright = fetch_pdf_with_browser`。
   - 内部把这块代码（行 311-314）：
     ```python
     manager = sync_playwright().start()
     browser = manager.chromium.launch(headless=headless)
     browser_context = browser.new_context(**context_kwargs)
     ```
     替换为：
     ```python
     from ..runtime_browser import BrowserContextManager
     manager = BrowserContextManager()
     browser_context = manager.new_context(headless=headless, **context_kwargs)
     ```
   - `finally` 块对应改为只 `manager.close()`（CloakBrowser 拥有 browser 生命周期，`manager.stop()` 不再需要）。
   - **类型导入仍可保留**：`from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError`（这两个异常类型用于 `try: ... except PlaywrightTimeoutError`，不启动浏览器，符合通用约束 §8）。
   - 失败 reason `missing_playwright` 改为 `missing_browser_runtime`，保留旧 alias。

2. 改造 `browser_workflow/pdf_fallback.py:fetch_seeded_browser_pdf_payload`：
   - `deps.fetch_pdf_with_playwright(...)` 改为 `deps.fetch_pdf_with_browser(...)`。
   - seed warming 调用从 `deps.pdf_browser_context_seed` 改为 `deps.warm_browser_context`（Phase 1 已经把 alias 指向同一 CloakBrowser 实现）。

3. 改造 IEEE provider：
   - `src/paper_fetch/providers/ieee.py` 行 40 / 403 中 `fetch_pdf_with_playwright` 改名为 `fetch_pdf_with_browser`（保留单行 alias 在 ieee.py 顶部不必要——直接改 import 即可）。
   - 注意 IEEE 既走 seeded clean-browser HTML 又走 seeded PDF fallback，确认两条路径都使用 CloakBrowser 启动。

4. 单测改造：
   - `tests/unit/test_pdf_fallback_helpers.py`：把所有 mock `playwright.sync_api.sync_playwright` 改为 mock `paper_fetch.runtime_browser.BrowserContextManager.new_context`。
   - 新增 `test_pdf_fallback_uses_cloakbrowser`：断言生产路径不进入 `sync_playwright(`，并且 PDF result 的 `final_url` 仍正确。
   - `tests/unit/test_atypon_browser_workflow_provider_fallbacks.py`：把 fallback 链断言改为 `cloakbrowser HTML -> cloakbrowser seeded PDF`。

**验收命令**：

```bash
PYTHONPATH=src python3 -m pytest \
  tests/unit/test_pdf_fallback_helpers.py \
  tests/unit/test_atypon_browser_workflow_provider_fallbacks.py \
  -q
git grep -nE "sync_playwright\(\)" src/paper_fetch/providers/_pdf_fallback.py src/paper_fetch/providers/browser_workflow/pdf_fallback.py src/paper_fetch/providers/ieee.py
# 期待：空。
PYTHONPATH=src python3 -m pytest tests/unit -q   # 全量回归
```

**风险与回滚锚点**：
- `_pdf_fallback.py` 内 `expect_download` 的事件模型依赖 Playwright API，但 CloakBrowser 返回的 `BrowserContext` 完全兼容，无需改 logic。
- IEEE clean-browser HTML 路径在 `ieee.py` 中可能也直接 import `runtime_playwright`，需 grep 后同步。
- 回滚：保留 alias 行后，可以单独 revert PDF fallback 改动而不影响 Phase 1/2/3。

---

### Phase 5 · 迁移正文资产和 supplementary 下载

**目标**：正文图片、表格图片、公式图片、supplementary 文件下载全部通过 CloakBrowser-created context；failure diagnostic 中的 `playwright_context_error` 保留为兼容 alias，新增 browser-neutral reason。

**输入文件**：
- `src/paper_fetch/providers/browser_workflow/fetchers/context.py`（行 44-80：`_new_playwright_context`）
- `src/paper_fetch/providers/browser_workflow/fetchers/image.py`（815 行）
- `src/paper_fetch/providers/browser_workflow/fetchers/file.py`
- `src/paper_fetch/providers/browser_workflow/fetchers/diagnostics.py`
- `src/paper_fetch/providers/browser_workflow/fetchers/__init__.py`
- `src/paper_fetch/providers/browser_workflow/asset_download.py`
- `tests/unit/test_atypon_browser_workflow_provider_asset_downloads.py`
- `tests/unit/test_atypon_browser_workflow_provider_asset_failures.py`
- `tests/unit/test_provider_request_options.py`

**细化操作步骤**：

1. 改造 `fetchers/context.py:_new_playwright_context`：
   - 新增 `_new_browser_context(*, runtime_context, headless, user_agent, use_runtime_shared_browser=True)`：
     - 当 `runtime_context is not None and use_runtime_shared_browser`：返回 `(None, None, runtime_context.new_browser_context(headless=headless, **context_kwargs))`。
     - 否则：
       ```python
       from ....runtime_browser import BrowserContextManager
       manager = BrowserContextManager()
       browser_context = manager.new_context(headless=headless, **context_kwargs)
       return manager, None, browser_context
       ```
   - 保留 `_new_playwright_context = _new_browser_context` 作为 alias。
   - 把元组中的 `browser` 槽位（之前是 stock chromium browser）改为 `None`，因为 `BrowserContextManager` 自身代表 browser owner。
   - 调用方 `_BasePlaywrightDocumentFetcher._ensure_context`（行 158-165）：把展开的三元组改为 `(self._browser_manager, _unused_browser, self._context)`，并在 `close()` 中：
     - 旧：依次 close page / context / browser / manager.stop()
     - 新：`page.close()` → `context.close()` → `self._browser_manager.close()`（`BrowserContextManager.close` 内部已 close browser）。

2. 类重命名（**仅命名，不改语义**）：
   - `_BasePlaywrightDocumentFetcher` → `_BaseBrowserDocumentFetcher`
   - `_SharedPlaywrightImageDocumentFetcher` → `_SharedBrowserImageDocumentFetcher`
   - `_SharedPlaywrightFileDocumentFetcher` → `_SharedBrowserFileDocumentFetcher`
   - `_ThreadLocalSharedPlaywrightImageDocumentFetcher` → `_ThreadLocalSharedBrowserImageDocumentFetcher`
   - `_ThreadLocalSharedPlaywrightFileDocumentFetcher` → `_ThreadLocalSharedBrowserFileDocumentFetcher`
   - `_build_shared_playwright_image_fetcher` → `_build_shared_browser_image_fetcher`
   - `_build_shared_playwright_file_fetcher` → `_build_shared_browser_file_fetcher`
   - 全部在文件末尾保留旧名 alias。

3. 改造 `diagnostics.py`：
   - 新增常量 `BROWSER_CONTEXT_ERROR = "browser_context_error"`。
   - `_context_failure_diagnostic` 写入 reason 时优先用 `browser_context_error`，再写一份 `playwright_context_error` 作为别名（key 同名时跳过）。
   - `_image_fetch_failure_reason` 中的字符串 `playwright_*` 改为 `browser_*` 并保留 alias。

4. 改造 `asset_download.py`：
   - `deps.fetch_html_with_flaresolverr(...)` （行 225 / 407 / 482）已在 Phase 1 改名为 `deps.fetch_html_with_browser(...)`，本阶段无新增改动。
   - 把 `_flaresolverr_image_document_payload` 重命名为 `_browser_image_document_payload`（Phase 6 才会引入真实 CloakBrowser 实现），保留旧名 alias。
   - `_supplementary_challenge_recovery_for` 中调用 `fetch_html_with_browser`，无需 `return_image_payload=True`（保持原行为）。
   - `_asset_challenge_recovery_for` 中 `deps.fetch_html_with_browser(..., return_image_payload=True)`：**注意 Phase 5 阶段这个参数仍会触发 `cloakbrowser_image_payload_unsupported` 失败**，但 challenge recovery 已有 attempts diagnostic，可以正常累积。该路径在 Phase 6 才会成功。

5. 单测改造：
   - `tests/unit/test_atypon_browser_workflow_provider_asset_downloads.py`：把所有 fetcher 名引用从 `playwright` 改为 `browser`；测试如直接构造 `_SharedPlaywrightImageDocumentFetcher`，改为 `_SharedBrowserImageDocumentFetcher`。
   - 新增 `test_no_direct_sync_playwright_in_fetchers`：通过 `inspect.getsource()` 断言 `fetchers/context.py` 不出现 `sync_playwright(`。
   - 新增 `test_failure_diagnostic_uses_browser_reason`：mock context error 触发 `browser_context_error`，旧 `playwright_context_error` 仍在 diagnostic dict 中作为 alias。

**验收命令**：

```bash
PYTHONPATH=src python3 -m pytest \
  tests/unit/test_atypon_browser_workflow_provider_asset_downloads.py \
  tests/unit/test_atypon_browser_workflow_provider_asset_failures.py \
  tests/unit/test_provider_request_options.py \
  -q
git grep -nE "sync_playwright\(\)\.start|chromium\.launch" src/paper_fetch/providers/browser_workflow/
# 期待：空。
git grep -nE "_BasePlaywrightDocumentFetcher\b" src/paper_fetch/   # 仅在 alias 定义行命中
```

**风险与回滚锚点**：
- 资产 worker 是多线程的（`_ThreadLocalShared*`），重命名时务必同步 `threading.local()` 引用。
- `imagePayload` 路径在本阶段仍失败，但 challenge recovery 应能 fallback 到普通 download。
- 回滚：本阶段改动量大，建议拆 2 个 commit（context+fetchers 一个；asset_download+测试一个），便于精准 revert。

---

### Phase 6 · 实现 CloakBrowser imagePayload 等价能力

**目标**：替代项目内 patched FlareSolverr 的 `solution.imagePayload` 能力。让 `fetch_html_with_browser(..., return_image_payload=True)` 在 CloakBrowser backend 内部实现等价行为。

**输入文件**：
- `src/paper_fetch/providers/_cloakbrowser.py`
- `src/paper_fetch/providers/browser_workflow/fetchers/image.py`
- `src/paper_fetch/providers/browser_workflow/fetchers/scripts.py`（持有 `_LOADED_IMAGE_CANVAS_EXPORT_SCRIPT`）
- `tests/unit/test_atypon_browser_workflow_provider_asset_failures.py`
- 新增 `tests/unit/test_browser_image_payload.py`

**细化操作步骤**：

1. 在 `_cloakbrowser.py` 实现 `_capture_image_payload(page, *, request_url, final_url) -> BrowserImagePayload | None`：
   - 监听 `page.goto(url)` 的 top-level response：
     - 通过 `page.expect_response(lambda r: r.url == request_url, timeout=timeout_ms)` 抓取真实图片 response。
     - 如果 `content_type` 起始 `image/`：直接 `response.body()` → base64。
   - 如果 top-level response 是 HTML（被 challenge 替换）：
     - 用 `page.query_selector("img")`：
       - 若存在 `<img>` 且 `naturalWidth > 0`：执行 `_LOADED_IMAGE_CANVAS_EXPORT_SCRIPT`（已存在于 `scripts.py`），返回 `dataURL` → 解码 base64 → 检验 magic bytes 是图片 → 构造 payload。
       - 若顶层文档是 SVG：`page.content()` 拿到原始 `<svg>` 文本 → 编码 `image/svg+xml`。
       - 否则：识别 Cloudflare / access gate HTML（用现有 `looks_like_cloudflare_challenge_failure` / `summarize_html` + `detect_html_block`），拒绝并返回 `None`。
   - 返回结构：
     ```python
     {
       "bodyB64": base64_str,
       "contentType": "image/png|jpeg|webp|svg+xml",
       "url": final_url,
       "status": int(response.status) if response else 200,
       "width": natural_width,
       "height": natural_height,
     }
     ```

2. 修改 `fetch_html_with_cloakbrowser`：
   - 删除原本 `return_image_payload=True` → raise `cloakbrowser_image_payload_unsupported` 的早返回。
   - 当 `return_image_payload=True` 时：
     - 设置 `disable_media = False`（图片必须真正加载）。
     - 在 `page.goto(...)` 后调用 `_capture_image_payload(...)`。
     - 把结果挂到 `FetchedPublisherHtml.image_payload`（该字段已经在 `_flaresolverr.py` 定义中存在）。
   - 失败时挂 `image_payload = None`，但仍返回 HTML 部分以便上层判断 challenge。

3. 改造 `fetchers/image.py:_flaresolverr_image_document_payload`：
   - 已经在 Phase 5 重命名为 `_browser_image_document_payload`，本阶段确保它读取的是 `FetchedPublisherHtml.image_payload`（即 CloakBrowser 写入的字段），无需改 logic。
   - `_payload_from_flaresolverr_image_payload` 已有验证逻辑（magic bytes / content_type），CloakBrowser 写入的字段会自然通过验证。

4. 提供更精细的 `summarize_html` 检测：
   - 如果 `_capture_image_payload` 看到 HTML 但 `detect_html_block` 没识别出 cloudflare：在 `failure reason` 中标记 `image_response_blocked_by_html_wrapper`。

5. 新增 `tests/unit/test_browser_image_payload.py`：
   - `test_capture_image_payload_returns_png_for_image_response`：mock `page.expect_response` 返回 `content-type: image/png` + 真实 PNG bytes。
   - `test_capture_image_payload_uses_canvas_when_response_is_challenge`：mock response 返回 HTML challenge，但 `<img>` 已加载 → canvas dataURL 返回 PNG。
   - `test_capture_image_payload_preserves_svg`：mock response 返回 `image/svg+xml`，断言 `contentType` 保留为 `image/svg+xml`。
   - `test_capture_image_payload_rejects_html_only`：mock response 返回 HTML 且 `<img>` 不存在 → 返回 `None`。

6. 改造旧测试：
   - `tests/unit/test_atypon_browser_workflow_provider_asset_failures.py` 中所有 `imagePayload` 路径的 mock：把 mock 目标从 `_flaresolverr.fetch_html_with_flaresolverr` 改为 `_cloakbrowser.fetch_html_with_cloakbrowser`，返回 `FetchedPublisherHtml` 时填充 `image_payload` 字段。
   - 验证 challenge recovery 现在能成功返回真实图片 bytes（不再是 fake）。

**验收命令**：

```bash
PYTHONPATH=src python3 -m pytest \
  tests/unit/test_browser_image_payload.py \
  tests/unit/test_atypon_browser_workflow_provider_asset_failures.py \
  tests/unit/test_atypon_browser_workflow_provider_asset_downloads.py \
  -q
PYTHONPATH=src python3 -c "
from paper_fetch.providers._cloakbrowser import fetch_html_with_cloakbrowser
# 仅 import smoke：确认签名兼容 return_image_payload
import inspect
sig = inspect.signature(fetch_html_with_cloakbrowser)
assert 'return_image_payload' in sig.parameters
print('signature ok')
"
```

**风险与回滚锚点**：
- canvas dataURL 在 cross-origin 图片上可能触发 SecurityError。CloakBrowser 通常注入与 FlareSolverr patch 类似的 stealth，但仍需在 `_LOADED_IMAGE_CANVAS_EXPORT_SCRIPT` 中保留 `try/catch` 并返回 `null`。
- SVG 检测必须严格：若 HTML 中包含 `<svg>` 但顶层是 HTML 文档（不是 image/svg+xml），不能误认为 SVG。
- 这是 Phase 9 删除 FlareSolverr patch 的硬阻塞 prerequisite；本阶段未通过验收前**禁止** 进入 Phase 9。
- 回滚锚点：CloakBrowser 实现失败时，可临时让 `return_image_payload=True` 仍调用旧 FlareSolverr 路径（保留 `_flaresolverr.fetch_html_with_flaresolverr` 作 fallback），但这会延后 Phase 9。

---

### Phase 7 · 状态探测、配置和 provider catalog 清理

**目标**：公开状态面、provider catalog、MCP 操作员说明不再暴露默认 FlareSolverr 要求。

**输入文件**：
- `src/paper_fetch/provider_catalog.py`
- `src/paper_fetch/providers/base.py`（行 754）
- `src/paper_fetch/config.py`
- `src/paper_fetch/mcp/_instructions.py`
- `docs/ai-onboarding/provider-manifest.schema.json`
- `docs/ai-onboarding/manifests/*.yml`（wiley / science / pnas / ams / 等）
- `tests/unit/test_provider_status.py`
- `tests/unit/test_probe_status_default.py`
- `tests/unit/test_manifest_bundle_sync.py`
- `tests/unit/test_scaffold_provider_from_manifest.py`

**细化操作步骤**：

1. 改造 `provider_catalog.py`：
   - 新增 `ProviderSpec.requires_browser_runtime: bool = False`。
   - 保留 `requires_flaresolverr: bool = False`，但在 `__post_init__` 中：若旧字段为 `True` 而新字段为 `False`，自动把新字段置 `True` 并 emit `DeprecationWarning`（仅一次）。
   - `to_dict()` 同时序列化新旧字段。

2. 改造 `providers/base.py:status()`（行 720-802）：
   - 用 `catalog.requires_browser_runtime or catalog.requires_flaresolverr` 触发 browser runtime 检查。
   - 替换 `flaresolverr_config` check 为 `browser_runtime`：
     - 检查 `cloakbrowser` 包可导入。
     - 检查 `CLOAKBROWSER_HEADLESS` 解析（用 `_cloakbrowser.probe_runtime_status`）。
     - **不强制** launch 浏览器（避免 status 探测慢）。
   - 旧 `flaresolverr_config` check 在 `requires_flaresolverr=True` 时仍可保留为只读 info（指向 `legacy/flaresolverr` 文档），但 status 不再因此变 `NOT_CONFIGURED`。

3. 改造 `config.py`：
   - `DEFAULT_VENDOR_FLARESOLVERR_DIR` / `DEFAULT_FLARESOLVERR_URL` / `FLARESOLVERR_*_ENV_VAR` 全部加 docstring：标记 "legacy; only consumed by paper_fetch.providers._flaresolverr"。
   - 新增 `CLOAKBROWSER_BINARY_PATH_ENV_VAR = "CLOAKBROWSER_BINARY_PATH"`（保留，Phase 8 安装器会用）。
   - 新增 `CLOAKBROWSER_USER_DATA_DIR_ENV_VAR = "CLOAKBROWSER_USER_DATA_DIR"`（可选）。

4. 改造 `mcp/_instructions.py:30-32`：
   - 删除 FlareSolverr 三条 env var 描述，新增：
     ```python
     ("CLOAKBROWSER_HEADLESS", "Optional override (true/false) for the CloakBrowser browser runtime. Defaults to true."),
     ("CLOAKBROWSER_TIMEOUT_MS", "Optional override for CloakBrowser per-request timeout. Defaults to 120000."),
     ```
   - 文案中"Wiley/Science/PNAS/AMS FlareSolverr endpoint"改为"Wiley/Science/PNAS/AMS browser runtime"。

5. 改造 manifest 与 schema：
   - `docs/ai-onboarding/provider-manifest.schema.json`：添加 `requires_browser_runtime: boolean` 字段；将 `requires_flaresolverr` 标为 deprecated（保留兼容）。
   - `docs/ai-onboarding/manifests/wiley.yml` / `science.yml` / `pnas.yml` / `ams.yml`：把 `requires_flaresolverr: true` 改为 `requires_browser_runtime: true`，或同时存在以便平滑迁移。

6. 同步 `tests/unit/test_provider_status.py` / `test_probe_status_default.py` / `test_manifest_bundle_sync.py` / `test_scaffold_provider_from_manifest.py`：
   - 把 `FLARESOLVERR_ENV_FILE=<path>` fixture 改为 `CLOAKBROWSER_HEADLESS=true`。
   - 断言 `provider_status({"wiley"})` 返回 `READY` 即可，无需检查 `flaresolverr_config` check。
   - 新增 `test_legacy_requires_flaresolverr_still_routes_to_browser_runtime`：构造 `requires_flaresolverr=True` 的旧 catalog，断言 status check 仍走新 browser_runtime 逻辑（通过 deprecation warning）。

**验收命令**：

```bash
PYTHONPATH=src python3 -m pytest \
  tests/unit/test_provider_status.py \
  tests/unit/test_probe_status_default.py \
  tests/unit/test_manifest_bundle_sync.py \
  tests/unit/test_scaffold_provider_from_manifest.py \
  -q
PYTHONPATH=src CLOAKBROWSER_HEADLESS=true python3 -c "
from paper_fetch.providers.registry import build_provider_registry
from paper_fetch.config import build_runtime_env
env = build_runtime_env()
for p in ('wiley','science','pnas','ams'):
    result = build_provider_registry().get(p).status(env)
    assert result.status == 'READY', (p, result)
print('all four READY without FLARESOLVERR_ENV_FILE')
"
```

**风险与回滚锚点**：
- MCP 用户已经习惯 `FLARESOLVERR_ENV_FILE`，文案变更可能影响外部 onboarding 文档；同步更新 `docs/flaresolverr.md` 为指向 legacy 状态。
- 回滚：仅 schema/manifest 改动，全部可单 commit revert。

---

### Phase 8 · 安装器、离线包和 CI 策略

**目标**：交付物与 CI 不再围绕 FlareSolverr 构建。在线安装器只需要 `cloakbrowser` Python 包；离线包不默认重分发 CloakBrowser binary。

**输入文件**：
- `install-offline.sh`
- `install-offline.ps1`
- `scripts/build-offline-package.sh`
- `scripts/build-offline-package-windows.ps1`
- `scripts/verify-offline-package.sh`
- `scripts/windows-installer-helper.ps1`
- `scripts/install-codex-skill.sh`
- `.github/workflows/release.yml`（如存在）
- `tests/unit/test_offline_package_build.py`
- `tests/unit/test_offline_install.py`
- `tests/unit/test_ci_release_workflow.py`
- `tests/unit/test_flaresolverr_setup_scripts.py`（本阶段标记为 legacy）

**细化操作步骤**：

1. 改造 `install-offline.sh` / `install-offline.ps1`：
   - 移除 `vendor/flaresolverr/setup_flaresolverr_source.sh` / `.ps1` 调用。
   - 移除 `python -m playwright install chromium` 默认调用（CloakBrowser 管理 binary）。
   - 增加：
     ```bash
     python3 -c "import cloakbrowser; cloakbrowser.ensure_runtime()" || true
     ```
     如果 `CLOAKBROWSER_BINARY_PATH` 已设置则跳过下载，否则首次运行时延迟下载。
   - 文档化 `CLOAKBROWSER_HEADLESS` / `CLOAKBROWSER_BINARY_PATH` 两个 env var。

2. 改造 `scripts/build-offline-package.sh` / `build-offline-package-windows.ps1`：
   - 移除 `vendor/flaresolverr` 源码 snapshot 打包步骤。
   - 移除 FlareSolverr wheelhouse 构建步骤。
   - 离线包内只携带 Python 依赖 wheels（含 `cloakbrowser`），**不携带** CloakBrowser binary。
   - 在 README 中明确 "首次运行需联网下载 CloakBrowser binary，或预置 `CLOAKBROWSER_BINARY_PATH`"。

3. 改造 `scripts/verify-offline-package.sh`：
   - 删除 `sessions.list` 健康检查。
   - 新增：`python3 -c "import cloakbrowser; assert hasattr(cloakbrowser, 'launch')"`。

4. 改造 `scripts/windows-installer-helper.ps1`：
   - 删除 FlareSolverr wrapper smoke。
   - 新增 `cloakbrowser` import + binary presence 检查（可选 launch probe，根据 `--probe-launch` 参数）。

5. 改造 `.github/workflows/release.yml` / CI 配置：
   - 删除 FlareSolverr source setup job 或降为 manual-trigger legacy job。
   - 新增 CloakBrowser runtime smoke job：`pip install cloakbrowser && python -c "import cloakbrowser"`。
   - 离线包 artifact 校验不再依赖 FlareSolverr wheelhouse。

6. 单测改造：
   - `tests/unit/test_offline_package_build.py`：断言生成的 archive **不包含** `vendor/flaresolverr/` 路径；包含 `cloakbrowser-*.whl`。
   - `tests/unit/test_offline_install.py`：断言 `install-offline.sh` dry-run 不调用 `python -m playwright install chromium` 也不调用 `flaresolverr-up`。
   - `tests/unit/test_ci_release_workflow.py`：断言 CI workflow YAML 中不出现 `flaresolverr` 字面量（除非在 legacy job 区段，被注释/skip 标记）。
   - `tests/unit/test_flaresolverr_setup_scripts.py` → 改名 `test_flaresolverr_setup_scripts_legacy.py`，并加 `pytest.mark.legacy`；普通 CI 不跑。

**验收命令**：

```bash
PYTHONPATH=src python3 -m pytest \
  tests/unit/test_offline_package_build.py \
  tests/unit/test_offline_install.py \
  tests/unit/test_ci_release_workflow.py \
  -q
bash scripts/verify-offline-package.sh path/to/built/archive   # 手动 smoke
```

**风险与回滚锚点**：
- 如果团队已经在 prod 部署中依赖 `vendor/flaresolverr`，本阶段建议 **同时保留** 旧脚本但默认不调用，给一个 minor release 的迁移期。
- CloakBrowser binary download 在受限网络下可能失败；离线包 README 必须包含手动 binary 部署说明。
- 回滚：保留所有旧脚本文件 + 在 Phase 8 commit 中只是新增"不再默认调用"的开关；可单 commit revert。

---

### Phase 9 · 删除或归档 FlareSolverr 正式路径

**目标**：FlareSolverr 退出默认产品路径。`_flaresolverr.py` 不再被生产代码 import；vendor / 脚本归档到 `legacy/`。

**前置条件**：Phase 6 已完成（CloakBrowser imagePayload 等价能力可用且通过测试）。

**输入文件**：
- `src/paper_fetch/providers/_flaresolverr.py`
- `vendor/flaresolverr/`（整个目录）
- `scripts/flaresolverr-up`
- `scripts/flaresolverr-down`
- `scripts/flaresolverr-status`
- `scripts/flaresolverr-up.ps1`
- `scripts/flaresolverr-down.ps1`
- `scripts/flaresolverr-status.ps1`
- `docs/flaresolverr.md`
- `docs/providers.md`
- `tests/unit/test_atypon_browser_workflow_flaresolverr.py`
- `tests/unit/test_flaresolverr_setup_scripts_legacy.py`
- `tests/unit/test_vendor_patches.py`

**细化操作步骤**：

1. 创建 `legacy/` 子树：
   ```bash
   mkdir -p legacy/flaresolverr/scripts
   git mv vendor/flaresolverr legacy/flaresolverr/vendor
   git mv scripts/flaresolverr-up legacy/flaresolverr/scripts/
   git mv scripts/flaresolverr-down legacy/flaresolverr/scripts/
   git mv scripts/flaresolverr-status legacy/flaresolverr/scripts/
   git mv scripts/flaresolverr-up.ps1 legacy/flaresolverr/scripts/
   git mv scripts/flaresolverr-down.ps1 legacy/flaresolverr/scripts/
   git mv scripts/flaresolverr-status.ps1 legacy/flaresolverr/scripts/
   git mv src/paper_fetch/providers/_flaresolverr.py legacy/flaresolverr/_flaresolverr.py
   ```

2. 在生产代码中移除最后的 `_flaresolverr` 依赖：
   - `_cloakbrowser.py` 顶部的 `from ._flaresolverr import FetchedPublisherHtml, FlareSolverrFailure, merge_browser_context_seeds, normalize_browser_cookies_for_playwright, parse_optional_int, DEFAULT_FLARESOLVERR_*` 需要替换：
     - 把 `FetchedPublisherHtml` / `FlareSolverrFailure` 的真正定义搬到 `browser_runtime/types.py`（Phase 1 时只是 alias）。
     - 把 `merge_browser_context_seeds` / `normalize_browser_cookies_for_playwright` / `parse_optional_int` 搬到 `browser_runtime/seed.py`。
     - 这些函数在 Phase 1-6 都被引用，因此搬运时保留 import path 兼容：
       ```python
       # browser_runtime/types.py
       @dataclass(frozen=True)
       class BrowserFetchedHtml: ...
       FetchedPublisherHtml = BrowserFetchedHtml  # public alias retained
       class BrowserRuntimeFailure(Exception): ...
       FlareSolverrFailure = BrowserRuntimeFailure  # public alias retained
       ```
   - 在 `browser_workflow/shared.py` / `asset_download.py` / `bootstrap.py` / `html_extraction.py` 中的 `from .._flaresolverr import ...` 全部改成 `from ..browser_runtime import ...`。
   - 旧 alias `from paper_fetch.providers._flaresolverr import ...` 仍可工作，但只通过 `legacy.flaresolverr._flaresolverr` shim 实现。

3. 移除 `config.py` 中的 FlareSolverr 默认值（但保留 env var 常量以便 legacy 模块使用）：
   - 删除 `DEFAULT_VENDOR_FLARESOLVERR_DIR` 与 `DEFAULT_FLARESOLVERR_URL`，或把它们迁到 `legacy/flaresolverr/_flaresolverr.py` 顶部。
   - 保留 `FLARESOLVERR_URL_ENV_VAR` / `FLARESOLVERR_ENV_FILE_ENV_VAR` 等常量字符串，但加 docstring "consumed only by legacy/flaresolverr."

4. 删除 `ProviderSpec.requires_flaresolverr` 字段：
   - 仅保留 `requires_browser_runtime`。
   - 同步 `manifests/*.yml` 与 schema：移除 `requires_flaresolverr` 行。

5. 文档归档：
   - `docs/flaresolverr.md` 顶部加显著的 `> ⚠️ Deprecated. FlareSolverr is no longer part of the default pipeline. See docs/providers.md and docs/architecture/target-architecture.md.`
   - `docs/providers.md` 能力矩阵更新为：
     ```text
     wiley   : CloakBrowser HTML -> CloakBrowser-seeded publisher PDF/ePDF -> Wiley TDM API PDF
     science : CloakBrowser HTML -> CloakBrowser-seeded publisher PDF/ePDF
     pnas    : CloakBrowser fast HTML preflight -> CloakBrowser HTML -> CloakBrowser-seeded publisher PDF/ePDF
     ams     : DOI landing -> CloakBrowser HTML -> CloakBrowser-seeded publisher PDF
     ieee    : CloakBrowser clean-browser HTML -> CloakBrowser-seeded PDF
     ```

6. 移除/重命名遗留测试：
   - `tests/unit/test_atypon_browser_workflow_flaresolverr.py`：拆为 browser-neutral 部分（重命名为 `test_atypon_browser_workflow_browser_runtime.py`）+ legacy 部分（删除或 mark legacy）。
   - `tests/unit/test_vendor_patches.py`：移到 `tests/legacy/`，加 `pytest.mark.legacy`，默认 CI 不跑。
   - `tests/unit/test_flaresolverr_setup_scripts_legacy.py`：保留但仅 legacy job 跑。

7. 在 `pyproject.toml` 中：
   - 把 `[project.optional-dependencies].legacy_flaresolverr`（如不存在则新增）设为 `["urllib3"]`，明确 legacy 仅在 opt-in 时可用。
   - 主依赖列表不再依赖 `urllib3` 唯一通过 FlareSolverr 才会用到的部分；如果其他地方仍需，保留。

**验收命令**：

```bash
PYTHONPATH=src python3 -m pytest tests/unit tests/integration -q
git grep -nE "flaresolverr|FlareSolverr|FLARESOLVERR" src/paper_fetch/ \
  | grep -v "# legacy" \
  | grep -v "browser_runtime/types.py"
# 期待：仅 alias 行或注释行命中；无活跃 import 路径。
git grep -nE "sync_playwright\(\)\.start|chromium\.launch" src/paper_fetch/
# 期待：空。
PAPER_FETCH_RUN_LIVE=1 PYTHONPATH=src CROSSREF_MAILTO=paper-fetch-skill@example.invalid python3 -m pytest -n 0 \
  tests/live/test_live_publishers.py::LivePublisherTests::test_wiley_doi_live_fulltext \
  tests/live/test_live_publishers.py::LivePublisherTests::test_science_doi_live_fulltext \
  tests/live/test_live_publishers.py::LivePublisherTests::test_pnas_doi_live_fulltext \
  tests/live/test_live_publishers.py::LivePublisherTests::test_ams_doi_live_fulltext \
  -q
```

**风险与回滚锚点**：
- 这是不可逆变更（git mv + 删除字段）；务必先在 release-candidate 分支推进，至少跑一次完整 live regression。
- 如果 live smoke 失败率 > 当前 FlareSolverr 路径，**回退到 Phase 8 状态**，把 `legacy/flaresolverr/` 移回 `vendor/flaresolverr/` 并恢复 `requires_flaresolverr` 字段，问题修复后重启 Phase 9。
- `_flaresolverr.py` 仍存在于 `legacy/`，因此 `from legacy.flaresolverr._flaresolverr import FlareSolverrFailure` 在调试时仍可用。

---

## 6. 测试矩阵

### 6.1 单元/集成测试（并行）

```bash
PYTHONPATH=src python3 -m pytest tests/unit -q
PYTHONPATH=src python3 -m pytest tests/integration -q
```

### 6.2 Live 测试（必须串行，`-n 0`）

```bash
CROSSREF_MAILTO=paper-fetch-skill@example.invalid \
PAPER_FETCH_RUN_LIVE=1 \
CLOAKBROWSER_HEADLESS=true \
PYTHONPATH=src python3 -m pytest -n 0 \
  tests/live/test_live_atypon_browser_workflow.py \
  tests/live/test_live_publishers.py::LivePublisherTests::test_wiley_doi_live_fulltext \
  tests/live/test_live_publishers.py::LivePublisherTests::test_science_doi_live_fulltext \
  tests/live/test_live_publishers.py::LivePublisherTests::test_pnas_doi_live_fulltext \
  tests/live/test_live_publishers.py::LivePublisherTests::test_ams_doi_live_fulltext \
  -q
```

### 6.3 全链路验收清单

每个 Phase 完成后，至少覆盖一次：

| 场景 | 覆盖文件 |
| --- | --- |
| Science HTML 成功 | `tests/live/test_live_publishers.py::test_science_doi_live_fulltext` |
| Wiley HTML 成功 | `tests/live/test_live_publishers.py::test_wiley_doi_live_fulltext` |
| PNAS fast preflight 成功 | `tests/live/test_live_publishers.py::test_pnas_doi_live_fulltext`（fast 路径） |
| PNAS fast preflight 失败 → full HTML 成功 | 同上，强制 challenge 时观察 fallback |
| AMS HTML 成功 | `tests/live/test_live_publishers.py::test_ams_doi_live_fulltext` |
| seeded PDF/ePDF fallback | `tests/live/test_live_atypon_browser_workflow.py::test_*_pdf_fallback` |
| 正文 figure/table/formula 图片 | `tests/live/test_live_atypon_browser_workflow.py::test_*_asset_downloads` |
| supplementary 文件 | 同上 |
| image challenge recovery（imagePayload 等价） | `tests/unit/test_browser_image_payload.py` + 一次 live AMS 样本 |

---

## 7. 风险与决策点

1. **CloakBrowser binary 授权**：默认不打入离线包；离线安装文档必须说明用户自备 binary 或首次运行下载。
2. **headed mode 兜底**：强防护站点可能仍要求 `CLOAKBROWSER_HEADLESS=false` + Xvfb。Phase 2 后 `BrowserContextManager` 必须支持 headless 切换。
3. **imagePayload 是 Phase 9 的硬阻塞依赖**：Phase 6 未通过验收不得进入 Phase 9。
4. **命名残留 vs 真实启动路径**：grep 时使用 v2 计划提供的精确 regex（`sync_playwright\(\)\.start` / `chromium\.launch`），不要 grep `Playwright` 等大小写无关词，否则会误伤类型注解和异常捕获。
5. **Live 成功率波动**：Live smoke 只能作为 trend 指标，单次失败不构成回退依据；至少观察 3 个不同时间窗口的样本。

---

## 8. 当前建议

按 Phase 顺序推进，每个 Phase 单独打 commit 并在分支上跑完验收命令再合主线。Codex `/goal` 推荐每次只接收一个 Phase 的细化步骤作为 prompt。

短期：先完成 Phase 1 + Phase 2，因为它们是后续阶段的语义和 lifecycle 基础。
中期：Phase 3-6 顺序推进；Phase 6 完成前不要碰 Phase 9。
长期：Phase 7-9 是文档与归档收尾，按团队迁移期长度灵活安排。

---

## 9. Codex `/goal` 单 Phase prompt 模板

每次给 Codex 的 prompt 建议遵守以下结构（最小可行版本）：

```text
Working directory: /home/dictation/paper-fetch-skill
Branch: cloakbrowser-migration-phase-N

[粘贴对应 Phase 细化步骤全文]

Constraints:
- 遵守 CLOAKBROWSER_FULL_MIGRATION_PLAN.md §3 通用约束。
- 不删除任何旧字段名，仅添加新字段并保留 alias。
- 完成后运行 §5 Phase N 验收命令，全部通过才提交 commit。
- 失败时优先回到本 Phase 的"风险与回滚锚点"。
```

如果 `/goal` 需要继续 Phase N+1，明确 "已完成 Phase 1..N 全部验收命令" 作为前置条件，并附上本计划文件路径。

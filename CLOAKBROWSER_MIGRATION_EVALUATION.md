# FlareSolverr 改为 CloakBrowser 的可行性评估

评估日期：2026-05-15

## 结论

目标口径更新：项目目标是把 CloakBrowser 作为唯一浏览器运行时，替代 FlareSolverr 服务和项目内直接 Playwright Chromium 启动路径。

这个目标可实现，但需要把“替代 Playwright”的边界定义清楚：CloakBrowser Python wrapper 本身依赖 Playwright API，并返回标准 Playwright `Browser` / `BrowserContext` 对象。因此合理目标不是从依赖树里完全删除 Playwright，而是：

- 项目代码不再直接调用 `sync_playwright().start()` 或 `chromium.launch()` 启动 stock Playwright Chromium。
- `RuntimeContext`、PDF fallback、HTML preflight、asset fetcher 都统一通过 CloakBrowser 启动器创建 browser/context。
- FlareSolverr 的本地 HTTP 服务、repo-local `vendor/flaresolverr` 工作流、`FLARESOLVERR_*` 配置、启动/停止 wrapper 和 patched source bundle 退出正式路径。
- FlareSolverr 特有的 `request.get`、session registry、`solution.imagePayload` 能力由项目内 CloakBrowser runtime 自己实现等价 contract。

这不是小替换。当前项目依赖的不是一个普通浏览器二进制，而是 FlareSolverr 的服务协议、session 生命周期、返回 payload 结构，以及项目内对 FlareSolverr 源码打过的 `imagePayload` patch。迁移应按 CloakBrowser-only runtime 重构推进，范围覆盖 runtime 抽象、provider workflow、安装器、离线包、状态探测、资产恢复、PDF seed 逻辑、文档和测试矩阵。

## 目标定义

### In scope

- 用 CloakBrowser 作为所有需要真实浏览器的唯一启动器。
- 替代 `src/paper_fetch/providers/_flaresolverr.py` 中的服务调用语义。
- 替代 `runtime_playwright.py`、browser workflow fetchers、PDF fallback 和 HTML preflight 中的直接 Playwright Chromium launch。
- 让 `wiley` / `science` / `pnas` / `ams` 的 provider-owned browser workflow 改为 `CloakBrowser HTML -> CloakBrowser seeded PDF/ePDF fallback`。
- 让 IEEE clean-browser HTML / seeded PDF fallback、PNAS direct preflight 等非 FlareSolverr 浏览器路径也走 CloakBrowser。
- 删除或废弃 FlareSolverr 安装、启动、状态检查和离线打包路径。

### Out of scope

- 完全移除 `playwright` Python 包依赖。除非放弃 CloakBrowser wrapper，改为直接走 CDP 或自研控制层，否则这与 CloakBrowser 官方 Python API 冲突。
- 自动登录、处理人工 CAPTCHA、绕过无授权 access gate。
- 默认打包 CloakBrowser binary 到离线分发物中，除非先解决 Binary License 的重分发授权。

### 成功判定

- 生产代码不再 import 或调用 `sync_playwright()` 作为浏览器启动入口。
- 生产 provider workflow 不再 import `_flaresolverr.py` 作为运行时依赖。
- `provider_status()` 不再要求 `FLARESOLVERR_ENV_FILE` 或 FlareSolverr 服务健康检查。
- 文档、安装器和 CI 不再把 FlareSolverr 作为 Wiley / Science / PNAS / AMS 必需组件。
- 常规 unit / integration 并行通过；live browser/provider smoke 在 CloakBrowser runtime 下达到不低于现有路径的成功率。

## 当前 FlareSolverr 的实际职责

### 1. Provider waterfall 的固定组成

当前 `wiley`、`science`、`pnas`、`ams` 的浏览器路径都把 FlareSolverr 当成 provider-owned browser workflow 的一环。

文档中的能力矩阵明确记录：

- `wiley`: `FlareSolverr HTML -> seeded-browser publisher PDF/ePDF -> Wiley TDM API PDF`
- `science`: `FlareSolverr HTML -> seeded-browser publisher PDF/ePDF`
- `pnas`: `direct Playwright HTML preflight -> FlareSolverr HTML -> seeded-browser publisher PDF/ePDF`
- `ams`: `DOI landing -> FlareSolverr HTML -> seeded-browser publisher PDF`

相关位置：

- `docs/providers.md`
- `docs/flaresolverr.md`
- `src/paper_fetch/providers/browser_workflow/bootstrap.py`

这表示 FlareSolverr 不是边缘 fallback，而是多个 provider 的正式 HTML bootstrap 和挑战恢复边界。

### 2. 运行配置与健康检查绑定 FlareSolverr 服务

`src/paper_fetch/providers/_flaresolverr.py` 当前要求：

- `FLARESOLVERR_ENV_FILE` 指向 repo-local preset。
- `FLARESOLVERR_SOURCE_DIR` 默认指向 `vendor/flaresolverr`。
- `FLARESOLVERR_URL` 默认是 `http://127.0.0.1:8191/v1`。
- `ensure_runtime_ready()` 会检查 repo-local workflow 文件并调用 `sessions.list` 做健康检查。

这套配置假设有一个常驻本地服务，而 CloakBrowser 的主 API 是在进程内启动 Playwright `Browser` 或 `BrowserContext`。二者运行模型不同。

### 3. HTTP API 协议不是 Playwright API

当前 `fetch_html_with_flaresolverr()` 发送的控制 payload 包括：

- `sessions.create`
- `request.get`
- `sessions.destroy`
- `returnScreenshot`
- `waitInSeconds`
- `maxTimeout`
- `disableMedia`
- `returnImagePayload`

返回值解析依赖 FlareSolverr 风格的 `solution`：

- `solution.response`
- `solution.url`
- `solution.status`
- `solution.headers`
- `solution.cookies`
- `solution.userAgent`
- `solution.screenshot`
- `solution.imagePayload`

CloakBrowser 不提供兼容 FlareSolverr `/v1` 的 `request.get` 服务协议。官方用法是替换 Playwright 启动入口，例如 `from cloakbrowser import launch` 后得到标准 Playwright `Browser` 对象。它也有 Docker / CDP 使用方式，但那仍然是浏览器远程调试协议，不是 FlareSolverr response contract。

### 4. Browser context seed 是下游 PDF 和资产链路的关键数据

FlareSolverr 成功后，项目会把 `solution.cookies` 和 `solution.userAgent` 规范化为：

- `browser_cookies`
- `browser_user_agent`
- `browser_final_url`

这个 seed 会继续用于：

- seeded-browser PDF / ePDF fallback
- 正文图片下载
- supplementary 文件下载
- 失败后刷新 seed 的 retry

相关代码：

- `extract_flaresolverr_browser_context_seed()`
- `merge_browser_context_seeds()`
- `warm_browser_context_with_flaresolverr()`
- `browser_workflow/pdf_fallback.py`
- `browser_workflow/asset_download.py`

如果改为 CloakBrowser，需要保证从 CloakBrowser context 中导出的 cookies、UA、final URL 与现有 seed contract 一致。

### 5. 图片 challenge 恢复依赖本项目的 FlareSolverr patch

当前项目在 `vendor/flaresolverr/patches/return-image-payload.patch` 中扩展了 upstream FlareSolverr，让图片文档被浏览器成功加载时返回 `solution.imagePayload`。下载器会验证它是真图片 payload 后再落盘。

相关代码：

- `src/paper_fetch/providers/browser_workflow/asset_download.py`
- `src/paper_fetch/providers/browser_workflow/fetchers/image.py`
- `docs/flaresolverr.md`

这是直接替换最大的功能缺口之一。CloakBrowser 可以打开页面，但不会天然返回本项目定义的 `imagePayload` 字段。需要在 CloakBrowser backend 内实现等价逻辑，例如：

1. 导航到图片 URL。
2. 读取 response body 或页面内主图片。
3. 对位图用 canvas 导出 PNG。
4. 对顶层 SVG 保存原始 `image/svg+xml`。
5. 返回与现有 `_payload_from_flaresolverr_image_payload()` 兼容的数据结构。

### 6. 离线包和安装器已经深度绑定 FlareSolverr

安装和离线分发链路包含：

- `vendor/flaresolverr` 源码工作流。
- patched FlareSolverr source snapshot。
- FlareSolverr wheelhouse。
- FlareSolverr release bundle。
- Linux / Windows 启停 wrapper。
- CI 和离线安装器验证。

相关位置：

- `install-offline.sh`
- `install-offline.ps1`
- `scripts/build-offline-package.sh`
- `scripts/build-offline-package-windows.ps1`
- `scripts/flaresolverr-up`
- `scripts/flaresolverr-down`
- `scripts/flaresolverr-status`
- `tests/unit/test_offline_package_build.py`
- `tests/unit/test_flaresolverr_setup_scripts.py`
- `tests/unit/test_ci_release_workflow.py`

因此，默认替换不仅是 Python runtime 修改，还会影响交付物。

## CloakBrowser 的能力与约束

### 能力概述

截至本评估日，CloakBrowser 官方描述是一个带源代码级 fingerprint patch 的 Chromium binary，并提供 Python / JavaScript wrapper。其主要使用方式是：

- Python: `from cloakbrowser import launch`
- JavaScript: `import { launch } from 'cloakbrowser'`
- 返回标准 Playwright / Puppeteer 兼容对象。
- 首次运行会下载对应平台的 Chromium binary。
- 支持 `launch_context()`、`launch_persistent_context()`、proxy、locale、timezone、humanize 等参数。
- 提供 Docker 镜像和 `cloakserve` / CDP 相关能力。

PyPI release history 当前显示 `0.3.28` 发布于 2026-05-11。官方 README 中仍可见 `Latest: v0.3.26` 的内容，因此版本判断应以 PyPI release history 和 changelog 为准。

### 与本项目的契合点

CloakBrowser 对本项目可能有价值的点：

- 它直接返回 Playwright 兼容对象，理论上可以接入现有 `RuntimeContext` / Playwright fetcher 体系。
- 它面向 bot-detection / Cloudflare Turnstile 这类场景，目标问题与 FlareSolverr 使用场景有重合。
- `launch_persistent_context()` 可以作为跨请求 cookie / localStorage 持久化的候选实现。
- `cloakserve` 或 CDP 模式可以降低多语言或多进程集成成本。

### 关键约束

1. **不是 FlareSolverr API 兼容替代品**

   当前项目需要的是 `request.get` 风格的服务返回，而 CloakBrowser 是 Playwright 启动器。直接改环境变量或 URL 不能替换。

2. **不能把 Playwright 从依赖树中完全拿掉**

   CloakBrowser Python wrapper 的公开 API 返回 Playwright 对象，并在依赖中声明 `playwright>=1.40`。所以迁移目标应表述为“项目只通过 CloakBrowser 启动浏览器，不直接启动 stock Playwright Chromium”，而不是“项目环境里没有 Playwright 包”。

3. **离线分发存在授权风险**

   CloakBrowser wrapper 是 MIT，但其 compiled Chromium binary 有单独的 Binary License。该 license 允许个人或商业使用，并允许列为依赖；但禁止把 binary 重新分发、重打包或嵌入分发给第三方的产品。当前项目的离线包会打包浏览器运行组件，如果把 CloakBrowser binary 打进去，可能需要单独 OEM/SaaS 授权。

4. **安全与供应链面扩大**

   引入自定义 Chromium binary 后，需要决定是否接受自动下载、如何校验签名 / checksum、是否允许用户在内网环境中镜像，以及如何在 CI / 离线包中处理 binary。

5. **headless/headed 语义需要重新验证**

   CloakBrowser 官方排障建议里，强防护站点可能仍需要 headed mode + Xvfb。这与当前 FlareSolverr headless preset / WSLg preset 的运维边界类似，但不能认为行为完全等价。

## CloakBrowser-only 替换可行性矩阵

| 维度 | 替换可行性 | 说明 |
| --- | --- | --- |
| HTML 抓取 | 中 | 可用 CloakBrowser 返回的 Playwright API 重写，但需要复刻 wait、media blocking、final URL、headers、title、block detection 和 artifacts。 |
| PDF/ePDF fallback seed | 中 | 可从 CloakBrowser context 导出 cookies 和 UA，但需要保持现有 seed contract。 |
| 图片 challenge 恢复 | 低到中 | 必须重写 `imagePayload` 等价实现；这是现有 FlareSolverr patch 的核心价值。 |
| supplementary 文件下载 | 中 | 可复用现有 fetcher 的控制流，但底层 context 必须由 CloakBrowser 创建。 |
| provider status | 中 | 当前 status 检查的是 FlareSolverr env 和 `sessions.list`；CloakBrowser 要改成本地 wrapper import、binary 状态和可选 launch probe。 |
| 安装脚本 | 低到中 | 当前脚本围绕 repo-local FlareSolverr 与 Playwright browser install 组织；需要改为 CloakBrowser dependency / binary 准备策略。 |
| 离线包 | 低 | Binary License 不允许随产品重新分发，除非拿到额外授权或改成目标机在线下载。 |
| Windows 支持 | 中 | CloakBrowser 提供 Windows binary，但本项目 Windows 安装器当前验证 FlareSolverr wrapper。 |
| 单元测试改造 | 中 | 依赖注入已有基础，但大量测试名称和断言仍是 FlareSolverr / Playwright 语义。 |
| live 回归风险 | 高 | 成功率取决于真实 publisher、防护策略、授权环境和 headless/headed 行为，必须以 live 样本验证。 |

## 推荐架构

### 目标架构：CloakBrowser-only runtime

目标不是新增第二套可选浏览器，而是把所有浏览器职责收敛到一个内部 runtime：

```text
src/paper_fetch/providers/browser_runtime/
  __init__.py
  types.py
  cloakbrowser_backend.py
```

抽象接口先对齐现有需求，不设计过宽：

```text
load_runtime_config(env, provider, doi) -> BrowserRuntimeConfig
ensure_runtime_ready(config) -> None
probe_runtime_status(env, provider, doi) -> ProviderStatusResult
fetch_html(candidate_urls, publisher, config, wait_seconds, warm_wait_seconds, disable_media, return_image_payload) -> BrowserFetchedHtml
warm_browser_context(candidate_urls, publisher, config, browser_context_seed) -> dict
new_context(headless, user_agent, locale, viewport, accept_downloads, storage_state) -> BrowserContext
```

初始实现可以短期兼容 `FetchedPublisherHtml` 的字段形状，但不应继续用 FlareSolverr 命名承载新语义。建议改名为：

- `BrowserFetchedHtml`
- `BrowserRuntimeFailure`
- `BrowserRuntimeConfig`

这样 browser workflow、PDF fallback 和 asset fetcher 不需要知道底层是服务、进程内 wrapper 还是 CDP。

### RuntimeContext 统一入口

当前 `RuntimeContext` 持有 `PlaywrightContextManager`，内部直接调用：

```text
sync_playwright().start()
manager.chromium.launch(headless=...)
```

迁移后应改成：

```text
from cloakbrowser import launch
browser = launch(headless=...)
context = browser.new_context(...)
```

或在需要持久 profile 的场景使用：

```text
from cloakbrowser import launch_persistent_context
context = launch_persistent_context(user_data_dir=..., ...)
```

上层仍然可以接收 Playwright 兼容 `BrowserContext`，但创建者必须是 CloakBrowser。这样 IEEE clean-browser HTML、PNAS preflight、PDF fallback 和资产 worker 都复用同一启动边界。

### Browser workflow 新顺序

当前顺序：

```text
FlareSolverr HTML -> seeded-browser publisher PDF/ePDF
```

目标顺序：

```text
CloakBrowser HTML -> CloakBrowser-seeded publisher PDF/ePDF
```

PNAS 的 direct preflight 不应再叫 direct Playwright preflight，而应成为同一 CloakBrowser runtime 下的 fast HTML preflight：

```text
CloakBrowser fast HTML preflight -> CloakBrowser full HTML -> CloakBrowser-seeded PDF/ePDF
```

### 配置边界

建议新增或保留的配置：

```text
CLOAKBROWSER_HEADLESS=true|false
CLOAKBROWSER_BINARY_PATH=<optional>
CLOAKBROWSER_USER_DATA_DIR=<optional>
CLOAKBROWSER_ALLOW_AUTO_DOWNLOAD=true|false
CLOAKBROWSER_LAUNCH_MODE=ephemeral|persistent
```

建议废弃的配置：

```text
FLARESOLVERR_URL
FLARESOLVERR_ENV_FILE
FLARESOLVERR_SOURCE_DIR
PAPER_FETCH_FLARESOLVERR_KEEP_SESSION
PLAYWRIGHT_BROWSERS_PATH
```

`PLAYWRIGHT_BROWSERS_PATH` 不应再用于项目浏览器运行时。即使 CloakBrowser wrapper 依赖 Playwright Python 包，浏览器 binary 也应由 CloakBrowser 管理，而不是由 `python -m playwright install chromium` 安装 stock Chromium。

## 分阶段迁移计划

### Phase 0：锁定 contract 和验收基线

目标：

- 冻结当前 FlareSolverr / Playwright 路径的公开行为：source trail、warning、diagnostics、asset failure shape、provider status shape。
- 用 live 样本记录当前成功率和失败类型，作为 CloakBrowser-only 替换后的验收基线。
- 明确哪些外部可见字段保留旧名，哪些字段可以在 major migration 中改名。

建议输出：

- `live-downloads/cloakbrowser-migration-baseline/*.json`
- 当前 FlareSolverr / Playwright direct path 的成功率、耗时、失败原因分布。

### Phase 1：引入 provider-neutral browser runtime 类型

目标：

- 新增 `BrowserRuntimeConfig`、`BrowserFetchedHtml`、`BrowserRuntimeFailure`。
- 将 browser workflow 的依赖字段从 `fetch_html_with_flaresolverr` / `warm_browser_context_with_flaresolverr` 改为 `fetch_html_with_browser` / `warm_browser_context`。
- 保持单测可注入，但生产默认实现指向 CloakBrowser runtime。
- `_flaresolverr.py` 只作为迁移期间参考，不再由生产默认 deps 引用。

需要同步更新：

- `src/paper_fetch/providers/browser_workflow/shared.py`
- `src/paper_fetch/providers/browser_workflow/bootstrap.py`
- `src/paper_fetch/providers/browser_workflow/html_extraction.py`
- `src/paper_fetch/providers/browser_workflow/asset_download.py`
- `src/paper_fetch/providers/browser_workflow/__init__.py`
- 相关 unit tests

### Phase 2：实现 CloakBrowser HTML runtime

目标：

- 用 CloakBrowser 实现 `fetch_html()`。
- 支持候选 URL waterfall。
- 支持 `disable_media`。
- 支持冷 / 热 wait 语义。
- 返回 `BrowserFetchedHtml`。
- 从 browser context 导出 cookies、UA、final URL。
- 复用现有 `detect_html_block()`、`summarize_html()`、`looks_like_abstract_redirect()`。

注意：

- `return_screenshot` 可以通过 `page.screenshot()` 实现。
- response headers/status 需要从 `page.goto()` response 或 request interception 捕获。
- 如果 CloakBrowser wrapper 没有暴露当前 UA，需要从 page evaluate 或 context 配置中获取。

### Phase 3：替换所有直接 Playwright 启动点

目标：

- `runtime_playwright.py` 改为 CloakBrowser lifecycle manager，或重命名为 `runtime_browser.py`。
- `_pdf_fallback.fetch_pdf_with_playwright()` 改名并改用 CloakBrowser-created context。
- `browser_workflow/fetchers/context.py` 的 `_new_playwright_context()` 改为 `_new_browser_context()`，底层使用 CloakBrowser。
- `fetch_html_with_direct_playwright()` 改名为 `fetch_html_with_fast_browser()` 或 `fetch_html_with_cloakbrowser_preflight()`。
- 生产代码中不再出现 `sync_playwright().start()`。

### Phase 4：补齐图片 payload 等价能力

目标：

- 在 CloakBrowser runtime 内实现 `return_image_payload=True`。
- 返回与当前图片恢复链路兼容的数据：

```text
{
  "bodyB64": "...",
  "contentType": "image/png" | "image/svg+xml" | ...,
  "url": "...",
  "status": 200,
  "width": 640,
  "height": 480
}
```

验收点：

- Cloudflare challenge HTML 不能被保存成图片。
- SVG 顶层文档保留原始 SVG。
- 位图能导出真实 PNG / JPEG / WebP payload。
- 失败诊断迁移为 backend-neutral reason，或保留旧 reason 的兼容 alias。

### Phase 5：移除 FlareSolverr 正式路径

目标：

- `default_browser_workflow_deps()` 不再导入 `_flaresolverr.py`。
- provider status 不再检查 `FLARESOLVERR_ENV_FILE`。
- `ProviderSpec.requires_flaresolverr` 迁移为更中性的 `requires_browser_runtime` 或删除 FlareSolverr 语义。
- 文档中的 Wiley / Science / PNAS / AMS 路径改为 CloakBrowser。
- FlareSolverr wrapper、vendor workflow、offline packaging 进入删除或 legacy archive 决策。

### Phase 6：安装器、离线包和 CI 策略

目标：

- 在线安装不再运行 `python -m playwright install chromium` 或 FlareSolverr setup。
- 在线安装可以安装 `cloakbrowser`，并根据配置选择是否预下载 CloakBrowser binary。
- 离线包默认不重分发 CloakBrowser binary，除非取得 OEM/SaaS 授权；否则离线能力需要重新定义为“离线 Python 包 + 首次运行官方渠道下载 binary”或提供用户自备 binary 路径。
- Windows installer 不再验证 `flaresolverr-up.cmd` / `sessions.list`，改为验证 CloakBrowser runtime 可导入和可定位 binary。

### Phase 7：live gate 和默认切换完成

目标：

- `wiley / science / pnas / ams` live 样本成功率不低于当前 FlareSolverr。
- HTML route、PDF/ePDF fallback、正文图片、supplementary 文件都有覆盖。
- Linux、Windows、headless、headed + Xvfb 均有 smoke 验证。
- 离线包策略和授权风险已经解决。
- CI / 文档 / installer / status surface 全部同步后，CloakBrowser-only 才算完成。

## 测试影响面

如果推进 CloakBrowser-only 迁移，至少需要新增或调整：

- `tests/unit/test_browser_workflow_deps.py`
- `tests/unit/test_atypon_browser_workflow_flaresolverr.py`
- `tests/unit/test_provider_request_options.py`
- `tests/unit/test_browser_workflow_fetchers.py`
- `tests/unit/test_service_browser_workflow.py`
- `tests/unit/test_offline_package_build.py`
- `tests/unit/test_ci_release_workflow.py`
- `tests/unit/test_runtime_playwright.py`
- `tests/live/test_live_atypon_browser_workflow.py`
- `tests/live/test_live_publishers.py`

其中 `test_atypon_browser_workflow_flaresolverr.py` 这类文件应重命名或拆分为 browser-runtime 语义，避免测试名继续暗示 FlareSolverr 是正式运行时。

普通 unit / integration 仍应按项目约定并行运行：

```bash
PYTHONPATH=src python3 -m pytest tests/unit -q
```

live browser/provider 验证由于共享真实站点、本地 browser runtime 和外部状态，可以串行运行，并需要在结果中说明原因。

## 风险清单

1. **语义回归**

   当前 FlareSolverr failure reason、artifact 命名、source trail、diagnostics 都被测试和文档消费。替换后需要避免破坏外部可见 contract。

2. **资产下载回归**

   当前正文图片失败后有 seed 刷新、figure page fetch、imagePayload recovery、多候选 preview fallback。CloakBrowser backend 需要逐个补齐。

3. **离线安装回归**

   现有离线包验证明确检查 FlareSolverr bundle 和 wrapper。CloakBrowser binary 不能默认打入离线包，除非授权策略明确。

4. **安全和合规**

   自定义浏览器 binary 会引入新的供应链审查点；同时 bot-detection 绕过类工具的使用必须继续限定在操作者有合法访问权限的场景。

5. **离线能力重定义**

   如果不取得 CloakBrowser binary 重分发授权，当前“完整离线包自带浏览器”的承诺需要调整。可选方案是要求用户自备 binary，或允许安装后从 CloakBrowser 官方渠道下载。

## 建议

短期建议：

- 先按 CloakBrowser-only 目标重命名和固化 browser runtime contract，不再设计 `flaresolverr|cloakbrowser` 双 backend 配置。
- 保留 `_flaresolverr.py` 作为迁移参考和回归基线，但生产默认 deps 先规划为只指向 CloakBrowser runtime。
- 不把 CloakBrowser binary 纳入离线包，除非先完成授权确认。
- 优先验证 HTML route、PDF/ePDF fallback 和图片 `imagePayload` 等价能力。

中期建议：

- 把 `_flaresolverr.py` 中真正通用的 seed、cookie normalizer、artifact redaction 和 failure helper 抽到 browser-neutral 模块。
- 将 failure、seed、payload、status check 命名逐步中性化。
- 所有 `sync_playwright().start()` 入口统一改为 CloakBrowser lifecycle manager。

长期建议：

- 删除或归档 FlareSolverr vendor workflow、wrapper、离线打包逻辑和文档。
- 将 provider catalog / onboarding manifest 里的 `requires_flaresolverr` 语义迁移为 `requires_browser_runtime` 或 CloakBrowser-specific 语义。
- 默认浏览器能力由 CloakBrowser live regression 数据持续守护，而不是保留 FlareSolverr 回退路径。

## 参考来源

外部来源：

- CloakBrowser GitHub README: https://github.com/CloakHQ/CloakBrowser
- CloakBrowser PyPI release history: https://pypi.org/project/cloakbrowser/
- CloakBrowser changelog: https://github.com/CloakHQ/CloakBrowser/blob/main/CHANGELOG.md
- CloakBrowser binary license: https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md

项目内依据：

- `src/paper_fetch/providers/_flaresolverr.py`
- `src/paper_fetch/providers/browser_workflow/bootstrap.py`
- `src/paper_fetch/providers/browser_workflow/html_extraction.py`
- `src/paper_fetch/providers/browser_workflow/asset_download.py`
- `src/paper_fetch/providers/browser_workflow/fetchers/image.py`
- `src/paper_fetch/runtime_playwright.py`
- `docs/providers.md`
- `docs/flaresolverr.md`
- `vendor/flaresolverr/patches/return-image-payload.patch`
- `install-offline.sh`
- `install-offline.ps1`

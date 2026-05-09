# Copernicus / MDPI / IEEE Provider TODO

本清单跟踪待接入 provider 的实现工作；不要把这些条目合并进根目录 `todo.md`。IEEE 条目保留为已完成接入记录。

新增 provider 必须遵循 [`docs/provider-development.md`](docs/provider-development.md)：
身份与 routing 通过 `paper_fetch.provider_catalog.PROVIDER_CATALOG` 派生；client 继承
`paper_fetch.providers.base.ProviderClient`，由 `fetch_result()` 模板方法编排；多步 fallback
统一通过 `paper_fetch.providers._waterfall.run_provider_waterfall()`；HTML 清洗 / availability
信号注册到 `paper_fetch.extraction.html.provider_rules` 和 `paper_fetch.quality.html_signals`，
不在 `quality/html_profiles.py` 或 `_runtime.py` 加 provider 字典分支；用户可见规则的核心测试
默认基于真实 DOI fixture（`tests/fixtures/golden_criteria/<doi_slug>/` + `manifest.json`）。
canonical 事实来源是 `docs/providers.md` 与 catalog；`references/api_notes.md` /
`references/routing_rules.md` 只保留 API 约束或历史草图。

## 1. Copernicus

设计语义参考 [`docs/providers.md`](docs/providers.md#copernicus) — 开放获取、`fulltext_first`、不需登录态或 FlareSolverr。

- [x] 在 `src/paper_fetch/provider_catalog.py` 新增 `copernicus` 的 `ProviderSpec`：domain（按 Copernicus 期刊主域名枚举）、`publisher_aliases=("copernicus publications", ...)`、`doi_prefixes=("10.5194/",)`、`asset_default="body"`、`abstract_only_policy="metadata_fallback"`、`client_factory_path="paper_fetch.providers.copernicus:CopernicusClient"`、稳定 `status_order`；同时把公开 `source` 名 `copernicus_xml` / `copernicus_pdf` 加入 `SOURCE_PROVIDER_MAP`。不要新增平行 provider 列表；`preferred_providers`、MCP allow-list、registry、preferred provider 推断都应自动从 catalog 派生。
- [x] 在 `src/paper_fetch/models/schema.py` 的 source 枚举与 `src/paper_fetch/quality/issues.py` 的 `EXPECTED_FULLTEXT_SOURCES_BY_PROVIDER` 中登记 Copernicus 的公开 source 名；`src/paper_fetch/mcp/_instructions.py` 的 `preferred_providers` 列表与 provider 描述同步追加。
- [x] 实现 `paper_fetch/providers/copernicus.py` 的 `CopernicusClient(ProviderClient)`：覆盖 `fetch_raw_fulltext`、`to_article_model`、`download_related_assets`、`probe_status`，必要时 `describe_artifacts` / `maybe_recover_fetch_result_payload`；返回 typed payload（`ProviderContent` / `RawFulltextPayload` / `ProviderArtifacts`），不向 `raw_payload.metadata[...]` 写结构化状态。
- [x] Fulltext waterfall 用 `paper_fetch.providers._waterfall.run_provider_waterfall()` 串成：`landing HTML → 发现 citation_xml_url / XML 下载链接 → NLM/JATS XML → PDF text-only fallback → metadata-only`；每 step 声明 `label` / `failure_marker` / `success_markers` / `continue_codes`，错误用稳定 `ProviderFailure.code`（`no_result` / `no_access` / `rate_limited` / `error`），成功必须校验 payload 形态（XML 含正文 section、PDF 是真实 PDF payload），不只看 HTTP 200。
- [x] Landing / metadata 复用 `paper_fetch.extraction.html.landing.fetch_landing_html` 与 `paper_fetch.extraction.html._metadata`；不要只靠 DOI 字符串拼 XML URL。
- [x] XML → Markdown 复用现有 NLM/JATS 渲染链（`paper_fetch.providers._article_markdown_xml` 与 `_article_markdown_common` / `_article_markdown_math`，必要时新增最小 helper 而非 fork 整套），覆盖章节、摘要、图表 caption、OASIS 表格、MathML、参考文献、supplementary links；公式走 `extraction.html.formula_rules` + `_article_markdown_math`，参考文献清理走 `paper_fetch.markdown.citations`。
- [x] Copernicus HTML cleanup hook 已删除；live 抽样未发现稳定 HTML-only 全文路径，当前与 Elsevier 保持一致，走 XML → PDF → metadata。
- [x] PDF fallback 接入 `paper_fetch.providers._pdf_fallback`，仅承诺 text-only；PDF 临时不可用必须用 `ProviderArtifacts` 标记跳过相关资产，并通过 warning + `source_trail` 暴露，不能让 PDF 失败覆盖已成功的 XML 正文。
- [x] `asset_profile` 三态语义沿用 base 标准：`none` 不下载、`body` 限正文 figure / 表格图 / 公式 fallback、`all` 在 body 基础上从明确 supplementary scope 增加附件；资产发现复用 `paper_fetch.extraction.html.assets`，禁止全文扫描后缀；资产输出和失败诊断保留 `kind` / `section` / `render_state` / `download_tier` / `download_url` / `original_url` / `preview_url` / `full_size_url` / `content_type` / `downloaded_bytes` / `width` / `height` 与失败 `status` / `title_snippet` / `body_snippet` / `reason`，正文已内联消费的图表设 `render_state="inline"`。
- [x] HTTP 行为：所有请求走 `RuntimeContext.transport` / `HttpTransport`，主链使用 `DEFAULT_FULLTEXT_TIMEOUT_SECONDS`，UA 用 `build_user_agent(env)`，可重试 GET 用 `retry_on_transient=True`；同次 fetch 内复用 `context.parse_cache`。如需 OAI-PMH 仅做 metadata 补发现，不应成为单篇 DOI 主链的首个必需网络步骤。
- [x] 测试矩阵：
  - `tests/unit/test_provider_catalog.py` 覆盖 domain / publisher alias / DOI prefix / source 映射 / `asset_default` / registry client。
  - 新增 `tests/unit/test_copernicus_provider*.py`：waterfall 主路径成功、第一路径失败 fallback 成功、全部失败降级、`source_trail` / warnings 断言、request options（timeout / headers / retry）覆盖。
  - 真实 DOI replay 放 `tests/fixtures/golden_criteria/<doi_slug>/`（最少覆盖一篇 NLM/JATS 主路径；表格 / 公式 / supplementary 视情况拆篇），同步登记 `tests/fixtures/golden_criteria/manifest.json`，必要时补 `_scenarios/` 最小 contract 与 `tests/fixtures/block/` 负样本。
  - 资产 `none` / `body` / `all` 行为、PDF text-only 标记、metadata-only fallback、`probe_status()` 本地 ready / not_configured / partial / error 各覆盖一例。
  - live smoke 样本登记到 `tests/provider_benchmark_samples.py`，受 `PAPER_FETCH_RUN_LIVE=1` 保护。
- [x] 文档同步：`docs/providers.md` 把“待接入设计：Copernicus”段升级为已接入能力矩阵 + 行为说明（含 fulltext waterfall、`asset_profile` 行为、metadata fallback 语义、env / status 说明）；`docs/extraction-rules.md` 更新任何用户可见提取 / 渲染新规则与对应 fixture；`CHANGELOG.md` 简短记录新增能力与限制；`docs/architecture/target-architecture.md`、`docs/deployment.md` / `.env.example` 仅在新增 canonical owner 或必需环境变量时才更新；`references/api_notes.md` / `references/routing_rules.md` 不作为事实来源，仅在确实记录公开 OAI-PMH 等 API 约束时补对应历史段落。

## 2. MDPI

设计语义参考 [`docs/providers.md`](docs/providers.md#待接入设计mdpi) — 公开 HTML/PDF/XML，但需要区分“公开内容传输失败”与“无全文权限”。

- [ ] 在 `src/paper_fetch/provider_catalog.py` 新增 `mdpi` 的 `ProviderSpec`：`domains=("mdpi.com",)`、`publisher_aliases=("mdpi", "mdpi ag")`、`doi_prefixes=("10.3390/",)`、`asset_default="body"`、`abstract_only_policy="provider_managed"`、`client_factory_path="paper_fetch.providers.mdpi:MdpiClient"`、稳定 `status_order`；公开 source 名（建议 `mdpi_xml` / `mdpi_html` / `mdpi_pdf`）加入 `SOURCE_PROVIDER_MAP`。
- [ ] 在 `src/paper_fetch/models/schema.py` 的 source 枚举、`src/paper_fetch/quality/issues.py` 的 `EXPECTED_FULLTEXT_SOURCES_BY_PROVIDER` 与 `src/paper_fetch/mcp/_instructions.py` 的 `preferred_providers` / provider 描述同步登记 `mdpi`。
- [ ] 实现 `paper_fetch/providers/mdpi.py` 的 `MdpiClient(ProviderClient)`：覆盖 `fetch_raw_fulltext`、`to_article_model`、`html_to_markdown`、`download_related_assets`、`probe_status`，必要时 `describe_artifacts` / `maybe_recover_fetch_result_payload`；主链返回 typed payload，不绕开 `ProviderClient.fetch_result()` 自拼最终 envelope。
- [ ] Fulltext waterfall 用 `run_provider_waterfall()` 串成：`landing HTML → 发现 article XML 链接（landing 暴露的 `/xml` / 正文链接为主，固定 `/xml` 路由仅作 secondary）→ MDPI XML → provider-cleaned article HTML fallback → direct Playwright HTML fallback（仅当 direct HTTP 被 CDN 拦截 / 403 时启用，复用 `RuntimeContext` 共享 browser，不引入 FlareSolverr）→ PDF text-only fallback → provider-managed abstract-only / metadata-only`；CDN 拦截要明确分流到 `no_access` 与 `error` 两类 `ProviderFailure.code`，不要把传输失败误判为无权限。
- [ ] Landing / metadata 复用 `paper_fetch.extraction.html.landing.fetch_landing_html` 与 `paper_fetch.extraction.html._metadata`；XML 链接发现优先解析 landing 暴露的 article notes / `/xml` 链接，不依赖纯 DOI 拼接。
- [ ] XML → Markdown 复用 `paper_fetch.providers._article_markdown_xml` / `_article_markdown_common` / `_article_markdown_math` 与 `extraction.html.formula_rules`、`paper_fetch.markdown.citations`、`paper_fetch.extraction.html.tables`；覆盖章节、摘要、图表 caption、表格、公式、参考文献、supplementary links。
- [ ] HTML cleanup / availability 注册到 `paper_fetch.extraction.html.provider_rules.PROVIDER_HTML_RULES`：增加 `mdpi` 条目（清掉导航、菜单、推荐文章、评论入口、引用弹层），availability 正向 / blocking 信号通过 `paper_fetch.quality.html_signals` 注册；不要在 `quality/html_profiles.py` 或 `_runtime.py` 加新分支。
- [ ] direct Playwright HTML fallback 通过 `RuntimeContext` 管理 browser；不复用 `RuntimeContext` 共享 browser 的并发 worker 必须用线程私有 page/context/browser，并在同一 worker 线程关闭，避免残留 Chrome for Testing 子进程。除非未来出现明确 Cloudflare challenge runtime 需求，否则不引入 FlareSolverr。
- [ ] PDF fallback 走 `paper_fetch.providers._pdf_fallback`，承诺 text-only；PDF 失败用 `ProviderArtifacts` 标记跳过资产 + warning + `source_trail`，不覆盖已成功正文。
- [ ] `asset_profile` 三态语义沿用 base 标准：`none` / `body` / `all`；资产发现限定到正文 figure / 表格图 / 公式 fallback 与明确 supplementary scope；资产输出与失败诊断字段同 §1；正文已内联图表设 `render_state="inline"`。
- [ ] HTTP 行为：走 `RuntimeContext.transport`，主链 `DEFAULT_FULLTEXT_TIMEOUT_SECONDS`，UA `build_user_agent(env)`，可重试 GET `retry_on_transient=True`；CDN/limit 敏感路线沿用既有 rate-limit retry 模式；同次 fetch 复用 `context.parse_cache`。
- [ ] 测试矩阵：
  - `tests/unit/test_provider_catalog.py` 增加 MDPI domain / publisher alias / DOI prefix / source 映射 / 默认 asset profile / registry client 样例。
  - 新增 `tests/unit/test_mdpi_provider*.py`：waterfall 主路径成功、第一路径失败 fallback、CDN 403 → Playwright HTML fallback、PDF text-only、abstract-only / metadata-only 降级、`source_trail` / warnings、request options。
  - 真实 DOI replay 放 `tests/fixtures/golden_criteria/<doi_slug>/`（覆盖 XML 主路径，HTML cleanup、表格、公式、supplementary 视情况拆篇），登记 `manifest.json`；CDN 拦截 / 403 / abstract-only 负样本放 `tests/fixtures/block/`，必要 contract 放 `_scenarios/`。
  - 资产 `none` / `body` / `all`、`probe_status()` 本地状态、live smoke 样本登记到 `tests/provider_benchmark_samples.py`，受 `PAPER_FETCH_RUN_LIVE=1` 保护。
- [ ] 文档同步：`docs/providers.md` 把“待接入设计：MDPI”段升级为已接入说明（含 CDN fallback 行为、Playwright 触发条件、`asset_profile` 行为、abstract-only 语义）；`docs/extraction-rules.md` 更新用户可见规则与 fixture；`CHANGELOG.md` 简短记录；`docs/architecture/target-architecture.md` / `docs/deployment.md` / `.env.example` 仅在新增 canonical owner 或必需环境变量时更新；`references/api_notes.md` / `references/routing_rules.md` 不作为事实来源。

## 3. IEEE

- [x] 在 provider catalog 中新增 `ieee`：domain `ieeexplore.ieee.org`、publisher aliases、DOI prefix `10.1109/`、默认 asset profile 和 status 顺序。
- [x] 接入 routing / preferred provider / provider status / CLI / MCP 可见 provider 列表。
- [x] 实现 DOI / landing URL 到 IEEE article number 的解析。
- [x] 实现动态全文端点请求：`/rest/document/{article_number}/?logAccess=true`。
- [x] 保留 publisher 页面上下文请求头：document `Referer`、`x-security-request: required`、browser UA 和兼容 `Accept`。
- [x] 实现 full-text HTML marker 校验，排除登录页、access gate、验证码、摘要页、空壳和错误 HTML。
- [x] 实现 IEEE HTML -> Markdown：章节、图表、表格、公式、参考文献和内部引用。
- [x] 默认 `fulltext_first`，但在无权限、无全文或校验失败时降级到 `abstract_only` / `metadata_only`。
- [x] 增加授权上下文 live smoke、无授权降级测试、provider routing 测试、Markdown golden 测试和 source trail 断言。
- [x] 同步 `docs/providers.md`、`references/api_notes.md`、`references/routing_rules.md` 和 CI live/skip 说明。

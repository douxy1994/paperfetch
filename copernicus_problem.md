# Copernicus Provider 接入待优化问题清单

本清单基于对 `src/paper_fetch/providers/copernicus.py`、`src/paper_fetch/providers/_article_markdown_copernicus.py`、`src/paper_fetch/extraction/html/provider_rules.py`、`src/paper_fetch/quality/html_signals.py` 以及对应单测和 golden corpus 的审查，按性价比/优先级排序。

> 处理状态：本轮已修复第 1–9、11–12 项；第 10 项（PDF fallback 图表资产抽取）按范围要求保留为后续专项，当前仍维持 text-only PDF fallback。

---

## 一、明显能省/能简化（性价比高）

### 1. `to_article_model` 在 XML 成功路径里第二次解析 XML

**位置**：`src/paper_fetch/providers/copernicus.py:638–662`

**现象**：`_fetch_xml_payload` 已经调用过 `parse_copernicus_xml`，并把 `markdown_text` / `merged_metadata` / `extracted_assets` 写进 `RawFulltextPayload`。`to_article_model` 在 `route == "xml"` 时又 `parse_copernicus_xml(raw_payload.body, ...)` 重新走一次完整 JATS 渲染，浪费一次 ElementTree 解析 + 一次 markdown 重建。

**建议**：直接复用 `content.markdown_text` / `content.merged_metadata` / `content.extracted_assets`，把 `extraction.references` / `extraction.semantic_losses` / `extraction.abstract_sections` 一并塞进 `ProviderContent.diagnostics` 即可。

---

### 2. `_fetch_xml_payload` + `_validate_xml_extraction` 也在重复解析同一份 bytes

**位置**：`src/paper_fetch/providers/copernicus.py:352–392`

**现象**：`parse_copernicus_xml` 内部 `ET.fromstring`，紧接着 `_validate_xml_extraction` 又 `ET.fromstring(xml_body)`。同一段 XML bytes 被解析了两次。

**建议**：`parse_copernicus_xml` 已经支持 `xml_root=` 参数，把解析后的 root 复用一次就好。

---

### 3. `_validate_xml_extraction` 的 `len(body_text) < 500` 是 magic threshold

**位置**：`src/paper_fetch/providers/copernicus.py:374`

**现象**：硬编码 500 字符门槛，对老文章 / commentary / corrigendum 可能误判；并且与上面"早期 abstract-only XML"的判定语义重叠。

**建议**：换成"必须存在至少一个 `<sec>` 含 `<p>` 且 `<p>` 累计字符 > 阈值"，把阈值集中到模块顶 `MIN_BODY_CHARS = …` 常量，并在单测里固化（目前没专门 owner 单测覆盖这条降级判定，仅 golden corpus 间接验证）。

---

### 4. 资产 entry 的 5 个等价 URL 字段冗余

**位置**：`src/paper_fetch/providers/_article_markdown_copernicus.py:262–270, 388`

**现象**：`_figure_entry` 在同一个资产上同时写 `link / url / full_size_url / original_url / source_url` 五份相同 URL；`_supplementary_entries` 写 `link / url / source_url / download_url` 四份。是为兼容下游多个消费点，但维护负担高。

**建议**：在 base 层定个 canonical 字段（建议 `original_url`），其他字段统一交给 `download_figure_assets` 在需要时镜像，避免 provider 端反复填同一份。

---

### 5. `_asset_for_article_model` 在 client 层做 kind 转换

**位置**：`src/paper_fetch/providers/copernicus.py:164–172`

**现象**：把 `kind="structured" / "fallback"` 改写成 `kind="table"` + `table_render_kind`。只在这一个 provider 里存在转换语义。

**建议**：让 `_table_entry` 一次性输出 article model 期望的 `kind="table"` + `table_render_kind="structured"|"fallback"`，删掉 `_asset_for_article_model` 这层。

---

### 6. `_iter_descendants` / `_iter_children` 在本文件重复造轮子

**位置**：`src/paper_fetch/providers/_article_markdown_copernicus.py:53–70`

**现象**：`_article_markdown_common` / `_article_markdown_xml` 已经有 `first_child` / `first_descendant` / `xml_local_name`，但本文件又新写了一对"按 local-name 枚举所有子/后代"的 helper。

**建议**：把这两个 helper 下沉到 common 模块，其他 JATS-style provider（未来 MDPI XML 也用 JATS）能复用。

---

## 二、行为上的真问题

### 7. landing 抓不到，整篇就放弃了 —— 太脆

**位置**：`src/paper_fetch/providers/copernicus.py:281–298, 300–334`

**现象**：当前流程

```
先抓文章首页 (landing HTML)  →  从首页翻出 XML 链接  →  下载 XML
              ↓ 抓不到
            直接报错收工
```

但 Copernicus URL 规则**非常稳定**，DOI `10.5194/acp-24-1-2024` 就一定对应：

```
https://acp.copernicus.org/articles/24/1/2024/acp-24-1-2024.xml
```

代码里其实已经有按 DOI 直接拼出 XML/PDF 地址的函数（`_doi_xml_candidate` / `_doi_pdf_candidate`），只是首页抓不到的时候没去用。

**通俗类比**：你已经知道朋友家门牌号是"5 号楼 301"，但你非要先打电话问他"你家在哪"，电话打不通就回家了 —— 其实直接按门牌号上去敲门就行。

**建议**：landing 抓失败时（超时、503、跳转超限）不要直接终止 waterfall，降级成 warning，继续用 DOI-derived URL 去试 XML 和 PDF。这是 OA + URL 模式稳定的 provider 才有的便宜 robustness。

---

### 8. 一整套 HTML 清洗规则写好了，但根本没人调用 —— 死代码（已按删除路线处理）

**原位置**：
- `src/paper_fetch/extraction/html/provider_rules.py:343–350`
- `src/paper_fetch/quality/html_signals.py:222–241`
- `src/paper_fetch/providers/copernicus.py:519–534` 的 `html_to_markdown`

**现象**：代码里注册了一堆 Copernicus 专用的 HTML 处理规则：

- `COPERNICUS_SITE_RULE_OVERRIDES` —— 哪些 CSS 选择器是导航/广告要清掉
- `COPERNICUS_ACCESS_BLOCK_TEXT_TOKENS` —— 怎么识别"访问被拦截"页面
- `copernicus_blocking_fallback_signals` —— HTML 信号判定
- `copernicus_positive_signals` —— HTML 正向信号
- `html_to_markdown` 方法 —— HTML 转 Markdown

但实际跑起来，Copernicus 的主流程只有 **XML → PDF** 两条路，**完全不走 HTML**。这些规则注册之后**永远不会被执行**。

**通俗类比**：在厨房里装了一台烤箱，结果店里只卖凉菜，烤箱通电但从来没开过 —— 维护成本（要除尘、要电费）一直在，却没产生任何价值。

**处理结果**：已选择删除路线，移除 Copernicus provider 的 `html_to_markdown` override、HTML provider rules 注册、Copernicus HTML availability signals，以及测试和文档里的占位 hook 表述。当前主链明确保持 `landing HTML 发现 XML/PDF -> XML -> PDF text-only fallback -> metadata-only fallback`。

---

### 9. 给 doi.org 发请求时把斜杠也编码了 —— 多绕一跳

**位置**：`src/paper_fetch/providers/copernicus.py:276`

**现象**：代码现在生成的 URL 长这样：

```
https://doi.org/10.5194%2Facp-24-1-2024
                     ↑
               斜杠被编码成 %2F
```

而正常写法是：

```
https://doi.org/10.5194/acp-24-1-2024
```

doi.org 两种都接受，但**编码版会多一次 301 跳转**才到正确格式，再继续往期刊域名跳。等于每次抓 Copernicus 都白白多走一跳。

**通俗类比**：导航起点写"北京市%2F海淀区"，导航能识别但要先帮你"翻译"一下再规划路线，不如直接写"北京市/海淀区"省事。

而且因为多这一跳，`MAX_COPERNICUS_HTML_REDIRECTS = 6` 被设得偏宽（其实正常情况 doi.org → 期刊域名一跳就够），数字偏宽容易掩盖真问题。

**建议**：`urllib.parse.quote` 加上 `safe='/'`（或干脆不 quote DOI），redirect 上限顺便降到 4。

---

### 10. PDF 兜底永远只给纯文本，图表全丢

**位置**：`src/paper_fetch/providers/copernicus.py:704–729`

**现象**：当 XML 路线挂了走 PDF 兜底时：

- PDF 已经下载到本地了 ✅
- 但 `describe_artifacts` 硬编码 `text_only=True` / `allow_related_assets=False`，**只输出纯文本 Markdown**
- 图、表、补充材料一律丢弃

**通俗类比**：饭已经买回家了，但规定"外卖盒里的菜只能吃饭，菜里的肉自动倒掉" —— 浪费现成资源。

这条对早期 Copernicus 文章影响最大，因为这些老文章 XML 是空壳，**主要靠 PDF 兜底**。用户拿到的就是个没图没表的纯文字版。

**建议**：评估能不能把 PDF bytes 接到现有的 PDF 资产抽取流程，让 `body` profile 也能从 PDF 里捞出图表。这是个工作量较大的改动，需要先确认 `paper_fetch.providers._pdf_fallback` 是否暴露了图表抽取入口；如果没有，则需要先做 PDF 资产抽取的 base-layer 能力。

---

## 三、测试 / 文档面

### 11. owner 单测对 abstract-only XML 必须降级到 PDF 这条规则没有最小覆盖

**位置**：`tests/unit/test_copernicus_provider.py`

**现象**：`test_xml_failure_skips_landing_html_and_falls_back_to_pdf` 用的是"非 XML 字符串"触发 fail；但真实早期 Copernicus XML 是**合法 JATS 但 body 为空**——这才是 `_validate_xml_extraction` 三个分支真正要守的语义。

**建议**：加个 fixture：合法 `<article><front>…</front><body/></article>` → 必须 `no_result` 并继续 PDF。这能锁住第 3 条改动。

---

### 12. `MAX_COPERNICUS_HTML_REDIRECTS` 是 module 级常量但仅一处使用

**位置**：`src/paper_fetch/providers/copernicus.py:62`

**现象**：module 级常量，但只在 `_fetch_landing` 中用了一次。

**建议**：收口成类常量或函数局部，且按第 9 条把值从 6 调到 4（与 doi.org 斜杠不再编码配合）。

---

## 优先级建议

按建议处理顺序：

1. **#1 → #2 → #3** —— 前三条都是"已经写好的代码做了两遍"的纯收益清理
2. **#7** —— landing 失败降级，提升真实弹性
3. **#8** —— 决定 HTML 路径死活，消除死代码
4. **#11** —— 补 abstract-only XML 单测缺口，配合 #3 落地
5. **#9 / #12** —— 小 polish，可与 #7 一起做
6. **#4 / #5 / #6** —— 重构清理，可独立 PR
7. **#10** —— 工作量最大，需要先评估 PDF 资产抽取基础能力是否就绪

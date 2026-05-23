# Royal Society Publishing Asset Download Issue

## 背景

在为 Royal Society Publishing golden fixtures 生成 `body` 档位 Markdown 时，正文 Markdown 可以成功生成，但多数样本的 body assets 没有成功落盘。

复现输出目录：

```text
live-downloads/royalsocietypublishing_body_md/
```

批处理结果中 7 篇 Markdown 均为 `status: ok`，其中 6 篇出现类似 warning：

```text
Royal Society Publishing related assets were only partially downloaded (N failed).
```

## 失败现象

Royal Society HTML 抽取出的 figure asset URL 形如：

```text
https://royalsocietypublishing.org/view-large/figure/17919659/rsta20190558f01.tif
```

通用图片下载器尝试直接下载该 URL，但响应不是图片，而是 HTML viewer 页面：

```text
status: 200
content-type: text/html; charset=utf-8
reason: Asset candidate did not return image content (content-type: text/html; charset=utf-8).
```

因此下载器按图片内容校验失败，未保存本地 asset。

## 根因

`/view-large/figure/.../*.tif` 在 Royal Society Publishing 站点上不是直接图片文件地址，而是图片查看页地址。真正可下载的图片通常位于该 viewer HTML 内部的 `img src` 或 `data-src` 字段中，例如 `trs.silverchair-cdn.com/.../*.png?...` 的签名 CDN URL。

当前实现把 `/view-large/figure/` URL 标记为 body figure，并交给通用 HTML asset downloader 直接下载。通用 downloader 对 figure 要求响应为真实图片内容，因此遇到 `text/html` viewer 页面会判定失败。

相关代码路径：

```text
src/paper_fetch/providers/_royalsocietypublishing_html.py
src/paper_fetch/providers/royalsocietypublishing.py
src/paper_fetch/extraction/html/assets/_kind.py
src/paper_fetch/extraction/html/assets/download.py
```

## 影响范围

- Markdown 正文生成不受影响。
- `asset_profile=body` 下，Royal Society 正文 figure assets 可能无法落盘。
- 失败样本的 `_assets/` 目录可能为空。
- 没有抽取到 figure asset 的样本不会报 asset 失败，例如本次 `10.1098/rsta.2020.0108` 没有 extracted assets，因此无 asset warning。

## 修复方向

Royal Society provider 需要把 viewer 页和真实图片地址分开建模：

1. 将 `/view-large/figure/...` 保存为 `figure_page_url`。
2. 解析 viewer HTML 中的 `img src` 或 `data-src`。
3. 将解析出的 `trs.silverchair-cdn.com/.../*.png?...` URL 写入 `full_size_url` 或 `preview_url`。
4. 再交给通用图片下载器下载真实图片 URL。
5. 增加 provider-local 回归测试，覆盖：
   - `/view-large/figure/...` 返回 HTML viewer。
   - viewer HTML 内含 CDN 图片 URL。
   - `asset_profile=body` 成功保存图片，并把 Markdown 链接改写到本地 asset path。

## 调试证据

本地复现时，直接调用 provider asset 下载可得到如下诊断：

```text
downloaded 0 failures 2
source_url: https://royalsocietypublishing.org/view-large/figure/17919659/rsta20190558f01.tif
reason: Asset candidate did not return image content (content-type: text/html; charset=utf-8).
status: 200
content_type: text/html; charset=utf-8
```

打开同一个 viewer 页面后，可以在 HTML 中看到真实图片地址：

```text
img src: https://trs.silverchair-cdn.com/trs/content_public/journal/rsta/.../rsta20190558f01.png?... 
```

## Markdown 人工审阅发现

审阅对象：

```text
live-downloads/royalsocietypublishing_body_md/*.md
```

7 篇 `body` 档位 Markdown 都能生成，正文主体大体可读，但还存在多类语义和结构问题，不能直接作为高质量 golden baseline。

### 1. Abstract 重复

所有样本都出现相同模式：

```text
## Abstract

Abstract

## Abstract
```

第一段 `Abstract` 是标题噪声，应在 Royal Society HTML 清洗或 Markdown 后处理阶段去掉，最终只保留一个 `## Abstract` 和真实摘要正文。

### 2. 文内引用保留 `javascript:;`

文内 citation、figure/table xref 大量渲染为 Markdown 链接：

```text
[[1](javascript:;)]
[Figure 1](javascript:;)
[table 2](javascript:;)
```

这类链接不可访问，也会污染 AI 阅读上下文。人工扫描到的 `javascript:;` 数量：

```text
10.1098_rsif.2019.0334.md   69
10.1098_rsos.150470.md      153
10.1098_rsos.201188.md      98
10.1098_rsos.201200.md      85
10.1098_rspb.2020.0097.md   128
10.1098_rsta.2019.0558.md   122
10.1098_rsta.2020.0108.md   149
```

修复方向：Royal Society 后处理应把 `javascript:;` citation/xref 转成纯文本引用标记，或解析为内部锚点；不能保留不可用链接。

### 3. Figures 区只剩空标签

多数样本末尾的 `## Figures` 只有类似内容：

```text
## Figures

- Figure
- Figure
- Figure
```

没有 figure 编号、caption、图片链接或本地 asset path。这个问题与 assets 下载失败有关，但即使图片无法下载，也应该保留 figure caption 和编号，避免图表语义完全丢失。

受影响样本包括：

```text
10.1098_rsif.2019.0334.md
10.1098_rsos.150470.md
10.1098_rsos.201188.md
10.1098_rsos.201200.md
10.1098_rspb.2020.0097.md
10.1098_rsta.2019.0558.md
```

`10.1098_rsta.2020.0108.md` 未出现 Figures 区，因为本次没有 extracted assets。

### 4. 表格转换重复和错位

表格存在两类问题：

- 同一个表重复出现。
- 引用列、sources 列或首列被压成不完整 Markdown，例如 `[|`、`FIII | ...` 缺少开头管道。

典型样本：

```text
live-downloads/royalsocietypublishing_body_md/10.1098_rsta.2019.0558.md
live-downloads/royalsocietypublishing_body_md/10.1098_rspb.2020.0097.md
live-downloads/royalsocietypublishing_body_md/10.1098_rsif.2019.0334.md
```

示例问题片段：

```text
| reference | number of patients | goal of the study | type of model | strategy |
|---|---|---|---|---|
| [|
```

```text
FIII | -3.372 | 2.176 | -1.550 | 0.121 |
PC2: FIII | 6.190 | 2.400 | 2.579 | 0.010 |
```

修复方向：Royal Society 表格提取需要去重，并对表格 cell 内 citation/link 做安全降级，避免破坏 Markdown pipe table 结构。

### 5. 数学公式和定理损坏

数学/模型类论文的 MathML 或公式块损坏明显，出现大量孤立符号、缺失变量和断裂文本。

典型样本：

```text
10.1098_rsos.201188.md
10.1098_rsif.2019.0334.md
```

示例问题：

```text
#### Proof.. Then, from (*n*[4.2](javascript:;)), the following is satisfied:
```

```text
*Consensus to**is reached exponentially with convergence rate*
```

```text
Notice also that when = 0, the *k* dependence cancels out entirely.
```

修复方向：Royal Society HTML 路径需要保留或转换 MathML。至少应把无法转换的 display formula 渲染为明确占位和原始 MathML/TeX fallback，不能静默丢变量。

### 6. Back Matter 丢失

Royal Society 原始 HTML 中常见 back matter 包括：

```text
Ethics
Data accessibility
Authors' contributions
Competing interests
Funding
Acknowledgements
Disclaimer
```

生成的 Markdown 中保留不稳定。多篇只保留 `Data accessibility`，有的直接从正文进入 `Figures`/`References`，导致伦理、作者贡献、利益冲突、资金和致谢信息丢失。

典型样本：

```text
10.1098_rspb.2020.0097.md
10.1098_rsif.2019.0334.md
10.1098_rsos.201188.md
10.1098_rsos.201200.md
10.1098_rsos.150470.md
10.1098_rsta.2019.0558.md
```

修复方向：Royal Society 清洗规则应把 article back matter 纳入正文保留范围，同时继续排除 publisher chrome、license boilerplate 和导航。

### 7. References 质量偏低

References 区能生成条目数量，但大量条目只有 DOI 或只有标题，作者、年份、期刊、页码等元数据经常丢失。

人工统计 DOI-only reference bullet 数量：

```text
10.1098_rsif.2019.0334.md   55
10.1098_rsos.150470.md      21
10.1098_rsos.201188.md      75
10.1098_rsos.201200.md      42
10.1098_rspb.2020.0097.md   91
10.1098_rsta.2019.0558.md   86
10.1098_rsta.2020.0108.md   160
```

修复方向：应优先从 Royal Society reference DOM 的 mixed citation 结构提取完整引用文本，并仅在完整文本不可用时才退回 DOI-only。

### 8. License 文本误入 Footnotes

`10.1098_rsos.201188.md` 的 `## Footnotes` 中混入 Creative Commons license 文本：

```text
[http://creativecommons.org/licenses/by/4.0/](http://creativecommons.org/licenses/by/4.0/), which permits unrestricted use, provided the original author and source are credited.
```

license/copyright boilerplate 不应作为论文 footnote 正文进入 Markdown。

## 建议修复优先级

1. Abstract 去重和标题噪声清理。
2. Figure caption/编号保留，并修复 viewer 页到 CDN 图片 URL 的 asset 下载链路。
3. 表格去重、cell 内引用安全降级、Markdown pipe table 修复。
4. MathML/display formula 保留或可见降级。
5. Back matter 保留策略。
6. References 完整引用文本提取。
7. `javascript:;` 链接清理。
8. License/footer boilerplate 从 footnotes/back matter 中剔除。

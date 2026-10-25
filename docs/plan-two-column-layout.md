# 方案：双栏/多栏原排版保留 + 排版自检不再误杀

状态：已实施（本地分支 `dev`，见文末“实施结果”）
分支计划：`main` → 新建本地分支 `dev`（不推送远端）

## 一、现状与根因（基于本次真实产物分析）

失败产物：`…\DUSt3R Geometric 3D Vision Made Easy_c02a82_zh\render-report.json`

### 1. 双栏变单栏（本方案的主目标）

`work/document_pipeline.py::assemble()` 把每页的 block 按阅读顺序拼成一整段 Markdown，
`work/latex_renderer.py::build_project()` 用 pandoc `article` + `geometry:margin=24mm` 生成
单栏正文。全流程没有任何"栏"的概念：AI 已经返回了每个 block 的归一化 `bbox`（含左右栏信息），
但 assemble 只用了 `markdown`，bbox 只在裁图时使用。

源 PDF 实际版式（PyMuPDF 实测，13 页）：
- p1 通栏标题/作者/图 1，摘要起进入双栏；
- p2–p12 双栏，栏缝稳定在 x≈0.47–0.50，左栏 0.08–0.47，右栏 0.50–0.89；
- p4/p5/p8 存在跨栏的宽图表（AI bbox 宽度 > 0.62 或跨越栏缝）。

即：栏结构是**确定可知**的，只是没被利用。

### 2. "缺字"致命（✓ U+2713）

`HEADER` 里只给 `☐`、`★` 做了 `\newunicodechar`，正文/表格里残留的 `✓` 交给 Times New Roman，
XeTeX 报 `Missing character: There is no ✓ (U+2713)`。`render_latex()` 把
`counts['missing_characters']` 非空直接判为 `LatexLayoutError`，于是整次输出失败、PDF 不更新。
实际只有一个字形缺失，完全可自动修复。

另外：`test_portable_fonts_compile_without_windows_fonts` 已证明 Overleaf 场景（无 SimSun/Times）
也必须零缺字，所以修复要"字体回退"，不能只靠往 Times 里塞字符。

### 3. "内容严重越界"致命（183pt / 262pt）

pandoc 把 AI 返回的 grid 表写成 `longtable` + `@{}llll…@{}`（14 列）或 `p{0.2\linewidth}` 列。
- 14 个 `l` 列按自然宽度排 → 183pt、262pt 超出版心；
- `p{}` 列里嵌 `minipage{\linewidth}`，不可断词，同样越界。

没有被任何缩放包装（`main.tex.before-fix` 可见原始形态），`Overfull \hbox … in alignment`
被 `SEVERE_OVERFULL_PT=20` 判定为失败。且 `longtable` **不能**放进多栏环境，这一点决定了双栏改造必须同时处理表格。

结论：这次失败是三个独立缺陷叠加，都要修；"译文缓存已落盘、只需重排版"的定位正确。

## 二、目标 / 非目标

目标
1. 双栏、三栏论文重排后仍是双栏/三栏：通栏元素（标题、跨栏宽图/宽表）仍通栏，正文按原阅读顺序在栏内流动。
2. 单栏文档（当前主力场景：教材、讲义）行为**完全不变**。
3. 缺字自动修复（字体回退），修不掉也只降级为警告，不再阻断 PDF 产出。
4. 表格统一缩放到版心/栏宽，不再产生"alignment 越界"。
5. 不重新调用模型即可生效（缓存已落盘，`renderOnly` 直接重排）。

非目标
- 不做"逐页复刻"（页码、分页位置与原 PDF 完全一致）。中文译文长度变化必然导致分页不同，只保证栏结构、阅读顺序、通栏/分栏关系一致。
- 不改 AI 提示词，不改页面识别结果格式，不新增模型调用。

## 三、设计

### A. 新增 `work/column_layout.py`：识别栏栅格与跨栏判定

```python
detect(source, pages) -> {'columns': 2, 'gutters': [{'start':0.47,'end':0.50}], 'pages': {...}}
spans(bbox, grid) -> bool
```

算法（确定性，不依赖模型）：
1. 取每页文本行（`page.get_text('dict')`），丢弃宽度 > 0.62 页宽的行（标题、表格行等通栏行），
   得到"栏内正文行"。
2. 200 格横向墨迹剖面；空白阈值 `t = max(1, 5% 行数)`（容忍跨栏行蹭到栏缝）。
3. 在 `[0.22, 0.78]` 内找宽度 ≥ 0.006、两侧各有 ≥15% 行数的空带 → 一条栏缝；
   若带宽 > 0.12 视为右边距，丢弃。
4. 三栏以上：对左右两侧递归同样处理（每侧再要求 ≥12% 行数）。
5. 文档栏数 = 有足够正文的页面的众数；栏缝位置取中位数（避免个别页表格导致抖动）。
6. 纯图页无文本时，退化用 `pages[*].blocks[].bbox` 的中点直方图推断；仍失败则视为单栏。

跨栏判定：`bbox` 与任一栏缝带相交（留 0.004 容差），或宽度 > 0.72 页宽 → 通栏。

实测校验（用本机 DUSt3R 原 PDF）：p2–p12 栏缝 0.465–0.51 全部命中，p1 判为无栏缝（通栏页），符合实际。

### B. `assemble()` 输出栏标记（唯一的"决策点"）

- 读 `cache/layout.json` 的 `columns`（0=自动，1/2/3=强制）。
- `parts` 由 `list[str]` 改为 `[(text, span: bool)]`：
  - figure-row Div：取首个成员 figure 的 bbox 判定；
  - 普通 block：用自身 bbox；
  - 跨页合并的段落：用起始 block；
  - 表格补一条保险规则：Markdown/HTML 表格列数 ≥ 6 且栏数 > 1 → 强制通栏（防止 AI bbox 偏窄导致宽表被压进窄栏）。
- 拼接时按 span 切换，插入不可见 HTML 注释标记：

```
<!-- translator-columns: 2 -->
…栏内内容…
<!-- translator-columns-end -->
```

- 脚注定义（`[^x]:`）本来就在文档末尾，会落在 close 之后，天然在栏外；
  单次 pandoc 解析保持不变，所以"引用与定义必须同一次解析"的既有约束不受影响。
- `translated.md` 里的标记是 HTML 注释，Markdown 阅读器不可见；单栏文档不产生任何标记。

### C. `build_project()` 渲染多栏

pandoc 把标记解析成独立的 `RawBlock html`（已实测）。在 `visit()` 之前做一次
`wrap_columns(blocks)`：按开/关标记把顶层 block 收拢成自定义节点
`{'t':'TranslatorColumns','c':[N, members]}` 并删除标记；`visit()` 遇到该节点时
（与现有 `TranslatorFigure` 同一套路）对该段单独 `pandoc -t latex`，再包一层：

```latex
\begin{multicols*}{N}
…
\end{multicols*}
```

- 用 `multicols*`（不均衡）而不是 `multicols`：内容先填满左栏再进右栏，符合论文阅读顺序；
  带星号版本允许跨页续排，不会在每段落尾把内容劈成两截短栏。
- 通栏元素就是把 `multicols*` 关掉、通栏输出、再打开，天然保持原文"文字—宽图—文字"的顺序。
- `figureMaxWidth/figureMaxHeight` 用 `\linewidth` 表达，进栏后自动变成栏宽，不需要改参数语义。
- 已用最小样例验证：`multicols*` + 跨栏表格 + `adjustbox` + 中文 + 符号回退，tectonic 编译通过、✓ 正常显示。

### D. 表格适配 `fit_tables(tex)`（新增，在 pandoc 之后、写 main.tex 之前）

把 pandoc 的 `longtable` 统一改写成可缩放、可入栏的形式：

```
\begin{adjustbox}{max width=\linewidth}
\begin{tabular}{<原列格式>}
…（去掉 \endhead/\endfirsthead/\endfoot/\endlastfoot）
\end{tabular}
\end{adjustbox}
```

- `\linewidth` 在栏内即栏宽、在通栏即版心宽，一条规则覆盖两种情况。
- `\caption{}` 若存在则提到 adjustbox 之前（现有流程图题本是独立 block，正常不会触发）。
- 行数 > 25 的表追加 `max totalheight=0.9\textheight`，避免 tabular 不可分页导致竖向溢出。
- `longtable` 不能进 `multicols*`，这一步也是双栏的前置条件。

### E. 字形回退 `heal_glyphs(project, engine_log)`（新增）

1. 静态映射（HEADER 常驻）：`✓✔✗✘✕☐☑☒★☆●○◆◇■□▲△▼▽→←↑↓↔⇒⇔⊗⊕≈≠≤≥±∞∇∂∑∫√∝⊥∠°′″⟨⟩−×²³` 等
   常见符号 → 对应数学命令（`\checkmark`、`\square`、`\texttimes`…）。
2. 动态兜底：编译后从 `main.log` 抓 `Missing character: There is no X (U+XXXX)`，
   把每个字符追加成 `\newunicodechar{X}{{\symbolfont X}}`（CJK 区用 `\cjkfallbackfont`），
   插到 `\begin{document}` 之前重编译；最多 2 轮，不消耗任何模型配额。
3. 字体链：`Segoe UI Symbol` → `DejaVu Sans`（TeX Live 自带，Overleaf 可用）→ 保持原字符；
   CJK 兜底：`Microsoft YaHei` → `FandolSong-Regular.otf`。

### F. 自检策略调整

| 情况 | 现状 | 改为 |
|---|---|---|
| 缺字（可回退） | 直接失败 | 回退字体后重编译，**不失败** |
| 缺字（回退后仍缺） | 失败 | 记 `unresolved_glyphs`，产出 PDF，`status=needs_review` |
| 越界可定位到数学区域 | AI 局部修复 → 失败则失败 | 不变（这条链路是有效的） |
| 越界无法定位 | 保留 PDF + 警告（`overfull_accepted`） | 不变 |

理由：单个字形缺失/单张表越界不该让整次翻译作废；真正影响可读性的数学区域越界仍走修复链路。

### G. 参数与通道

- `validate_layout` 增加 `columns`（整数 0–4，0=自动）；`layout.json` 与 AI 核验 `apply.layout` 可直接覆盖。
- `src/index.js`（`pdf_review` 的 layout schema）、`src/review.js`（zod + 提示文案）各加一行 `columns`，
  保证核验流程能用它修版式；`node --check` 校验语法（该仓库无 node_modules，跑不了 JS 单测）。

## 四、改动清单

| 文件 | 改动 |
|---|---|
| `work/column_layout.py` | 新增：栏检测、栏数统计、跨栏判定（约 160 行） |
| `work/document_pipeline.py` | `assemble()` 读 `layout.columns`、按 span 分组、写标记、表格列数兜底（约 50 行改动） |
| `work/latex_renderer.py` | `HEADER` 加 `multicol`、符号映射与字体链；新增 `wrap_columns`、`fit_tables`、`heal_glyphs`、`compile_with_heal`；`validate_layout` 加 `columns`；`render_latex` 接入回退与降级（约 180 行） |
| `src/index.js`、`src/review.js` | layout schema 加 `columns` |
| `work/test_column_layout.py` | 新增单测 |
| `work/test_latex_renderer.py` | 新增 4 个用例（多栏、表格、缺字、宽表） |
| `CHANGELOG.md`、`README.md`、`VERIFICATION.md` | 记录行为变化（若需要） |

## 五、验证方案

1. 单元测试（新）
   - 合成双栏/三栏 PDF：`detect()` 栏数、栏缝位置正确；跨栏 bbox 判定正确；单栏 PDF 判为 1 且不产生标记。
   - 标记 → `main.tex` 含 `\begin{multicols*}{2}`，通栏段在其外。
   - `longtable` → `adjustbox`+`tabular`，无 `\endhead`；14 列宽表编译后 `overfull_boxes_pt` 为空。
   - 含 `✓ ✔ ☑ →` 的文档：`missing_characters == []`；模拟无 Windows 字体（patch HEADER）同样零缺字。
2. 既有回归：`work/test_latex_renderer.py`、`test_document_pipeline.py`、`test_panel_pipeline.py`、`test_review_pipeline.py` 全绿。
3. 真实回归（不花 token）：对已缓存的 DUSt3R 跑 `renderOnly`
   - 产出新 PDF；`render-report.json`：`missing_characters == []`，`overfull_boxes_pt` 为空或仅剩非阻塞项；
   - 用 PyMuPDF 复测输出 PDF 的栏缝（期望双栏且栏缝 ≈ 0.48）；
   - 目视 p1（通栏标题+双栏摘要）、p4/p8（跨栏宽表）三页截图。
4. 单栏回归：用测试 fixture（`tests/fixtures/session-p10-equation.md` 等）确认单栏文档 `main.tex` 无 `multicols`、版式与改动前一致。

## 六、风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| `multicols*` 关闭/重开处右栏留白 | 观感 | 只在真正通栏元素处切换；通栏元素通常是宽图宽表，原文同样在此断栏 |
| 宽表被压进窄栏后字太小 | 可读性 | 列数 ≥6 或 bbox 跨栏 → 强制通栏；通栏走 `\textwidth` |
| 超长表格无法分页 | 竖向溢出 | 行数 > 25 时加 `max totalheight`；实测论文表均远小于此 |
| 栏内公式越界判定变化 | 误报 | 越界阈值与归因逻辑不变，只改表格与字形 |
| 纯图 PDF 无文本行 | 栏检测失效 | 退化为 bbox 中点直方图；再失败按单栏处理（等价当前行为） |
| 核验流程 `assemble(stage)` 读不到 layout | 覆盖失效 | `review_pipeline` 已先写 `stage/layout.json` 再调 `assemble`，天然可用 |

## 七、实施顺序

1. `git switch -c dev`（本地分支，不推送）。
2. `column_layout.py` + 单测 → 用 DUSt3R 原 PDF 验证栏检测。
3. `assemble()` 标记 + `build_project()` 多栏渲染 → 端到端 `renderOnly` 看双栏效果。
4. `fit_tables` → 消掉 alignment 越界。
5. `heal_glyphs` + 自检降级 → 消掉缺字致命。
6. 全量回归 + 文档/CHANGELOG，提交若干独立 commit（每步可回滚）。

## 八、需要你确认的三点

1. 双栏实现方式：`multicols*` 流式（推荐，稳定、支持 2/3 栏、通栏元素自然穿插）还是"逐页固定栏框"（更像原页码，但中文长度一变就会错位、易崩）。默认按前者。
2. 宽表策略：列数 ≥6 或跨栏 → 自动通栏放大（推荐）；还是强制全部缩进栏内（字会很小）。
3. 缺字是否允许"降级不失败"：推荐允许（产出 PDF + `needs_review` + 报告列出未解决字形）。

## 九、实施结果（相对方案的三处调整）

按评审确认的三项默认值实施（multicols 流式、宽表自动通栏、缺字降级为警告）。实施中发现并调整了以下细节：

1. **双栏改用 `twocolumn` 类选项，不用 multicols。** 实测 multicols 区域结束时会强制分页：DUSt3R 13 页重新排版后 20 页里出现 2 个半页空白（p4 填 42%、p11 填 66%）。改为 `\documentclass[...,twocolumn]` + 首段 `\twocolumn[{…}]` 承载通栏标题后，正文连续流动，跨栏图表用 `figure*`/`table*` 浮动到页顶，18 页全部填满（89%–92%），没有空白页。三栏仍走 multicols（类选项只支持两栏），单栏文档不产生任何标记、行为不变。
2. **跨栏图表用浮动体而不是就地插入。** 只关掉 multicols 再插入宽图仍会在图表前留下半页空白；改成浮动到页顶后正文会把当前页填满。为此题注按原页几何位置（图下方 0–6% 页高、横向重叠 >30%）绑定到同一个浮动体，避免“图表在页顶、题注跑到上一页栏里”。
3. **表格做了两级适配。** `longtable` → `adjustbox` + `tabular`（宽表缩放；同时是进 multicols 的前提）；窄栏里的定宽 `p{}` 列表格先按 1.6 倍宽度排版再整体缩放，否则 5 列表会被压成一列一个字。另外按 colspan 重新计算 HTML 表列数（原来按首行列数统计，9 列表会被算成 4 列而留在栏内挤成 3pt）。

验证数据（DUSt3R，`renderOnly` 复用缓存，0 次模型调用）：
- 18 页，全部页面填充率 0.89–0.92；原失败产物为 13 页单栏 + 失败。
- `missing_characters: []`、`overfull_boxes_pt: []`、`status: complete`（原为两者的致命错误）。
- 目视复核 p1（通栏标题/图 1 + 双栏摘要）、p5/p6（通栏图 2/图 3 + 题注）、p8/p10/p11（9/14/16 列宽表浮动到页顶并带题注）。
- Python 单测 70 项全绿（新增 6 项：栏检测、栏标记、双栏类选项、三栏 multicols、宽表缩放、符号回退）。

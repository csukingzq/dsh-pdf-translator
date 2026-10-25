# Changelog

## 0.4.3 — 2026-10-25

- 保留原 PDF 的栏结构：新增栏栅格识别（正文行墨迹剖面 + 栏缝递归拆分，支持 1/2/3 栏），按块坐标区分通栏与栏内内容。双栏文档用 `twocolumn` 流式排版，三栏用 `multicols` 区域，单栏文档行为不变。
- 跨栏的宽图、宽表按浮动体排到页顶，正文继续填满当前页，不再出现半页空白；题注按原页几何位置绑定，随图表一起浮动。
- 表格统一改写 pandoc 的 `longtable` 为 `adjustbox` + `tabular`：按可用宽度缩放，14 列宽表不再溢出，也不再产生“alignment 越界”并让整次输出失败。窄栏里的定宽列先按 1.6 倍宽度排版再缩放，避免每行一个字。
- 修正表头/表尾横线：pandoc 把重复页脚（`\bottomrule`）写在表体之前，之前会在表头下方多出一条线、同时丢掉表格最后的收尾线；现在按 head/rows/footer 三段重排，表头一条中线、末尾一条收尾线。
- 宽图表浮动改用 `[!t]` 并放宽浮动比例限制，避免大于半页的表格无法落页、一路漂到参考文献之后。
- 公式排版：比栏宽的行间公式不再整体缩小（会看不清），改为按关系符断行、保持原字号，编号右对齐另起一行；带 array/aligned 的多行公式仍等比缩放。无编号公式现在真正居中（之前偏左 2em）。
- 提示词要求参考文献（作者、标题、期刊、年份）保持原文不翻译。
- 参考文献（`参考文献` / References / Bibliography 标题之后）改用 `\small` 排版，与原文习惯一致；不加的话 140 条文献会从 3 页涨到 8 页。只在正文后 45% 处的标题才判定为文献表，不影响附录。
- 缺字自动修复：常见勾选/方框/箭头字符映射到符号字体回退，编译后仍缺的字用 `newunicodechar` 逐字回退并重新编译（最多两轮，不消耗模型配额）。回退后仍缺的字只记入 `unresolved_glyphs` 并保留 PDF，不再让整次翻译失败。
- 越界自检只在能定位到具体内容块时失败；已缩放的表格内部越界不再计入 `overfull_boxes_pt`，改记 `scaled_table_boxes`。
- `layout.json` / `pdf_review apply.layout` 新增 `columns`（0=自动，1/2/3=强制栏数）。
- 新增 `column_layout.py` 及其单测；`document_pipeline`、`latex_renderer` 增加栏标记、浮动体、表格适配、字形回退的回归用例。

## 0.4.2 — 2026-10-24

- 模型配置对话框在接口地址为空时预填 `https://api.deepseek.com/v1`，避免把 placeholder 误当成已填写而无法点保存。
- 空文件或 0 字节的 `config.json` 视为未配置（不再报格式错误），可直接在面板保存，`setup.ps1` 也会重新写入示例配置。

## 0.4.1 — 2026-10-24

- 环境安装默认使用国内镜像：Tectonic / Pandoc 优先经 `ghproxy.net`、`gh-proxy.com`、`ghfast.top` 下载，pip 依赖优先用清华、阿里源；失败自动回退官方 GitHub / PyPI。可用 `-OfficialOnly` 强制官方源。
- `setup.ps1` 控制台输出改用 UTF-8，PowerShell 的中文错误信息不再乱码。
- 修复 pip 多镜像重试时把 pip 输出当成退出码、导致每个镜像都被误判为失败的问题。

## 0.4.0 — 2026-10-24

- 首次运行改为在 PDF 翻译面板内一键完成：自动创建 Python 环境、安装依赖并下载 Pandoc / Tectonic，显示阶段、可取消、可重试。
- 新增面板内「模型配置」表单，直接填写 `base_url`、`model`、`api_key`，不再需要手动编辑 `config.json`。
- 环境未就绪时 `pdf_translate` 会提示并自动打开面板；错误信息不再引导用户去终端跑脚本。
- 新增面板接口 `setupStart`、`setupCancel`、`saveConfig`；`status` 返回环境与配置状态。API 密钥只写本机配置文件，不通过状态接口回传。
- 安装完成和配置保存后无需重启即可翻译；手动 `setup.ps1` 作为离线/高级方式保留。

## 0.3.0 — 2026-10-24

- 输出目录改为每次翻译一个子文件夹，里面只有中文 PDF 和 LaTeX 源码 zip；不再写出 `translated.md`、`crops/`、`document.json`、`layout.json`、`*.report.json` 和 `previews/`。
- zip 内的工程可直接用 XeLaTeX 或 Tectonic 编译，不包含 `.aux`、`.log`、`main.pdf` 等编译中间产物。
- 译文、结构数据和报告移入插件数据目录，AI 核验的 `apply` 会同时重新打包 zip，保持 PDF 与源码一致。
- 缓存清理仍保留已导出的 PDF 和 zip。
- 生成的 `main.tex` 不再强制使用 Windows 字体：本机有宋体 / Times New Roman 时保持原样，Overleaf 等缺少这些字体的环境自动退回 Fandol / TeX Gyre Termes，整包可直接用 XeLaTeX 编译。

## 0.2.5 — 2026-10-24

首个面向公众分发的版本。

- 发布到 npm，可用 `dsh-pdf-translator` 包名安装。
- 提供 GitHub Release 预构建 `.tgz`，无需安装时构建。
- 新增 `LICENSE`（MIT）、仓库/问题链接和发布元数据。
- 默认把配置、Python 环境、Tectonic/Pandoc 和缓存保存到 `%DSH_HOME%\dsh-pdf-translator`，插件更新不再清掉用户数据；检测到旧版包内配置或状态时继续使用旧目录。
- `scripts/setup.ps1` 支持 DSH 桌面自带的 Python，自动创建虚拟环境、安装依赖并下载排版运行时。
- `pdf_translator_doctor` 返回数据目录、配置路径、运行时目录和插件路径，便于排查。
- 新增 `scripts/verify-package.mjs`、CI 和 tag 发布工作流。
- README 改为外部用户安装说明；清理验证记录中的本机路径。

## 0.2.4 — 2026-10-24

- 适配 Harness 0.2.1-rc.3：`engines.dsh`、peer 和依赖版本同步，修复插件管理器判定不兼容的问题。
- 运行代码和前端 bundle 与 0.2.3 相同。

## 0.2.3 — 2026-10-24

- 面板、AI 核验、缓存清理和 LaTeX 修订流程的稳定性更新。

## 0.2.2 — 2026-10-24

- 240px 极简面板、深浅主题不透明背景、入口拖动和记忆。

## 0.2.1 — 2026-10-24

- 修复远程接口依赖声明和面板首次挂载问题。

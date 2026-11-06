# DeepSeek Harness AI PDF 翻译插件

先提取原文并确定全文结构，再按段落批次翻译，最后用 LaTeX 重排。输出中文 PDF 和可编辑 LaTeX 源码压缩包；不要求保持原书分页或文字位置。0.6.0-rc.1 为候选预发布版本，通过 npm next 或对应 GitHub 预发布安装。

## 功能

- 页面只是提取与来源定位单位。先识别原文与候选角色，再统一裁决章节、页眉及脚注关联；翻译按最多 8 个单元、目标 2,000 tokens 的批次组织，携带章节、相邻原文与关联脚注上下文；表格只重建结构，单元格内容保持原文不翻译，避免译文撑坏列宽。
- 自动识别原 PDF 的栏结构：双栏、三栏论文重排后仍是双栏/三栏；跨栏的宽图宽表保持通栏并浮动到页顶，只占一栏的小表留在本栏，题注跟随图表。
- 缺字自动改用符号字体回退，单个字形缺失不再让整次翻译失败。
- 图形通过原 PDF 图形与标签证据校验裁剪边界，保留原始曲线和数据；题注独立翻译。
- 表格重建为 Markdown / HTML，支持合并单元格；单元格、表头、表注一律照抄原文，不翻译。宽表按版心缩放，窄栏表格避免逐字换行。
- 每次翻译在输出目录下新建一个子文件夹，里面只有中文 PDF 和 LaTeX 源码 zip 两个文件。
- 首次运行在 PDF 翻译面板一键准备环境、填写模型配置，不需要终端或手改 JSON。
- 支持后台任务、任务取消、断点续跑和缓存复用。
- 可选 AI 核验：逐页检查译文，最多两轮修订与重新编译。
- 缓存由用户手动清理，不自动删除。

## 0.6 结构与编辑

- 脚注有独立 ID、原显示标记和正文锚点；支持 Unicode/数学上标、符号标记及有原生上标证据的普通数字。未关联脚注保留为明确标识的注释并报告，绝不自动降为正文或丢弃。跨页续注须双方都有续接证据，否则保持待核验。
- 重复页眉从正文中排除，LaTeX 按章节标题生成运行页眉；原书页码保存在来源信息中。混合块或证据不足的页边内容保留并报警。
- LaTeX ZIP 内新增 `translation-project.json`，保存块 ID、原文区域、译文、章节、脚注关联与诊断。可直接修改 `main.tex`；重新导出使用新任务目录，外部 `.tex` 修改不自动回写结构化项目。
- 核验 `blockEdits` 支持 `note_override: {anchors: [正文块ID]}`，与 `structure_override`、文本修订一起保存。空锚点列表表示显式保留未关联；完整页面接口可用 null 清除覆盖。
- 提取缓存与 `semantic-translations` 翻译缓存分开。翻译键包括模型、上下文、术语表、保护对象和算法版本。`renderOnly` 不会补做识别或翻译；仅有原文提取时明确报缺项。

### 可选本地解析工作进程

默认视觉提取路线继续可用，但不再逐页翻译。需要本地解析时运行 `scripts/setup-structure.ps1`：独立安装 BabelDOC 0.6.4、兼容的 bitstring 4.3.1、PaddleOCR 3.3.1 和 PaddlePaddle CPU 3.2.0，并将工作进程路径写入本机配置的 `structure_python`。首次运行可能下载模型。使用默认较短数据目录以避免 Windows 路径长度限制，无需修改系统权限。

适配层在 BabelDOC 完成段落/公式解析后停止，不调用其翻译或 PDF 排版；扫描页 OCR 输出文字、坐标和置信度，作为视觉提取证据，原书不变。低可信 OCR 不能直接成为删除正文或脚注的依据。可选解析失败会明确报错，不静默视为成功。

参考：[BabelDOC 0.6.4](https://github.com/funstory-ai/BabelDOC/tree/v0.6.4)、[Zotero PDF2zh](https://github.com/guaguastandup/zotero-pdf2zh)。第三方引擎单独安装并遵循各自许可证；安装包不内嵌第三方源码、模型或原书。

## 环境要求

- Windows 10/11；
- DeepSeek Harness 0.2.1-rc.3 或更新的 0.2.x；
- Python 3.10+（DSH 桌面版自带的 Python 会被自动使用）；
- 支持图片输入的 OpenAI 兼容 API 和 API 密钥；
- 编译 LaTeX 时优先使用宋体（SimSun）和微软雅黑（Microsoft YaHei）；没有这些字体时自动退回 TeX Live 自带的 Fandol 字体，例如在 Overleaf 上。

## 安装

### 方式一：npm（推荐）

npm 包地址：<https://www.npmjs.com/package/dsh-pdf-translator>

桌面版：

1. 打开 DSH，点击 **插件 → 添加插件**。
2. 输入 `dsh-pdf-translator`，点击 **安装**，然后 **立即启用**。

CLI：

```powershell
npx.cmd @deepseek-ai/dsh plugin --profile web add dsh-pdf-translator
```

### 方式二：GitHub Release

下载 [dsh-pdf-translator.tgz](https://github.com/csukingzq/dsh-pdf-translator/releases/latest/download/dsh-pdf-translator.tgz)，在 **插件 → 添加插件** 中选择该文件。

### 首次运行：面板一键完成

安装并启用插件，重启 Harness 后打开左下角或标题栏的 **PDF 翻译** 面板：

1. 首次会显示「首次使用需要准备运行环境」，点 **一键准备环境**。插件会自动创建 Python 环境、安装依赖并下载 Pandoc / Tectonic（约 300 MB，需要联网），面板显示进度，可取消或重试。默认优先走国内镜像（`ghproxy.net` / `gh-proxy.com` / `ghfast.top`，pip 用清华 / 阿里源），失败会自动回退官方 GitHub / PyPI。
2. 就绪后点 **填写模型配置**，填写接口地址、模型名称和 API 密钥并保存。密钥只写入本机 `config.json`，不会上传。
3. 直接 **选择 PDF** 开始翻译，不需要重启。

已配置过的用户不会看到向导；之后可随时用面板里的 **模型配置** 修改。

### 手动安装环境（离线/网络受限时）

如果自动安装失败（例如无法访问 GitHub 或 pip 源），可以在 PowerShell 中手动执行：

> 下载默认使用国内镜像，无需额外配置；也可以显式强制官方源：
>
> ```powershell
> & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-pdf-translator\scripts\setup.ps1" -OfficialOnly
> ```
>
> 自定义镜像或单独覆盖安装包地址：
>
> ```powershell
> setup.ps1 -PipIndexUrls "https://pypi.tuna.tsinghua.edu.cn/simple" -TectonicUrl "https://..." -PandocUrl "https://..."
> ```
>
> 安装长时间停在某个镜像时，脚本会自动尝试下一个镜像和官方源；全部失败可手动下载后放进 `%USERPROFILE%\.dsh\dsh-pdf-translator\runtime`。

```powershell
# 直接调用脚本（推荐，不依赖 powershell 在 PATH 中）
& "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-pdf-translator\scripts\setup.ps1"

# 或使用完整路径的 powershell.exe
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-pdf-translator\scripts\setup.ps1"
```

Web / CLI profile 把 `desktop` 换成 `web`。然后编辑模型配置：

```text
%USERPROFILE%\.dsh\dsh-pdf-translator\config.json
```

```json
{
  "base_url": "https://api.deepseek.com/v1",
  "model": "REPLACE_WITH_A_VISION_MODEL",
  "api_key": "REPLACE_WITH_YOUR_KEY",
  "thinking": "auto",
  "auto_repair_rounds": 3
}
```

手动改完后无需重启，直接翻译即可。也可以在聊天中发送「调用 pdf_translator_doctor 检查 PDF 翻译插件环境」。

## 使用

页面左下角和聊天标题栏都有 **PDF 翻译** 入口：

1. 点击 **选择 PDF**。
2. 确认输出目录和翻译页码，支持 `all`、`1-5`、`1,3,5-8`。
3. 点击 **开始翻译**。
4. 在 Harness 任务列表查看进度和结果。

也可以直接在聊天中说明：

> 使用 pdf_translate，把 D:\资料\paper.pdf 的第 1–3 页翻译为中文，先用 pdf_inspect 检查页数。

常用工具：

| 工具 | 用途 |
| --- | --- |
| `pdf_translate` | 翻译并生成中文 PDF 和 LaTeX 源码压缩包 |
| `pdf_inspect` | 查看页数、文件大小，校验页码范围 |
| `pdf_review` | 开启 AI 核验后逐页检查、预览和修订 |
| `pdf_translator_doctor` | 检查 Python、排版运行时和模型配置 |
| `pdf_cache_list` | 只读查看缓存 |
| `pdf_panel` | 显示或隐藏翻译面板 |

`pdf_translate` 主要参数：`pdf`、`pages`、`workers`（1–8，默认 4）、`imageQuality`、`thinking`、`renderOnly`、`outputDir`、`background`。默认后台执行，也可以通过 `background: false` 等待结果。

### 输出结构

每次翻译在所选输出目录下新建一个以文档名和时间命名的子文件夹，里面只有两个文件：

```text
输出目录\论文名_20261024-120019_ab12cd\
├── 论文名_0cb8b7_zh.pdf          中文 PDF
└── 论文名_0cb8b7_zh-latex.zip    LaTeX 源码压缩包
```

zip 内是可直接用 XeLaTeX 或 Tectonic 编译的完整工程（`main.tex`、`layout.tex`、`images/`、`README.txt` 等），不包含编译日志和中间文件。译文、结构数据和核查报告保存在插件数据目录的 `work` 下，不会出现在输出目录。

`main.tex` 的字体是条件选择的：本机有宋体 / Times New Roman 时保持原样，缺少时（如 Overleaf）自动改用 Fandol 和 TeX Gyre Termes。因此整个 zip 可以直接上传 Overleaf，编译器选 XeLaTeX 即可，不需要改字体；记得连同 `images/` 一起上传。

翻译前先分析全文结构：结合书签、目录、原文区域和跨页证据建立章节树，页面级书签无需纵坐标也能参与匹配。扫描件默认使用视觉模型读取目录和结构样本；配置 structure_python 后可加入本地 OCR 证据。部分页翻译仍保留原书的章／节关系，支持罗马数字章号、§ 节号和十进制编号。

图片裁剪以模型框为定位种子，利用原 PDF 图形路径、位图对象及图中文字核验完整边界，保护框线、箭头、坐标轴与边缘标签，并隔开图题和正文。原始识别框保持不变，实际裁剪框及证据进入任务报告和核验接口。扫描页等无法取得独立边界证据的情况会保留原框并标记待核验；此校验不调用模型或本地 OCR。

页眉、页脚和页码保留在识别缓存中，确认角色后只从排版输出中排除；正文中的同名标题不会随页眉一起被删除。定理、命题、定义等标签与章节编号分开判断。无法确认的页边文字或层级保留并标记 `needs_review`，任务报告中的 `structure_warnings` 给出页码、块和原因。

结构结果与识别结果分别缓存。结构算法升级可以重新计算而不重译，`renderOnly: true` 始终不调用模型。旧缓存可能已经省略页眉或误删正文，离线重排不能恢复缺失内容，会明确提示旧识别局限。核验时可在内容块设置 `structure_override: {"role":"heading","heading_level":2}` 固定层级，或 `{"role":"body"}` 恢复误排除内容；设置为 `null` 清除覆盖。完整替换页需保留所有块，包括 `excluded` 块。

正文、标题和代码字体分别检测并回退，数学 Unicode 符号使用数学字体。超宽公式限制到版心内，长代码自动折行，跨页代码保留换行和缩进。若编译成功但仍有缺字或严重越界，会保留 PDF 并将任务标为 `needs_review`，详情记录在任务报告的 `font_warnings` / `layout_warnings` 中；这类结果仍需检查。真正的 TeX 编译错误继续触发局部修复，不会用旧 PDF 冒充新结果。Python 调用方可用 `render_latex(..., strict_layout=True)` 要求排版警告阻止发布。

已有翻译可通过 `renderOnly: true` 使用缓存重新排版，无需再次调用翻译模型。

## 数据与更新

用户数据默认保存在：

```text
%USERPROFILE%\.dsh\dsh-pdf-translator
```

包含 `config.json`、`.venv`、`runtime`、`outputs` 和 `work`。更新或重装插件不会删除这些数据；卸载后如需彻底清理，可手动删除该目录。

可用环境变量覆盖：

| 变量 | 用途 |
| --- | --- |
| `DSH_PDF_DATA_DIR` | 数据、缓存和输出目录 |
| `DSH_PDF_CONFIG` | 模型配置文件 |
| `DSH_PDF_PYTHON` | Python 可执行文件 |
| `DSH_PDF_RUNTIME_DIR` | Pandoc / Tectonic 目录 |

翻译时选中的页面图片，以及用于结构分析的目录／章节起始页／选区边界样本，会发送到配置的模型接口，可能产生 API 费用。结构样本按页缓存，不同翻译选区可以复用；未识别到目录时先检查前 20 页。API 密钥只保存在本机配置或进程环境中。

## 开发与测试

```powershell
npm.cmd ci
npm.cmd run build
npm.cmd run check
npm.cmd test
.venv\Scripts\python.exe -m unittest discover -s work -p 'test_*.py'
npm.cmd pack
node scripts\verify-package.mjs dsh-pdf-translator-0.2.5.tgz
```

## 许可证

MIT，详见 [LICENSE](LICENSE)。

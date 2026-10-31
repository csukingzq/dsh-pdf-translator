# DeepSeek Harness AI PDF 翻译插件

用视觉 AI 把 PDF 翻译成中文，输出中文 PDF 和可编辑 LaTeX 源码压缩包。正文、公式、图表边界、图内文字与表格结构由视觉模型识别，不使用本地 OCR。

## 功能

- 逐页渲染 PDF，由视觉 AI 定位并翻译正文、图注和公式；表格只重建结构，单元格内容保持原文不翻译，避免译文撑坏列宽。
- 自动识别原 PDF 的栏结构：双栏、三栏论文重排后仍是双栏/三栏；跨栏的宽图宽表保持通栏并浮动到页顶，只占一栏的小表留在本栏，题注跟随图表。
- 缺字自动改用符号字体回退，单个字形缺失不再让整次翻译失败。
- 图形按原边界裁取，保留原始曲线和数据；图下附中文对照说明。
- 表格重建为 Markdown / HTML，支持合并单元格；单元格、表头、表注一律照抄原文，不翻译。宽表按版心缩放，窄栏表格避免逐字换行。
- 每次翻译在输出目录下新建一个子文件夹，里面只有中文 PDF 和 LaTeX 源码 zip 两个文件。
- 首次运行在 PDF 翻译面板一键准备环境、填写模型配置，不需要终端或手改 JSON。
- 支持后台任务、任务取消、断点续跑和缓存复用。
- 可选 AI 核验：逐页检查译文，最多两轮修订与重新编译。
- 缓存由用户手动清理，不自动删除。

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

翻译时选中的页面图片会发送到配置的模型接口，可能产生 API 费用。API 密钥只保存在本机配置或进程环境中。

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

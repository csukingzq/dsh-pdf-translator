# DeepSeek Harness PDF 翻译插件

**当前正式版：1.0.0。** 将英文等原文 PDF 翻译为中文，**保留原版式**（公式、图表、目录、双栏排版原位替换），交付单语译文 PDF（mono）和双语对照 PDF（dual）。

内核使用 [pdf2zh-next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next) / [BabelDOC](https://github.com/funstory-ai/BabelDOC)，实现方式参考 [Zotero PDF2zh](https://github.com/guaguastandup/zotero-pdf2zh) 的服务端技术路径。1.0.0 起不再使用「AI 视觉逐页识别 + LaTeX 重排」，因此不再输出 LaTeX 源码包、Markdown 或可编辑结构文档；升级前请阅读 [CHANGELOG](CHANGELOG.md)。

## 当前处理流程

```text
PDF 版式解析（BabelDOC：栏、段落、公式、图、表、目录）
    ↓
自动术语抽取（可选阶段，随引擎默认开启）
    ↓
按段落批量调用模型翻译（保留公式与引用占位）
    ↓
原位排版：译文回填到原坐标
    ↓
单语 PDF（mono）+ 双语对照 PDF（dual）+ report.json
```

- **翻译所选页码**：只翻译指定页，其余页保留原文；输出仍是完整文档。
- **表格单元格文字默认不翻译**（与旧版一致）；表题、正文正常翻译。
- **扫描件**需要先有文本层（OCR），否则引擎会报「没有可翻译文本」。
- 输出目录内每次任务新建一个子文件夹：`<文件名>_<时间>_<随机>/`，内含 `<文件名>-mono.pdf`、`<文件名>-dual.pdf`、`report.json`。文件名会截断到 48 个字符，避免 Windows 路径长度限制。

## 环境要求

- Windows 10/11；
- DeepSeek Harness 0.2.1-rc.3 或更新的 0.2.x；
- Python 3.10–3.13（DSH 桌面版自带的 Python 3.12 会被自动使用）；
- 一个 OpenAI 兼容的文本翻译接口与 API 密钥（不需要图片输入）；
- 磁盘：Python 依赖约 1 GB；首次翻译还会下载 BabelDOC 模型（约 300 MB），需要联网。

## 安装

### 方式一：npm（推荐）

npm 包地址：<https://www.npmjs.com/package/dsh-pdf-translator>

桌面版：

1. 打开 DSH，点击 **插件 → 添加插件**。
2. 输入 `dsh-pdf-translator@1.0.0`，点击 **安装**，然后 **立即启用**。

CLI：

```powershell
npx.cmd @deepseek-ai/dsh plugin --profile web add dsh-pdf-translator@1.0.0
```

打开 PDF 翻译面板后会通过 DSH 插件市场检查版本。也可点 **检查更新** 手动刷新，再点 **更新插件**；面板会显示安装结果，以及是否需要刷新或重启。没有兼容的市场接口时，手动检查会查询 npm 并提供新版安装包入口。

### 方式二：GitHub Release

下载 [dsh-pdf-translator.tgz](https://github.com/csukingzq/dsh-pdf-translator/releases/latest/download/dsh-pdf-translator.tgz)，在 **插件 → 添加插件** 中选择该文件。

### 首次运行：面板一键完成

安装并启用插件，重启 Harness 后打开左下角或标题栏的 **PDF 翻译** 面板：

1. 首次会显示「首次使用需要准备运行环境」，点 **一键准备环境**。插件会创建 Python 环境并安装 `pdf2zh-next`（约 1 GB，需要联网），面板显示进度，可取消或重试。默认优先走国内镜像（pip 用清华 / 阿里源），失败会自动回退官方 PyPI。
2. 就绪后点 **填写模型配置**，填写接口地址、模型名称和 API 密钥并保存。密钥保存在本机 `config.json`，不随译文导出。
3. 直接 **选择 PDF** 开始翻译，不需要重启。

已配置过的用户不会看到向导；之后可随时用面板里的 **模型配置** 修改。

### 手动安装环境（离线/网络受限时）

```powershell
# 直接调用脚本（推荐，不依赖 powershell 在 PATH 中）
& "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-pdf-translator\scripts\setup.ps1"

# 或使用完整路径的 powershell.exe
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-pdf-translator\scripts\setup.ps1"
```

Web / CLI profile 把 `desktop` 换成 `web`。可选参数：

```powershell
setup.ps1 -DataDir "D:\dsh-pdf" -OfficialOnly -PipIndexUrls "https://pypi.tuna.tsinghua.edu.cn/simple"
```

脚本成功后会在 `runtime\pdf2zh.json` 写入就绪标记（含引擎版本），面板据此判断环境是否可用。

如需复用已有的 pdf2zh-next 环境（例如另一套工具已经装好），把 `DSH_PDF_PYTHON` 指向该环境的 `python.exe` 即可，无需重复安装；面板会探测该解释器里的 `pdf2zh-next` 版本。然后编辑模型配置：

```text
%USERPROFILE%\.dsh\dsh-pdf-translator\config.json
```

```json
{
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "api_key": "REPLACE_WITH_YOUR_KEY"
}
```

`base_url` 必须是 OpenAI 兼容端点；可选字段 `lang_in`（默认 `en`）、`lang_out`（默认 `zh-CN`）、`qps`（默认 4）。手动改完后无需重启，直接翻译即可。也可以在聊天中发送「调用 pdf_translator_doctor 检查 PDF 翻译插件环境」。

## 使用与核验

打开 **PDF 翻译** 面板，选择文件、输出目录和页码（`all`、`1-5`、`1,3,5-8`），开始后台任务。支持取消（同时结束引擎及其子进程）和断点式缓存（引擎会复用已完成的段落翻译）。

| 工具 | 用途 |
| --- | --- |
| `pdf_translate` | 翻译 PDF，输出 mono + dual + report |
| `pdf_inspect` | 检查文件、页数与页码范围 |
| `pdf_translator_doctor` | 检查 Python、pdf2zh-next 引擎与模型配置 |
| `pdf_cache_list` | 查看翻译缓存 |
| `pdf_panel` | 显示或隐藏面板 |

`pdf_translate` 常用参数：`pdf`、`pages`、`workers`（并发请求 1–8，默认 4）、`outputDir`、`background`。

1.0.0 移除了 `AI 核验`、`pdf_review`、`renderOnly`、`imageQuality`、`thinking` 与 LaTeX 源码包。翻译质量由 BabelDOC 的原位排版决定；如需逐页核对，请直接打开输出的 PDF。

### 输出与缓存

- 输出目录内每次任务一个子目录，包含 mono、dual 两个 PDF 和 `report.json`（含页范围、模型、token 用量、耗时）。
- 引擎翻译缓存由所有文档共享（默认位于 `%USERPROFILE%\.cache\babeldoc`）。面板「清理缓存」可整体清理该缓存；已导出的 PDF 不会被删除。
- 翻译缓存命中不会再次调用模型；清理缓存后重新翻译会重新计费。

### 数学公式字体（MathType）与行内公式乱码

部分期刊 PDF 的公式用 MathType/Advance 的 Type1 字体排版，字体缺少正确的 `ToUnicode` 映射，文本层会变成 `¼`、`ð`、`r`、`ﬃ` 之类的错位字符。插件会自动检测 `AdvMacMth*`、`AdvP4C4E*`、`AdvEls-*`、`AdvPi*` 等字体，并把它们加入引擎的公式字体模式（`formular_font_pattern`），让这些字形保留原样、不再作为正文送给模型，从而避免译文里出现 `ffff`/`ffi` 乱码。

- 检测与保护结果写入每次任务的 `report.json` 的 `diagnostics` 字段（`mathFonts`、`formulaProtected`）。
- 自动检测不生效时，可以在 `config.json` 手动覆盖：`"formular_font_pattern": "(...)"`（会替换引擎默认模式，需自行包含默认项）；或加 `"formular_char_pattern": "..."` 按字符补充。
- 如果某页仍无法正确翻译，可以用 `pages` 排除该页（例如 `1-17,19`），输出会保留该页原文。公式内容本身不做翻译或 LaTeX 重建。

## 数据、费用与限制

用户数据默认位于 `%USERPROFILE%\.dsh\dsh-pdf-translator`，包括本地模型配置、运行环境、任务状态和运行记录。更新插件不会删除这些数据。可用 `DSH_PDF_DATA_DIR`、`DSH_PDF_CONFIG`、`DSH_PDF_PYTHON`、`DSH_PDF_RUNTIME_DIR` 覆盖对应路径。

待翻译原文会发送到用户配置的模型接口，可能产生 API 费用；密钥只保存在本地配置中。已知限制：复杂公式与特殊字体的回填效果由 BabelDOC 决定；表格单元格默认保持原文；扫描件需要文本层；双栏与跨栏图表的位置在个别文档上仍可能偏移。

## 开发与测试

```powershell
npm.cmd ci
npm.cmd run build
npm.cmd run check
npm.cmd test
.venv\Scripts\python.exe -m unittest discover -s work -p 'test_*.py'
npm.cmd pack
node scripts\verify-package.mjs dsh-pdf-translator-1.0.0.tgz
```

Python 单元测试只依赖标准库；`requirements.txt` 只装桥接层（PyMuPDF、pypdf），`requirements-engine.txt` 才是 pdf2zh-next。真实翻译验证可临时把 `DSH_PDF_PYTHON` 指向已装好 pdf2zh-next 的解释器。

只提交源码、合成 PDF 与最小测试样本；完整原书、私人会话和任务缓存不纳入仓库或安装包。

## 许可证

本插件为 MIT（详见 [LICENSE](LICENSE)）。第三方组件单独安装、以独立进程调用，遵循各自许可证：pdf2zh-next 与 BabelDOC 为 AGPL-3.0，PyMuPDF 为 AGPL-3.0，pypdf 为 BSD-3-Clause。安装包不内嵌这些组件。

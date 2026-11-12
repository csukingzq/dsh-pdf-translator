# DeepSeek Harness PDF 翻译插件

**当前正式版：0.8.0。** 将英文等原文 PDF 翻译为中文，使用 LaTeX 重排，交付 PDF 和可编辑源码包。默认保留原文栏数：双栏论文继续使用双栏正文，原文跨栏大图可以跨栏；不承诺保留原分页和文字坐标。

## 当前处理流程

```text
全文结构索引（书签、目录、章节与来源页码）
    ↓
逐页提取原文、区域和候选角色
    ↓
全文结构裁决：标题、页眉页脚、脚注与续接关系
    ↓
按语义单元批次翻译，附带章节、邻近原文和关联脚注上下文
    ↓
结构化译稿 → LaTeX 重排 → PDF + 可编辑源码 ZIP
```

**页面用于提取和定位，不再逐页生成整页译稿。** 翻译每批最多 8 个单元，目标原文预算约 2,000 tokens（包含脚注）；有证据的跨页段落可以进入同一批次。章节与术语上下文在并发请求前固定，公式和引用以占位符保护。模型返回的 ID、保护对象和空内容会被检查；失败最多重试两次，保留同批已成功单元，未成功内容保留原文并标记核验。

### 标题、页眉与脚注

- 根据书签、目录、编号与正文区域共同确定章节层级；定理、定义、命题标签与章节标题分开判断。部分页翻译仍使用全文结构索引。
- 识别到印刷目录后，按目录层级编排正文标题。目录采用译文标题，点击条目可跳到正文；页码取自译本最终分页。章从新页开始，小节连续排版。选区外或无法匹配的条目保留原题，页码显示「—」，并写入核验诊断。
- 确认的重复页眉从正文移除。文章输出页眉采用原文作者／期刊文字，不替换为章节标题；没有原文页眉证据时不额外生成。输出页码随重排生成，原印刷页码保留为来源信息。
- 脚注具有稳定 ID 和正文锚点，支持数字、上标、`* / † / ‡`、同页编号重置、多次引用及有明确证据的跨页续接。找不到引用的脚注不会被丢弃或悄悄变成普通正文，而是显示为未关联注释并进入核验。
- 首页作者行中间的通讯作者星号可关联到页脚，保留原符号；作者单位 `a/b/c` 逐条显示。无引用标记的版权、ISSN、DOI 作为无编号页脚出版信息，不虚构正文锚点。

### 图片与表格

- 图内文字、图例、坐标轴和面板标记保持原图原文，**不翻译，也不额外生成中文对照说明**。图题独立翻译并与图绑定。
- 模型框只是定位种子。优先匹配完整原生图片对象；混合矢量图结合路径、位图、文字标签和正文边界计算完整区域，避免相邻栏正文干扰。
- 已确认截断、正文重叠或标签边界冲突时，停止使用危险旧框并报告原文页码、图块 ID 和诊断文件。扫描件缺少独立图形证据时仍需人工核验，不能把“没有报错”当成裁剪已验证。
- 单栏图按栏宽、跨栏图按页宽等比排版。默认宽度上限为可用宽度，高度上限为正文高度的 55%；显式自定义尺寸继续生效。浮动页不再把大量空白均分到图间。
- 表格重建为 Markdown / HTML / LaTeX，支持合并单元格。**单元格、表头、表注保持原文，不翻译**；表题单独翻译。独立表号和说明可绑定到表体。

### 可编辑公式与排版

- 正文公式使用可编辑 LaTeX，编号在公式右侧；多行公式的编号垂直居中，不另占一行。
- 长等式、加法根式按安全边界分行；长行内公式可独立成行，标点随公式排版。不可分的宽矩阵仍可能缩放，需检查字号可读性。
- 不确定内容或公式编译修复失败时保留缓存并定位问题，**不再用截图替代公式交付**。
- 缺字和越界记录到任务报告。编译成功不代表翻译、公式识别或结构核验已经通过。

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
2. 输入 `dsh-pdf-translator@0.8.0`，点击 **安装**，然后 **立即启用**。

CLI：

```powershell
npx.cmd @deepseek-ai/dsh plugin --profile web add dsh-pdf-translator@0.8.0
```

打开 PDF 翻译面板后会通过 DSH 插件市场检查版本。也可点 **检查更新** 手动刷新，再点 **更新插件**；面板会显示安装结果，以及是否需要刷新或重启。没有兼容的市场接口时，手动检查会查询 npm 并提供新版安装包入口。

### 方式二：GitHub Release

下载 [dsh-pdf-translator.tgz](https://github.com/csukingzq/dsh-pdf-translator/releases/latest/download/dsh-pdf-translator.tgz)，在 **插件 → 添加插件** 中选择该文件。

### 首次运行：面板一键完成

安装并启用插件，重启 Harness 后打开左下角或标题栏的 **PDF 翻译** 面板：

1. 首次会显示「首次使用需要准备运行环境」，点 **一键准备环境**。插件会自动创建 Python 环境、安装依赖并下载 Pandoc / Tectonic（约 300 MB，需要联网），面板显示进度，可取消或重试。默认优先走国内镜像（`ghproxy.net` / `gh-proxy.com` / `ghfast.top`，pip 用清华 / 阿里源），失败会自动回退官方 GitHub / PyPI。
2. 就绪后点 **填写模型配置**，填写接口地址、模型名称和 API 密钥并保存。密钥保存在本机 `config.json`，不随译文或源码包导出；模型请求使用该密钥向配置的接口认证。
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

## 使用与核验

打开 **PDF 翻译** 面板，选择文件、输出目录和页码（`all`、`1-5`、`1,3,5-8`），开始后台任务。支持取消、断点续跑和缓存复用，也可以在聊天中调用工具。

| 工具 | 用途 |
| --- | --- |
| `pdf_translate` | 翻译或使用缓存重新排版 |
| `pdf_inspect` | 检查文件、页数与页码范围 |
| `pdf_review` | 检查、预览、修订和结束核验 |
| `pdf_translator_doctor` | 检查 Python、LaTeX 运行时与模型配置 |
| `pdf_cache_list` | 查看缓存 |
| `pdf_panel` | 显示或隐藏面板 |

`pdf_translate` 常用参数：`pdf`、`pages`、`workers`（1–8，默认 4）、`imageQuality`、`thinking`、`renderOnly`、`outputDir`、`background`。

AI 核验可选，最多两轮修订。关闭核验时不会自动做人工式内容检查。开启后：

- `inspect` 默认返回当前版本下一未读原文页，显式 `page` 可重读；读完返回完成状态，不循环到第一页。
- `preview` 查看原文或输出；`diagnostics` 按页、原因和游标分页读取警告。
- `apply.blockEdits` 按稳定块 ID 修改文字、`structure_override` 或 `note_override: {anchors: [正文块ID]}`；也可完整替换页面，两种接口互斥。修订要求匹配文档版本。
- `recomputeStructure: true` 用已有证据离线重算全任务；一次事务重新编译并替换成果，保留备份。人工覆盖不会被结构重算静默清除。
- `finish` 由程序计算读取和预览覆盖情况。未读完或存在未解决问题时保持 `needs_review`，不能因 `issues=[]` 或编译成功宣称完整核验通过。

### 输出与编辑

每次任务创建独立输出子目录，包含中文 PDF 和 `*-latex.zip`。源码 ZIP 包含 `main.tex`、`layout.tex`、图片资源及 `translation-project.json` 等结构数据，可用 XeLaTeX 或 Tectonic 编译；上传 Overleaf 时选 XeLaTeX，并保留图片目录。

可直接编辑 `.tex`；手工修改不会自动回写结构化译稿，重新导出创建新目录，不覆盖外部手工源码。原文、稳定块 ID、来源区域、脚注关系及诊断保存在结构化项目和插件工作目录中。

### 缓存与升级

提取、结构、段落翻译和排版结果分开缓存。修改结构或排版可复用已有译文；`renderOnly: true` 不调用模型，也不会偷偷补做翻译。仅有原文提取、缺少译文或旧缓存缺失内容时会明确报告，离线重排不能恢复从未识别到的文字。

0.7.0 增加目录重排。升级后可用旧任务缓存重新排版来应用脚注、页眉、图片与公式排版修复；如旧任务保留了明确的人工尺寸或关联覆盖，它们仍然优先。缓存由用户手动清理，不自动删除。

### 可选本地解析

默认视觉提取可独立运行。需要额外解析证据时，运行 `scripts/setup-structure.ps1`，独立安装 BabelDOC 0.6.4、bitstring 4.3.1、PaddleOCR 3.3.1 和 PaddlePaddle CPU 3.2.0，并把工作进程路径写入配置的 `structure_python`。首次使用可能下载模型，普通插件安装**不会自动启用**这些引擎。

BabelDOC 适配层在段落／公式解析后停止，不使用其翻译或原位 PDF 输出；OCR 提供原文、坐标和置信度，不直接决定删除内容。使用默认短数据路径，避免 Windows 路径长度问题；不需要修改系统权限。

参考：[BabelDOC](https://github.com/funstory-ai/BabelDOC/tree/v0.6.4)、[Zotero PDF2zh](https://github.com/guaguastandup/zotero-pdf2zh)。第三方引擎单独安装，遵循各自许可证，安装包不内嵌模型或原书。

## 数据、费用与限制

用户数据默认位于 `%USERPROFILE%\.dsh\dsh-pdf-translator`，包括本地模型配置、运行环境和工作缓存。更新插件不会删除这些数据。可用 `DSH_PDF_DATA_DIR`、`DSH_PDF_CONFIG`、`DSH_PDF_PYTHON`、`DSH_PDF_RUNTIME_DIR` 覆盖对应路径。

页面图片、必要的目录／章节样本及待翻译原文会发送到用户配置的模型接口，可能产生 API 费用；密钥保存在本地配置中。全文结构分析可能读取选区外的必要样本，部分页翻译不等于只分析这些页。

已知限制：扫描图的边界证据、复杂公式识别、宽矩阵字号、变动页眉及目录冲突仍需核验；当前文章页眉使用已确认原文页眉中的主要重复文本。图片正常浮动可能与正文引用隔页。原文区域与重排后的页码不是一一对应关系。详细验证记录见 [VERIFICATION.md](VERIFICATION.md)。

## 开发与测试

先准备 Python / Pandoc / Tectonic 运行时，再执行：

```powershell
npm.cmd ci
npm.cmd run build
npm.cmd run check
npm.cmd test
.venv\Scripts\python.exe -m unittest discover -s work -p 'test_*.py'
npm.cmd pack
node scripts\verify-package.mjs dsh-pdf-translator-0.8.0.tgz
```

只提交源码、合成 PDF 与最小测试样本；完整原书、私人会话和任务缓存不纳入仓库或安装包。

## 许可证

MIT，详见 [LICENSE](LICENSE)。

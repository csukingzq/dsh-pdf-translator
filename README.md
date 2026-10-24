# DeepSeek Harness AI PDF 翻译插件

用视觉 AI 把 PDF 翻译成中文，输出中文 PDF、可编辑 LaTeX、Markdown 和核查报告。正文、公式、图表边界、图内文字与表格结构由视觉模型识别，不使用本地 OCR。

## 功能

- 逐页渲染 PDF，由视觉 AI 定位并翻译正文、图注、表格和公式。
- 图形按原边界裁取，保留原始曲线和数据；图下附中文对照说明。
- 表格重建为 Markdown / HTML，支持合并单元格。
- 输出中文 PDF、LaTeX 工程、Markdown、图片和核查报告。
- 支持后台任务、任务取消、断点续跑和缓存复用。
- 可选 AI 核验：逐页检查译文，最多两轮修订与重新编译。
- 缓存由用户手动清理，不自动删除。

## 环境要求

- Windows 10/11；
- DeepSeek Harness 0.2.1-rc.3 或更新的 0.2.x；
- Python 3.10+（DSH 桌面版自带的 Python 会被自动使用）；
- 支持图片输入的 OpenAI 兼容 API 和 API 密钥；
- 宋体（SimSun）和微软雅黑（Microsoft YaHei）字体。

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

### 首次运行环境

安装插件后，打开 PowerShell 执行对应 profile 的环境安装脚本：

```powershell
# 桌面版
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-pdf-translator\scripts\setup.ps1"

# Web / CLI
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\profiles\web\node_modules\dsh-pdf-translator\scripts\setup.ps1"
```

然后编辑模型配置：

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

最后新建聊天，发送「调用 pdf_translator_doctor 检查 PDF 翻译插件环境」。

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
| `pdf_translate` | 翻译并生成 PDF、LaTeX、Markdown、报告 |
| `pdf_inspect` | 查看页数、文件大小，校验页码范围 |
| `pdf_review` | 开启 AI 核验后逐页检查、预览和修订 |
| `pdf_translator_doctor` | 检查 Python、排版运行时和模型配置 |
| `pdf_cache_list` | 只读查看缓存 |
| `pdf_panel` | 显示或隐藏翻译面板 |

`pdf_translate` 主要参数：`pdf`、`pages`、`workers`（1–8，默认 4）、`imageQuality`、`thinking`、`renderOnly`、`outputDir`、`background`。默认后台执行，也可以通过 `background: false` 等待结果。

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

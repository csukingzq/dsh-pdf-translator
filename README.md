# DeepSeek Harness PDF 翻译插件

**1.1.0：双翻译引擎。** 保留原 OCR 识图与 LaTeX 重排功能，新增默认推荐的 Zotero PDF2zh 路线（实际运行 pdf2zh-next / BabelDOC）。支持后台任务、页码选择、取消、缓存、插件更新和独立模型配置。

| 引擎 | 适用文档与处理方式 | 输出 | AI 核验 |
| --- | --- | --- | --- |
| **Zotero PDF2zh（推荐）** | 有文本层的论文，保留公式、图表和原版式；使用文本模型 | 单语 mono PDF、双语 dual PDF、报告 | 不提供 |
| **OCR 识图** | 扫描件或需要重新排版的文档；视觉模型识别后翻译正文、LaTeX 重排 | PDF、LaTeX 源码包、Markdown、结构文档、报告 | 可选，逐页核验，最多修复两轮 |

本项目是独立的 DSH 插件。感谢 [Zotero PDF2zh](https://github.com/guaguastandup/zotero-pdf2zh)、[PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next) 和 [BabelDOC](https://github.com/funstory-ai/BabelDOC)。此版本不是上述作者的官方发行版。

## 安装和首次使用

需要 Windows 10/11、DSH 0.2.1-rc.3 或更新的 0.2.x、Python 3.10–3.13（可使用 DSH 自带 Python）。

1. 在 DSH **插件 → 添加插件** 中安装 `dsh-pdf-translator@1.1.0`；也可下载 [GitHub Release 安装包](https://github.com/csukingzq/dsh-pdf-translator/releases/latest/download/dsh-pdf-translator.tgz)。
2. 启用插件并打开 **PDF 翻译** 面板，选择引擎。默认推荐 Zotero PDF2zh。
3. 点 **一键准备环境**，只安装所选引擎需要的组件。Python 依赖优先使用清华、阿里镜像，失败回退官方 PyPI。Pandoc/Tectonic 无可验证的国内镜像时使用官方发行文件。
4. 在 **模型配置** 中填写 OpenAI 兼容接口、模型和密钥。OCR 必须使用支持图片输入的视觉模型；推荐引擎可使用 DeepSeek 等文本模型。两套配置分别保存。
5. 选择 PDF、输出目录和页码，开始后台翻译。OCR 模式可勾选 **翻译后 AI 核验**；高级选项保留识图质量、模型思考模式和仅缓存重排。

推荐引擎首次安装约需 1 GB，首次翻译还需下载约 300 MB 的模型；OCR 首次 LaTeX 编译会下载字体及排版资源。准备环境可取消或重试。面板的 **检查更新** 保留原有 DSH 插件市场更新功能。

CLI 安装示例：

```powershell
npx.cmd @deepseek-ai/dsh plugin --profile web add dsh-pdf-translator@1.1.0
```

## 页码、结果和缓存

- 页码支持留空、`all`、`2-4`、`1,3,5-8`，使用 PDF 的物理页序号。
- 推荐引擎选 `2-4` 时，mono 和左右对照 dual **各只保留所选的 3 页**。保留页面内原印刷页码。
- OCR 仅处理所选原文页；LaTeX 重排后的输出页数可能变化，不承诺原页数。
- 每次任务在输出目录中新建一个子文件夹。推荐引擎包含 mono、dual、report.json；OCR 保留旧版可编辑源码和诊断成果。
- 推荐引擎使用 BabelDOC 共享翻译缓存；OCR 保留 `work/document-cache` 逐文档缓存和离线重排。面板区分两者，清理须用户确认，原 PDF 和导出成果保留。
- OCR AI 核验由当前 DSH 会话执行，通过 `pdf_review` 检查覆盖率、预览并修复，最多两轮。未完成或存在遗留问题会如实报告。推荐引擎在界面和后端均禁止该核验流程。

## 升级与配置

从 0.8.0 升级保留原来的识图、数学公式重建、文档结构、目录与章节重排、图表保留、源码包、缓存、核验恢复和更新面板。首次升级默认选择推荐引擎，可切回 OCR。

数据默认保存在 `%USERPROFILE%\.dsh\dsh-pdf-translator`；旧配置位于安装目录时继续兼容。旧版顶层 `base_url`、`model`、`api_key` 作为兼容配置，不会被保存新引擎配置覆盖。新配置分别写入 `engines.pdf2zh` 与 `engines.ocr`；旧的额外配置字段保留。

密钥只保存在本地配置中，用于向用户指定的模型服务发送请求，不随译文导出。翻译会发送文字或页面图片并可能产生 API 费用；AI 核验也会使用当前会话模型。缓存命中可减少重复请求。

可用 `DSH_PDF_DATA_DIR`、`DSH_PDF_CONFIG`、`DSH_PDF_PYTHON`、`DSH_PDF_RUNTIME_DIR` 自定义目录和运行时。`DSH_PDF_API_KEY`、`DSH_PDF_BASE_URL`、`DSH_PDF_MODEL` 是两种引擎共用的环境覆盖；需要不同模型时优先在面板分别配置，避免设置这些全局覆盖。

手动安装脚本：`scripts/setup.ps1` 安装推荐引擎，`scripts/setup-ocr.ps1` 安装 OCR 运行时。均支持 `-DataDir`、`-Python`、`-OfficialOnly`。旧版可选本地结构分析器由 `scripts/setup-structure.ps1` 单独安装。

## 聊天工具

| 工具 | 用途 |
| --- | --- |
| `pdf_translate` | `engine=pdf2zh/ocr`；省略使用面板选择；支持页码、并发、输出目录、后台任务 |
| `pdf_review` | 仅开启 AI 核验的 OCR 任务：inspect、diagnostics、preview、apply、finish |
| `pdf_inspect` | 本地检查文件和页码，不调用模型 |
| `pdf_translator_doctor` | 按 `engine` 检查依赖和配置，不返回密钥 |
| `pdf_cache_list` | 查看两种缓存，不能直接清理 |
| `pdf_panel` | 打开面板或定位缓存/输出目录操作 |

仅 OCR 接受 `aiReview`、`imageQuality`、`thinking`、`renderOnly`；推荐引擎拒绝启用这些选项，防止误用。`renderOnly` 需要已有相应页面的 OCR 缓存。

## 公式修复与限制

推荐引擎包含本地 1.0.1–1.0.3 的修复：Advance/MathType 字体保护、独立变量保护、正文误识别纠正、算法和定理分行、水平线及单像素遮罩分数线规范化、CMR 算子保护、损坏译文缓存重试。只修改临时输入副本，诊断数量记录在 report.json。

公式排版仍不是所有论文都可靠：DDPM 的部分图内标签和算法底部横线仍有位置问题，不能视为整篇核验通过。表格单元格在推荐引擎中默认保留原文；无文本层扫描件应选择 OCR。OCR 依赖视觉模型，可能识别错误；重排布局与原文不同。详见 [验证记录](VERIFICATION.md)。

## 开发与验证

```powershell
npm ci
python -m pip install -r requirements.txt
./scripts/setup-ocr.ps1 -DataDir "$PWD/tmp/ocr-test"
$env:DSH_PDF_RUNTIME_DIR="$PWD/tmp/ocr-test/runtime"
npm run build
npm run check
npm test
python -m unittest discover -s work -p 'test_*.py'
python -m unittest discover -s work/ocr -p 'test_*.py'
npm pack
node scripts/verify-package.mjs dsh-pdf-translator-1.1.0.tgz
```

两套 Python 测试分别运行，避免同名模块冲突。OCR 回归包含真实 LaTeX 编译，需联网准备资源；模型调用使用固定测试响应。推荐引擎固定为 pdf2zh-next 2.10.2 / BabelDOC 0.7.1，升级依赖前需重新验证兼容补丁。安装包不包含用户密钥、论文、缓存、虚拟环境或测试输出。

## 许可证和源码

1.1.0 集成版按 [GNU AGPL-3.0](LICENSE) 发布完整源码与构建脚本；旧版 MIT 声明保留在 [LICENSE-MIT](LICENSE-MIT)，原有授权不变。第三方来源和许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。对应版本源码可从本仓库同名 Git 标签获取。

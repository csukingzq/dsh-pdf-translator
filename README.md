# DeepSeek Harness PDF 翻译插件

支持文本 PDF 和扫描件两条路线。保留后台任务、页码选择、取消、逐文档缓存和插件更新功能。

| 引擎 | 处理方式 | 输出 |
| --- | --- | --- |
| **Zotero PDF2zh（推荐）** | 文本 PDF 直接用 pdf2zh-next / BabelDOC 翻译，保留公式、图表和版式 | 单语 mono、双语 dual PDF |
| **MinerU 识别 + PDF2zh** | 本机 MinerU 识别扫描件，生成带文字的 PDF，然后自动交给同一翻译引擎 | MinerU 识别版、mono、dual PDF |

1.2.0 起用 MinerU 替换视觉大模型 OCR 和 LaTeX 重排；不再生成源码包、Markdown、report.json，也不提供 AI 核验。识别版保留原文语言。

本项目是独立 DSH 插件，使用 [MinerU](https://github.com/opendatalab/MinerU)、[Zotero PDF2zh](https://github.com/guaguastandup/zotero-pdf2zh) 的集成方式、[PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next) 和 [BabelDOC](https://github.com/funstory-ai/BabelDOC)。不是上述项目的官方发行版。

## 安装与使用

需要 Windows 10/11、DSH 0.2.1-rc.3 或更新的 0.2.x。推荐 Python 3.12；PDF2zh 支持 3.10–3.13，MinerU 需要 3.11–3.14。

1. 在 DSH 插件管理中安装发布的 tgz 安装包，启用插件并打开 PDF 翻译面板。
2. 选择引擎，点击 **一键准备环境**。MinerU 路线会同时检查和准备 PDF2zh。两个 Python 环境隔离，避免依赖冲突。
3. 在 **模型配置** 填写 OpenAI 兼容的文本翻译接口、模型名和密钥。两条路线共用此配置，无需视觉模型。
4. 选择 PDF、输出目录和页码，开始翻译。

Python 依赖优先使用清华、阿里镜像，失败回退官方 PyPI。MinerU 识别模型从 ModelScope 下载；缺少模型时首次识别会下载，之后复用。安装、下载和 CPU 识别可能耗时较长，可取消后重试。面板保留检查更新功能。

MinerU 固定使用本地 Basic 档位进行 OCR、公式和表格识别，不连接远程 MinerU/VLM 服务；识别不消耗外部模型 API token。PDF2zh 翻译仍将文字发送到配置的接口并产生相应费用。

## 页码、成果与缓存

- 页码使用 PDF 的物理页序号，支持留空、all、2-4、1,3,5-8。选择 2–4 时，仅处理这三页，每份输出 PDF 也保留这三页。
- 每次运行新建一个成果子目录。MinerU 模式保存 `*-mineru.pdf`、`*-mono.pdf`、`*-dual.pdf`；直接 PDF2zh 模式只有后两份。
- MinerU 使用原版块位置生成可选中文字的 PDF，不是给扫描图片叠加隐藏 OCR 层，也不承诺像素级还原。识别错误会影响翻译，建议先试少量页面。
- 识别成功、翻译失败时保留 MinerU PDF，错误消息会给出位置；重试可复用识别缓存。
- 缓存按原始文档统一列出。MinerU 的识别缓存按文件内容、所选页码、识别版本和参数区分；PDF2zh 翻译数据库继续复用。更换页面、版本或翻译配置可能新增计算和模型请求。
- 清理仍需在面板逐文档确认；会清理对应文档的识别和翻译缓存，保留原 PDF、导出成果和共享模型。旧 OCR 缓存单独标记，可照常清理。

## 配置与升级

数据默认保存在 `%USERPROFILE%\.dsh\dsh-pdf-translator`。旧版引擎选项 ocr 自动迁移为 mineru；旧成果、配置和缓存不自动删除。旧 OCR 模块仅保留用于历史缓存维护和未完成事务恢复，不再出现在翻译工具和面板中。

模型配置统一读写 `engines.pdf2zh`，兼容旧顶层配置；原 `engines.ocr` 密钥和未知设置保留。密钥不随成果导出。

目录覆盖：DSH_PDF_DATA_DIR、DSH_PDF_CONFIG、DSH_PDF_PYTHON、DSH_PDF_RUNTIME_DIR。翻译模型覆盖：DSH_PDF_API_KEY、DSH_PDF_BASE_URL、DSH_PDF_MODEL。MinerU 环境在数据目录的 .venv-mineru 中，与 .venv 中的 PDF2zh 隔离。

手动安装可使用 scripts/setup.ps1 或 scripts/setup-mineru.ps1，均支持 -DataDir、-Python、-OfficialOnly；推荐直接使用面板。

## 聊天工具

| 工具 | 用途 |
| --- | --- |
| pdf_translate | engine=pdf2zh/mineru，省略时使用面板选择；支持页码、并发、输出目录和后台任务 |
| pdf_inspect | 本地检查文件与页码，不调用模型 |
| pdf_translator_doctor | 检查环境和配置，不返回密钥 |
| pdf_cache_list | 查看文档缓存；不能直接清理 |
| pdf_panel | 打开面板或定位缓存、输出目录操作 |

旧 aiReview、imageQuality、thinking、renderOnly 参数不再接受。成功任务按 completionPolicy 返回对应的 PDF 链接。

## 公式修复与开发验证

PDF2zh 保留 Advance/MathType/MT2 字体保护、独立变量和算子保护、共享字体隔离、分数线规范化、算法/定理分行及损坏译文缓存重试等修复。MinerU PDF 渲染时保留嵌入字体形式的数学字形，避免纯矢量行内公式在翻译中丢失。仅在独立进程内适配，不修改安装的上游代码或源 PDF。公式、图内文字、复杂表格仍可能识别或排版有误，不能视为整篇核验通过。

开发检查：npm run build、npm run check、npm test、npm run test:visual；Python 使用 `python -m unittest discover -s work -p 'test_*.py'`。历史 OCR 恢复模块的回归另在 work/ocr 下运行。打包后用 scripts/verify-package.mjs 检查 tgz。

固定依赖：pdf2zh-next 2.10.2 / BabelDOC 0.7.1、MinerU 4.2.3。升级前需重新验证识别 PDF、公式和页码。安装包不包含密钥、论文、缓存、虚拟环境或模型权重。详细记录见 [VERIFICATION.md](VERIFICATION.md)。

## 许可证

插件按 [GNU AGPL-3.0](LICENSE) 发布；旧 MIT 声明保留在 [LICENSE-MIT](LICENSE-MIT)。MinerU 是独立安装的上游依赖，适用其 [MinerU Open Source License](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md)。第三方来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

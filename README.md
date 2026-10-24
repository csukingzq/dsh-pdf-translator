# DeepSeek Harness AI PDF 翻译插件

基于原 PDF 翻译项目拆出的独立 Harness bundle。**正文、公式、图表边界、图内文字与表格结构全部交给视觉 AI 识别。** 无 MinerU、PyTorch、OCR 模型下载或本地图框修正规则。

流程：PDF 整页原图 + 同尺寸坐标参照图 → 单次 AI 定位与翻译 → 按 AI 坐标裁图 → LaTeX → 中文 PDF。

首轮同一个请求携带干净原图和等距坐标网格参照。AI 先确定所有图内元素的外边界，再一次性输出图框与译文；没有额外图框复核请求，也不使用本地边界扩张。坐标网格仅作统一参照，不识别图表，不进入输出 PDF。结构无效或接口失败时仍按重试策略处理，LaTeX 编译失败时可局部修复公式。

图形保留原始曲线和数据，AI 翻译的轴标题、图例等以中文对照说明放在图下；图题单独翻译。表格由 AI 重建成 Markdown / HTML（支持合并单元格）。不是将中文直接覆盖到原图上的重绘工具。本地保留栅格化、裁图、结构校验、排版与编译。

## 本机使用

项目目录：`D:\dsh-pdf-translator`。本机 Python、轻量依赖及 Pandoc/Tectonic 已准备好，模型配置从原项目复制到本项目的 `config.json`，密钥不进入源码包。原项目保持不变。

桌面版的 `desktop` profile 由 Electron 应用管理，不能使用 CLI 安装。请在 Harness 桌面界面操作：

1. 左侧点击 **插件**，然后点击 **添加插件**（或旁边箭头 → **安装第三方插件**）。
2. 在包名/安装地址输入框填入 `D:/dsh-pdf-translator`，只填路径，不加命令或引号。
3. 点击 **安装**，完成后点击 **立即启用**。
4. 如果界面提示需要重启，退出并重新打开 Harness。
5. 新建聊天，让 AI「调用 pdf_translator_doctor 检查 PDF 翻译插件环境」。

该目录保留了已配置好的 Python、编译器和 API 配置，因此本机优先安装目录，而不是不包含运行时和密钥的压缩包。

仅 Web/CLI profile 使用命令行：

```powershell
cd D:\dsh-pdf-translator
npm.cmd install --ignore-scripts
npx.cmd @deepseek-ai/dsh plugin --profile web add 'link:D:/dsh-pdf-translator'
```

重新加载 Harness 后，在聊天中说：

> 使用 pdf_translate，把 D:\资料\paper.pdf 的第 1–3 页翻译为中文，先用 pdf_inspect 检查页数。

本次开发不会自动修改你的 Harness profile。

## 小面板与聊天

升级到 **0.2.3** 后，重新加载／重启 Harness。页面左下角和聊天标题栏均有 **PDF 翻译** 入口。主面板宽约 **240px**，深浅主题均为完全不透明的背景，提供 **选择 PDF、选择输出目录、清理缓存** 和一行 **AI 核验** 开关；运行时显示进度。

拖动浮动入口后展开，面板会跟随入口的位置并自动限制在窗口内，展开时浮动入口隐藏。面板标题栏仍可拖动；点击 **收起** 后，入口回到展开前的位置。入口位置在当前浏览器中保存；也可聚焦入口或标题后用方向键移动。收起面板不影响后台任务。

1. 点击 **PDF 翻译**。空白聊天也可直接使用，无需先发送“你好”。没有当前会话时，插件仅在点击开始后通过 Harness Session API 创建并打开会话。
2. 点击 **选择 PDF**，在 Windows 原生文件窗口中选择文档。取消选择不会启动任务。
3. 确认框显示文件名、总页数、输出目录和 **翻译页码**。默认“全部”，留空也表示全部；支持 `1-5`、`1,3,5-8`。格式错误、倒序或超出范围时不能启动。
4. 点击 **开始翻译** 才会发起后台任务。默认并发 4 页、无损图片、自动思考。更多参数可通过聊天指定。
5. 任务和成果在 **Harness 原生任务列表** 查看；取消任务也通过原生任务操作。失败或中断后，可在聊天中请求按原参数继续，复用已完成的页缓存。

**AI 核验首次默认关闭，之后记住选择。** 每个任务保存启动时的开关值；运行中修改只影响后续任务，聊天工具省略 `aiReview` 时也使用保存值。旧配置没有该字段时按关闭处理。取消选文件或确认框不会创建会话。

- **关闭**：仍做流水线结构校验、编译及文件有效性检查。对话 AI 收集一次任务结果后简短提示“翻译完成”并附 PDF；已有警告只简短提示，不再自动列目录、读取译文/报告、预览或重新编译。这不代表内容已人工核验。仅由完成通知唤起的轮次有工具调用限制；用户后续要求、同轮其他工作及其他会话不受限制。
- **开启**：当前 Harness 对话 AI 使用 `pdf_review` 逐页读取报告和译文，按需查看原文/输出页面，最多两轮结构化修订与重新编译。面板显示“AI 核验”或“修复中”，可点击“取消核验”。没有新增问题时直接结束。
- 排版修订支持受范围限制的图宽、图高和正文字号；排版参数随正式译文与导出的 `layout.json` 一起保存，后续仅重排时继续使用。
- 修订先在暂存区编译，通过后同步发布 PDF、Markdown、LaTeX、报告和正式译文缓存。失败保留最近可用 PDF；每次修复尝试（包括编译失败）均计入两轮上限。`work/review-transactions/<id>/journal.json` 保存旧文件映射和备份；异常退出时下次加载按日志回滚未完成发布。
- 核验结束、取消或重启中断后不会再发起新的自动核验。中断不代表核验通过；成果仍可打开。核验工具校验任务所属会话、开关授权、文档版本和修复次数，不接受任意缓存路径。

**选择输出目录** 会打开 Windows 原生文件夹选择窗口，验证可写后保存为后续任务的默认目录。取消不改变设置；未设置时使用现有 `outputs` 目录。修改设置不会改变正在运行任务的输出位置。

系统窗口重复点击不会重复打开。选择窗口出错时，会出现独立的手动路径输入框；输入 PDF 后仍需确认页码并点击开始。非 Windows 环境也使用手动路径输入。

聊天也可以说「把 D:\资料\paper.pdf 的第 1–3 页翻译为中文，输出到 D:\译文」。聊天和面板共用同一任务服务；已有任务运行时不会重复启动。聊天启动任务不会强制弹出面板。

进度显示简短阶段和完成页数；编译阶段显示进行中，不显示虚构的百分比。后台任务同时出现在 Harness 原生任务列表中。模型使用原生任务工具收集结果，无需频繁轮询。

## 原生工具

| 工具 | 用途 |
| --- | --- |
| `pdf_translate` | 翻译并生成 PDF、LaTeX、Markdown、核查报告 |
| `pdf_review` | inspect / preview / apply / finish；仅允许当前会话已开启核验的任务 |
| `pdf_inspect` | 查看页数、文件大小，验证页码范围 |
| `pdf_translator_doctor` | 检查 Python、排版运行时、配置是否存在；不调用 AI、不返回密钥 |
| `pdf_cache_list` | 只读列出缓存；清理必须由用户在面板确认 |
| `pdf_panel` | 用户明确要求时显示／隐藏面板，或定位输出目录操作、打开缓存管理；不启动翻译或删除 |

`pdf_translate` 参数：`pdf`、`pages`（`all` 或 `1,3-5`）、`workers`（1–8，默认 4）、`imageQuality`（默认 `safe` 无损）、`thinking`（`auto/off/on`）、`renderOnly`、`outputDir`、`background`。`safe` 更适合细小坐标轴和数学公式。

插件默认后台执行，立即返回 `{background:true, jobId, pages, outputDir}`；设置 `background:false` 可等待最终结果。后台任务发布后，结束当前聊天工具调用不会取消翻译；用户取消任务、插件卸载或超时会终止 Python 及 Windows 编译子进程。默认超时一小时，可配置。每个插件同时运行一个文档；同一 dataDir 的命令行任务也由文件锁互斥。应用退出后不会自动续跑，保留缓存并等待用户继续。

## 缓存完全由用户控制

点击 **清理缓存** 打开独立窗口，查看每份文档的名称、占用空间和使用状态。选择文档，再点击 **确认清理**，才会删除其所有模型版本的缓存。确认两分钟内有效且只能使用一次。

没有定时清理、容量清理或完成后清理，也没有供 AI 调用的删除工具。翻译或取消尚未完成时暂不能清理；缓存路径含符号链接或目录联接时拒绝清理。原 PDF、输出成果、模型配置和运行环境均保留。

新版成果含独立图片；旧版成果若引用缓存图片，会先补齐独立 Markdown 资源，补齐失败则保留缓存。清理后重新翻译可能再次产生 API 费用。

## 独立命令行

```powershell
node scripts/doctor.mjs
node scripts/translate.mjs 'D:\资料\paper.pdf' '1,3-5'
node scripts/translate.mjs 'D:\资料\paper.pdf' '1,3-5' --render-only
```

每次导出在输出目录建立独立子目录，包含 PDF、`translated.md`、图片、`document.json`、报告，以及包含 `main.tex` 和编译日志的 LaTeX 项目。相同文件名和不同页码范围不会互相覆盖。命令行保留前台 JSON 输出；面板保存的默认目录仅用于插件调用。

`status: complete` 代表结构和编译检查通过，不代表 AI 内容已经人工核实。`needs_review` 表示有局部原图回退、脚注问题或排版警告，请查看 `.report.json`。不可辨认内容会保留原图并标记，不伪装成已完成的翻译。

## 换机器或从插件包安装

需要 Windows 10/11、Node.js 22+、Python 3.10+、支持图片输入的 OpenAI 兼容 API。运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -Python 'C:\Python312\python.exe'
```

首次 LaTeX 编译可能下载 TeX 宏包。插件默认使用 Windows 的宋体、微软雅黑。安装脚本会准备 Python 环境及编译器，不安装本地识别模型。打包文件不包含 Python、编译器和密钥。

编辑 `config.json`：`base_url`、`model`、`api_key`。也可用 `DSH_PDF_BASE_URL`、`DSH_PDF_MODEL`、`DSH_PDF_API_KEY` 环境变量覆盖。必须选择实际支持图片输入的模型；Harness 登录态与本插件 API 配置相互独立。API 接收选中页的图片，凭据只在本地配置/进程环境和 HTTPS 鉴权中使用。

Harness 插件配置项：`pythonPath`、`configPath`、`dataDir`、`outputDir`、`timeoutMs`。面板设置和任务记录保存在 `dataDir/work/plugin-state.json`；其中不保存 API 密钥。`outputDir` 是首次设置默认值，后续以面板保存值为准。用 profile patch 覆盖示例：

```yaml
- id: ai-pdf-translator
  config:
    pythonPath: D:/dsh-pdf-translator/.venv/Scripts/python.exe
    configPath: D:/dsh-pdf-translator/config.json
    dataDir: D:/dsh-pdf-translator
    timeoutMs: 3600000
```

缓存按源文件内容、提示词版本、模型、接口和图片质量隔离。`renderOnly` 不发 AI 请求；新版没有对应页缓存时，可离线复用同一文档、模型和质量的旧版缓存，并用当前排版器重新生成成果。更换模型或缺页时明确报错。

报告的 `canonical_document` 指向该页码范围的已接受结构化译文（含 `pages` 和 `repairs`）；离线重排版优先使用这个版本，并生成同步的 PDF、Markdown、LaTeX 和报告。需要手动修订时修改该文件的页面内容，保留版本与来源哈希，再使用相同页码范围重新排版；不要只修改临时 `translated.md`。报告的 `issues` 提供原文页码、块编号、原因和预览路径。

## 开发与测试

```powershell
npm.cmd run build
npm.cmd test
.venv\Scripts\python.exe -m unittest discover -s work -p 'test_*.py'
node tests/visual-panel.mjs
npm.cmd pack
```

前端已构建为 Harness 0.2.1 的 lazy-CJS 模块，随包发布，不需要用户在安装时编译。开发构建使用 esbuild；视觉测试使用本机 Chrome，可在脚本中调整浏览器路径。

测试包括真实 Cordis 工具、Harness 后台任务与严格 Remote 调用、浏览器面板选择/隐藏/确认操作、进程取消、首次 AI 图框坐标直通、表格、公式/脚注、缓存清理与独立导出、目录锁及 LaTeX 编译。`tests/fixtures/vision-sample.pdf` 是图表输入；`session-p10-equation.md` 是从用户会话提取的编译失败回归样例。详细结果见 `VERIFICATION.md`。

接口依据：[官方工具规范](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cookbook/adding-a-tool.md)、[官方插件打包规范](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/develop/basic/publish.md)。Harness 仍在快速迭代，本项目匹配本机 `@deepseek-ai/dsh-tools@0.2.1-rc.2`；桌面版本的实际加载以安装后的状态为准。

来源说明见 [NOTICE.md](NOTICE.md)。

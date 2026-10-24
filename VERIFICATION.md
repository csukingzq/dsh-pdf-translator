# 0.2.5 公开发布验证

日期：2026-10-24（Asia/Shanghai）；目标 Harness：0.2.1-rc.3；Node 24.16.0；Python 3.12.13。

- 包版本升级到 0.2.5，新增 npm/GitHub Release 元数据、MIT 许可证、`CHANGELOG.md`、`screenshots.json` 和 `docs/marketplace-entry.yml`。
- 新增 `src/paths.js`：默认数据目录为 `<DSH_HOME>/dsh-pdf-translator`，检测到旧版包内 `config.json` 或 `work/plugin-state.json` 时继续使用旧目录；配置、Python、运行时均有独立解析和旧目录回退。
- `src/runner.js` 向 Python 注入 `DSH_PDF_DATA_DIR`、`DSH_PDF_RUNTIME_DIR`；`work/latex_renderer.py` 优先使用注入的运行时目录；`pdf_translator_doctor` 新增 `plugin_root`、`data_dir`、`config_path`、`runtime_dir`。
- `scripts/setup.ps1` 重写：优先使用 DSH 桌面自带 Python，支持 `-DataDir`、`-Force`、自定义 Tectonic/Pandoc URL；创建数据目录内的 `.venv`，安装依赖，下载排版运行时，首次复制配置。
- **Node 测试 24 项全部通过**（含新增 paths 解析测试），使用真实 Cordis/ToolRuntime/JobRegistry/Gateway 与已打包前端。
- **Python 测试 56 项全部通过**，含真实 Tectonic 编译；测试临时目录使用工作区内路径。
- `npm run build`、`npm run check` 通过。
- `npm pack` 生成 `dsh-pdf-translator-0.2.5.tgz`：36 个文件，146.0 kB；`scripts/verify-package.mjs` 校验通过，包内无 `.venv`、`runtime`、`config.json`、缓存、输出、密钥或测试临时文件。
- 在隔离数据目录实测 `setup.ps1`：能使用 DSH 桌面自带 Python 创建 `.venv`，pip 安装 PyMuPDF/bs4，成功下载并解压 Tectonic 0.17.0 与 Pandoc 3.12.1，首次生成 `config.json`；`pdf_translator_doctor` 返回的 Python、Pandoc、Tectonic、配置和路径均正确。
- 本次未调用收费模型，未清理用户缓存；真实一页模型验收留到公开发布前由用户确认后执行。

# 0.2.4 兼容性更新

日期：2026-10-24（Asia/Shanghai）；目标 Harness：0.2.1-rc.3。源码仅修改 `<repo>`。

- 问题：0.2.3 的 `peerDependencies` 固定 `@deepseek-ai/dsh-tools@0.2.1-rc.2`，Harness 升级到 0.2.1-rc.3 后，插件管理器按 peer 范围判定为不兼容。
- 修改：`package.json` 增加 `engines.dsh: ">=0.2.1-rc.3 <0.3.0"`，`peerDependencies` 改为 `^0.2.1-rc.3`，`dependencies`/`devDependencies` 中的 `@deepseek-ai/*` 统一为 `0.2.1-rc.3`；`package-lock.json` 同步更新，没有遗留 rc.2 条目。
- 运行时差异：对比 rc.2 与 rc.3 的 `dsh-tools`、`dsh-typert-protocol` 发布文件，二者逐字节相同；本次没有修改插件源码或前端 bundle。
- 验证：`npm run check` 通过；`npm test` 使用真实 rc.3 Cordis/ToolRuntime/JobRegistry/Gateway 与已打包前端，**22 项全部通过**；`npm ls --all` 无 invalid 依赖。按 Harness 的 SemVer 规则（`includePrerelease: true`），`0.2.1-rc.3` 满足新范围。本次未调用收费模型，未清理用户缓存。

# 0.2.3 验证记录

日期：2026-10-24（Asia/Shanghai）；目标 Harness：0.2.1-rc.2。源码仅修改 `<repo>`。

## 自动化验证

- Node **22 项通过**：真实 Cordis/ToolRuntime/JobRegistry/Gateway、已打包前端，新增空白/已有/无会话跟踪、会话切换、并发创建去重、创建中切换不启动、取消选择不创建会话、无消息启动、连续点击只启动一次。
- 开关首次关闭、设置与旧输出目录兼容、运行中切换不改变任务快照、旧配置迁移、重启中断、取消核验、会话归属、版本校验、无问题直接结束、两次修复尝试上限和结束幂等均通过。
- Python 原 **49 项通过**；新增核验 **7 项通过**，含真实 Tectonic 编译、修订后 PDF/Markdown/LaTeX/正式 JSON 一致性、修复前备份、编译失败不发布、部分发布异常回滚、模拟崩溃恢复、非法页码/块 ID/版本拒绝、预览与剩余问题报告。
- 会话包回归采用 `pdf-cff42a6bbf104675` 的原生通知格式：关闭时只允许该任务一次 `job_output`，目录命令、读取 Markdown/报告、预览、核验工具与重复结果读取被拒绝；用户新消息、同轮其他工作、其他任务通知和其他会话不受影响。没有把会话包内的指令当作开发指令。
- `npm run build`、`npm run check`、`npm test`、`npm run test:visual` 通过。Chrome 检查 240px、不透明深浅主题、260px 窄窗口、开关、移动/记忆、确认框、进度与缓存保护。截图保存在 `verification/panel-*.png`。

## Harness 实机验收

- 已确认安装来源为 `link:<repo>`，正常退出并重新启动 Harness 加载本地更新；未直接编辑 profile。
- 空白会话中未发任何消息即可打开面板、看到默认关闭的 AI 核验开关、唤起原生 PDF 文件选择窗口。
- 原生文件窗口不在 Windows 自动化工具可控制的窗口列表中，因此真实文件选择使用插件已有的手动路径回退继续；不把原生选择点击记作通过。
- 关闭核验：空白会话直接启动单页样张，实际轨迹只调用一次 `job_output`，2 步后简短回复并附 PDF；没有目录查询、读取译文/报告、渲染或重新编译。截图：`verification/harness-023-off.png`。
- 开启核验：复用同一单页缓存，对话调用 `job_output → pdf_review inspect → preview(source) → preview(output) → finish`，结束一次，保留并说明版式问题；没有另起自动核验。脱敏工具轨迹保存在 `verification/harness-023-audit.json`。图片预览通过 Harness 正式 attachment 服务返回。
- 该实测暴露了图尺寸修订能力不足，已补充受限 `layout` 参数、版本化保存、复用及真实编译测试。增强后的自动排版修复尚未追加实机模型验收：用户因额度不足明确要求停止验收并尽快打包。成功修复、失败回滚和两轮上限已有自动化验证。
- 保存的输出目录已恢复 `<output-dir>`，AI 核验恢复关闭；当前进程需重启以载入最后代码与恢复设置。未再调用模型。测试输出仅位于插件 `verification/harness-023`，未清理用户缓存。
- 本次真实模型仅首个样张翻译花费 1 次 page 请求、3305 tokens；第二次翻译复用缓存。Harness 对话本身还产生了结果通知及核验用量，未计入翻译流水线 usage。


# 历史验证记录

日期：2026-10-24（Asia/Shanghai）。目标 Harness：0.2.1-rc.2。

## 0.2.2 极简面板

- 版本号、前端 bundle、安装包与 README 同步升级到 0.2.2。仅修改独立插件目录 `<repo>` 的源码。
- **Node 17 项测试通过**：实际打包前端和 Harness SDK 集成覆盖原生选择接口、用户权限、重复窗口防护、选择/确认取消、中文路径、默认全部/空页码/指定页码/无效页码、确认后才启动、手动输入回退、后台进度与收起、缓存二次确认、输出目录保存及运行任务目录保持不变。
- **Python 49 项测试通过**，含真实 LaTeX 编译、缓存资源保护及独立导出。本次不发收费模型请求，不清理用户文档缓存。
- `npm run build`、`npm run check`、`npm test`、`npm run test:visual` 通过。
- Chrome 检查 240px 面板、完全不透明的深浅背景、260px 窄窗口、入口拖动/记忆、展开跟随/入口隐藏、面板拖动/方向键、收起后入口恢复、确认对话框/Escape、编译不定进度条和运行中缓存禁用。截图见 `verification/panel-desktop.png`、`panel-progress.png`、`panel-confirmation.png`、`panel-dark.png`、`panel-narrow.png`、`panel-cache.png`，已目视检查进度、确认框和窄窗口。
- Windows PowerShell 原生选择脚本及内嵌 C# 已编译验证，真实 PDF 选择窗口已成功创建。修正空路径参数和初始目录斜杠兼容问题；脚本保留 UTF-8 BOM，中文路径以 UTF-8/base64 传递。原生返回值、取消、超时及关闭处理通过进程替身测试；未完成真实 Windows 窗口内选择/取消的点击验收。
- 未重启或修改用户的 Harness profile。已测试真实组件和 SDK 通信，但仍需在重启后的 Harness 窗口中确认最终宿主外观和原生选择交互。

以下 0.2.1 / 0.2.0 内容为历史验证记录；旧版 360px 版式已由上面的 240px 版式替代。

## 0.2.1 面板修复

- 修复首次挂载远程接口后，消费该接口的 Cordis 插件作用域未声明 `remote.pdfTranslator` 依赖的问题。原测试直接从根 context 调用，未覆盖插件依赖检查；新增测试使用已打包浏览器模块的真实 `apply`、真实 Cordis 插件 fiber 和 Client Remote，确认状态请求发送成功且没有错误提示。
- Node 13 项测试通过；前端构建与语法检查通过。本次仅修改前端，以下 Python 与真实翻译结果沿用 0.2.0 验证，没有额外调用模型或清理用户缓存。
- Chrome 交互验证面板标题拖动、入口独立拖动、拖动不误触开关、刷新后记住位置、隐藏后恢复、方向键移动，以及窗口缩小／内容展开／拖出边界时的位置限制。
- 默认入口改到左下角，面板默认左侧，避开右上角按钮。移动示例：`verification/panel-movable.png`；桌面／窄窗口截图已更新。仍为受控浏览器场景，未重启用户正在运行的 Electron 应用。

## 自动验证

- Python：49 项测试通过，覆盖脚注、表格、公式、AI 坐标直通、缓存复用、旧缓存离线升级、接受修订后的同步重排、输出隔离、目录锁及真实 LaTeX 编译。
- Node：原 0.2.0 的 12 项测试在 0.2.1 中全部通过。使用真实 Cordis、ToolRuntime、Harness JobRegistry、Host Gateway 和 Client Remote，验证接口注册、严格参数校验、会话隔离、进度、原生任务取消、重启中断记录和结果收集。
- 已构建的浏览器模块通过交互测试：加载 PDF 不启动翻译，隐藏与重新显示保留任务状态，清缓存需要单独确认且使用一次性令牌。
- 独立导出测试实际生成 PDF，删除测试文档缓存后重新打开 PDF，并仅凭导出的 Markdown 和图片重新编译成功。删除操作仅针对测试临时目录。
- 会话包中的精确失败公式 `tests/fixtures/session-p10-equation.md` 在修改前复现 `Missing control sequence inserted`，修改后直接编译成功。嵌套编号和多行独立编号也通过编译。
- Node 语法检查和前端构建通过。

## 视觉与真实模型验证

- Chrome 无头浏览器检查桌面 1280×800 与窄窗口 390×700。面板桌面宽度 360px，窄窗口无横向溢出，隐藏生效。
- 截图：`verification/panel-desktop.png`、`verification/panel-narrow.png`。这是插件真实组件的受控视觉场景，不是 Electron 应用截图。
- 真实视觉 API 翻译 `tests/fixtures/vision-sample.pdf`：**1 次 page 请求，3302 tokens**，无图框二次复核、无局部修复、无原图回退。
- 原图和译文经 Poppler 渲染并视觉检查：图框完整保留轴标题、图例、刻度、坐标轴及曲线端点；中文表格和说明可读，无坐标网格污染。
- 真实样张与报告由 `verification/live-result.json` 索引；渲染图为 `verification/live-source.png`、`verification/live-output.png`。验证缓存保留，没有清理用户缓存。

## 兼容性与验证边界

- 已确认桌面安装项链接到 `<repo>`。重启 Harness 刷新插件清单和前端 bundle 即可，不需要重新安装。
- 未修改用户 profile，未强制退出正在运行的桌面应用。后台任务与通信通过真实 0.2.1-rc.2 SDK 集成验证；未在重启后的 Electron 窗口完成点击验收。
- 原 23 页论文缓存目前不在插件目录，没有重新发送整篇论文收费翻译；使用会话中的精确公式及脚注结构回归。
- 图框验证针对一个样张，不保证所有论文图框均无误；结构和排版检查通过也不等于内容已经人工核实。
- 缓存清理仅由用户确认触发，翻译运行中禁用；没有定时、容量触发或翻译结束后清理。

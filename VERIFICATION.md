# 1.1.0 双引擎集成验证（2026-11-16）

- 原 0.8.0 OCR 核心恢复到 work/ocr，独立进程加载；未覆盖现有推荐引擎公式修复。
- OCR 176 项回归通过，使用实际 Pandoc 3.12.1 / Tectonic 0.17.0 编译；覆盖公式、目录章节、语义结构、图表、缓存重排、核验与失败恢复。模型响应使用测试固定数据，本次未调用真实视觉模型。
- Node 47 项、推荐引擎 Python 93 项测试通过。Node 双引擎测试验证默认选择、OCR 核验限制、配置互不覆盖、旧配置保留、缓存清理分流及两个 Python 入口。
- 浏览器验证默认推荐项、AI 核验只在 OCR 显示、切换后核验偏好保留；测试明暗主题、260px 窄屏、拖动和键盘操作。
- 经新版 TranslatorManager → Python 子进程实际运行 Batch Normalization 第 2–4 页：mono/dual 各 3 页，报告 normalizedRuleLines=47，CMR10/CMR5/CMR7 保护生效，aiReview=false。复用既有翻译缓存。
- 以下历史实译记录仍适用。DDPM 已知问题保留，未宣称所有公式或整篇论文通过核验。

# 1.0.3 本地修复验证（2026-11-16）

- Batch Normalization 第 2–4 页：转换 47 条图片横线；保护 CMR10/CMR7/CMR5，使 sigmoid 分母中的 exp 保持在公式内。截图所示分式已恢复分数线与分子、分母的位置关系。算法 2 的步骤已分行，长公式仍会折行、缩小字号。
- 输入副本转换仅产生横线附近的栅格抗锯齿差异；2 倍渲染中，所有差异均落在原图片边框外扩 1 点内，其他位置及相邻非选页逐像素一致。未覆盖或修改原文文件。
- DDPM 第 2–4 页：完成单语/左右对照输出，算法 1 步骤已分行；第 4 页算法框下边线贴近后续正文，仍需进一步版面修复，不记为完全通过。
- LoRA 第 3–5 页：完成输出并逐页检查，未发现明显分数线、矩阵符号错位；此结论不等于逐字符数学或译文语义校验。
- RoFormer 第 3–5 页：首次模型响应含 U+FFFD 损坏字符，缓存复现。新增保护成功触发 1 次重试，译文恢复为“相对位置嵌入”；复检矩阵与位置编码公式。
- 四份结果的 mono 和左右对照 dual 均为 3 页。Python 92 项回归测试通过，覆盖遮罩解码、透明像素跳过、颜色及 alpha、正文 CMR 排除、算法分行，以及损坏缓存的有界重试。

# 1.0.2 本地修复验证

- Adam（arXiv:1412.6980v9）原文第 2–4 页，经实际配置的模型重译；pdf2zh-next 2.10.2 / BabelDOC 0.7.1。
- 输出 mono 和左右对照 dual 均恰好 3 页，报告记录选择 `[2, 3, 4]`；页面内原始页码仍为 2、3、4。
- 渲染并逐页查看 3 页 mono：第 2 页算法逐行排版，第 4 页 Theorem 4.1 与 Corollary 4.2 未再把前两行公式合并为一个大块；第 3 页显示公式与正文完整。此检查不构成全文逐字符数学校验；密集公式仍有间距和换行不均。
- 进一步修复了零高度路径未随公式移动：所选 3 页转换 43 条水平实线，分式中的分数线和根号横线随公式移动。输入转换前后以 2 倍分辨率渲染逐像素一致。
- 新回归测试覆盖算法/定理行分隔、根号与上下标不产生伪行、普通段落和独立公式保持原处理、旋转页跳过、指定页/全文的输出配置，以及共享 Form/非选页不变、转换渲染一致、特殊描边跳过。Python 85 项、JavaScript 37 项通过。

# 1.0.1 本地修复验证

日期：2026-11-15。使用已安装的 pdf2zh-next 2.10.2 / BabelDOC 0.7.1 和本机配置的 DeepSeek 模型，实际重译论文第 18 页。

- 复现了字体保护后的剩余问题：普通斜体字体中的变量 `c` 没有纳入公式，根式因此被拆成多个片段；版面模型把第 (2) 段及末尾部分正文当作独立公式，导致漏译。
- 修复后报告：`protectedVariableRuns=44`、`layoutCorrectedPages=[18]`、`layoutCorrectedBoxes=2`、`mathListLayoutBoxes=7`。三个边界条件恢复分段与中文正文。
- 输入副本的字体资源分离不改变显示：对第 18 页做 144 dpi 渲染，保护前后像素一致。输出页原有数学字体的非空白字符计数无缺失；独立保护的 `c` 共 44 个。
- 单语/双语结果各保留 19 页，交付文件只替换第 18 页，其余 18 页分别与使用者提供的原译文做像素比较，一致；目录保留。第 18 页渲染核对了根号、上下标、等式与三段正文。复杂行内公式仍沿用引擎换行，个别跨行公式留白较大。
- Python 79 项、JavaScript 37 项测试通过。新增覆盖单字母变量与完整斜体词的区别、未选页资源隔离、字体状态恢复、公式/正文误判纠正、编号条件分段。字体资源集成测试需要已声明的 pypdf 依赖；缺少依赖时跳过该项，其余 Python 单测不依赖引擎。
- 此次没有全文重新翻译或核验其他页的翻译质量，也没有发布 npm/GitHub 或替换已安装的插件。

# 1.0.0 发布验证（历史记录）

日期：2026-11-14。本次是**内核替换**版本，验证以离线自动化为主；真实翻译需由使用者在本机用自备 API 密钥执行，本文不声称已完成真实内容核验。0.8.0 及更早的验证记录保存在 git 历史中，对应已移除的 AI 视觉 + LaTeX 内核。

## 已执行的验证

- `npm ci`、`npm run build`、`npm run check`、`npm test`：JavaScript 37 项全部通过。
- `python -m unittest discover -s work -p "test_*.py"`：Python 74 项全部通过，只依赖标准库，不联网、无需引擎。
  - 页码范围解析与归一化、引擎配置映射与环境变量覆盖（含 workers/qps/lang 校验与密钥不经 argv）、BabelDOC 进度事件到面板阶段的映射（百分比不回退）、错误分类与 ANSI 清理、运行目录创建与产物收集、运行记录与缓存维护、桥接协议的 inspect/doctor/translate/cacheList/cacheClear、独立引擎进程的 JSON 协议（伪引擎事件、失败清理、引擎缺失提示）。
- `npm pack` + `node scripts/verify-package.mjs`：包内必需文件齐全，未包含 `.venv`、`runtime`、`config.json`、`work/runs.json`、输出目录与临时文件。
- 静态检查：`grep` 确认源码不再引用 `pandoc`、`tectonic`、`pdf_review`、`aiReview`、`renderOnly`、`imageQuality` 或旧内核模块；旧模块与旧测试已删除。
- 本地假 OpenAI 接口驱动的端到端进度验证（真实 BabelDOC 0.7.1，不访问外网、不产生费用）：进度事件从 0% 递增到 11% → 18% → 24% → 30% → 53% → 71% → 89% → 99% → 100%，阶段在解析/术语/翻译/排版/导出之间推进，`completed/total` 随阶段更新，产物与 `report.json` 正常生成；修复了「事件被映射两次导致百分比恒为 0」的问题，并为引擎启动阶段增加心跳（面板显示已等待秒数）。
- 使用本机已有的 pdf2zh-next 2.9.0 环境（`D:\zotero-pdf2zh\server\zotero-pdf2zh-next-venv`）验证真实引擎集成：
  - `engine_host.settings_from` 能构造并通过真实 `SettingsModel.validate_settings()`（语言、页码、去水印、并发、qps、OpenAI 兼容参数经引擎 `transform` 后仍保留模型/地址/密钥），重复校验幂等；
  - 通过 JS 桥接 → `cli.py` → `engine_host.py` → 真实引擎跑通一次失败链路：无效密钥访问端点在引擎初始化阶段返回 401，桥接输出分类后的中文提示并清理运行目录与输入副本，不写运行记录，`~/.cache/babeldoc` 不被改动；
  - 这些探测未产生 API 费用，也未执行成功的真实翻译。
- Windows PowerShell 5.1 安装链路验证：
  - 用假 `pdf2zh-next` 包在临时目录完整跑通 `setup.ps1`（建 venv → 装桥接依赖 → 装引擎 → 导入校验 → 读版本 → 写无 BOM 就绪标记 → 复制 config.json）；
  - 在 `%USERPROFILE%\.dsh\dsh-pdf-translator` 真实安装 `pdf2zh-next 2.10.2` + `babeldoc 0.7.1`，`pdf_translator_doctor` 报告 `engine.ready=true`、版本 2.10.2，就绪标记为无 BOM UTF-8；
  - 在新装的 2.10.2 上重复 `settings_from` + 双重 `validate_settings`，确认 OpenAI 兼容参数转换、页码、去水印、并发、qps 与密钥保留，`do_translate_async_stream` 可用。
- 面板测试用 jsdom 覆盖：打开面板、选择 PDF、页码校验、开始翻译、进度百分比、输出目录、缓存确认（仅共享引擎缓存可清理）、手动路径回退、首次环境向导与模型配置保存。
- MathType 行内公式乱码对照实验（原始 19 页 PDF、只翻第 18 页、离线 identity 翻译器，不产生 API 费用）：
  - 源页字体：`AdvMacMthSyN`/`AdvMacMthIt`/`AdvP4C4E46`/`AdvEls-ent4`/`AdvPi1`，其中 4 个字体没有 ToUnicode 或映射错误；
  - 默认设置下发给模型的文本含 **6 组 `ffi…` 串、542 个 `f`、12 个 `þ`、4 个 `ð`**，输出页仍有 3 组 `ffi` 串；
  - 注入「BabelDOC 默认宽模式 + MathType/Advance 字体」的 `formular_font_pattern` 后，翻译输入中 **`ffi` 0 组、`þ/ð` 0 个**，输出页 `ffi` 0 组，原数学字体保留。这个离线实验只能验证噪声字符未进入模型，不能证明实际中文回填后的公式完整。
  - 当时只修复了特殊符号被送入模型这一环节。2026-11-15 的真实输出进一步确认变量拆散和正文漏译，见上方 1.0.1 验证。
- 真实翻译（由使用者在本机面板执行，配置 DeepSeek 文本模型）：两篇论文（15 页、19 页）成功产出 mono + dual + `report.json`；第 18 页乱码正是由此发现并用于上述实验。未做全文人工核验。
- `tests/visual-panel.mjs`（Playwright + 本机 Chrome）已执行通过，并重新生成 `verification/panel-*.png` 截图。

## 未执行的验证（需真实环境）

- 第 18 页真实模型单页验收已于 2026-11-15 补做，见上方 1.0.1 验证；1.0.0 发布时尚未完成。
- 19 页全文「修复后」的真实重跑与逐页人工核对未执行。
- mineru-pdf-translate / MinerU 对比实验未端到端执行：本机存在 MinerU 模型文件（`C:\Users\23893\.mineru\models\...`）但未找到可调用的 `mineru` CLI/包，云端路线需要使用者提供 MinerU token；源码与文档分析显示其产物为重新排版 PDF（非原位、无双语），因此本轮未采用。
- `tests/visual-panel.mjs` 依赖本机 Chrome，已在开发机执行；其他机器需自备浏览器。
- 未在干净 Windows 机器上跑完整安装流程；`scripts/setup.ps1` 只做了静态检查与阶段标记约定核对。

## 真实翻译的手动验证步骤

1. 在面板点「一键准备环境」，确认阶段依次推进：创建 Python 环境 → 安装 Python 依赖 → 安装翻译引擎 → 就绪，并生成 `runtime/pdf2zh.json`。
2. 填写模型配置后，用 3–5 页的小 PDF 执行 `pdf_translate`（或面板直接开始），确认：
   - 进度按「解析版式 → 提取术语 → 翻译段落 → 排版生成 PDF」推进，百分比单调；
   - 输出子目录含 mono、dual、`report.json`；
   - `report.json` 的页范围、模型、耗时与 token 用量与实际一致；
   - 取消任务后进程树结束，重新翻译可复用已完成段落的缓存。
3. 用 `pdf_translator_doctor` 确认引擎版本与配置状态，且输出中不含密钥。
4. 复用已装环境时，把 `DSH_PDF_PYTHON` 指向该环境的 `python.exe`，确认面板显示引擎就绪（无需重新安装）。

## 数据说明

完整原书、会话、私人缓存与本地验收 PDF 不提交仓库、不随 npm 包发布。仓库只保留合成测试 PDF（`tests/fixtures/vision-sample.pdf`）用于页码检查。

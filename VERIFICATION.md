# 1.0.0 发布验证

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
  - 注入「BabelDOC 默认宽模式 + MathType/Advance 字体」的 `formular_font_pattern` 后，翻译输入中 **`ffi` 0 组、`þ/ð` 0 个**，输出页 `ffi` 0 组，原数学字体（`AdvMacMthSyN`、`AdvP4C4E46` 等）保留，公式视觉正常；
  - 结论：乱码来自「MathType 字体文本层错位 → 被当正文送模型 → 译文保留 `ffi`」，公式字体保护可在不引入 MinerU、不改变版式与双语对照的前提下解决。
- 真实翻译（由使用者在本机面板执行，配置 DeepSeek 文本模型）：两篇论文（15 页、19 页）成功产出 mono + dual + `report.json`；第 18 页乱码正是由此发现并用于上述实验。未做全文人工核验。
- `tests/visual-panel.mjs`（Playwright + 本机 Chrome）已执行通过，并重新生成 `verification/panel-*.png` 截图。

## 未执行的验证（需真实环境）

- 第 18 页修复后的**真实模型单页验收**：修复代码已就绪，但仍需用使用者的 API key 对第 18 页做一次真实翻译（费用极小），确认中文正文与公式同时正常；本次签名验证只做到离线输入/输出文本与公式字体层面。
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

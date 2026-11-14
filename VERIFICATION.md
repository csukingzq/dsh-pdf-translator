# 1.0.0 发布验证

日期：2026-11-14。本次是**内核替换**版本，验证以离线自动化为主；真实翻译需由使用者在本机用自备 API 密钥执行，本文不声称已完成真实内容核验。0.8.0 及更早的验证记录保存在 git 历史中，对应已移除的 AI 视觉 + LaTeX 内核。

## 已执行的验证

- `npm ci`、`npm run build`、`npm run check`、`npm test`：JavaScript 35 项全部通过。
- `python -m unittest discover -s work -p "test_*.py"`：Python 64 项全部通过，只依赖标准库，不联网、无需引擎。
  - 页码范围解析与归一化、引擎配置映射与环境变量覆盖（含 workers/qps/lang 校验与密钥不经 argv）、BabelDOC 进度事件到面板阶段的映射（百分比不回退）、错误分类与 ANSI 清理、运行目录创建与产物收集、运行记录与缓存维护、桥接协议的 inspect/doctor/translate/cacheList/cacheClear、独立引擎进程的 JSON 协议（伪引擎事件、失败清理、引擎缺失提示）。
- `npm pack` + `node scripts/verify-package.mjs`：包内必需文件齐全，未包含 `.venv`、`runtime`、`config.json`、`work/runs.json`、输出目录与临时文件。
- 静态检查：`grep` 确认源码不再引用 `pandoc`、`tectonic`、`pdf_review`、`aiReview`、`renderOnly`、`imageQuality` 或旧内核模块；旧模块与旧测试已删除。
- 使用本机已有的 pdf2zh-next 2.9.0 环境（`D:\zotero-pdf2zh\server\zotero-pdf2zh-next-venv`）验证真实引擎集成：
  - `engine_host.settings_from` 能构造并通过真实 `SettingsModel.validate_settings()`（语言、页码、去水印、并发、qps、OpenAI 兼容参数经引擎 `transform` 后仍保留模型/地址/密钥），重复校验幂等；
  - 通过 JS 桥接 → `cli.py` → `engine_host.py` → 真实引擎跑通一次失败链路：无效密钥访问端点在引擎初始化阶段返回 401，桥接输出分类后的中文提示并清理运行目录与输入副本，不写运行记录，`~/.cache/babeldoc` 不被改动；
  - 这些探测未产生 API 费用，也未执行成功的真实翻译。
- 面板测试用 jsdom 覆盖：打开面板、选择 PDF、页码校验、开始翻译、进度百分比、输出目录、缓存确认（仅共享引擎缓存可清理）、手动路径回退、首次环境向导与模型配置保存。

## 未执行的验证（需真实环境）

- 真实 PDF 翻译：需要安装 pdf2zh-next（约 1 GB）、首次下载 BabelDOC 模型并产生 API 费用，本次未执行。
- `tests/visual-panel.mjs`（Playwright + 本机 Chrome）未执行；该脚本只做面板外观回归，不涉及翻译逻辑。
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

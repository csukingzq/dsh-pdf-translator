# Changelog

## 0.4.3 — 2026-10-25

- 标题层级优先按原文书签、章节编号和字体信息统一校正，修复逐页重置层级及将图题、程序输出、正文引用误作章节的问题。
- 正文、无衬线、等宽及中文字体分别检测回退，补充数学 Unicode 字形处理与扩展汉字回退。
- 长代码自动折行；修复 HTML 缩进实体和跨页代码围栏直接拼接导致的越界；限制超长行内公式宽度。
- 将编译失败与排版警告分开：成功编译的 PDF 可带明确的缺字/越界报告导出并标为需复核，保留可选严格模式；清理旧编译产物，防止失败时误用旧 PDF。

## 0.4.2 — 2026-10-24

- 模型配置对话框在接口地址为空时预填 `https://api.deepseek.com/v1`，避免把 placeholder 误当成已填写而无法点保存。
- 空文件或 0 字节的 `config.json` 视为未配置（不再报格式错误），可直接在面板保存，`setup.ps1` 也会重新写入示例配置。

## 0.4.1 — 2026-10-24

- 环境安装默认使用国内镜像：Tectonic / Pandoc 优先经 `ghproxy.net`、`gh-proxy.com`、`ghfast.top` 下载，pip 依赖优先用清华、阿里源；失败自动回退官方 GitHub / PyPI。可用 `-OfficialOnly` 强制官方源。
- `setup.ps1` 控制台输出改用 UTF-8，PowerShell 的中文错误信息不再乱码。
- 修复 pip 多镜像重试时把 pip 输出当成退出码、导致每个镜像都被误判为失败的问题。

## 0.4.0 — 2026-10-24

- 首次运行改为在 PDF 翻译面板内一键完成：自动创建 Python 环境、安装依赖并下载 Pandoc / Tectonic，显示阶段、可取消、可重试。
- 新增面板内「模型配置」表单，直接填写 `base_url`、`model`、`api_key`，不再需要手动编辑 `config.json`。
- 环境未就绪时 `pdf_translate` 会提示并自动打开面板；错误信息不再引导用户去终端跑脚本。
- 新增面板接口 `setupStart`、`setupCancel`、`saveConfig`；`status` 返回环境与配置状态。API 密钥只写本机配置文件，不通过状态接口回传。
- 安装完成和配置保存后无需重启即可翻译；手动 `setup.ps1` 作为离线/高级方式保留。

## 0.3.0 — 2026-10-24

- 输出目录改为每次翻译一个子文件夹，里面只有中文 PDF 和 LaTeX 源码 zip；不再写出 `translated.md`、`crops/`、`document.json`、`layout.json`、`*.report.json` 和 `previews/`。
- zip 内的工程可直接用 XeLaTeX 或 Tectonic 编译，不包含 `.aux`、`.log`、`main.pdf` 等编译中间产物。
- 译文、结构数据和报告移入插件数据目录，AI 核验的 `apply` 会同时重新打包 zip，保持 PDF 与源码一致。
- 缓存清理仍保留已导出的 PDF 和 zip。
- 生成的 `main.tex` 不再强制使用 Windows 字体：本机有宋体 / Times New Roman 时保持原样，Overleaf 等缺少这些字体的环境自动退回 Fandol / TeX Gyre Termes，整包可直接用 XeLaTeX 编译。

## 0.2.5 — 2026-10-24

首个面向公众分发的版本。

- 发布到 npm，可用 `dsh-pdf-translator` 包名安装。
- 提供 GitHub Release 预构建 `.tgz`，无需安装时构建。
- 新增 `LICENSE`（MIT）、仓库/问题链接和发布元数据。
- 默认把配置、Python 环境、Tectonic/Pandoc 和缓存保存到 `%DSH_HOME%\dsh-pdf-translator`，插件更新不再清掉用户数据；检测到旧版包内配置或状态时继续使用旧目录。
- `scripts/setup.ps1` 支持 DSH 桌面自带的 Python，自动创建虚拟环境、安装依赖并下载排版运行时。
- `pdf_translator_doctor` 返回数据目录、配置路径、运行时目录和插件路径，便于排查。
- 新增 `scripts/verify-package.mjs`、CI 和 tag 发布工作流。
- README 改为外部用户安装说明；清理验证记录中的本机路径。

## 0.2.4 — 2026-10-24

- 适配 Harness 0.2.1-rc.3：`engines.dsh`、peer 和依赖版本同步，修复插件管理器判定不兼容的问题。
- 运行代码和前端 bundle 与 0.2.3 相同。

## 0.2.3 — 2026-10-24

- 面板、AI 核验、缓存清理和 LaTeX 修订流程的稳定性更新。

## 0.2.2 — 2026-10-24

- 240px 极简面板、深浅主题不透明背景、入口拖动和记忆。

## 0.2.1 — 2026-10-24

- 修复远程接口依赖声明和面板首次挂载问题。

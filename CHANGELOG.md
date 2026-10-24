# Changelog

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

# 来源、许可证与分发范围

本项目基于用户的 `D:\mineru-pdf-translator` 当前工作副本改造：复用并调整逐页 AI 识别、结构化校验、脚注/公式修复与 LaTeX 排版逻辑。

新增 Harness bundle、原生工具注册、Python 桥接、取消和超时处理、独立模型通信与 AI 图表流程。没有复制原项目 Git 历史、用户文档、模型或 MinerU 上游代码。原项目包含未提交修改，本项目没有修改原工作副本。

图形按 AI 给出的边界裁取，图内译文作为对照说明；没有用生成式重绘替换科研曲线或原始数据。裁图、栅格化和编译仍在本地执行，识别和图表理解由配置的视觉 AI 执行。

## 许可证

- 本插件源码采用 **GNU Affero General Public License v3.0 or later（AGPL-3.0-or-later）**，全文见 [LICENSE](LICENSE)。
- PyMuPDF 采用 AGPL-3.0 或 Artifex 商业许可，由 `scripts/setup.ps1` 单独安装，不随 npm 包分发。若你的使用方式不能满足 AGPL，请自行联系 Artifex 获取商业许可。
- Pandoc 采用 GPL-2.0-or-later，Tectonic 采用 MIT，Python 采用 PSF 许可证；它们由安装脚本下载到用户本机，不进入 npm 包。
- 第三方依赖保留各自许可证。发布或再分发前，请按你的实际使用方式复核上述许可证。

## 分发说明

- npm 包不包含 Python、Tectonic、Pandoc、模型密钥、缓存、输出或用户配置。
- 插件运行环境由用户在本地运行 `scripts/setup.ps1` 准备；API 凭据只保存在用户本机配置或进程环境中。
- 官方接口依据：
  - <https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cookbook/adding-a-tool.md>
  - <https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/develop/basic/publish.md>
  - <https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/blob/main/contributing.md>

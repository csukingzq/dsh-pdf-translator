# 来源与范围

本项目基于用户的 `D:\mineru-pdf-translator` 当前工作副本改造：复用并调整逐页 AI 识别、结构化校验、脚注/公式修复与 LaTeX 排版逻辑。

新增 Harness bundle、原生工具注册、Python 桥接、取消和超时处理、独立模型通信与 AI 图表流程。没有复制原项目 Git 历史、用户文档、模型或 MinerU 上游代码。原项目包含未提交修改，本项目没有修改原工作副本。

图形按 AI 给出的边界裁取，图内译文作为对照说明；没有用生成式重绘替换科研曲线或原始数据。裁图、栅格化和编译仍在本地执行，识别和图表理解由配置的视觉 AI 执行。

第三方依赖保留各自许可证。PyMuPDF 适用 AGPL 或其商业许可证；分发前需按自己的使用方式检查相应许可。Pandoc、Tectonic、Python 的本机运行时不进入 npm 插件包。

官方接口依据：
- https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cookbook/adding-a-tool.md
- https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/develop/basic/publish.md

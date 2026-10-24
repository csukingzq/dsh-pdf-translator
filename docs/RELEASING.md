# 发布清单

## 一次性准备

- GitHub 仓库公开：`https://github.com/csukingzq/dsh-pdf-translator`；
- 仓库添加 `dsh-plugin` topic；
- npm 账号已登录，或在 GitHub 仓库 Secrets 中配置 `NPM_TOKEN`；
- 仓库创建满 24 小时后，才能向 awesome-dsh-plugin 提交条目。

## 本地校验

```powershell
npm.cmd ci
npm.cmd run build
npm.cmd run check
npm.cmd test
.venv\Scripts\python.exe -m unittest discover -s work -p 'test_*.py'
npm.cmd pack --pack-destination dist
node scripts\verify-package.mjs dist\dsh-pdf-translator-0.2.5.tgz
```

`verify-package` 必须通过；包内不能出现 `.venv`、`runtime`、`config.json`、缓存、输出、密钥或测试临时文件。

## 发版

1. 确认 `package.json` 与 `package-lock.json` 版本一致，更新 `CHANGELOG.md`。
2. 提交并打 tag：

```powershell
git add -A
git commit -m "release: v0.2.5"
git tag v0.2.5
git push origin main
git push origin v0.2.5
```

3. 推送 tag 后，GitHub Actions 的 `Release` 工作流会：
   - 校验 tag 与包版本；
   - 重新构建、测试、打包；
   - 上传 `dsh-pdf-translator.tgz`、带版本号的副本和 `SHA256SUMS.txt`；
   - 如果配置了 `NPM_TOKEN`，同时发布 npm。

4. 验证：

```powershell
npm view dsh-pdf-translator@0.2.5 version
```

并访问：

```text
https://github.com/csukingzq/dsh-pdf-translator/releases/latest/download/dsh-pdf-translator.tgz
```

## 手动发布 npm（CI 不可用时）

```powershell
npm login
npm publish --access public
```

`publishConfig.registry` 已固定为 `https://registry.npmjs.org/`。发布前确保有 `prepublishOnly` 所需的 Python 运行环境。

## 提交插件市场

1. Fork `awesome-dsh-plugin/awesome-dsh-plugin`。
2. 新建 `data/plugins/csukingzq__dsh-pdf-translator.yml`，内容复制本仓库的 `docs/marketplace-entry.yml`。
3. 只改这一个文件，提交 PR。
4. 等 CI 通过并等待维护者审核；合并后 dsh-market 的索引会自动更新。

## 发布后验收

在干净环境或另一台 Windows 机器上：

1. 从 DSH 插件对话框按包名安装；
2. 启用并重启；
3. 打开 PDF 翻译面板，确认出现「首次使用需要准备运行环境」，点「一键准备环境」，观察进度、取消与重试；
4. 安装完成后在面板填写模型配置并保存（另测一次留空密钥保持不变）；
5. 调用 `pdf_translator_doctor`，确认环境就绪且未暴露密钥；
6. 用一页 PDF 做真实翻译（需用户同意，可能产生费用）；
7. 检查输出目录：每次翻译的子文件夹中只有中文 PDF 和 LaTeX 源码 zip；解压 zip 后可独立编译。
8. 已有环境的升级场景：面板不应再出现首次使用向导。

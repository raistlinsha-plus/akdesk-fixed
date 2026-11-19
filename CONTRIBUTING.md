# 参与 AKDesk Fixed

感谢你愿意改进 AKDesk Fixed。项目优先接受能够提升个人固收研究的可信度、可用性、低门槛体验和 macOS 本地运行稳定性的贡献。

## 提交反馈

- 产品 Bug：使用 Bug 报告模板，先确认能否稳定复现；
- 数据不可用：使用数据源异常模板，并附“数据健康”页的非敏感状态；
- 功能建议：使用功能建议模板，描述实际研究任务和预期结果；
- 安全问题：请按 [SECURITY.md](./SECURITY.md) 私下报告，不要公开披露细节。

请勿在 Issue、日志或截图中提交 API Key、本机数据库、真实账户信息、未公开研究材料或其他敏感数据。

## 本地开发

后端要求 Python 3.11–3.13：

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
PYTHONPATH=backend .venv/bin/pytest backend/tests
.venv/bin/ruff check backend scripts
```

前端建议使用当前 Node.js LTS：

```bash
cd frontend
npm ci --cache .npm-cache
npm run check
```

运行本地服务：

```bash
PYTHONPATH=backend AKDESK_NO_BROWSER=1 .venv/bin/python -m app.main
```

## Pull Request 约定

1. 一个 PR 只解决一个清晰问题，说明用户场景和可信边界；
2. 行为变更应增加或更新自动化测试；
3. UI 变更请附 1440×900 截图，必要时补充 1280×800；
4. 数据适配必须明确来源、观测时间、抓取时间、缓存和降级行为；
5. 不得把演示数据伪装为真实数据，不得在缺少证据时自动生成评级、违约概率或投资结论；
6. 新增依赖时同步更新锁文件、SBOM 和第三方声明；
7. 用户可见变更应更新 README、用户手册或 CHANGELOG 中对应内容。

提交 PR 即表示你有权贡献相关内容，并同意该贡献按本项目 MIT License 发布。

## 正式发布顺序与检查

版本标签和已公开的安装包视为不可变产物，不为修正文档或获得绿色检查而移动标签、覆盖附件。运行时发生变化应发布新版本；发布后补充说明可单独提交，并链接到明确的提交。

1. 本地完成构建、测试、全量 npm 审计（包含开发依赖）、打包、脱敏和 ZIP 校验；确认所需文档、安装入口、SHA-256 与版本一致。
2. 推送发布提交和标签，只创建草稿 Release。等待 **同一提交** 的 Python 3.11、3.12、3.13 和 Node.js 22 CI 全部成功。Pages 成功、其他 PR 的 CI 成功或本地测试成功不能代替它。
3. 在仓库根目录执行只读门禁（需要已登录的 GitHub CLI）：

   ```bash
   python3 scripts/check_release_ci.py --tag v1.4.2
   ```

   将参数替换为待发布版本。此脚本读取远端标签、该提交最近的 main 推送 CI 和准确的重试任务；缺少任务、失败、取消、排队、跳过、GitHub 请求异常均返回非零。它不创建或公开 Release，也不是绕过审计的工具。
4. 若公告已由官方撤回但 npm 尚未同步，应等待重新审计并重跑该提交的 CI；不以 `continue-on-error`、仅审计生产依赖、忽略列表或强制降级来取得通过。
5. 草稿附件从 GitHub 回下载后核对 SHA-256，再公开为正式版。公开后额外验证匿名 Release 元数据、ZIP 与校验文件完整下载，以及 Pages 的版本和任务入口；只得到 HTTP 200、部分下载或已认证 API 校验不能替代匿名完整下载。
6. 记录运行链接、提交、产物哈希及网络限制。未通过的外部冷装、浏览器兼容或复访观察继续保留为待验收，不能在发布文案中混称通过。

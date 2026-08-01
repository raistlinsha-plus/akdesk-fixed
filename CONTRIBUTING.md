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

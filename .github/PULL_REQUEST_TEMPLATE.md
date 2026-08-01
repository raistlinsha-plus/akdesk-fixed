## 变更内容

请简要说明解决的问题、目标用户场景和实现范围。

## 可信边界

请说明来源、时间口径、缓存/降级行为，以及是否影响研究结论、提醒或 AI 发送范围。

## 验证

- [ ] 后端测试通过：`PYTHONPATH=backend .venv/bin/pytest backend/tests`
- [ ] 后端静态检查通过：`.venv/bin/ruff check backend scripts`
- [ ] 前端检查通过：`cd frontend && npm run check`
- [ ] 新行为已增加或更新测试
- [ ] UI 变更已附 1440×900 截图
- [ ] 用户可见变更已更新文档或 CHANGELOG
- [ ] 未提交 API Key、数据库、缓存、日志或敏感研究内容

## 截图或补充说明

如无可写“无”。

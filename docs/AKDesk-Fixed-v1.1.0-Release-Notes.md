# v1.1.0「GitHub 自助体验版」

这版先解决“打开后不知道做什么、还没试过就要安装”的问题：看一组市场变化，核验收益率曲线，带走一页有出处的固收简报。

[无需安装在线体验](https://raistlinsha-plus.github.io/akdesk-fixed/) · [60秒界面导览](https://raistlinsha-plus.github.io/akdesk-fixed/akdesk-demo-60s.mp4) · [用户手册](https://github.com/raistlinsha-plus/akdesk-fixed/blob/main/docs/AKDesk-Fixed-v1.1.0-用户手册.md)

## 有什么变化

- 在线三步示例：变化筛选 → 曲线核验 → 一页简报；固定合成数据，不用登录或API Key，不请求行情和AI。
- 本地每日复盘新增一页摘要，仍可切换完整复盘；来源、观测时间、抓取时间和样例/混合/未知标识随Markdown与打印保留。
- 启动前环境预检、分类恢复提示、帮助入口和主动预览的脱敏诊断；不自动上传私人信息。
- 新增独立可运行的AKShare简报案例、中英文项目入口、更新手册、测试清单和发布证据。
- 修复缺失数据方向误判、临时备注切换丢失、停止器等待无界、旧日期测试与依赖安全问题。原有研究、信用、全球数据和可选BYOK AI均保留；schema仍为1600。

## 如何安装

支持macOS 12+与Python 3.11–3.13，主要适配Apple Silicon MacBook Air。

1. 下载本页 `AKDesk-Fixed-v1.1.0.zip`，使用同页 `SHA256SUMS` 核对SHA-256。
2. 完整解压，双击 `start-macos.command`。首次安装需要网络；日常运行无需Node.js、Docker或Rust。
3. 停止时在原终端按Control+C，或运行 `stop-macos.command`。关闭浏览器不会停止服务。

GitHub自动生成的Source code包不等于经过清单、执行权限和预构建资源检查的正式ZIP。已有用户升级前先备份，不删除原有研究数据库；新安装使用稳定用户数据目录，旧项目数据继续兼容。

## 验证与已知边界

Python 3.11–3.13各177项后端测试、87项前端测试、类型/构建/依赖检查通过；干净候选包安装启停、历史迁移恢复、3分钟稳态和三项公开行情源受控检查已完成。详细范围见[发布与验收记录](https://github.com/raistlinsha-plus/akdesk-fixed/blob/main/docs/AKDesk-Fixed-v1.1.0-发布与验收记录.md)。

打印的离线A4排版与长备注完整性已验证；本次设备锁定，**macOS原生打印窗口尚未完成人工验收**。公开源本次返回正常不代表持续稳定，部分来源仍明确“部分可用”。FRED/AI可选，需用户本人Key；没有默认遥测。

在线固定样例为2026-08-03手工合成数据，非该日真实行情。AKShare是公开数据访问层，不是交易所授权实时源。软件MIT许可不授予第三方数据再分发权；不构成投资建议。

## 帮我们决定下一步

如果试过，只需回答：**你要完成什么任务？在哪一步停住？下周还会用这份简报吗，为什么？** [反馈入口](https://github.com/raistlinsha-plus/akdesk-fixed/issues/new/choose) · [讨论](https://github.com/raistlinsha-plus/akdesk-fixed/discussions/16)

不必提供账户、Key、数据库或未公开业务资料。我们先用四周观察真实任务反馈，不把Star或下载当作活跃用户。

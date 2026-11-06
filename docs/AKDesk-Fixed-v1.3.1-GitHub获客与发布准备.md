# v1.3.1 GitHub 获客与发布准备

更新：2026-11-07。目标是让陌生访客完成一个任务并愿意再用，不以刷Star、虚构用户或版本数量替代需求验证。本文是可执行素材，不表示已经向第三方社区投稿。

## 对外定位与体验路径

一句话：本地优先的固收与宏观研究工作台，现在可从黄金、指数和ETF开始，先观察、再核验、最后整理自己的研究底稿。

首要入口：[3分钟股债金汇合成体验](https://raistlinsha-plus.github.io/akdesk-fixed/#/cross-assets)。次入口：[一页固收简报](https://raistlinsha-plus.github.io/akdesk-fixed/#/brief)。感到有用再[下载本地版](https://github.com/raistlinsha-plus/akdesk-fixed/releases/latest)。不强制登录、提供Key、Star或上传研究资料。

README首屏应明确：产出、在线入口、正式下载、合成标记、数据边界。保留历史演示截图但标明其版本，不把旧截图当成新界面验收。

## 三分钟演示脚本

1. 0:00–0:30：解释“这是固定合成样例，不是实时行情”，选择熟悉的黄金或指数。
2. 0:30–1:30：加载日线，检查单位、观测时间与价格变化，不把指数变化当总回报。
3. 1:30–2:30：点选一个ETF示例，解释盘后、不复权、无净值折溢价；写一句观察和一个待核验问题。
4. 2:30–3:00：下载合成底稿；说明本地真实模式仅导出查询引用与人工文字，之后可关联研究项目。

完成标准是用户得到一份自己理解的底稿，而不是只点开页面。新录屏尚待可用的实机视觉验收后制作；本轮不以自动测试冒充新录屏。

## 中文发布文案

AKDesk Fixed v1.3.1：从黄金、指数和ETF进入跨资产观察。

这次没有做全市场股票终端，而是增加四个指数、Au99.99黄金及四个按需ETF示例，配合日线、共同日期比较、查询引用和自己的研究备注。无需安装或Key，可以先在线走完一个合成案例；需要持续研究，再使用本地项目、证据、任务与复盘工作流。

免费接口不是授权实时行情。新行情不落盘、不进AI；真实研究保存/导出保留查询引用与人工文字，不宣称交易级时效或总回报。

想听一个具体反馈：你想完成什么任务、在哪一步卡住、是否愿意下周再用？无需提供密钥或私有研究。

## English release copy

AKDesk Fixed v1.3.1 — a local-first fixed-income and macro research workbench, with a small gold, index and on-demand ETF observation path.

Try a synthetic walkthrough without installation or API keys. Inspect daily observations, compare common dates, and draft your own notes. The local edition connects query references to research projects, evidence and review checkpoints.

This is not a real-time trading terminal. New public-feed values are memory-only and excluded from numeric exports and AI processing. Four ETF examples are not a ranking or recommendation; unadjusted price changes are not total returns. Feedback on a completed task or a concrete obstacle is more useful than a Star alone.

## 发布与渠道清单

- [ ] GitHub正式Release：说明v1.3.0基础与v1.3.1增量，附正式ZIP、SHA-256、当前手册和已知限制。
- [ ] Actions及Pages实际完成后核对深链；不将排队或部署中标为成功。
- [ ] 确认README/英文README/Issue模板版本一致，示例可以复现。
- [ ] 可选：发布到本人GitHub Discussions的版本讨论；保持一次清楚更新，不反复顶帖。第三方仓库投稿另行核验规则后再授权提交。
- [ ] 发布后手工记录Traffic与反馈，不增加默认遥测、自动邮件、批量私信或Star交换。

## 四周观察与决策

每周使用同口径人工快照：独立访客窗口、来源、正式资源下载增量、外部有效反馈、自愿报告的任务完成与七日复用。不同窗口独立访客不可简单相加；访问、Clone、下载、Star都不等于安装或留存，排除已知维护者检查，未知保留未知。

沿用原有实验门槛：连续14天30名独立访客、3位外部用户确认完成核心任务、2位确认七日内再用。这是决策门槛，不是增长预测。曝光少先优化入口和案例；有体验却卡安装则修交付；能完成却不复用则收窄周期任务。有可复现卡点先修，再谈扩充个股、更多ETF或复杂AI。

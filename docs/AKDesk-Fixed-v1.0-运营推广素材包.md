# AKDesk Fixed v1.0 运营推广素材包

> 用途：公开介绍、种子用户邀请、社群分享和首月运营  
> 产品：AKDesk Fixed v1.0.0  
> 仓库：https://github.com/raistlinsha-plus/akdesk-fixed  
> 下载：https://github.com/raistlinsha-plus/akdesk-fixed/releases/latest
> 路线图：https://github.com/raistlinsha-plus/akdesk-fixed/issues/20  
> 需求投票：https://github.com/raistlinsha-plus/akdesk-fixed/discussions/21

## 1. 统一定位

标准一句话：

> AKDesk Fixed 是一款免费、开源、本地优先的固收与宏观研究工作台，面向在 Mac 上进行个人市场观察和投研记录的用户。

30 字短句：

> Mac 上免费的开源固收与宏观研究工作台。

对外介绍时优先使用“研究工作台”，不使用“免费 Wind”“替代 Wind/Qeubee”或“机构级实时终端”等表述。

## 2. 核心卖点

- 本地优先：SQLite、macOS Keychain、只监听 `127.0.0.1`；
- 免费开源：自有代码采用 MIT License；
- 固收场景：资金、曲线、现券、国债期货、发行事件、信用观察；
- 研究闭环：市场变化、证据篮、研究项目、专题、每日与每周复盘；
- 全球信息：FRED、World Bank、GDELT 和人民币外汇参考；
- BYOK AI：用户提供自己的 Key，明确发送范围和预算，默认不自动生成投资结论；
- 可信边界：展示来源、观测时间、抓取时间、缓存、降级和质量状态。

## 3. 种子用户邀请文案

### 私聊版

我最近用 Vibe Coding 完成了一款本地运行的开源固收研究工具 AKDesk Fixed，目前已经发布 v1.0.0。

它可以在 Mac 上查看中国固收市场、外汇和全球宏观数据，也能把市场线索保存到研究项目、证据和复盘里。代码采用 MIT 协议，普通使用不需要 Docker 或 Node.js。

想邀请你帮我测试一条大约 10 分钟的流程：

1. 下载并启动；
2. 打开“市场变化”；
3. 查看一个原始行情模块；
4. 告诉我哪一步最难理解或没有达到预期。

项目地址：https://github.com/raistlinsha-plus/akdesk-fixed

请不要为了测试上传真实 API Key、数据库或未公开研究材料。

### 同事群版

分享一个近期通过 Vibe Coding 完成的成果：AKDesk Fixed v1.0.0。

这是一个运行在个人 Mac 上的免费开源固收与宏观研究工作台，包含市场变化、资金与曲线、现券与国债期货、信用观察、FRED/World Bank/GDELT、研究项目、证据和周期复盘。

目前希望收集两类反馈：首次安装是否顺畅，以及“市场变化—原始数据—研究记录”的路径是否符合真实工作习惯。欢迎试用，也欢迎科技同事从工程实现、隐私和可信边界角度提出建议。

GitHub：https://github.com/raistlinsha-plus/akdesk-fixed

## 4. 技术社区发布稿

### 标题备选

- 我用 Vibe Coding 做了一款 Mac 本地固收研究工作台，并把它开源了
- AKDesk Fixed v1.0：FastAPI + React + SQLite 的本地固收投研终端
- 从 v0.1 到 v1.0：一个金融业务方向的 Vibe Coding 实践

### 正文

AKDesk Fixed 是一次偏业务场景的 Vibe Coding 实践。目标不是做一个行情页面 Demo，而是把公开数据、数据可信边界和研究流程放进同一款可以长期运行的本地产品。

当前版本使用 React、TypeScript、Vite、FastAPI、Python 和 SQLite。行情与外部数据主要来自 AKShare、FRED、World Bank 和 GDELT；AI 能力采用用户自备 API Key，不在代码中内置公共 Key。

产品包含市场变化、资金与收益率曲线、现券、国债期货、信用观察、研究项目、证据篮、专题研究、每日复盘和每周复盘。所有外部数据都会尽量显示来源、时点、缓存和降级状态，避免把演示或过期数据包装成实时数据。

项目目前优先适配 Apple Silicon MacBook Air。正式版已经完成 Python 3.11–3.13 后端测试、前端测试、依赖锁、SBOM、发布清单、迁移恢复和长稳检查。

项目采用 MIT License，欢迎试用、提交问题和参与改进：

https://github.com/raistlinsha-plus/akdesk-fixed

它仍然只是个人研究工具，不是交易所授权实时行情，也不应成为交易、估值或风控的唯一依据。

## 5. 业务社区发布稿

### 标题备选

- 一个免费的 Mac 本地固收与宏观研究工作台
- 从市场变化到研究复盘：AKDesk Fixed v1.0 开源发布
- 面向个人研究者的本地固收工作台 AKDesk Fixed

### 正文

很多公开行情工具能展示数据，但真正的研究过程还需要回答：数据是什么时点、是否已经降级、这次变化是否值得记录、证据放在哪里、观点后来有没有变化。

AKDesk Fixed 尝试把这些环节串起来。用户可以从资金、曲线、期货、现券、外汇和全球宏观数据发现变化，再保存到本地研究项目、专题和复盘中。信用观察坚持人工核验字段和严格计算门禁，不自动生成评级或违约概率。

产品运行在个人 Mac，只监听本机地址；研究数据保存在本地 SQLite。FRED 和 AI 能力由用户提供自己的 Key，并明确显示发送范围。

当前版本免费开源，适合个人学习、市场观察和研究记录：

https://github.com/raistlinsha-plus/akdesk-fixed

公开数据存在时效、连续性和授权边界，本产品不构成投资建议，也不替代机构正式行情、估值和风控系统。

## 6. 英文短文案

> AKDesk Fixed is a free, open-source and local-first fixed-income and macro research workstation for macOS. It connects public data from AKShare, FRED, the World Bank and GDELT with market monitoring, evidence collection, research projects and periodic reviews. MIT licensed; intended for personal research, not trading or investment advice.

Repository: https://github.com/raistlinsha-plus/akdesk-fixed

## 7. 90 秒演示脚本

### 0–10 秒：定位

画面：启动器与首页。

旁白：

> 这是 AKDesk Fixed，一款免费开源、运行在 Mac 本地的固收与宏观研究工作台。

### 10–30 秒：市场扫描

画面：市场变化中心，依次指向变化摘要、可信筛选和来源时点。

旁白：

> 打开市场变化，可以集中查看上一收盘以来和上次查看后的资金、曲线、国债期货与现券变化。每条线索都保留来源、观测时间、抓取时间和质量边界。

### 30–45 秒：原始模块核验

画面：从一条曲线变化进入收益率曲线页面。

旁白：

> 变化卡片不是自动投资结论。用户可以回到原始模块核验曲线、历史和数据状态。

### 45–65 秒：进入研究

画面：证据篮、研究项目或专题工作台。

旁白：

> 可信线索可以进入证据篮，并保存到研究项目。问题、假设、结论、反证、任务和观点变化都保存在本地。

### 65–80 秒：周期复盘

画面：每日复盘与每周复盘。

旁白：

> 每日和每周复盘把市场变化与研究活动整理在一起，但不会自动生成投资建议。

### 80–90 秒：行动

画面：GitHub 首页与 Release。

旁白：

> AKDesk Fixed 采用 MIT License。欢迎下载试用，并通过 GitHub 分享你的真实使用场景和改进建议。

## 8. 首月运营节奏

### 第 1 周：种子用户

- 定向邀请 10–20 位业务与科技同事；
- 每位只要求完成一条 10 分钟任务；
- 记录“是否成功启动、卡在哪一步、是否愿意再次使用”。

### 第 2 周：场景内容

- 发布一篇业务场景文章；
- 发布一篇 Vibe Coding 技术复盘；
- 所有文章统一导流到 Release 和欢迎讨论。

### 第 3 周：公开反馈

- 汇总 Issues 和 Discussions；
- 发布一则“已知问题与正在处理”；
- 选择 3–5 个真实高频问题进入 v1.0.1。

### 第 4 周：版本回应

- 发布 v1.0.1；
- 在 Release Notes 中逐条关联用户反馈；
- 邀请首批用户验证修复，而不是继续无边界扩功能。

## 9. 指标记录表

每周固定记录一次：

| 指标 | 口径 | 首月目标 |
| --- | --- | ---: |
| 实际安装用户 | 明确反馈已启动 | 20 |
| 完成核心路径 | 市场变化→原始模块→反馈 | 10 |
| 有效反馈 | 可理解、可复现或有明确场景 | 5 |
| 已确认问题 | 维护者确认范围 | 3 |
| 回访用户 | 两周内再次使用或回复 | 5 |
| Release 下载 | GitHub 资源下载 | 30 |
| Star | 仅作为传播结果 | 30–50 |

GitHub Traffic 只保留最近一段时间的访问视图，建议每周在 `Insights → Traffic` 手工记录独立访问、Clone、Referrer 和热门页面。

## 10. 统一风险说明

每次公开传播至少保留以下简版声明：

> AKShare/AKTools 是公开数据访问层，不是交易所授权行情。数据可用性、时效和准确性不作保证。AKDesk Fixed 仅供个人学习与研究，不构成投资建议，也不应作为交易、估值或风控的唯一依据。

不要在公开文章、视频或 Issue 中展示真实 API Key、数据库、未公开研究材料、客户信息或账户数据。

## 11. 素材清单

- GitHub Social Preview：`docs/media/akdesk-social-preview.png`；
- 市场变化截图：`docs/audits/v0.18.0-release-readiness-20260728/screenshots/01-market-changes.png`；
- 研究首页截图：`docs/audits/v0.18.0-release-readiness-20260728/screenshots/04-research-home.png`；
- 产品说明：`docs/AKDesk-Fixed-v1.0.0-产品介绍.md`；
- 用户手册：`docs/AKDesk-Fixed-v1.0.0-用户手册.md`；
- Vibe Coding 项目总结：`docs/AKDesk-Fixed-v1.0.0-面向科技人员的项目总结.md`。

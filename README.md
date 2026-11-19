# AKDesk Fixed

**这周记下判断，下周接着核验。** AKDesk 是一款以固收为核心的开源 macOS 个人研究工具。

**[在线做一次两周复盘](https://raistlinsha-plus.github.io/akdesk-fixed/#/week-story)** · [查看 Markdown 成品](./docs/examples/AKDesk-v1.5.0-连续两周复盘样例.md) · [60 秒导览](https://raistlinsha-plus.github.io/akdesk-fixed/akdesk-continuity-60s.mp4) · [下载 macOS 版](https://github.com/raistlinsha-plus/akdesk-fixed/releases/latest) · [English](./README_EN.md)

![连续两周复盘：固定合成案例，先记录判断和问题、再回来核验](./docs/media/v1.5.0/two-week-review.png)

**保存本周判断 → 下一周回看 → 人工核验 → 导出底稿。** 图中是固定合成样例，不是真实行情；在线练习无需安装、登录或 API Key。站点暂不可达时，可以直接阅读 Markdown 成品。

**v1.5.0「连续复盘版」**：本地可保存判断、待核验事项与修订，下周继续，不必先建研究项目。仍观察沪深 300、10 年国债收益率、Au99.99 与美元兑人民币参考价；缺项不补零，真实底稿只导出用户文字与查询引用。[使用与验收](./docs/AKDesk-Fixed-v1.5.0-使用与验收指南.md)

[![MIT](https://img.shields.io/badge/license-MIT-44c8bb.svg)](./LICENSE) [![macOS](https://img.shields.io/badge/platform-macOS-0b1727.svg)](#本地安装三步)

## 本地安装三步

主要适配 Apple Silicon MacBook Air，要求 **macOS 12+、Python 3.11–3.13**。首次安装需要网络与约 1 GB 可用空间。正式包已带预构建界面，普通使用无需 Node.js、Docker 或 Rust。

macOS 12+ 为兼容目标，并非所有系统版本均已实机验收；见 [验收指南](./docs/AKDesk-Fixed-v1.5.0-使用与验收指南.md)。

1. 准备受支持的 Python。使用 Homebrew 时可执行 `brew install python@3.13`。
2. 从 [GitHub Releases](https://github.com/raistlinsha-plus/akdesk-fixed/releases/latest) 下载该版本的 `AKDesk-Fixed-v版本号.zip` 与 `SHA256SUMS`。核对 SHA-256 后完整解压。
3. 双击 `start-macos.command`。启动器执行本地预检、安装锁定依赖，并打开 `http://127.0.0.1:8765`。

GitHub 自动生成的 **Source code** 压缩包用于源码查看和开发，与经过发布清单、构建资源和执行权限检查的安装 ZIP 不同；源码用户可能需要自行构建界面或恢复脚本权限。公开可下载版本以 Releases 实际资产为准。

macOS 阻止脚本时，可右键选择“打开”。执行权限丢失时，在项目目录运行：

```bash
chmod +x start-macos.command start-macos-demo.command stop-macos.command
```

**停止服务**：在原启动终端按 `Control+C`，或用同一安装目录的 `stop-macos.command`。只关闭浏览器不会停止服务。启动器仅复用同安装、版本、模式与数据目录的实例；自定义 `AKDESK_PORT` 须在启停时一致。

**启动遇到问题**：预检检查 Python、文件、权限、空间和证书位置；依赖失败有分类恢复提示。可独立执行 `python3 scripts/preflight.py --json`。进入应用后，打开“使用与反馈”，主动生成并预览脱敏诊断摘要，再决定是否分享；不会自动上传 Key、路径、数据库或研究正文。详细恢复步骤见 [用户手册](./docs/AKDesk-Fixed-v1.4.1-用户手册.md)。

## 能完成哪些工作

- **快速市场底稿**：查看变化、核验曲线，生成包含资金、利差、期货、出处和时间的一页简报；完整每日复盘仍保留现券、发行事件和研究工作流。
- **小范围跨资产观察**：黄金、四个指数、四个按需ETF，连接原有固收与外汇模块；按需日线、同类共同日期比较、查询引用及人工备注，不扫描全市场。
- **股债金汇周复盘**：选一周，四项独立返回并可单项重读。回原模块核验再返回，所选日期和标签页内草稿不丢；真实底稿不导出行情数值。
- **持续个人研究**：统一自选、证据篮、研究项目、专题、反证、任务与每周复盘，记录观点如何变化。
- **信用与跨市场观察**：信用观察 R2、外汇、宏观图表、主权比较与事件线索。
- **解释数据状态**：区分真实、缓存、过期、演示和混合来源；缺失保持为空，关键数值不足时方向待核验。

临时备注可以随简报复制、下载 Markdown 或打印/PDF，不会自动保存为研究笔记。旧归档没有逐源出处时会显示待核验。具体操作见 [当前用户手册](./docs/AKDesk-Fixed-v1.4.1-用户手册.md)，数据限制见[数据使用规则](./DATA_USAGE.md)。

## 四类数据源

| 数据源 | 主要用途 | 配置与边界 |
| --- | --- | --- |
| AKShare / AKTools 生态 | 中国资金、曲线、现券、国债期货、转债、发行、部分外汇；新增新浪指数、上金所黄金及东方财富ETF日线 | 当前本地版使用 Python AKShare；它是公开数据访问层，不是交易所授权实时行情；新增数值仅内存/no-store |
| FRED 官方 API | 美国利率、通胀、就业、增长与发布复盘 | 用户自备 Key；内容仅按请求展示，研究只保存用户查询引用；无数值导出、不送入 AI |
| World Bank API v2 | 跨经济体主权结构比较 | 无需 Key；署名与变换说明，本地缓存；默认开放许可有指标/数据集例外 |
| GDELT DOC 2.0 | 外部事件检索与待核验线索 | 无需 Key；按需查询和缓存元数据，不抓取新闻正文，不自动判断信用风险 |

中国市场路径不需要 FRED 或 AI Key。FRED 与 AI 都是独立可选功能：用户按需提供自己的凭据；macOS 使用 Keychain 管理凭据。AI 经用户授权发送裁剪上下文，提供摘要与待核验任务，使用额度由用户自己的服务账户承担。

This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.

应用没有使用遥测或追踪 SDK。研究数据保存在本机；反馈由用户主动提交。数据缓存、凭据、AI 发送范围和备份规则见 [当前用户手册](./docs/AKDesk-Fixed-v1.4.1-用户手册.md) 与 [数据使用规则](./DATA_USAGE.md)。

## 适合谁

适合关注固收与宏观的个人研究者、AKShare/Python 使用者，以及想评估本地投研工作流的业务与科技人员。可以先用在线样例判断产出是否对自己有用，再安装完整版。

不适合作为机构生产交易、正式估值、会计核算、监管报送或风控限额的唯一依据。公开数据的时效和连续性受上游影响；产品不承诺实时行情或机构级 SLA，不构成投资建议。

## 文档与反馈

- 当前：[v1.5.0 连续复盘与验收](./docs/AKDesk-Fixed-v1.5.0-使用与验收指南.md) · [首次体验背景（v1.4.2）](./docs/AKDesk-Fixed-v1.4.2-使用与验收指南.md) · [完整功能手册（v1.4.1）](./docs/AKDesk-Fixed-v1.4.1-用户手册.md)
- 快速体验：[60 秒固收简报导览](https://raistlinsha-plus.github.io/akdesk-fixed/akdesk-demo-60s.mp4) · [ETF 首任务](https://raistlinsha-plus.github.io/akdesk-fixed/#/start) · [可复现 AKShare 案例](./docs/examples/AKShare-一页固收简报.md)
- 历史：[v1.4.0 指南](./docs/AKDesk-Fixed-v1.4.0-产品与使用指南.md) · [v1.3.2 首任务](./docs/AKDesk-Fixed-v1.3.2-体验指南.md) · [v1.3.1 产品介绍](./docs/AKDesk-Fixed-v1.3.1-产品介绍.md)
- [v1.3.1 Review](./docs/AKDesk-Fixed-v1.3.1-开发与Review记录.md) · [升级与发布验收](./docs/AKDesk-Fixed-v1.3.1-升级与发布验收.md) · [获客素材与观察计划](./docs/AKDesk-Fixed-v1.3.1-GitHub获客与发布准备.md)
- [v1.2 产品与使用指南](./docs/AKDesk-Fixed-v1.2.0-产品与使用指南.md) · [发布与验收](./docs/AKDesk-Fixed-v1.2.0-发布与验收记录.md)
- [三条场景指南](./docs/AKDesk-Fixed-v1.1.2-场景案例与使用指南.md) · [English casebook](./docs/examples/AKDesk-v1.1.2-casebook-EN.md) · [利率研究成品](./docs/examples/AKDesk-v1.1.2-利率研究样例.md) · [信用复核成品](./docs/examples/AKDesk-v1.1.2-信用复核样例.md)

- [v1.1 产品介绍](./docs/AKDesk-Fixed-v1.1.0-产品介绍.md) · [用户手册](./docs/AKDesk-Fixed-v1.1.0-用户手册.md) · [测试用例清单](./docs/AKDesk-Fixed-v1.1.0-测试用例清单.md)
- [发布与验收记录](./docs/AKDesk-Fixed-v1.1.0-发布与验收记录.md) · [更新记录](./CHANGELOG.md) · [公开路线图](./ROADMAP.md)
- [提交功能/数据问题](https://github.com/raistlinsha-plus/akdesk-fixed/issues/new/choose) · [分享使用场景](https://github.com/raistlinsha-plus/akdesk-fixed/discussions/16)

反馈最有帮助的信息是：要完成的任务、操作步骤、预期与实际结果、应用版本和模式。请先检查截图和附件，不上传 API Key、本机数据库或未公开研究材料。

## 开发与复现

后端：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock -r backend/requirements-dev.txt
PYTHONPATH=backend:. .venv/bin/python -m pytest backend/tests
```

前端与独立静态演示：

```bash
cd frontend
npm ci
npm run check
npm run build:demo
npm run preview:demo
```

无需第三方依赖的固定 CLI 样例：`python3 examples/fixed_income_brief.py --output brief-example.md`。真实模式与超时说明见 [examples/README.md](./examples/README.md)。应用由 React/TypeScript/Vite、FastAPI/Python 与 SQLite 组成，完整开发流程见 [CONTRIBUTING](./CONTRIBUTING.md)。

## 许可与贡献

自有代码采用 [MIT License](./LICENSE)。第三方组件与数据分别受其原始许可、使用条款和署名要求约束；**MIT 不授予第三方行情或内容的再分发权**。参见 [第三方声明](./THIRD_PARTY_NOTICES.md)。

AKShare 官方将接口和相关数据定位为学术研究；机构/商业场景应自行核验原始提供方授权。本产品不是合规认证。FRED 使用还须遵守完整服务与 API 条款，自备 Key 不豁免限制；具体实现与官方链接见[数据使用规则](./DATA_USAGE.md)。

欢迎可复现 Bug、文档修正、适配器测试和研究案例。参与前请阅读 [贡献指南](./CONTRIBUTING.md)、[行为准则](./CODE_OF_CONDUCT.md)；敏感漏洞按 [安全政策](./SECURITY.md) 报告。

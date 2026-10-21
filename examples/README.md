# 从三个数据源生成一页固收简报

先运行一个不安装依赖、不申请 Key 的示例，看看 AKDesk 能产出什么。下面命令均在项目根目录执行，需要 Python 3.11–3.13。

```bash
python3 examples/fixed_income_brief.py
python3 examples/fixed_income_brief.py --output brief-example.md
```

默认使用脚本内手工编写的固定合成数据，连日期也是固定示例。不会联网，不会读取用户数据库、Keychain、FRED 或 AI 配置；每次运行得到相同的 Markdown。`—（缺失）` 用来演示字段缺失，真实的 `0.00` 会保留为零。输出包含资金面、国债曲线、国债期货，以及各源的观测和抓取时点。

## 可选：请求真实公开数据

使用已有 AKDesk 环境：

```bash
.venv/bin/python examples/fixed_income_brief.py --live --timeout 15 --output brief-live.md
```

如尚未安装，先按项目 [快速开始](../README.md#macbook-air-快速开始) 准备 Python；开发者也可创建独立环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
.venv/bin/python examples/fixed_income_brief.py --live --output brief-live.md
```

真实模式复用项目 `DataService` 的 Shibor、国债收益率曲线与国债期货适配器。它只启动顺序执行的隔离数据进程；每源默认15秒超时、不重试，某源失败后继续其他源。运行时仅有内存缓存，不启动 Web 服务或调度器，不导入 `app.main`，不打开 AKDesk 数据库，也不读取 Keychain。期货适配器可能在其隔离进程中查询交易日历，此请求也受该源的总超时限制。

真实请求失败后，项目适配器内部可能返回演示数据；本例会丢弃这些值，将对应模块标成“不可用”，绝不会把合成示例写成真实数据。字段、历史前值或可信时间缺失时也保持缺失。Shibor 的独立扩展源（FR/FDR/LPR）不在本例采集范围内，因此资金面可能显示“真实数据部分可用”。

退出码：`0` 表示固定示例已生成，或真实模式至少一个源可用；`1` 表示环境/输出错误；`2` 表示三个真实源均不可用，但仍会输出带缺失和错误分类的简报。输出不含上游原始错误正文。命令不会自动创建输出父目录；重用同一 `--output` 文件名会覆盖该文件。

案例讲解见 [AKShare → 一页固收简报](../docs/examples/AKShare-一页固收简报.md)。这份 CLI 是学习案例，不启动完整研究工作台。真实行情及其再分发仍受上游许可和使用条件约束。

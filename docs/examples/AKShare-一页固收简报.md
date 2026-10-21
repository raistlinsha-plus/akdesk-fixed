# 案例：从 AKShare 到一页固收简报

目的：不先理解完整终端，用一条可复现命令观察“公开数据 → 统一格式 → 带出处的研究底稿”。这个案例随 AKDesk Fixed v1.1.0 提供，代码见 [fixed_income_brief.py](../../examples/fixed_income_brief.py)。

## 先看产出

在项目根目录运行：

```bash
python3 examples/fixed_income_brief.py --output brief-example.md
```

无需安装第三方依赖。脚本默认使用手工合成的固定数据，明确标示“非真实市场”；两个时间字段均为固定示例，不意味着实际发生过抓取。可以反复运行并比较文件，结果保持一致。

简报回答三个基础问题：

| 模块 | 展示内容 | 可用于核验的动作 |
| --- | --- | --- |
| 资金面 | Shibor O/N、1W及较前值变化 | 检查短端资金利率是否变化，确认前值是否缺失 |
| 国债曲线 | 1Y、5Y、10Y、30Y收益率和BP变化 | 比较不同期限的变化，再回到来源核对口径 |
| 国债期货 | TS/TF/T/TL适配器结果中的价格及涨跌幅 | 核对合约和报价时间，不将其当作曲线收益率 |

百分比和BP不能混用：利率从1.80%到1.81%是上升1 BP。缺失的前值不会补成0 BP；没有取得真实价格时也不显示0元。

## 再切换到真实数据

按 [运行说明](../../examples/README.md) 安装项目后端依赖后执行：

```bash
.venv/bin/python examples/fixed_income_brief.py --live --timeout 15 --output brief-live.md
```

真实模式复用已有 `DataService`，而不是在案例中复制或猜测上游接口：

| 适配器 | 当前AKShare接口 | 出处说明 |
| --- | --- | --- |
| `money_rates` | `macro_china_shibor_all` | [AKShare利率文档](https://akshare.akfamily.xyz/data/interest_rate/interest_rate.html) |
| `yield_curves` | `bond_china_yield` | [AKShare债券文档](https://akshare.akfamily.xyz/data/bond/bond.html) |
| `treasury_futures` | `futures_zh_spot` | [AKShare期货文档](https://akshare.akfamily.xyz/data/futures/futures.html) |

上述映射以本版本代码为准，公开接口可能变化。每源顺序执行、限制隔离进程时间；失败模块显示错误分类和缺失，其他模块继续。资金扩展源不额外采集，研究工作台的数据库、项目、Keychain和AI能力也不会被加载。

## 输出结构与边界

脚本内部 `schema_version=1`；`mode` 为 `synthetic` 或 `live`，`sources` 数组保存三个模块的 `status`、`source`、`source_url`、`observation_time`、`fetched_at`、`error_category` 和格式化前的 `data`。当前CLI只导出 Markdown，尚未提供JSON选项。

`status` 分为 `synthetic`、`available`、`partial`、`unavailable`。真实源返回演示、过期或可疑数据时丢弃其数据；不会用固定示例填补缺口。Markdown保留出处、观测与抓取时间，避免把不同日期的结果误当成同步快照。不同源成功并不证明它们处于同一交易时点。

这是一份可继续人工核验的市场底稿，不自动给出投资判断。AKShare是公开数据访问层；原始数据的使用、署名和再分发条件仍需遵守。若你需要自选、研究项目和周期复盘，可继续体验 [完整AKDesk](../../README.md)。

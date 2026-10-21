# v1.1.0 后端验收记录

验收日期：2026-10-22（Asia/Shanghai）。本记录只保留版本、测试数量、审计汇总与公开数据源结果，不包含本机个人路径、Key、数据库内容或原始网络错误日志。

## 环境与依赖

- 平台：macOS 26.6.2，Apple Silicon / arm64。
- Python：3.11.15、3.12.13、3.13.3，分别使用隔离虚拟环境。
- 三套环境均先安装更新后的 `backend/requirements.lock`。
- 生产依赖重点版本：AKShare 1.19.1、certifi 2026.10.19、h2 4.4.1、soupsieve 2.9、urllib3 2.8.0（soupsieve 的锁文件采用安装元数据中的标准版本写法）。
- 验收工具：pip 26.2.2、pytest 9.0.3、httpx2 2.12.0、httpcore2 2.12.0、Ruff 0.15.22。
- `backend/requirements-dev.txt` 引用生产锁文件，并将 pytest/httpx2 的最低版本更新到已修复版本；CI 使用相同的精确 pip、pytest、httpx2 版本。

## 自动化测试矩阵

运行命令采用项目内的相对路径，核心检查为：

```text
python -m pip check
PYTHONPATH=backend:. python -m pytest -q backend/tests
python -m ruff check backend scripts
```

| Python | 后端测试 | 本次测试耗时 | pip check | Ruff |
| --- | --- | ---: | --- | --- |
| 3.11.15 | 177 passed | 5.76 秒 | 通过 | 通过 |
| 3.12.13 | 177 passed | 5.86 秒 | 通过 | 通过 |
| 3.13.3 | 177 passed | 5.37 秒 | 通过 | 通过 |

三套环境均执行 `ruff check backend scripts examples`，全部通过。原有与当前日期耦合的历史窗口用例在本次矩阵中均通过；诊断、预检、来源元数据和简报案例相关后端用例包含在 177 项内。

最终浏览器复核发现诊断导出的未检查来源沿用了模型默认 `trusted`。现已仅在诊断输出层将 `not_checked` 校准为 `unavailable`，保持其 `unchecked` 状态与全局服务健康不变。另仅对明确的主动演示模式项输出 `demo_mode` 错误类别，实际网络失败及自动回退仍保留原有错误分类。新增两项回归覆盖上述边界后，重新执行了上表完整矩阵；诊断与预检相关用例共 18 项。

## Python 安全审计

使用 pip-audit 2.10.1 与当次可访问的 PyPI 漏洞数据库，分别执行两种范围的审计，均无跳过项目。

| 审计范围 | 包数 | 最终已知漏洞命中 | 结果 |
| --- | ---: | ---: | --- |
| 生产锁文件 `backend/requirements.lock` | 55 | 0 | 通过 |
| 主 Python 3.13 环境，包含开发与安装工具 | 64 | 0 | 通过 |

生产锁文件使用精确版本列表执行 `--no-deps --disable-pip` 审计；三套环境的 `pip check` 同时通过。主环境使用已安装 site-packages 的依赖清单审计，因此其范围与生产锁文件不同。

首次主环境审计曾发现 4 个包的 10 条漏洞记录命中：旧版 httpx2、其传递依赖 httpcore2、pytest 和 pip；数据库对部分同一 ID 返回了重复记录，因此不将 10 条记录称为 10 个独立漏洞。已升级上述开发/安装工具，并在升级后重新执行三套后端测试与主环境审计，最终命中数为 0。

该结果对应本次审计日期和范围，不表示已证明不存在未知漏洞；新用户系统自带的 pip 版本也不等同于本次验收环境。

## 受控公开行情 smoke

使用 `examples/fixed_income_brief.py` 的真实模式逻辑，只请求公开 AKShare 的资金、国债曲线、国债期货三源。使用内存缓存，每源隔离进程超时 15 秒、每源一次尝试；本次总耗时 3.89 秒。

本次未导入应用主服务、未查询本机研究数据库、未访问 Keychain，也未调用 FRED 或 AI 服务。示例逻辑会拒绝用演示或过期数据补位。

| 来源 | 本次状态 | 返回规模 | 观测时点 | 错误分类 |
| --- | --- | --- | --- | --- |
| AKShare / Shibor | 部分可用 | 2 条资金利率 | 2026-10-21 | none |
| AKShare / ChinaBond | 可用 | 9 个期限 | 2026-10-21 | none |
| AKShare / Sina Futures | 部分可用 | 4 条期货记录 | 2026-10-21T15:15:00+08:00 | none |

对应抓取时间字符串分别为 `2026-10-22T01:27:27.635340`、`2026-10-22T01:27:29.070107`、`2026-10-22T01:27:30.040210`。原返回的抓取字符串不含时区偏移，因此本文不替其补充偏移。请求批次生成时间为 `2026-10-21T17:27:26.688508+00:00`。

部分可用状态应继续在界面和导出中保留，不能把三源连接成功描述为全部数据具有完整研究可信度。本次测试是特定时点的连接与适配检查，不承诺公开接口持续可用。

公开来源说明：

- [AKShare 利率接口](https://akshare.akfamily.xyz/data/interest_rate/interest_rate.html)
- [AKShare 债券接口](https://akshare.akfamily.xyz/data/bond/bond.html)
- [AKShare 期货接口](https://akshare.akfamily.xyz/data/futures/futures.html)

## 结论

后端 177 项测试在 Python 3.11–3.13 均通过；生产锁与主开发环境的当次已知漏洞审计均为 0；三个公开行情入口在本次受控请求中均返回了非演示数据，其中两源保留“部分可用”标识。

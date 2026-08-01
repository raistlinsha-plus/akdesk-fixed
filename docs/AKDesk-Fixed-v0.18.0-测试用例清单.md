# AKDesk Fixed v0.18.0 测试用例清单

> 适用版本：v0.18.0「低门槛交付版」  
> 用途：版本回归、发布候选版验收、后续自动化补齐  
> 更新日期：2026-07-29

## 1. 测试基线

当前仓库包含：

| 类型 | 文件数 | 源码测试声明 | v0.18.0 发布门禁收集结果 |
| --- | ---: | ---: | ---: |
| 后端 pytest | 22 | 138 个测试函数 | 142 项 |
| 前端 Vitest | 22 | 67 个 `it/test` 声明 | 70 项 |
| 合计 | 44 | 205 个声明 | 212 项 |

源码声明数和实际收集数不同，是因为部分测试会通过参数化生成多个测试项。

本清单另整理了 **196 项业务验收用例**，覆盖自动化、人工和混合验证；它们用于从用户场景角度组织回归，不等同于上表的 212 项自动化测试。

发布门禁还包括：

- Ruff；
- ESLint；
- CSS 变量检查；
- TypeScript 编译；
- Vite 生产构建；
- `pip check`；
- npm 生产依赖审计；
- SQLite `quick_check` 和外键检查；
- 历史数据库迁移验证；
- macOS 启停脚本语法与人工启动检查。

## 2. 用例字段说明

| 字段 | 含义 |
| --- | --- |
| P0 | 发布阻断；失败时不能发布 |
| P1 | 核心功能；失败时原则上不能发布 |
| P2 | 重要体验或边界；可评估风险后处理 |
| 自动 | 已有自动化测试直接或间接覆盖 |
| 人工 | 需要浏览器、真实网络、macOS 或视觉判断 |
| 混合 | 自动化覆盖逻辑，仍需人工验证真实环境 |

本文的业务用例与源码测试不是严格一一对应。一个业务用例可能由多个测试函数覆盖，一个自动化测试也可能覆盖多个业务断言。

## 3. 建议测试环境

### 环境矩阵

| 环境 | 用途 |
| --- | --- |
| macOS 12+，Apple Silicon MacBook Air | 主要交付环境 |
| Python 3.11、3.12、3.13 | 后端兼容性 |
| Safari 和 Chromium | 浏览器兼容与视觉回归 |
| 1440×900 | 主要设计视口 |
| 1280×800、1024×768 | 中小视口回归 |
| 正常网络、限速网络、完全断网 | 数据降级和恢复 |
| 正常模式、演示模式 | 真实数据与离线体验 |

### 数据配置

- 空白数据库；
- 当前正式数据库副本；
- schema 701、800、900、1100、1201、1301 历史备份；
- 有效与无效 FRED Key；
- 有效与无效 AIHubMix Key；
- 信用观察正常、缺字段、重复、跨日期和大样本文件；
- 上游正常、超时、空表、限流、字段变化和异常值响应。

## 4. 安装、启动与运行时

| ID | 优先级 | 方式 | 测试场景 | 预期结果 | 主要映射 |
| --- | --- | --- | --- | --- | --- |
| RT-001 | P0 | 人工 | 全新 Mac 首次双击 `start-macos.command` | 创建独立 `.venv`、安装依赖、启动服务并打开浏览器 | 启动脚本 |
| RT-002 | P0 | 人工 | 已安装依赖后再次启动 | 不重复安装，直接启动 | 启动脚本 |
| RT-003 | P0 | 人工 | Python 版本低于 3.11 或高于等于 3.14 | 明确提示版本不支持，不留下半启动服务 | 启动脚本 |
| RT-004 | P0 | 人工 | 8765 端口被其他程序占用 | 阻止启动并说明处理方式 | 启动脚本 |
| RT-005 | P1 | 人工 | 同版本已经运行时再次双击启动器 | 不启动第二个实例，直接打开现有服务 | 启动脚本 |
| RT-006 | P0 | 人工 | 双击 `stop-macos.command` | 只终止当前 AKDesk 服务，不误杀其他进程 | 停止脚本 |
| RT-007 | P1 | 人工 | 在原启动窗口按 `Control+C` | 服务正常退出；端口释放 | 启停验收 |
| RT-008 | P1 | 人工 | 只关闭浏览器页面 | 后端继续运行，重新打开地址可访问 | 运行模型 |
| RT-009 | P0 | 自动 | API lifespan、健康检查和日报归档启动 | 应用生命周期正确，接口返回有效状态 | `test_main.py` |
| RT-010 | P1 | 自动 | 重复 SQLite 读取 | 文件描述符不持续增长 | `test_runtime.py` |
| RT-011 | P1 | 自动 | 运行时诊断接口 | 返回进程、线程、FD 上限和利用率 | `test_runtime.py` |
| RT-012 | P1 | 混合 | 页面切到后台再返回 | 后台暂停轮询，回到前台立即同步 | `visibilityPolling.test.ts` |
| RT-013 | P0 | 自动 | 演示模式启动 | 不调用任何真实网络数据源 | `test_provider.py` |
| RT-014 | P1 | 人工 | 完全断网启动演示模式 | 核心页面可体验，所有数据显著标注演示 | 演示验收 |

## 5. 行情适配、缓存与可信门禁

| ID | 优先级 | 方式 | 测试场景 | 预期结果 | 主要映射 |
| --- | --- | --- | --- | --- | --- |
| MD-001 | P0 | 自动 | Shibor 正常、FR/FDR/LPR 失败 | 保留核心 Shibor，扩展源独立降级 | `test_provider.py` |
| MD-002 | P1 | 自动 | FR、FDR、LPR 中单个源失败 | 不影响其他资金指标，显示缺失说明 | `test_provider.py` |
| MD-003 | P0 | 自动 | 收益率曲线返回国债、国开债和政策金融债 | 正确识别期限与前值，BP 变化正确 | `test_provider.py`、研究测试 |
| MD-004 | P0 | 自动 | 现券源没有可信时间戳 | 不伪造观测时间，只记录抓取时间 | `test_provider.py` |
| MD-005 | P1 | 自动 | 现券短代码可保守推断 | 推断代码被标记为待核验 | `test_provider.py`、`test_database.py` |
| MD-006 | P0 | 自动 | 现券出现异常大幅变动 | 标记为可疑并隔离，不进入研究信号 | `test_provider.py`、`test_research.py` |
| MD-007 | P0 | 自动 | 国债期货返回中文合约字段 | 正确识别 TS、TF、T、TL | `test_provider.py` |
| MD-008 | P0 | 自动 | 期货源只有时间、没有交易日 | 不推断到未来日期 | `test_provider.py` |
| MD-009 | P0 | 自动 | 上游明确返回未来观测时间 | 拒绝写入数据集和历史 | `test_provider.py`、`test_database.py` |
| MD-010 | P1 | 自动 | 工作日恰逢中国法定休市 | 市场状态为非交易日 | `test_provider.py` |
| MD-011 | P1 | 自动 | 盘前、交易中、午休、收盘和周末 | 状态分别正确，不把盘前误报为已收盘 | `test_provider.py`、`healthStatus.test.ts` |
| MD-012 | P1 | 自动 | 全球外汇在中国节假日交易 | 外汇时钟不跟随中国交易日历 | `test_fx.py`、`healthStatus.test.ts` |
| MD-013 | P0 | 自动 | 外汇 bid/ask 正常 | 规范化代码、中间值、点差和精度 | `test_fx.py`、`fxUtils.test.ts` |
| MD-014 | P0 | 自动 | 外汇出现 bid 大于 ask | 记录被隔离，不能进入可信使用路径 | `test_fx.py` |
| MD-015 | P1 | 自动 | 人民币参考价包含央行中间价与其他牌价 | 只使用央行中间价，正确处理 100 JPY/CNY 单位 | `test_fx.py` |
| MD-016 | P1 | 自动 | 外汇缺少可信观测时点 | 可搜索和加入自选，但限制历史与提醒 | `test_fx.py`、`marketSafety.test.ts` |
| MD-017 | P0 | 自动 | 转债比价主源失败 | 切换价格备用源，缺失字段明确标出 | `test_aux_worker.py`、`test_provider.py` |
| MD-018 | P0 | 自动 | 转债备用源包含零价或失效行 | 隔离无效记录 | `test_aux_worker.py` |
| MD-019 | P0 | 自动 | AKShare 同时发起多个任务 | 最大并发不超过 2 | `test_provider.py` |
| MD-020 | P0 | 自动 | 数据子进程超时 | 终止子进程并释放并发槽 | `test_provider.py` |
| MD-021 | P1 | 自动 | 多次连续失败 | 打开熔断并在恢复时间前跳过加载器 | `test_provider.py` |
| MD-022 | P1 | 自动 | 熔断打开 | 下一次检查时间使用 retry 时间 | `test_provider.py` |
| MD-023 | P0 | 自动 | 缓存未过期并重启进程 | 持久缓存恢复，健康状态正确 | `test_cache.py`、`test_provider.py` |
| MD-024 | P0 | 自动 | 缓存已过期 | 只有显式允许 stale 时才能读取 | `test_cache.py` |
| MD-025 | P1 | 自动 | 非持久数据集 | 仅留在内存，不写市场缓存库 | `test_cache.py` |
| MD-026 | P0 | 自动 | 演示、过期或可疑数据 | 不写入研究历史 | `test_database.py` |
| MD-027 | P1 | 自动 | 同一日多次盘中刷新 | 更新当日研究点，不重复制造多条日数据 | `test_database.py` |
| MD-028 | P1 | 自动 | 连接成功但质量可疑 | 连接状态与研究可用性分开表达 | `test_provider.py`、`healthStatus.test.ts` |
| MD-029 | P1 | 人工 | 上游失败但有最近真实缓存 | 页面立即显示缓存并后台刷新，状态标注清楚 | 真实降级验收 |
| MD-030 | P1 | 人工 | 没有真实数据且上游失败 | 切换演示数据，并显著标注“演示” | 真实降级验收 |

## 6. 市场页面、导航与交互

| ID | 优先级 | 方式 | 测试场景 | 预期结果 | 主要映射 |
| --- | --- | --- | --- | --- | --- |
| UI-001 | P1 | 自动 | 选择四类任务入口 | 映射到不同默认落地页 | `experienceProfiles.test.ts` |
| UI-002 | P1 | 自动 | 保存非法入口设置 | 拒绝非法值，只保留支持的配置 | `experienceProfiles.test.ts` |
| UI-003 | P1 | 自动 | 市场/投研模式切换 | 首页切换，专业页面不被强制跳走 | `workspaceMode.test.ts` |
| UI-004 | P1 | 自动 | 浏览器存储损坏或不可用 | 回退到安全默认模式 | `workspaceMode.test.ts` |
| UI-005 | P1 | 自动 | 市场变化首次访问和再次访问 | 识别新增或显著变化的信号 | `marketChanges.test.ts` |
| UI-006 | P1 | 自动 | 市场变化筛选条件非法 | 修复筛选并优先展示可信严重变化 | `marketChanges.test.ts` |
| UI-007 | P1 | 自动 | 驾驶舱模块偏好缺失或损坏 | 恢复有效模块组合 | `marketDashboard.test.ts` |
| UI-008 | P2 | 自动 | 计算历史分位 | 公式透明，样本不足时不伪造结果 | `marketDashboard.test.ts` |
| UI-009 | P2 | 自动 | 最近访问市场页面超过上限 | 保留最近 5 个不重复页面 | `marketDashboard.test.ts` |
| UI-010 | P1 | 自动 | 保存视图读取旧版本格式 | 正确迁移，非法内容被忽略 | `savedViews.test.ts` |
| UI-011 | P1 | 自动 | 同名保存视图 | 覆盖内容但保持原 ID | `savedViews.test.ts` |
| UI-012 | P1 | 自动 | 筛选后结果页数缩小 | 页码自动收敛到有效范围 | `savedViews.test.ts` |
| UI-013 | P1 | 自动 | 图表含有效值和空值 | 可访问描述使用最新有效值并忽略空值 | `chartAccessibility.test.ts` |
| UI-014 | P1 | 自动 | 图表全部为空 | 无障碍描述明确说明无数据 | `chartAccessibility.test.ts` |
| UI-015 | P2 | 自动 | 数值范围很窄 | Y 轴仍能区分变化 | `chartAccessibility.test.ts` |
| UI-016 | P1 | 自动 | 页面运行异常 | 错误边界显示可恢复且不破坏本地数据的提示 | `AppErrorBoundary.test.tsx` |
| UI-017 | P1 | 自动 | API 网络失败 | 转换为本地服务恢复提示 | `api.test.ts` |
| UI-018 | P1 | 自动 | 同一读取并发发起 | 合并请求并复用短缓存 | `api.test.ts` |
| UI-019 | P1 | 自动 | 读取失败 | 失败响应不进入前端缓存 | `api.test.ts` |
| UI-020 | P1 | 自动 | 用户主动刷新 | 强制请求新数据并替换缓存 | `api.test.ts` |

## 7. 搜索、自选与提醒

| ID | 优先级 | 方式 | 测试场景 | 预期结果 | 主要映射 |
| --- | --- | --- | --- | --- | --- |
| AL-001 | P1 | 自动 | 按债券代码、名称和别名搜索 | 返回正确标的并支持深链 | `test_database.py` |
| AL-002 | P1 | 自动 | 搜索演示标的 | 结果明确标出演示 | `test_database.py` |
| AL-003 | P1 | 自动 | 搜索推断代码 | 标记为待核验 | `test_database.py` |
| AL-004 | P1 | 自动 | 自选新增、更新和删除 | SQLite 往返一致 | `test_database.py` |
| AL-005 | P1 | 自动 | 旧版自选数据升级 | 不丢失标的和元数据 | `test_database.py` |
| AL-006 | P1 | 自动 | 可信缓存行情进入自选 | 展示当前值并正确跳回原模块 | `test_v070.py` |
| AL-007 | P0 | 自动 | 提醒条件首次满足 | 触发一次并进入冷却 | `test_alerts.py` |
| AL-008 | P0 | 自动 | 数据不可信、过期或演示 | 不触发提醒 | `test_alerts.py` |
| AL-009 | P1 | 自动 | 指标不属于当前标的类型 | 拒绝创建提醒 | `test_alerts.py` |
| AL-010 | P1 | 自动 | 条件从不满足穿越到满足 | 触发；持续满足不重复触发 | `test_alerts.py` |
| AL-011 | P1 | 自动 | 预览提醒 | 不修改真实触发历史 | `test_alerts.py` |
| AL-012 | P1 | 自动 | 达到每日触发上限 | 抑制后续重复触发 | `test_alerts.py` |
| AL-013 | P1 | 自动 | 静默时段跨越午夜 | 正确判断夜间区间 | `test_alerts.py` |
| AL-014 | P1 | 人工 | 真实 macOS 通知 | 通知标题、对象、数值和深链正确 | 系统通知验收 |

## 8. 研究项目、专题和复盘

| ID | 优先级 | 方式 | 测试场景 | 预期结果 | 主要映射 |
| --- | --- | --- | --- | --- | --- |
| RS-001 | P0 | 自动 | 创建、更新、归档研究项目 | 状态、结论、置信度和时间线完整 | `test_v070.py` |
| RS-002 | P1 | 自动 | 标签包含重复和异常空白 | 规范化并去重 | `researchUtils.test.ts` |
| RS-003 | P1 | 自动 | 项目已归档 | 不再被标记为到期工作 | `researchUtils.test.ts` |
| RS-004 | P1 | 自动 | UTC 午夜附近计算复盘日期 | 使用上海日历日期 | `researchUtils.test.ts` |
| RS-005 | P0 | 自动 | 市场信号写入研究 | 只选择可行动、非演示、非可疑信号 | `researchUtils.test.ts` |
| RS-006 | P1 | 自动 | 研究工作流刚创建 | 下一步指向建立证据，而非错误完成 | `researchWorkflow.test.ts` |
| RS-007 | P1 | 自动 | 项目逐步补齐证据和结论 | 下一步随完成度推进 | `researchWorkflow.test.ts` |
| RS-008 | P1 | 自动 | 初始值进入活动时间线 | 显示初始状态，不伪装为前后变化 | `researchActivity.test.ts` |
| RS-009 | P1 | 自动 | 结论或置信度更新 | 展示 before/after | `researchActivity.test.ts` |
| RS-010 | P1 | 自动 | 活动详情格式损坏 | 忽略异常，不破坏页面 | `researchActivity.test.ts` |
| RS-011 | P0 | 自动 | 证据篮批量提交 | 关联研究对象、项目并生成跨源时间线 | `test_topics.py` |
| RS-012 | P1 | 自动 | 同一证据跨专题提交 | 保留来源专题和目标专题关系 | `test_topics.py` |
| RS-013 | P1 | 自动 | 按研究对象过滤时间线 | 只返回相关证据 | `test_topics.py` |
| RS-014 | P1 | 自动 | 删除专题 | 只清理未被其他项目引用的对象 | `test_topics.py` |
| RS-015 | P0 | 自动 | 项目 JSON 导入 | 校验并恢复证据和对象链接 | `test_topics.py` |
| RS-016 | P1 | 自动 | 规则化项目摘要 | 暴露问题、结论、证据与缺口，不生成投资判断 | `test_topics.py` |
| RS-017 | P1 | 自动 | 专题组件配置越界 | 规范化并限制序列、年份和数量 | `test_topics.py` |
| RS-018 | P1 | 自动 | 专题达到 50 条 | 筛选与读取保持可用，不产生 N+1 连接 | `test_topics.py` |
| RS-019 | P1 | 自动 | 专题时间线分页 | 页面不重复，完整导出不截断 | `test_topics.py`、`topicResearch.test.ts` |
| RS-020 | P1 | 自动 | 证据篮按专题、来源和日期筛选 | 结果正确，批量删除不误删 | `test_topics.py`、`topicResearch.test.ts` |
| RS-021 | P1 | 自动 | 每日复盘使用缓存研究数据 | 不因为外部刷新失败而丢失复盘 | `test_research.py` |
| RS-022 | P0 | 自动 | 每日复盘遇到可疑现券 | 隔离异常，不写成可信异动 | `test_research.py` |
| RS-023 | P1 | 自动 | 核心源仅为缓存 | 不标记为高置信复盘 | `test_research.py` |
| RS-024 | P1 | 自动 | 核心源健康且覆盖完整 | 才允许高置信状态 | `test_research.py` |
| RS-025 | P1 | 自动 | 每周复盘 | 正确汇总项目、任务、反证和复盘节奏 | `test_v070.py` |
| RS-026 | P0 | 自动 | 行动助手草稿 | 只有明确勾选确认后写入，并支持撤销 | `test_research_actions.py` |
| RS-027 | P1 | 自动 | 同一行动草稿重复接受 | 第二次被拒绝 | `test_research_actions.py` |

## 9. FRED、World Bank 与 GDELT

| ID | 优先级 | 方式 | 测试场景 | 预期结果 | 主要映射 |
| --- | --- | --- | --- | --- | --- |
| EX-001 | P0 | 自动 | FRED 有效 Key 请求序列 | 返回观测值、vintage、来源和署名；数值不入库 | `test_macro.py` |
| EX-002 | P0 | 自动 | 未配置 FRED Key | 状态明确为未配置，不伪造本地缓存 | `test_macro.py` |
| EX-003 | P1 | 自动 | FRED 数据存在真实缺失日期 | 变换后继续保留缺失边界 | `test_macro.py` |
| EX-004 | P1 | 自动 | 计算同比 | 使用 FRED 官方 `pc1` 口径 | `test_macro.py` |
| EX-005 | P1 | 自动 | 发布日历查询 | 明确传递时间窗口并完成分页 | `test_macro.py` |
| EX-006 | P1 | 自动 | FRED 连续三次失败 | 打开熔断 | `test_macro.py` |
| EX-007 | P1 | 自动 | FRED 返回 429 或鉴权失败 | 429 重试，鉴权错误单独分类 | `test_macro.py` |
| EX-008 | P0 | 自动 | 保存 FRED 图表证据 | 只保存序列、变换和来源引用，不保存观测值 | `test_v070.py`、`researchUtils.test.ts` |
| EX-009 | P0 | 自动 | World Bank 多页返回和年度缺失 | 正确分页、同年对齐，缺失保持空 | `test_world_bank.py` |
| EX-010 | P1 | 自动 | World Bank 切换视图 | 年份对齐不被破坏 | `test_world_bank.py` |
| EX-011 | P1 | 自动 | World Bank 刷新失败但有缓存 | 明确降级到过期缓存 | `test_world_bank.py` |
| EX-012 | P1 | 自动 | World Bank 长时间运行 | 健康状态和缓存年龄持续更新 | `test_world_bank.py` |
| EX-013 | P1 | 自动 | World Bank 非法经济体、指标或年份范围 | 拒绝请求 | `test_world_bank.py` |
| EX-014 | P1 | 自动 | 直连和系统代理同时可用 | 优先直连，失败后按规则使用代理 | `test_world_bank.py` |
| EX-015 | P0 | 自动 | GDELT 正常查询 | 规范化标题、链接、来源、语言和时间并复用缓存 | `test_gdelt.py` |
| EX-016 | P1 | 自动 | GDELT 刷新失败 | 降级复用过期元数据并明确标注 | `test_gdelt.py` |
| EX-017 | P1 | 自动 | GDELT 查询范围无上限 | 拒绝请求 | `test_gdelt.py` |
| EX-018 | P0 | 自动 | GDELT 缓存超过 512 KB | 拒绝写入，防止无界增长 | `test_gdelt.py` |
| EX-019 | P1 | 人工 | 从 GDELT 线索打开原文 | 链接正确；系统不把匹配结果表示为已确认事实 | 人工验收 |

## 10. 信用观察 R2

| ID | 优先级 | 方式 | 测试场景 | 预期结果 | 主要映射 |
| --- | --- | --- | --- | --- | --- |
| CR-001 | P0 | 自动 | CSV 导入并生成多期历史 | 当前快照、历史、信号和组合均正确 | `test_credit_r2.py` |
| CR-002 | P0 | 自动 | Excel 预览和手工字段映射 | 映射覆盖自动识别并正确导入 | `test_credit_r2.py` |
| CR-003 | P0 | 自动 | 缺少必填字段映射 | 拒绝导入并说明字段 | `test_credit_r2.py` |
| CR-004 | P1 | 自动 | 可选期限列为空 | 允许导入，不伪造期限 | `test_credit_r2.py` |
| CR-005 | P1 | 自动 | 当前视图导出后重新导入 | 数据往返一致 | `test_credit_r2.py` |
| CR-006 | P1 | 自动 | 历史导出 | 保留所有观察日 | `test_credit_r2.py` |
| CR-007 | P0 | 自动 | 历史字段原本为空 | 导出不使用当前值回填历史空值 | `test_credit_r2.py` |
| CR-008 | P0 | 自动 | 导入旧历史快照 | 不覆盖更新的当前快照 | `test_credit_r2.py` |
| CR-009 | P0 | 自动 | 日期、评级、期限、基准全部满足 | 才机械试算利差 | `test_v070.py` |
| CR-010 | P0 | 自动 | 任一门禁缺失 | 不计算利差 | `test_v070.py` |
| CR-011 | P0 | 自动 | 候选行情为演示或部分可信 | 不用于信用辅助 | `test_v070.py` |
| CR-012 | P1 | 自动 | 单券按发行人、文本和关注状态筛选 | 结果正确 | `creditR2.test.ts` |
| CR-013 | P1 | 自动 | 发行人主档筛选 | 名称、行业、地区等条件有效 | `creditR2.test.ts` |
| CR-014 | P1 | 自动 | 组合成员重复添加和删除 | 不重复，状态同步 | `creditR2.test.ts` |
| CR-015 | P1 | 自动 | 组合候选筛选 | 不隐藏已选成员状态 | `creditR2.test.ts` |
| CR-016 | P1 | 自动 | 页签或筛选替换结果区 | 面板回到 sticky 工具栏下方 | `creditR2.test.ts` |
| CR-017 | P1 | 人工 | 大量单券滚动、分页和切换页签 | 不跳到错误位置，工具栏和标题对齐 | 信用滚动验收 |

## 11. AI 助手、页面洞察与安全

| ID | 优先级 | 方式 | 测试场景 | 预期结果 | 主要映射 |
| --- | --- | --- | --- | --- | --- |
| AI-001 | P0 | 自动 | 未配置用户 Key | 拒绝调用并提示配置 | `test_ai_assistant.py` |
| AI-002 | P0 | 自动 | 正常问答 | 使用固定模型，只返回最终答案 | `test_ai_assistant.py` |
| AI-003 | P0 | 自动 | 研究模式附加项目 | 只在研究模式附加；发送前说明最小上下文 | `aiAssistant.test.ts` |
| AI-004 | P0 | 自动 | AI 上下文生成 | 排除完整研究记录正文 | `test_ai_assistant.py` |
| AI-005 | P0 | 自动 | 信用页面上下文 | 排除来源备注和历史明细行 | `test_ai_insights.py` |
| AI-006 | P0 | 自动 | 专题上下文 | 排除笔记正文、新闻正文和完整组件数值 | `test_ai_insights.py` |
| AI-007 | P1 | 自动 | 上下文没有变化 | 指纹稳定，不重复自动生成 | `test_ai_insights.py`、`aiInsights.test.ts` |
| AI-008 | P1 | 自动 | 数据上下文变化 | 缓存摘要标记过期，并进入自动待生成状态 | `test_ai_insights.py` |
| AI-009 | P0 | 自动 | 洞察结果落库 | 只保存最终摘要、模型、指纹和时间，不保存完整提示词 | `test_ai_runtime.py`、`test_ai_insights.py` |
| AI-010 | P1 | 自动 | 每日次数或 token 预算达到上限 | 阻止继续调用 | `test_ai_runtime.py` |
| AI-011 | P1 | 自动 | AI 页面洞察默认配置 | 所有模块默认关闭并需主动授权 | `test_ai_runtime.py` |
| AI-012 | P1 | 自动 | 模型第一次返回空最终答案 | 工作线程重试一次 | `test_ai_insights.py` |
| AI-013 | P0 | 自动 | 响应流超过大小限制 | 在解析前停止读取 | `test_ai_assistant.py` |
| AI-014 | P0 | 自动 | AIHubMix 长时间不响应 | 硬总超时生效 | `test_ai_assistant.py` |
| AI-015 | P0 | 自动 | Key 写入 Keychain | Key 不出现在进程命令行 | `test_settings.py` |
| AI-016 | P1 | 自动 | 模型回答包含常见 Markdown | 正确渲染，不显示原始标记 | `AiAnswerText.test.tsx` |
| AI-017 | P1 | 人工 | AI 抽屉回答很长 | 内容区域可完整滚动，底部操作不遮挡正文 | AI 视觉验收 |
| AI-018 | P1 | 人工 | 页面洞察授权、触发和清除缓存 | 频率、预算、发送范围和清除动作与设置一致 | AI 场景验收 |

## 12. 数据库、迁移、备份和秘密

| ID | 优先级 | 方式 | 测试场景 | 预期结果 | 主要映射 |
| --- | --- | --- | --- | --- | --- |
| DB-001 | P0 | 自动 | 旧市场缓存 schema | 原地兼容迁移，不丢缓存 | `test_cache.py` |
| DB-002 | P0 | 自动 | schema 700/701 项目升级到 800 | 项目和研究数据保留 | `test_v070.py` |
| DB-003 | P0 | 自动 | schema 800 升级到 1201 | 专题新增且旧项目保留 | `test_topics.py` |
| DB-004 | P0 | 自动 | 旧提醒 schema | 规则不丢失 | `test_database.py` |
| DB-005 | P0 | 自动 | 旧自选 schema | 标的和元数据不丢失 | `test_database.py` |
| DB-006 | P0 | 自动 | 旧 FRED 值缓存升级 | 删除观测值，保留引用 | `test_database.py` |
| DB-007 | P0 | 自动 | 尝试保存含 FRED 数值的证据 | 拒绝写入 | `test_database.py` |
| DB-008 | P0 | 自动 | 手工备份和恢复 | 数据库往返一致 | `test_v070.py` |
| DB-009 | P0 | 自动 | 自动备份 | 备份有效、数量有界、近期快照不重复 | `test_backup.py` |
| DB-010 | P0 | 自动 | 临时备份文件损坏 | 原子替换，不留下无效正式备份 | `test_backup.py` |
| DB-011 | P0 | 人工 | 15 份正式 SQLite 备份 | `quick_check`、外键和迁移全部通过 | 发布门禁 |
| DB-012 | P0 | 自动 | FRED Key 写入 Keychain | 密钥不进入数据库、API 响应或命令参数 | `test_settings.py` |
| DB-013 | P0 | 自动 | AIHubMix Key 写入 Keychain | 密钥不进入数据库、API 响应或命令参数 | `test_settings.py` |
| DB-014 | P1 | 人工 | 清空市场缓存 | 不删除项目、证据、自选、提醒或复盘 | 数据健康验收 |
| DB-015 | P1 | 人工 | 恢复历史备份后启动 | 自动迁移，页面可进入，研究数据完整 | 恢复验收 |

## 13. 计算器

| ID | 优先级 | 方式 | 测试场景 | 预期结果 | 主要映射 |
| --- | --- | --- | --- | --- | --- |
| CAL-001 | P1 | 自动 | 平价债券 | YTM 接近票面利率 | `test_calculator.py` |
| CAL-002 | P1 | 自动 | 折价债券 | YTM 高于票面利率 | `test_calculator.py` |
| CAL-003 | P1 | 自动 | ACT/365、ACT/ACT、30/360 | 应计利息随日计数规则正确变化 | `test_calculator.py` |
| CAL-004 | P1 | 人工 | 久期、凸性、DV01 和情景价格 | 输入输出单位、精度和异常提示正确 | 计算器验收 |
| CAL-005 | P1 | 人工 | 非法日期、负面值和缺失现金流 | 阻止计算并提供可理解提示 | 计算器验收 |

## 14. 人工视觉、可访问性与长稳验收

| ID | 优先级 | 方式 | 测试场景 | 预期结果 |
| --- | --- | --- | --- | --- |
| MAN-001 | P1 | 人工 | 1440×900 全页面巡检 | 无横向溢出、遮挡、异常换行或截断 |
| MAN-002 | P1 | 人工 | 1280×800 全页面巡检 | 核心操作可见，卡片和表格不挤压 |
| MAN-003 | P1 | 人工 | 1024×768 全页面巡检 | 导航、筛选和主内容可用 |
| MAN-004 | P1 | 人工 | 市场变化中心 | 摘要、筛选、信号证据和核验入口层级清楚 |
| MAN-005 | P1 | 人工 | 每日复盘发行事件 | 分组标题、计数、时间线圆点和内容左边距一致 |
| MAN-006 | P1 | 人工 | 外汇数据说明侧栏 | 图标、标题、说明和边界文案对齐 |
| MAN-007 | P1 | 人工 | 信用观察长列表 | sticky 区域、滚动和回到结果区行为稳定 |
| MAN-008 | P1 | 人工 | 空数据、部分数据、降级和演示状态 | 每种状态的文案与颜色可区分 |
| MAN-009 | P2 | 人工 | 200% 浏览器缩放 | 核心流程不因缩放不可操作 |
| MAN-010 | P2 | 人工 | 键盘 Tab 导航 | 焦点顺序合理，焦点样式可见 |
| MAN-011 | P2 | 人工 | VoiceOver 基础巡检 | 页面标题、按钮、表单和图表摘要可理解 |
| MAN-012 | P1 | 人工 | 8 小时正常运行 | 无明显内存、FD、线程或请求堆积 |
| MAN-013 | P0 | 人工 | 24 小时长稳与自动备份 | 服务可用，备份有效，后台刷新未失控 |
| MAN-014 | P1 | 人工 | 上游超时、限流、空表和字段变化演练 | 单源隔离、熔断、缓存和恢复符合预期 |
| MAN-015 | P1 | 人工 | 生产构建首次启动 | 前端静态资源、API 深链和刷新均可用 |
| MAN-016 | P1 | 人工 | Safari 与 Chromium 比较 | 关键布局、日期输入、滚动和图表行为一致 |
| MAN-017 | P1 | 人工 | 浅色系统、深色系统及不同字体渲染 | 产品深色主题不受系统主题破坏，中文字体稳定 |

## 15. 自动化测试文件索引

### 后端

| 文件 | 主要覆盖 |
| --- | --- |
| `test_provider.py` | AKShare 适配、交易状态、时间边界、质量、熔断和并发 |
| `test_database.py` | 自选、搜索、历史、日报、旧 schema 和 FRED 存储边界 |
| `test_topics.py` | 专题、证据篮、跨源时间线、项目导入和大规模筛选 |
| `test_v070.py` | 研究项目、备份、发布复盘、信用 R1 和跨版本迁移 |
| `test_research.py` | 日报、研究信号、置信度和异常隔离 |
| `test_research_actions.py` | 行动草稿、确认、重复写入和撤销 |
| `test_credit_r2.py` | 信用导入、历史、导出、组合和字段门禁 |
| `test_macro.py` | FRED、变换、发布日历、重试和熔断 |
| `test_world_bank.py` | 主权比较、分页、年度对齐、缓存和代理 |
| `test_gdelt.py` | 事件元数据、缓存、查询边界和降级 |
| `test_ai_assistant.py` | 模型、Key、上下文、流大小和超时 |
| `test_ai_runtime.py` | 授权、预算和摘要缓存 |
| `test_ai_insights.py` | 上下文裁剪、指纹、队列和自动触发 |
| `test_alerts.py` | 阈值、穿越、冷却、静默和每日上限 |
| `test_fx.py` | 外汇规范化、参考价、时钟和可信时点 |
| `test_cache.py` | 持久缓存、过期读取和旧 schema |
| `test_backup.py` | 自动备份、原子性和保留数量 |
| `test_settings.py` | FRED 与 AI Keychain 安全 |
| `test_calculator.py` | YTM 和日计数规则 |
| `test_aux_worker.py` | 转债备用源和异常行隔离 |
| `test_runtime.py` | 文件描述符和运行时诊断 |
| `test_main.py` | API 生命周期、健康和归档 |

### 前端

| 文件 | 主要覆盖 |
| --- | --- |
| `workspaceMode.test.ts`、`experienceProfiles.test.ts` | 双入口、四类任务和首页映射 |
| `experienceGuide.test.ts` | 新手引导和下一步 |
| `marketChanges.test.ts`、`marketDashboard.test.ts` | 市场变化和驾驶舱 |
| `healthStatus.test.ts`、`marketSafety.test.ts` | 状态、研究可用性和可信使用 |
| `fxUtils.test.ts` | 外汇排序、搜索和精度 |
| `savedViews.test.ts` | 保存视图、兼容与分页 |
| `researchUtils.test.ts`、`researchWorkflow.test.ts` | 研究标签、日期、证据和流程 |
| `researchActivity.test.ts` | 活动时间线 |
| `topicResearch.test.ts` | 专题、分页、筛选和组件可用性 |
| `creditR2.test.ts` | 信用筛选、组合和滚动定位 |
| `aiAssistant.test.ts`、`aiInsights.test.ts` | AI 上下文和触发 |
| `AiAnswerText.test.tsx` | AI Markdown 呈现 |
| `api.test.ts` | 请求缓存、刷新和错误恢复 |
| `visibilityPolling.test.ts` | 前后台轮询 |
| `chartAccessibility.test.ts` | 图表摘要和坐标范围 |
| `AppErrorBoundary.test.tsx` | 页面异常恢复 |
| `sovereignUtils.test.ts` | World Bank 手工刷新行为 |

## 16. 建议的发布阻断条件

出现以下任一情况时，不建议发布：

- 启动器无法在干净 Mac 上完成安装和启动；
- 正式数据库或任一支持的历史备份迁移失败；
- 真实数据被错误标成演示，或演示/过期/可疑数据进入提醒和研究历史；
- 观测时间被推断为未来；
- FRED 观测值、新闻正文、完整提示词或 API Key 被写入 SQLite；
- AI 未授权自动发送或自动修改业务数据；
- 信用利差在字段、日期或期限门禁不满足时仍被计算；
- 单个上游超时能够拖死主服务；
- 核心页面出现横向溢出、操作遮挡或无法滚动；
- 后端、前端、迁移、构建或依赖审计门禁未通过。

## 17. 执行命令

后端：

```bash
PYTHONPATH=backend .venv/bin/pytest backend/tests
.venv/bin/ruff check backend
.venv/bin/pip check
```

前端：

```bash
cd frontend
npm test
npm run lint
npm run build
npm audit --omit=dev
```

数据库检查应在服务停止或使用数据库副本时执行，并同时检查：

```sql
PRAGMA quick_check;
PRAGMA foreign_key_check;
```

测试通过只表示已覆盖的断言成立。公开数据源、真实网络、macOS 通知、长时间运行和视觉可用性仍需要人工验收。

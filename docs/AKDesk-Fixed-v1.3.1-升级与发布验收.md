# v1.3.1 升级与发布验收

日期：2026-11-07。v1.3.0为先完成并review的开发里程碑，v1.3.1为包含其全部能力的当前对外交付候选。实际公开状态以[Release](https://github.com/raistlinsha-plus/akdesk-fixed/releases/tag/v1.3.1)和[Actions](https://github.com/raistlinsha-plus/akdesk-fixed/actions)为准。

## 升级原则

停止旧服务，保留升级前备份，完整解压正式ZIP后启动。新增资产自选可能不被旧程序识别；回退用旧程序和升级前备份，不直接复用升级后研究库。启动与恢复仅对已识别的新增公开行情引用规范化，源备份不改写。FRED既有引用、导出、AI限制不放宽。

## 验收范围

自动测试使用隔离HOME与临时研究库、凭据访问替身，无真实用户Key或研究库、无AI调用。公开源探测只做单次字段连通验证，不等同授权或长期稳定性。浏览器受工具限制，实机视觉、无障碍和外部全新环境冷安装尚未验收。

以下为推送前本机验收结果；远端发布状态单独核对，未完成项不视为通过。

| 项目 | 状态 |
| --- | --- |
| 后端全量Python3.13 | 315项通过 |
| 前端全量 | 147项通过，39个测试文件 |
| Ruff/ESLint/CSS变量/TypeScript | 通过 |
| 正式界面与独立静态演示构建 | 通过 |
| Python3.11/3.12最终矩阵 | 各315项通过 |
| 正式ZIP白名单、秘密与权限检查 | 106个文件；版本、manifest、Markdown链接、脚本权限、SBOM检查通过；无疑似凭据或用户数据库；最终摘要以SHA256SUMS为准 |
| 解压后隔离合成HTTP冒烟 | 通过：HTML/资源、health版本、目录/FRED no-store、黄金/指数/ETF/日线、非法ID、复盘基线、备注及ETF引用的保存/幂等/严格字段校验 |
| 依赖 | Python pip check通过；官方npm registry生产依赖审计0项漏洞 |
| GitHub源码、Release资源和Pages | 不以本机通过代替远端成功；最终状态与运行记录列于本版Release |
| Inkstone文档同步 | 单独在本机同步记录中核对，不将文档准备等同已导入 |

完整修复依据见[Review记录](./AKDesk-Fixed-v1.3.1-开发与Review记录.md)，可执行场景见[测试清单](./AKDesk-Fixed-v1.3.1-测试用例清单.md)。

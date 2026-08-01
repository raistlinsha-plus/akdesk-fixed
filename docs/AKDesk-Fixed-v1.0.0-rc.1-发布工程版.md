# AKDesk Fixed v1.0.0-rc.1「发布工程候选版」

> 发布日期：2026-07-31  
> 基线：v0.18.0「低门槛交付版」  
> 范围：发布工程、依赖复现、迁移恢复、洁净度与长稳门禁  
> 状态：候选版；业务功能冻结

## 1. 本版本解决什么

v0.18.0 已形成完整的本地市场观察和投研工作流，但开发目录包含虚拟环境、前端依赖、测试缓存、用户数据库和历史备份，不能直接作为可重复交付的产品包。

rc.1 不增加业务页面，集中解决：

- 安装依赖是否可复现；
- 发布包是否只包含运行所需文件；
- 是否错误带入用户数据或 API Key；
- 历史研究库是否可以自动迁移和恢复；
- 第三方组件能否被机器和人工识别；
- 自动化测试是否有未解释告警；
- 本地服务在持续访问下是否出现资源增长。

## 2. 发布工程

### 2.1 精确 Python 依赖

新增：

- `backend/requirements.txt`：保留便于维护的顶层约束；
- `backend/requirements.lock`：锁定完整生产依赖及传递依赖。

启动器计算锁文件 SHA-256。锁文件变化或依赖缺失时才重新安装，成功后把摘要写入当前 `.venv`；不会把 stamp 放进发布包。

全新安装演练发现部分 python.org macOS Python 没有默认 CA 文件。启动器会优先复用系统 Python 已安装的 certifi CA；如果证书仍不可用，中文错误信息会提示运行 Python 安装目录中的 `Install Certificates.command`。

### 2.2 一键发布

执行：

```bash
.venv/bin/python scripts/release.py
```

脚本会：

1. 检查后端、前端、package lock 和启动器版本一致；
2. 执行前端生产构建；
3. 生成 SBOM 和第三方组件声明；
4. 只收集后端源码、精确依赖、生产前端、启动器、许可证和文档；
5. 检查 Markdown 本地链接；
6. 扫描疑似凭据；
7. 拒绝数据库、缓存、虚拟环境和开发依赖；
8. 生成文件级发布清单；
9. 创建 ZIP 并重新解压复验；
10. 生成归档 SHA-256。

### 2.3 发布包边界

明确排除：

- `.venv`；
- `node_modules` 和 npm 缓存；
- pytest、Ruff 和 Python 字节码缓存；
- `data/`；
- SQLite 数据库、WAL 和 SHM；
- 自动备份和历史备份；
- 本机 Keychain 内容；
- FRED、AIHubMix 或其他 API Key。

## 3. 软件物料清单

- `SBOM.cdx.json`：CycloneDX 1.5 机器可读清单；
- `THIRD_PARTY_NOTICES.md`：Python 和前端生产依赖的版本及许可证声明；
- `RELEASE_MANIFEST.json`：发布包内每个文件的路径、体积、权限和 SHA-256；
- `SHA256SUMS`：最终 ZIP 的 SHA-256。

AKDesk Fixed 采用 MIT License。外部数据、公开页面和 API 分别受其自身条款约束，MIT License 不授予第三方数据再分发权。

## 4. 数据库迁移与恢复门禁

执行：

```bash
PYTHONPATH=backend .venv/bin/python scripts/check_migrations.py
```

门禁只操作临时副本，不修改正式研究库或历史备份。

覆盖真实历史 schema：

- 701；
- 800；
- 900；
- 1100；
- 1201；
- 1301。

每个样本必须：

1. 自动升级至 schema 1600；
2. 核心业务表记录数量不减少；
3. `PRAGMA quick_check` 返回 `ok`；
4. `PRAGMA foreign_key_check` 无结果；
5. 迁移记录齐全；
6. 可以生成有效备份；
7. 可以恢复到新数据库；
8. 损坏文件必须被拒绝。

## 5. 长稳门禁

执行短时验证：

```bash
.venv/bin/python scripts/soak_test.py \
  --duration-seconds 300 \
  --report .tmp/soak-report.json
```

如需正式长稳：

```bash
.venv/bin/python scripts/soak_test.py \
  --duration-seconds 86400 \
  --interval-seconds 30 \
  --report .tmp/soak-24h.json
```

脚本使用隔离临时数据目录、演示模式和独立端口，循环访问市场、外汇、研究、连接器和数据健康 API，并检查：

- 服务进程未异常退出；
- HTTP 请求无失败；
- RSS、线程和文件句柄未越过增长容差；
- SQLite 完整性和外键正常；
- 自动备份可以生成并通过 `quick_check`；
- 停止时可以正常收到 `SIGTERM`。

## 6. 测试基线

候选版发布前必须通过：

- 后端 pytest：149 项；
- 前端 Vitest：70 项；
- Ruff；
- ESLint；
- CSS 自定义属性检查；
- TypeScript；
- Vite 生产构建；
- `pip check`；
- npm 生产依赖审计；
- 真实历史数据库迁移恢复；
- 发布包生成、解压和自检；
- macOS 启动、重复启动和停止。

## 7. 升级和回退

升级前：

1. 停止旧服务；
2. 在研究项目页生成备份；
3. 保留旧目录；
4. 使用候选版启动；
5. 在数据健康页确认版本和数据库状态。

全新发布包默认把运行数据保存在 `~/Library/Application Support/AKDesk Fixed/`，因此后续把程序解压到新目录时仍会复用同一数据目录。已有旧版项目如果检测到自身 `data/` 中存在数据库或备份，则继续使用原目录，不做静默移动；数据健康页的服务信息会显示实际路径。

研究数据库 schema 仍为 1600，本版不执行新的业务数据迁移。

需要回退时，停止候选版并重新打开旧目录。不要在服务运行时直接替换 SQLite 文件。

## 8. 已知边界

- 当前仍是源码形态的 macOS 本地启动器，不是签名、公证的 `.app`；
- 发布包不包含 Python，需要用户具备 Python 3.11—3.13；
- AKShare 等公开数据源不提供机构级 SLA；
- 本版本不是交易、估值、会计、正式评级或机构多人系统；
- RC 兼容矩阵发现 NumPy 2.5.1 不支持 Python 3.11，已将锁定版本校准为 2.4.6；Python 3.11、3.12、3.13 均完成 149 项后端测试。
- rc.1 通过后只修复发布阻断问题，再封板 v1.0.0。

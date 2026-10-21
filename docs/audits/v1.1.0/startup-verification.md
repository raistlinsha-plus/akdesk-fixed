# v1.1.0 启动器集成验收

执行日期：2026-10-22。范围：第一轮为源码隔离副本的启停与错误恢复；第二轮为候选正式ZIP干净解压、真实依赖安装、核心API与启停。

## 第一轮：源码副本环境与隔离

- 实测环境：macOS 26.6.2、arm64、Python 3.13.3；应用健康接口返回版本1.1.0。
- 先只读检查8765端口，开始时没有监听服务；没有结束任何预先存在的用户进程。
- 使用仓库忽略目录 `.tmp/v1.1-startup-verification/`，复制启动/停止脚本、后端应用、锁文件、预检与已构建前端。所有运行数据库和备份均由本次副本创建。
- 显式隔离 `HOME` 与 `AKDESK_DATA_DIR`；通过 `/api/v1/info` 断言数据目录确实属于测试副本，不使用用户已有数据库。
- 设置 `AKDESK_NO_BROWSER=1`、`AKDESK_NONINTERACTIVE=1`、`AKDESK_DEMO=1`、`AKDESK_NOTIFICATIONS=0`，清空本测试进程中的FRED/AI凭据环境变量。未打开浏览器，未请求真实行情或AI服务。
- 复用已安装的解释器和依赖；隔离 `.venv/bin/python` wrapper禁止正常用例执行pip安装，仅将其他命令转发到现有解释器。依赖hash stamp写在隔离目录，未对原环境执行安装/升级。
- `security` 命令由测试stub截获并返回“未找到凭据”；两次应用启动共记录两次stub命中，没有读取真实Keychain。

这一轮是**已安装依赖条件下的隔离集成验收**，不是全新Mac、干净ZIP首次安装或真实证书链验收。干净安装的实际执行结果另见第二轮。

## 第一轮逐项结果

| 用例 | 方式与实际结果 | 结论 |
| --- | --- | --- |
| 不受支持的Python | 显式 `AKDESK_PYTHON` 指向模拟版本探测失败的解释器wrapper；启动器exit1，1.004秒内显示“需要Python 3.11–3.13” | 版本拒绝分支符合预期；未实际安装Python3.10 |
| 依赖证书错误 | 在隔离环境强制依赖安装分支，pip wrapper返回 `CERTIFICATE_VERIFY_FAILED`；exit1，0.669秒，显示证书恢复及不要关闭TLS校验的指引 | 错误分类符合预期；不证明真实TLS握手结果 |
| 依赖网络错误 | 同一隔离分支模拟包源连接失败；exit1，0.201秒，显示检查网络/代理/包源并可重试的指引 | 错误分类符合预期；没有故意破坏实际网络 |
| 无响应端口：启动 | 本次创建的socket监听8765但不回应HTTP；启动器exit1，2.079秒，提示无响应进程占用 | 探测有界，未启动第二个服务 |
| 无响应端口：停止 | 对相同测试socket运行独立停止器；exit1，2.454秒，提示无法确认AKDesk身份；随后确认占用PID仍在监听 | 安全拒绝，未误杀本次socket；未测试其他真实应用 |
| 正常启动 | 隔离副本启动Uvicorn，健康接口200/v1.1.0；info确认demo模式及隔离数据目录 | 已安装依赖下启动成功 |
| 重复启动 | 服务运行时再次调用启动器；exit0，0.020秒，提示服务已运行；前后健康接口的进程PID相同 | 复用同一进程，没有重复启动 |
| 原终端Control+C | 向启动服务的真实PTY发送Ctrl+C；出现application shutdown complete、finished server process，终端命令exit0；随后8765无监听 | 正常完成应用生命周期关闭并释放端口 |
| 独立停止器 | 再次启动隔离应用后运行 `stop-macos.command`；停止器exit0，0.305秒，提示已停止；服务输出完整shutdown日志，8765无监听 | 独立停止成功 |

独立停止由SIGTERM触发。该次服务PTY工具回报exit1，而停止器exit0，应用生命周期完整关闭且端口已释放；此处如实保留两种返回信息，不将服务会话工具返回码混记为启动失败或停止器失败。

## 本次发现与修复

`stop-macos.command` 原先调用 `/api/v1/info` 的curl没有连接/总超时；当8765存在无响应监听时，停止器可能长期等待。

本次将其改为与启动器相同的 `--connect-timeout 1 --max-time 2`。上表的无响应停止结果是在修复后执行，确认2.454秒内安全拒绝，未向未确认进程发送信号。脚本语法检查及diff空白检查一并完成。

## 第二轮：候选正式ZIP干净首次安装

验收对象：`.tmp/v1.1-release-candidate/AKDesk-Fixed-v1.1.0.zip`。本轮候选包SHA-256：

```text
b86b40f21ee09255d6630465e096d0068b4e38c7d914c7ef68c77381e82ab60a
```

### 安装条件

- 解压到新的 `.tmp/v1.1-clean-install-20261022/`，确认此前不存在 `.venv`；ZIP解压后的启动脚本已保留可执行权限，无需另行chmod。
- `AKDESK_PYTHON` 显式指向系统Python3.13.3，验证 `sys.prefix == sys.base_prefix`；不复用第一轮的venv或python wrapper。
- 使用独立HOME、运行数据与pip缓存；设置 `PIP_CONFIG_FILE=/dev/null`，显式使用公开 `https://pypi.org/simple`，不读取用户pip配置。
- **显式提供 `PIP_CERT`，指向测试机已有的已知certifi CA文件**。未关闭TLS校验，未设置trusted-host绕过。因此这是“提供有效CA条件下”的真实安装，不代表缺失CA的机器无需恢复步骤。
- 仍以 `security` stub禁止真实Keychain读取，清空FRED/AI凭据环境变量，采用demo模式、不自动打开浏览器。
- 本轮仅Keychain被stub；创建venv、pip下载与安装均由正式包原启动脚本实际执行，没有模拟pip结果。

### 实际结果

| 项目 | 实际检查 | 结果 |
| --- | --- | --- |
| 全新环境创建 | 启动器显示创建独立Python环境，从不存在的`.venv`创建本轮环境 | 完成 |
| 锁定依赖安装 | 公开PyPI真实下载安装，逐项比较已安装元数据与发布包锁文件 | 55项精确版本全部一致，含AKShare1.19.1 |
| 依赖一致性 | 使用新venv执行`python -m pip check` | `No broken requirements found.` |
| 安装stamp | 比较新venv stamp与包内requirements.lock的SHA-256 | 一致 |
| 本地服务 | `/api/v1/health`、`/api/v1/info` | HTTP200、v1.1.0、demo模式；data目录断言为本轮隔离目录 |
| 核心数据API | `/api/v1/rates`、`/api/v1/curves`、`/api/v1/futures` | 均HTTP200，有数据且`meta.demo=true` |
| 每日复盘 | `/api/v1/research/daily-report` | HTTP200，5项逐源元数据均明确为demo |
| 诊断摘要 | `/api/v1/diagnostics` | HTTP200、版本正确；不含本次绝对测试路径，隐私标识正确 |
| 重复启动 | 再次运行包内启动器，前后查询进程ID | exit0，复用同一PID，未重复启动 |
| Control+C | 向本次启动PTY发送真实Ctrl+C | 正常生命周期关闭，命令exit0，8765端口释放 |

本轮没有将演示API成功描述为真实行情源成功，也没有使用用户原有数据库。另在18769启动同一干净包、独立qa-data的临时demo服务供后续浏览器验收；其页面结果与清理由发布负责人另行记录。

候选包后续会因收录本验收文档而重新生成。最终发布应核对应用代码、启动脚本和锁文件未变，并登记最终包哈希；如这些核心内容变化，需要重新执行受影响门禁，不能直接把候选哈希当作最终包哈希。

### 诊断单文件修复后的复核

后续页面验收发现诊断状态表达需校准。停止临时QA服务后，仅将解压副本的 `backend/app/diagnostics.py` 替换为仓库修复版本，逐字节确认一致；没有重装依赖或修改锁文件。此时解压副本已不等同于上方候选ZIP的完整原始字节内容，最终包需重新生成。

同一隔离环境重启后：首次诊断的15个`not_checked`来源全部显示`trust_level=unavailable`；主动请求资金、曲线与期货三个demo模块后，再次诊断确认这3项均为`error_category=demo_mode`且可信状态为unavailable，其余12个未检查项仍为unavailable，版本保持1.1.0。该检查验证新诊断逻辑；原有干净安装的依赖匹配与启停结论不被用来替代此项复核。

## 未覆盖与后续门禁

- 第二轮已覆盖本环境、提供有效CA条件下的候选ZIP真实安装，但不能推导Python3.11/3.12全新环境、其他网络/地区的PyPI可用性、证书缺失后的实际恢复、Finder首次安全提示或真实Keychain授权。
- 没有执行用户旧数据库迁移/恢复；本测试不读取用户已有研究内容。
- 本记录未执行浏览器操作，不替代页面、在线演示、打印或可访问性验收。
- 第一轮日志/模拟wrapper保留在忽略的 `.tmp/v1.1-startup-verification/`；第二轮干净环境和API核验摘要保留在 `.tmp/v1.1-clean-install-20261022/`。本公开记录不包含个人绝对路径、API Key或研究正文。
- 上述8765验收服务及占端口fixture均已结束，8765端口无监听；临时18769浏览器QA服务由发布负责人后续停止。

最终包与其他发布门禁统一记录在 [发布与验收记录](../../AKDesk-Fixed-v1.1.0-发布与验收记录.md)；第一轮模拟错误分支与第二轮真实安装应保持分开记录。

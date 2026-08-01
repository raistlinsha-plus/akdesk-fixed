# 安全政策

## 支持范围

当前只为最新正式版本提供安全修复。请先确认问题可以在 [最新 Release](https://github.com/raistlinsha-plus/akdesk-fixed/releases/latest) 中复现。

## 私下报告漏洞

请使用 GitHub 仓库 Security 页面中的 **Report a vulnerability** 私下提交安全报告。报告建议包含：

- 受影响版本与 macOS/Python 版本；
- 漏洞类型、影响范围和最小复现步骤；
- 仅用于验证的脱敏截图或日志；
- 你认为可行的缓解措施。

如果私密报告入口暂时不可见，请新建一个不含漏洞细节的 Issue，标题写 `[SECURITY CONTACT REQUEST]`，维护者会建立私下沟通方式。

请勿在公开 Issue 中披露利用方法、API Key、数据库、账户信息、研究材料或其他敏感内容。维护者会尽快确认收到报告，在完成评估和修复前与你协调披露时间。

## 凭据与本地数据

AKDesk Fixed 的 FRED 和 AIHubMix Key 应保存在 macOS Keychain 或环境变量中，不应写入代码、SQLite、日志、截图或导出文件。发现疑似泄漏时，请先在对应服务撤销并轮换 Key，再提交私密报告。

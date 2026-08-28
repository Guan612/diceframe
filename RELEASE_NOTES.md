# DiceFrame v2.4.1-beta.1

> 这是预览版本，主要用于验证 Windows 便携版与托管 Docker 的自动更新流程。重要数据请提前备份。

## 中文

### 本次更新

- **减少更新误回滚**：新版本启动后，偶发的连接重置或短暂不可用不再立即触发回滚；只有健康检查持续失败才会恢复旧版本。
- **统一更新等待策略**：Windows 便携版与托管 Docker 现在使用一致的启动等待、观察期和连续失败容错规则，存档较多或设备较慢时更可靠。
- **改进 Docker 更新诊断**：健康检查遵循更新包声明的接口路径，并在失败时显示进程退出、接口异常或版本不匹配等更具体的原因。
- **安全设置布局**：无本地证书时，证书指纹占位卡片会与访问保护卡片并排显示，并继续随窗口宽度自动适配。

### 下载与校验

- Windows 便携版：`DiceFrame-v2.4.1-beta.1-windows-portable.zip`
- Windows 源码包：`DiceFrame-v2.4.1-beta.1-windows.zip`
- Docker 托管更新：`DiceFrame-v2.4.1-beta.1-docker-update-linux-amd64.zip`
- 手动下载时，请使用 Release 中的 `SHA256SUMS` 统一校验。

## English

> This is a preview release intended primarily to verify automatic updates for Windows portable and managed Docker installations. Back up important data before upgrading.

### What's changed

- **Fewer false update rollbacks**: A transient connection reset or brief health-check interruption no longer rolls back a newly started version immediately. Rollback now requires a continuous health-check failure.
- **Aligned update timing**: Windows portable and managed Docker now use matching startup, probation, and continuous-failure tolerance policies for more reliable updates on slower devices or installations with more saved games.
- **Better Docker update diagnostics**: Health checks follow the path declared by the update package and report clearer process-exit, endpoint, and version-mismatch failures.
- **Security settings layout**: When no local certificate exists, the certificate fingerprint placeholder is aligned beside Access Protection and remains responsive at narrower widths.

### Downloads and verification

- Windows portable: `DiceFrame-v2.4.1-beta.1-windows-portable.zip`
- Windows source: `DiceFrame-v2.4.1-beta.1-windows.zip`
- Managed Docker update: `DiceFrame-v2.4.1-beta.1-docker-update-linux-amd64.zip`
- For manual downloads, verify all archives with the `SHA256SUMS` file attached to the Release.

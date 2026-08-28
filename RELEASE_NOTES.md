# DiceFrame v2.4.1

## 中文

DiceFrame v2.4.1 带来统一的多人跑团体验、高级 DND5E 规则支持、冒险包管理、移动端游玩能力，以及更可靠的更新和问题排查工具。

### 本次更新

- **统一游玩流程**：剧情、公共消息、行动输入、队伍状态和 GM 控制台回到同一条对局流程；帮助内容不再打断正常游玩。
- **高级 DND5E 规则**：加入角色创建、角色中心、法术与资源、休息、升级资格和规则校验，并由服务端维护权威状态。
- **AI GM 与冒险推进**：支持根据玩家行动推进剧情、收集多人行动、处理检定和唤醒符合剧情的遭遇；GM 仍可随时裁定和接管。
- **多人战斗**：提供先攻、回合、移动、攻击、伤害、敌方行动、准备状态和公共战斗历史的同步流程。玩家只能操作自己的角色，GM 管理遭遇和战役状态。
- **冒险包**：支持可视化新建、复制、编辑、校验、导入、导出、删除和 AI 草稿。冒险包提供剧情结构，世界书继续负责世界背景；两者可以组合使用但不会互相覆盖。
- **稳定重开**：对局会固定冒险包的 identity、版本和内容摘要；内容缺失或被修改时会明确报告，而不是静默切换到另一套场景。
- **叙事视角**：创建对局时可选择第一人称或第三人称叙事，GM 也可在对局中调整；该能力适用于所有规则，而非 DND5E 专属设置。
- **连接安全**：设置中新增“安全”页，可在 HTTP、本地自签名 HTTPS 与受信任 HTTPS 之间切换，并支持为域名或符合条件的公网 IP 申请和自动续期 Let’s Encrypt 证书。
- **语音输入**：可配置 OpenAI 兼容的语音识别模型，在 HTTPS 或 localhost 环境中通过行动输入框旁的麦克风按钮把语音转为文字。
- **移动端与联机**：改进移动端导航、对局界面、地图、角色和多人连接流程，并改善独立 Web 前端的连接体验。
- **运行日志与排障**：新增按天轮转、默认保留 30 天的运行日志，可在设置中查看、清除或导出给开发者；DF 助手可以分析脱敏后的日志，帮助定位常见问题。
- **模型请求控制**：普通模型请求超时可独立配置，不再与连接测试超时绑定，长篇生成与临时连通性检查可以使用不同等待时间。
- **托管 Docker 更新**：容器内支持下载、校验、健康检查、观察期切换和失败回滚；当前与上一应用版本独立保存，业务数据不随版本切换。
- **更新可靠性**：改进 Windows 便携版与托管 Docker 的运行时依赖校验、启动等待和连续失败判断，减少慢速设备、存档较多或短暂断连造成的误回滚，并修复 Docker 更新包缺少加密依赖时无法启动的问题。
- **更新包校验**：Release 使用统一的 `SHA256SUMS` 清单，便于手动下载和新版更新器校验。
- **兼容性**：DND5E 专属机制保持在高级 DND5E 规则边界内，不会自动改变传统规则、CoC、赛博朋克或 generic d20 的玩法。

### 升级提示

- 升级前请备份完整的 `data/` 文件夹。
- Windows 便携版、源码包和托管 Docker 均可使用各自的应用内更新流程；只有涉及 Python ABI、系统库、字体或 launcher 协议变化时，Docker 才需要更新基础镜像。
- Docker Update 当前支持 `linux-amd64`。

### 下载与校验

- Windows 便携版：`DiceFrame-v2.4.1-windows-portable.zip`
- Windows 源码包：`DiceFrame-v2.4.1-windows.zip`
- Docker 托管更新：`DiceFrame-v2.4.1-docker-update-linux-amd64.zip`
- 手动下载时，请使用 Release 中的 `SHA256SUMS` 统一校验。

## English

DiceFrame v2.4.1 brings a unified multiplayer play flow, advanced DND5E rules, adventure-bundle management, improved mobile play, and more reliable updates and diagnostics.

### What's new

- **Unified play flow**: Narrative, public messages, action input, party state, and the GM console now follow one play flow. Help content no longer interrupts normal play.
- **Advanced DND5E rules**: Character creation, character center, spells and resources, rests, advancement eligibility, and rules validation are backed by authoritative server state.
- **AI GM and adventure progression**: Player actions can advance the story, collect multiplayer actions, resolve checks, and awaken encounters that fit the current narrative. The GM can always adjudicate or take over.
- **Multiplayer combat**: Initiative, turns, movement, attacks, damage, enemy actions, readiness, and public combat history are synchronized. Players control only their own characters while the GM manages encounters and campaigns.
- **Adventure bundles**: Visual create, copy, edit, validate, import, export, delete, and AI-draft workflows are available. Adventure bundles provide optional story structure while lorebooks continue to define world context; they can be combined without overwriting each other.
- **Deterministic resume**: Games pin an adventure identity, version, and content digest. Missing or changed content is reported explicitly instead of silently switching scenes.
- **Narrative perspective**: Choose first- or third-person narration when creating a game, and let the GM adjust it during play. This setting works across all rulesets rather than being specific to DND5E.
- **Connection security**: A new Security settings page can switch between HTTP, local self-signed HTTPS, and trusted HTTPS, with Let’s Encrypt issuance and automatic renewal for domains or eligible public IP addresses.
- **Voice input**: Configure an OpenAI-compatible speech-recognition model and dictate actions from the microphone button beside the action composer when using HTTPS or localhost.
- **Mobile and multiplayer connectivity**: Navigation, play, maps, characters, and peer connection flows are improved for mobile, along with standalone Web frontend connectivity.
- **Runtime logs and diagnostics**: Daily-rotated runtime logs retain the latest 30 days by default and can be viewed, cleared, or exported for developers from Settings. DF Assistant can analyze redacted logs to help diagnose common issues.
- **Model request controls**: Normal model request timeout is configurable independently from connection-test timeout, so long generations and quick connectivity checks can use different limits.
- **Managed Docker updates**: Containers can download, verify, health-check, probation-test, switch, and roll back application versions while keeping current and previous payloads separate from business data.
- **Update reliability**: Runtime dependency checks, startup waits, and continuous-failure handling are improved for Windows portable and managed Docker updates. This reduces false rollbacks on slower devices, installations with many saved games, or brief connection interruptions, and fixes Docker startup failures caused by missing cryptography dependencies.
- **Update verification**: Releases use one unified `SHA256SUMS` manifest for manual downloads and newer updater clients.
- **Compatibility**: DND5E-specific mechanics stay within the advanced DND5E rules boundary and do not automatically change traditional rules, CoC, cyberpunk, or generic d20 gameplay.

### Upgrade notes

- Back up the complete `data/` directory before upgrading.
- Windows portable, source-package, and managed-Docker installations can use their respective in-app update flows. Docker needs a base-image update only when the Python ABI, system libraries, fonts, or launcher protocol change.
- Docker Update currently supports `linux-amd64`.

### Downloads and verification

- Windows portable: `DiceFrame-v2.4.1-windows-portable.zip`
- Windows source: `DiceFrame-v2.4.1-windows.zip`
- Managed Docker update: `DiceFrame-v2.4.1-docker-update-linux-amd64.zip`
- For manual downloads, verify all archives with the `SHA256SUMS` file attached to the Release.

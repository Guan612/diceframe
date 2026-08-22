# DiceFrame v2.3.0-beta.2

## 中文

DiceFrame 2.3.0-beta.2 是 2.3 系列的第二个预览版，重点完善 AI 服务配置、语音与图片能力，并修复战斗判定和断线续流的一致性问题。

### 新增

- **统一 AI 服务商与模型配置**：集中维护服务商、Base URL、API Key 和模型目录，并在独立页面为主模型、向量模型、TTS、语音识别与图片生成分配模型。旧版内联配置继续兼容，无需强制迁移。
- **内置图片生成**：可通过 OpenAI 兼容接口生成场景图、头像、物品图和地图背景；生成结果会保存为游戏素材，未配置时不影响现有玩法。
- **云端语音识别**：支持 OpenAI 兼容的音频转写接口，玩家可在行动输入框旁录音并将识别文本直接填入输入框。
- **免费 Edge TTS**：新增微软 Edge 在线音色，无需 API Key 或 Base URL，可直接用于 GM 和角色朗读。

### 改进与修复

- **AI 配置帮助与连接测试**：恢复服务商和模型配置帮助，以 DeepSeek 为示例；连接测试超时可在高级设置中配置为 5–300 秒。
- **战斗检定一致性**：战斗命中与暴击统一以服务端 `CheckResult` 为准，不再二次掷命中骰；重试不会重复掷骰或重复扣血，异常缺少检定结果时会安全停止结算。
- **断线续流**：游戏事件流使用稳定游标恢复，网络抖动或页面恢复时减少事件丢失和重复展示，同时保持旧客户端兼容。
- **多人和移动端体验**：直连邀请码与玩家身份绑定；房主和玩家视图共用布局规则，修复移动端日志区、卡片遮挡和输入区排列问题。
- **规则与骰子可靠性**：统一 D&D、CoC 等规则的检定入口与奖惩骰行为，并加强长期战役和多人权限边界校验。
- **设置页布局**：高级设置新增项目后仍能稳定排列；顶部状态卡保持单排，可横向查看完整信息。

### 容器镜像

- 本预览版发布 `ghcr.io/diceframe/diceframe:2.3.0-beta.2` 和 `docker.io/falconku/diceframe:2.3.0-beta.2`。
- 预览版不会更新 `latest`；`latest` 仍只指向正式版。

### 已知限制

- 玩家直连仍为实验性功能：对称 NAT 或严格防火墙可能阻止连接，房主必须保持 DiceFrame 和房间在线。
- Edge TTS 使用微软在线朗读接口，服务协议变化时可能需要升级依赖。
- 图片生成和云端语音识别需要用户自行配置兼容服务；P2P 直连模式不传输录音音频。

### 下载指南

- **普通 Windows 用户**：下载 `DiceFrame-v2.3.0-beta.2-windows-portable.zip`。
- **源码运行用户**：下载 `DiceFrame-v2.3.0-beta.2-windows.zip`。
- `.sha256` 是更新校验文件，普通用户不需要手动下载。

## English

DiceFrame 2.3.0-beta.2 is the second preview of the 2.3 series. It focuses on AI service configuration, speech and image capabilities, and consistent combat resolution and stream recovery.

### New

- **Unified AI providers and model routing**: manage providers, base URLs, API keys, and model catalogs in one place, then assign models for chat, embeddings, TTS, transcription, and image generation on a dedicated page. Legacy inline settings remain compatible and do not require forced migration.
- **Built-in image generation**: generate scene art, portraits, item images, and map backgrounds through OpenAI-compatible APIs. Generated assets persist with the game, while unconfigured installations continue to work normally.
- **Cloud speech recognition**: use OpenAI-compatible audio transcription endpoints to record beside the action input and insert recognized text directly into the editor.
- **Free Edge TTS**: Microsoft Edge online voices are available without an API key or base URL for GM and character narration.

### Improvements and Fixes

- **AI setup help and connection tests**: provider and model help is restored with DeepSeek as the example. Connection-test timeout is configurable from 5 to 300 seconds in advanced settings.
- **Consistent combat checks**: combat hits and criticals now use the server `CheckResult` as the sole authority, without a second attack roll. Retries do not reroll or apply damage twice, and missing check results fail safely.
- **Stream recovery**: game event streams resume from stable cursors after network interruptions or page recovery, reducing missing or duplicated events while remaining compatible with older clients.
- **Multiplayer and mobile UX**: direct-connect invitations are bound to player identities; host and player views share layout rules, with fixes for mobile logs, overlapping cards, and action controls.
- **Reliable rules and dice**: D&D, CoC, and other bundled rules share consistent check planning and bonus/penalty behavior, with stronger long-campaign and multiplayer authority validation.
- **Stable settings layout**: advanced settings remain aligned as options are added, and the top status cards stay on one horizontally scrollable row without truncating their content.

### Container Images

- This preview publishes `ghcr.io/diceframe/diceframe:2.3.0-beta.2` and `docker.io/falconku/diceframe:2.3.0-beta.2`.
- Preview releases do not update `latest`; `latest` remains reserved for stable releases.

### Known Limits

- Player-to-player direct connect remains experimental: symmetric NAT or strict firewalls may prevent connections, and the host must keep DiceFrame and the room online.
- Edge TTS relies on Microsoft's online read-aloud interface and may require dependency updates if that service changes.
- Image generation and cloud transcription require a user-configured compatible service. P2P direct mode does not transport recorded audio.

### Download Guide

- **Regular Windows users**: download `DiceFrame-v2.3.0-beta.2-windows-portable.zip`.
- **Source-run users**: download `DiceFrame-v2.3.0-beta.2-windows.zip`.
- `.sha256` files are update checksums; regular users do not need to download them manually.

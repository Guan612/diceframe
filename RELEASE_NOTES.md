# DiceFrame v2.5.9

> 正式版：包含 **v2.5.9-beta.1 的全部变更**（德语支持与长文本语言布局修复），并新增 D&D 2024 AI 队友（战斗 / 代检定 / 战斗外施法）、检定规划器的物品与 NPC 上下文，恢复 GM 流程两列布局，修复多人幸运选择等待可靠性。

## 中文

### 新增内容（v2.5.9-beta.1 之后）

- **D&D 2024 AI 队友战斗**：队友是"己方角色"而不是友方怪物，全链路走同一权威 validate / resolve / apply——开战先攻 = 玩家 + 活跃队友 + 敌人；敌我、治疗、增益、攻击目标全部按阵营（side）判定；队友武器攻击走与玩家相同的装备 / 目录确定性链；队友 HP / 法术位 / 专注 / 状态写回 `ruleset_state.party.companions[*].ruleset_character` canonical 权威。AI 队友自动回合按确定性优先级行动（治疗濒危己方 → 攻击最近 / 低血敌人 → 移动 → Dodge → 结束回合），提交权威为 GM 自动化，玩家伪造队友意图会被服务端拒绝；0 HP 队友跳过回合，队友死亡不触发玩家团灭判定。
- **队友代检定与协助**：检定请求新增 `actor_ref`（缺省 `player:<uid>`，旧路径完全兼容）——"让米拉去推门"用米拉的力量 / 运动做检定；"米拉帮我"是玩家检定 + 队友协助，规则声明 `assistance_grants` 时给优势。匹配显式前缀 / 玩家与队友名字，精确优先、歧义拒绝、不猜测叙事 NPC；安全网按 actor_uid 去重，队友检定不会被覆盖成玩家检定。
- **战斗外施法**：新增 `exploration.cast_spell` 意图（仅非战斗中、玩家本人）：校验法术合法性 / 已知 / 法术位 / 目标 / 专注；复用 canonical `spellcasting.class.slots_current`，不建第二份资源；确定性治疗 / 增益直接结算，伤害类确定性效果在探索态拒绝；无确定性效果的已知法术扣位后交叙事层（`resolution=narrative`），禁止模型改数值。
- **检定规划器物品与 NPC 上下文**：回合检定规划器在决定是否检定前可见行动者已有的物品摘要（小背包完整、大背包确定性筛选，每人最多 20 条）与明确 NPC 目标的关系摘要——"用已有的钥匙开门"与徒手撬锁按不同行动手段裁定；没有显式目标或行动同时命中多方时省略摘要，不按名字猜目标；英文 / 日文 / 德文 prompt 补充字段契约，中文裁定指南按裁定流程重组。
- **前端**：先攻 / 目标列表自动包含队友（服务端投影），回合标签显示"米拉（AI 队友）正在行动…"；战斗工具页按服务端 `available_intents` 渲染「非战斗施法」卡（法术 / 法术位 / 队伍目标），不硬编码按钮。

### 修复内容（v2.5.9-beta.1 之后）

- **GM 控台布局**：恢复多语言布局前 GM 流程栏的两列按钮布局，桌面控制栏适度加宽；移动端保持单列。
- **多人幸运选择等待可靠性**：多人默认超时提升为 180 秒（显式设置仍优先）；前端明确显示自己的待处理状态与仍在等待的玩家数量，服务端状态仍为唯一真值；补充手动 / 超时竞态与并发决议回归测试。

### 以下为 v2.5.9-beta.1 的全部内容（随本版一并发布）

#### 德语（Deutsch）支持

- **德语作为第四种界面语言**：主 UI 全面支持德语（设置、创建、GM、机器人等）；GM 叙事 / 检定规划 / 战斗解说等后端 prompt 提供德语版本；浏览器语言 `de` / `de-DE` / `de-AT` / `de-CH` 自动进入德语界面。
- **德语专业组件回退策略**：D&D 2024 建卡 / 职业升级 / 专业角色中心等暂无德语翻译的专业页面统一回退英文，而不是错误回退中文。
- **德语 AI 规则生成字段协议统一**：德语生成的自定义规则会把德语文本物化进 `*_de` 字段，再次用于德语建卡 / prompt 时不再掉回英语；authoritative 字段协议与 `localized_field()` 回退顺序未改动。

#### 德语相关修复

- **语音识别语言**：德语界面语音输入使用 `de-DE`（此前被误送 `zh-CN`）。
- **公告回退**：官方公告只有中英双语，德语 / 日语及其他非中文界面统一回退英文公告。
- **世界语言标签**：世界卡列表能正确显示 `de` 世界的"Deutsch"标签。
- **规则名回退**：角色页在德语 / 日语界面显示英文规则名，而不是中文 canonical 名。

#### 界面自适应（长文本语言溢出修复）

- **Settings 状态卡**：删除固定单行 flex 覆盖，改为自适应网格（`auto-fit minmax(220px, 1fr)`）；状态标题与标签可换行，长词自动折行；≤800px 保留横向滚动策略。
- **GM 控台**：流程按钮组改为自适应列数（宽屏 2 列、窄屏自动 1 列）；工具栏按钮允许换行且保持完整可读（不使用省略号）；文风选择按钮改 flex 折行。
- **Characters**：当前角色操作按钮不再强制单行，操作区按内容自适应列数（≤520px 单列）；共享角色卡按钮允许换行。
- **语言下拉**：右上角语言名称统一为 简体中文 / English / 日本語 / Deutsch。

### 升级提示

- **无破坏性存档迁移**：队友状态挂在 `ruleset_state.party.companions[*].ruleset_character`，新增字段均为可选 / 追加。
- 建议升级重要战役前备份完整 `data/` 目录。

### 下载与校验

- **普通 Windows 用户**：`DiceFrame-v2.5.9-windows-portable.zip`
- **源码运行用户**：`DiceFrame-v2.5.9-windows.zip`
- **托管 Docker 更新**：`DiceFrame-v2.5.9-docker-update-linux-amd64.zip`
- 下载后请使用 Release 中的 `SHA256SUMS` 校验文件。

## English

### New (after v2.5.9-beta.1)

- **D&D 2024 AI companions in combat**: companions are party-side characters rather than friendly monsters, and the whole chain shares the same authoritative validate / resolve / apply — combat initiative = players + active companions + enemies; hostility, healing, buffing and attack targeting are all decided by side; companion weapon attacks reuse the player's equipment/catalog deterministic chain; companion HP / spell slots / concentration / conditions write back to `ruleset_state.party.companions[*].ruleset_character` as canonical authority. Automatic companion turns follow a deterministic priority (heal endangered allies → attack nearest / low-HP enemies → move → Dodge → End Turn) with GM automation as submit authority; forged companion intents from players are rejected server-side; 0 HP companions are skipped, and a companion dying never triggers the player party wipe check.
- **Delegated checks and companion assistance**: check requests take a new `actor_ref` (default `player:<uid>`, fully backward compatible) — "let Mira push the door" runs the check with Mira's STR / Athletics; "Mira, help me" is a player check with companion assistance, gaining advantage when the rules declare `assistance_grants`. Matching accepts explicit prefixes and player/companion names — exact first, ambiguous refused, narrative NPCs never guessed; the safety net deduplicates by actor_uid so a companion check is never overwritten by the player's.
- **Out-of-combat spellcasting**: new `exploration.cast_spell` intent (only while combat is not active, by the player themselves): validates spell legality / known / slots / targets / concentration; reuses canonical `spellcasting.class.slots_current` instead of a second resource; deterministic heals / buffs resolve directly, deterministic damage effects are refused in exploration; known spells without deterministic effects spend a slot and hand off to narration (`resolution=narrative`), with the model forbidden from touching numbers.
- **Check planner item & NPC context**: the turn check planner now sees a read-only summary of the actor's owned items (small packs complete, large packs deterministically filtered, max 20 entries per actor) and of explicitly targeted NPCs' identity and relations — "open the door with the owned key" and bare-handed lockpicking adjudicate as different means; summaries are omitted when there is no explicit target or the action simultaneously hits several parties, never guessed from name length; en / ja / de prompts gain the same field contract and the Chinese adjudication guide is reorganized around the adjudication flow.
- **Frontend**: initiative / target lists automatically include companions (server projection) with turn labels like "Mira (AI companion) is acting…"; the combat tool page renders the "out-of-combat spellcasting" card (spells / slots / party targets) from server `available_intents` instead of hardcoded buttons.

### Fixes (after v2.5.9-beta.1)

- **GM console layout**: restored the pre-multilingual two-column flow button layout and modestly widened the desktop console; mobile stays single-column.
- **Multiplayer luck decision reliability**: the multiplayer default timeout is raised to 180 seconds (explicit settings still win); the frontend shows your own pending state and how many players are still waiting, while server state remains the single source of truth; regression tests cover manual/timeout races and concurrent resolutions.

### All of v2.5.9-beta.1 (included in this release)

#### German (Deutsch) support

- **German as the fourth UI language**: full main-UI German coverage (settings, creation, GM, bots); backend prompts for GM narration / check planning / combat commentary ship German variants; browser locales `de` / `de-DE` / `de-AT` / `de-CH` activate the German UI automatically.
- **German professional-page fallback**: D&D 2024 builder / advancement / professional character center pages without German translations fall back to English instead of incorrectly showing Chinese.
- **German AI rule field protocol**: AI-generated German rules materialize German text into `*_de` fields, so reusing them in German character creation / prompts no longer falls back to English; authoritative field contracts and the `localized_field()` fallback order are unchanged.

#### German-related fixes

- **Speech recognition language**: German UI voice input uses `de-DE` (previously sent as `zh-CN`).
- **Announcements fallback**: official announcements are zh/en only; German, Japanese and other non-Chinese UIs fall back to English announcements.
- **World language labels**: world cards show a "Deutsch" label for `de` worlds.
- **Rule name fallback**: the characters page shows English rule names in German/Japanese UIs instead of the Chinese canonical name.

#### UI adaptive layout (long-language overflow fixes)

- **Settings status cards**: removed the fixed single-row flex override in favor of an auto-fit grid (`minmax(220px, 1fr)`); headings and tags wrap; long words break anywhere; the ≤800px horizontal-scroll strategy is preserved.
- **GM console**: flow button groups use adaptive columns (2 on wide, 1 on narrow); toolbar buttons wrap while staying fully readable (no ellipsis); style option buttons flex-wrap.
- **Characters**: current-character action buttons no longer force a single line, the action area adapts its column count (single column ≤520px); shared character card buttons wrap.
- **Language dropdown**: unified names — 简体中文 / English / 日本語 / Deutsch.

### Upgrade notes

- **No breaking save migration**: companion state lives under `ruleset_state.party.companions[*].ruleset_character`; new fields are optional/additive.
- Back up the complete `data/` directory before upgrading important campaigns.

### Downloads and verification

- **Regular Windows users**: `DiceFrame-v2.5.9-windows-portable.zip`
- **Source users**: `DiceFrame-v2.5.9-windows.zip`
- **Managed Docker update**: `DiceFrame-v2.5.9-docker-update-linux-amd64.zip`
- Verify downloads with the `SHA256SUMS` file attached to the Release.

# 恋爱养成玩法：设计草案与 SDK 缺口清单

> 状态：已拍板（2026-10-19 grill 定稿，原讨论稿 2026-10-12）。未施工。P1/P3 供与 EOEOY 讨论合入。
> 基线：`diceframe/diceframe` `main` @ v3.0.0-beta.3（含 ADR 0006–0011）。§2 现状对照已按该基线逐条复核。
> 原则：恋爱养成**只用数据实现**（规则 JSON + 冒险包 + 角色卡 + 世界书）；**不把恋爱专用 Python 写进通用引擎**（`src/engine`、`src/adventures`、`src/lorebook`）。做不到的地方补**通用引擎能力**。`src/game_profiles` 是上游认可的具体玩法层，但不用于本玩法 MVP（理由见 §2 末行）。这个玩法本身就是 SDK 的验收测试。

---

## 1. MVP 范围

- 单人优先；多人（各自路线、互相可见性）放 v2。
- 3 名可攻略角色、14 天、每天 3 个时段（上午 / 下午 / 晚上）、4 项自身属性（魅力 / 学识 / 体力 / 金钱）。
- 每名角色 5 个关键事件 + 3 种结局（HE / NE / BE），另有 1 个通用 BE。
- 循环：选日程 → 属性变化 → 自由对话 / 遇到角色 → 好感变化 → 满足条件时解锁事件 → 第 14 天结算结局。
- 内容合规：攻略对象全部成年，内容分级开关从第一天就有（机制见 §6-6）。
- 砍范围预案（按 §6-8 优先级）：先砍攻略对象数（3 → 1），再砍天数（14 → 7），不破"数据实现"原则。

## 2. 现状对照（2026-10-19 按 beta.3 复核）

| 需要的能力 | 现有（beta.3） | 缺口 |
|---|---|---|
| 自身属性 | `special_stats` / `resource_schema`（`src/rules/rule_system.py:347/597`，经 `core:legacy` runtime 暴露），GM 用 `STAT:uid:key:delta` 标签，`apply_resource_delta` 会钳制 min/max，`resource_triggers` 有一次性阈值 | 基本够用；缺每轮变化上限（目前只拒绝 ±100 以上） |
| 好感 / 信任（玩家 × NPC） | **无**。NPC 只有 `instance.npcs` 自由 dict + 文本 `tier`（`npc_state_applier`）；world relation 只有固定 kind + 状态，world 容器禁止放数值；`plot_tracker` 的 RelationTier 只是注入给模型的文本 | **新的通用 module slot** |
| 时间 / 日程 | `world_state.clock {day, minute}`；时间只在 LLM 报 `world_time_advance` 时推进（`src/commands/round_processor.py:485`） | 缺"日历 / 时段 / 日程选项"的声明，缺由引擎（而非 LLM）推进时间的模式 |
| 路线 / 事件 | adventure v2 图（`src/adventures/graph_v2.py`），有回边、门控、on_complete outcomes；时间推进后自动激活满足条件的后继节点（`src/adventures/progress.py` + `src/webui/services/adventure_runtime.py`）。**beta.3 变化**：门控新增 `adventure.objective_status` 类型（ADR-0008）；DF Agent 已有 `complete_adventure_node` 工具（GM 权限实例 + run_id/revision 守卫，`src/webui/services/assistant_gameplay_tools.py`）；"节点提醒"功能为建议-only | 门控仍是相等判断 if/elif（`src/adventures/gates.py:109-128`），无比较运算、不能读数值/时钟/关系；对局内 AI GM 叙事流仍不能完成节点；进度按整局一份 flat dict（`completed_nodes/objectives/milestones` + `history`），不按玩家存 |
| 角色卡 → 攻略对象 | 酒馆卡可以 `target="npc"` 导入（`src/webui/services/character_cards.py:701/729`），但只会生成一条世界书条目 | 不会登记为 world entity / 关系对象 |
| 按关系阶段改变语气 | 世界书有关键词、常驻、概率、计时器、可见性（`src/lorebook/matcher.py`） | **不能按游戏状态条件注入**（例如"恋人阶段"专属条目） |
| 好感对他人隐藏 | `private_channels` 有按 uid 的私有日志；`participant_view` 区分 GM / 座位 / 外人。**beta.3 新基建**：存档 schema 44→45 已拆出"本局配置与展示偏好"层 | 没有通用的按座位私有数值；`list_characters` 会把每个玩家的完整角色卡给所有人。展示偏好层正好是可见性显示模式的落点（§6-1） |
| 前端面板 | 按 ruleset adapter 注册的面板（`frontend-v2/src/features/rulesets/registry.ts`）；`resource_schema` 渲染成通用资源条；"DND5E工具"写死文案仍在（`registry.ts:74-76`） | 缺关系面板、日程选择器、结局 / 回忆图鉴 |
| 插件扩展 | 插件是进程外 JSON-RPC，只有 tool / provider / bot 扩展钩子 | 没有回合级 prompt 注入、状态写入、对局 UI 插槽。所以本玩法走**数据路径**，不走插件 |
| （新）有界具体玩法层 | **beta.3 新增** `src/game_profiles/`（2026-10-14 落地）：`phase`/`calendar` 两种模式、确定性 Python runtime（initial/validate/legal/move/advance）、走 action gate、独立路由与 UI 区块；硬上限 1–4 actors、history ≤ 100；绑定 profile 后路由**离开**叙事 composer（`projection.py`） | **不用于本玩法**：GAL 的价值（自由对话、阶段语气、事件演出）全在叙事栈，profile 框架刻意绕开叙事栈；14 天 × 3 时段的对话密度也超其硬上限。留作将来"纯机制版"（无自由对话的小游戏化日程）的货架 |

**惯例注意**：旧讨论稿引用的 `MODULE_API_WRITERS` 白名单已随 GameInstance facade 退役而**不存在**；现行模块惯例为 `src/engine/modules/*_state.py` 自持状态 + `ensure/install` + `set_module_state`（owner boundary 写法参见 `src/engine/modules/profile_progression.py`），写入经 `src/webui/services/` 命令路径。旧 `tavern_free` 模板已不存在，ruleset 注册表现为 `Dnd2024Runtime` + `LegacyRulesetAdapter`（`core:legacy`，`src/rulesets/builtin.py`）。

## 3. 需要新增的通用能力

### A. `relationships` module slot（核心）

通用的"主体 × 对象 → 多维数值 + 阶段"状态，不绑定恋爱。以后可复用于阵营声望、剧本杀嫌疑度。

**归属已拍板（§6-4）**：引擎通用模块槽 `src/engine/modules/relationships_state.py`，与 `lorebook_runtime` / `economy_state` 同级；不进任何 ruleset 私有 `ruleset_state`。

**规则模板中的声明**（新增 `relationship_schema` 顶层字段）：

```json
"relationship_schema": {
  "dimensions": [
    {"key": "affection", "label": "好感", "min": 0, "max": 100, "default": 10, "per_round_cap": 8, "visibility": "gm", "player_adjustable": true},
    {"key": "trust",     "label": "信任", "min": 0, "max": 100, "default": 0,  "per_round_cap": 5, "visibility": "gm", "player_adjustable": true}
  ],
  "stages": [
    {"key": "stranger", "label": "陌生"},
    {"key": "friend",   "label": "朋友", "enter": {"affection": {"gte": 30}}},
    {"key": "crush",    "label": "暧昧", "enter": {"affection": {"gte": 60}, "trust": {"gte": 30}}},
    {"key": "lover",    "label": "恋人", "enter": {"affection": {"gte": 85}}, "requires_milestone": true}
  ],
  "stage_mode": "monotonic"
}
```

- `visibility`：`self` / `party` / `gm` / `hidden`。**默认定档（§6-1）**：数值默认 `gm`（玩家只见阶段标签），玩家可在展示偏好层调"阶段 / 数值 / 隐藏"，服务端投影过滤、可中途改；`player_adjustable: false` 允许作者锁死（如只给叙事暗示的悬疑维度）。
- `stage_mode: monotonic`：阶段只升不降（避免数值抖动来回切）；也可以选 `derived`。
- `requires_milestone`：进入该阶段还需要冒险图里的对应里程碑（告白事件），**数值够了不等于自动成为恋人**。

**slot 形态**（schema v1）：

```json
{
  "schema_version": 1,
  "tracks": {
    "<subject_uid>": {
      "npc:<id>": {"values": {"affection": 35, "trust": 12}, "stage": "friend", "updated_round": 17}
    }
  }
}
```

**写入**：

- GM 标签 `REL:<uid>:<npc_id>:<key>:<delta>`，加入 PLAYER 标签组（`src/commands/tag_handlers.py`）。
- 新增 applier，必须执行以下校验：只能写本轮行动过的 uid（同 `player_state_applier`）；`npc_id` 必须是已声明的关系对象；钳制 min/max 和 `per_round_cap`；阶段由**引擎**重新计算，模型不能直接设阶段。
- 遵循 beta.3 现行模块惯例（见 §2 末"惯例注意"）：模块状态经 owner boundary（`ensure/install` + `set_module_state`）安装；变更走 services/commands 单一路径；owner 守卫测试与 `tests/architecture/` 现役模式对齐。**不要**按旧稿引用 `MODULE_API_WRITERS` / 具体行号施工，以当期实现为准。

**读取投影**：

- 座位视角：只返回自己的 tracks，并按 `visibility` 与展示偏好过滤维度。
- GM 视角：全部可见。
- LLM 上下文：只注入**行动者**与**在场 NPC** 之间的关系（数值、阶段、阶段说明），不注入其他玩家的。

**阶段变化通知**：走 `resource_triggers` 那种"下一轮给 GM 一条指令"的方式（例如"她现在把你当作朋友了，语气可以更随意"）。

### B. 日历与日程

**复用** `world_state.clock`，不另造时钟。规则模板新增 `calendar_schema`：

```json
"calendar_schema": {
  "days": 14,
  "slots": [
    {"key": "morning",   "label": "上午", "minute": 480},
    {"key": "afternoon", "label": "下午", "minute": 780},
    {"key": "evening",   "label": "晚上", "minute": 1140}
  ],
  "time_authority": "schedule",
  "activities": [
    {"key": "study",  "label": "自习", "slots": ["morning", "afternoon"], "effects": {"knowledge": 3, "stamina": -1}},
    {"key": "work",   "label": "打工", "slots": ["afternoon", "evening"], "effects": {"money": 50, "stamina": -2}},
    {"key": "free",   "label": "自由行动", "slots": ["morning", "afternoon", "evening"], "effects": {}}
  ]
}
```

- 新 intent `calendar.activity.choose {activity}`：由玩家发出，引擎**确定性地**应用效果并推进到下一个时段，再交给 GM 叙事。
- `time_authority: schedule`：该模式下忽略或钳制 LLM 的 `world_time_advance`，防止模型自己跳时间。
- "自由行动"时段允许正常对话；时段结束由玩家选下一项来推进。
- 日程记录放在一个很小的 slot（或者 relationships 之外的 `schedule` slot）；多人各自日程放 v2。
- **锚点（§6-9）**：规则 JSON 指向 `core:legacy` runtime（`tavern_free` 已不存在）。P5 开工首查项：确认模板导入校验不会丢弃未知顶层字段（`relationship_schema` / `calendar_schema`）。

### C. 门控：改成注册表 + 比较运算

- 把 `src/adventures/gates.py:109-128` 的 if/elif 改成**条件注册表**（SDK 的关键一步，其他玩法也会需要）。
- 新增 `op` 字段：`eq`（默认，兼容现有）/ `gte` / `lte` / `gt` / `lt` / `in`。
- 新的条件类型：
  - `relationship.value {target, key, op, value}`：主体默认是当前行动者。
  - `relationship.stage {target, op, value}`：阶段按声明顺序比较。
  - `world.clock {op, day, slot?}`
  - `rules.resource {key, op, value}`：玩家自身属性。
- 同一套条件词汇同时给 D（世界书条件）和结局判定使用。

### D. 节点完成：单人确认入口 + `completion: "auto"`（形态已拍板 §6-3）

现状：节点完成由人类 GM intent 驱动；beta.3 给 DF Agent 加了带守卫的 `complete_adventure_node` 权威工具，另有"节点提醒"（AI 建议 GM 检查，GM 手动确认，AI 不自动推进）。对局内 AI GM 叙事流仍不能完成节点——这在单人 GAL 里意味着"没有手"。

**MVP 方案（a-2）**：

- 把 beta.3"AI 建议 → 人工确认"通道扩展成**单人局一键确认**：AI GM 演出完事件 → 界面弹出"事件完成？确认"→ 玩家点按，走现有权威完成事务（单人局玩家本就持有 GM 权威；事务全有或全无）。
- 节点声明 `completion: "gm"（默认） | "auto"`。默认节点即可被人类 GM intent 或单人一键确认完成——两者是同一条权威事务；`"auto"` 节点在门控满足的回合由引擎直接完成（适合"第 14 天结算"这类机械节点）。
- 激活中的事件节点注入 GM 上下文："可触发事件：X（条件已满足），请在合适时机演出，演出后提示玩家确认"。
- PR 叙事是"给单人局补确认入口"，不改变多人局"节点由人类 GM 推进"的语义。

**推迟项（a-1）**：`NODE:complete:<node_id>` GM 输出标签（AI 自主完成，引擎验证激活 + 门控）。上游 beta.3 刚明确"AI 不自动推进节点"的保守选择，此标签正撞其上；待试玩证明"玩家点确认"打断沉浸后，拿数据向上游提案。

### E. 世界书条件注入

- 条目新增 `conditions`（复用 C 的条件词汇），在关键词匹配之后、预算之前过滤。
- 典型用法：每个攻略对象一组"阶段语气"条目，例如 `{"type":"relationship.stage","target":"npc:lin","op":"gte","value":"crush"}`。
- 未满足条件的条目视为未激活，不能失败开放。

### F. 攻略对象登记

- 冒险包新增 `relationship_targets: [{"npc_id": "npc:lin", "card_ref": "...", "lorebook_ref": "..."}]`。
- 绑定冒险时把这些 NPC 登记为 world entity 和关系对象；酒馆卡以 `target="npc"` 导入时可以选择"同时登记为攻略对象"。

### G. 前端通用面板

- 由 `relationship_schema` 驱动的关系面板：每个对象一行头像 + 维度条 + 阶段标签，按可见性与展示偏好隐藏。
- 由 `calendar_schema` 驱动的日程选择器：当前第几天 / 哪个时段 + 可选活动及其效果预览。
- 结局 / 回忆图鉴：读里程碑 + 场景图（v2）。ADR-0008 的 objectives / milestones 投影可作数据源。
- 这些都注册为**通用面板**（按 schema 是否存在决定是否显示），不是按 runtime_id 注册；顺手修掉写死的"DND5E工具"文案（`registry.ts:74-76`）。

## 4. MVP 内容包结构

```text
romance-sample/
  manifest.json            # kind: content-pack, engine 版本范围, 分级声明（§6-6）
  rules/romance_sim.json   # runtime: core:legacy; special_stats + relationship_schema + calendar_schema
  adventure/adventure.json # graph v2: 每个对象 5 个事件节点 + 结局 milestone 节点
  cards/*.json             # 3 张攻略对象卡（chara_card_v3）
  lorebook/*.json          # 世界设定 + 每个对象的阶段语气条目（带 conditions）
```

事件节点示例：

```json
{"id": "lin_ev3_rain", "type": "scene", "chapter_id": "lin",
 "completion": "gm",
 "transitions": [{"to": "lin_ev4_confess", "conditions": [
   {"type": "relationship.value", "target": "npc:lin", "key": "affection", "op": "gte", "value": 60},
   {"type": "world.clock", "op": "gte", "day": 7}
 ]}],
 "on_complete": [{"type": "progress_event", "kind": "milestone_reached", "id": "lin_rain_memory"}]}
```

（`completion` 取值由 D 节定义：`"gm"`（默认）人类 GM intent 或单人一键确认，同一权威事务；`"auto"` 引擎门控满足即完成。）

**归属已拍板（§6-7）**：MVP 放本仓库测试夹具，文案 AI 初稿 + 人工审；玩法验证成立后再考虑迁 diceframe-content。发布是单向门（beta.3 已有发布源所有权保护），不急着进公共渠道。

## 5. 分 PR 计划

1. **P1**：门控注册表 + `op` 比较运算（行为不变，现有测试全部通过）。对 D&D / CoC 直接有用，先做。
2. **P2**：`relationships` slot + `REL` 标签 + applier + 投影 + 上下文注入。施工说明按 §2 末"惯例注意"的 beta.3 惯例执行。
3. **P3**：单人节点确认入口（扩展 beta.3 建议→确认通道）+ `completion: "auto"`（D 节 a-2 方案）。对 AI GM 单人玩法通用。
4. **P4**：`relationship.*` / `world.clock` / `rules.resource` 门控 + 世界书 `conditions`。
5. **P5**：`calendar_schema` + `calendar.activity.choose` intent + `time_authority`。开工首查项见 B 节锚点。
6. **P6**：前端通用关系面板 + 日程选择器；修"DND5E工具"文案。
7. **P7**：样板内容包，只用以上公开能力；过程中发现的缺口回填进 SDK。
8. **v2**：多人各自路线（按 uid 的进度 map + 显式迁移，见 §6-5）、结局图鉴完整版、通用私有数值投影。

## 6. 已拍板的决定（2026-10-19）

1. **好感默认可见性**：默认只显示阶段（数值默认 `visibility: "gm"`）。玩家可在 beta.3 新拆出的**展示偏好层**（存档 schema 45）调整"阶段 / 数值 / 隐藏"，服务端投影过滤、可中途改；schema 用 `player_adjustable` 封套保作者控制权；难度预设可捆绑推荐档位但不强制。
2. **日程制**，时段内允许自由对话；时间权威在引擎，LLM 不可跳时间。
3. **节点完成**：先做 a-2（复用建议→确认通道，单人一键确认）+ `completion: "auto"`；`NODE:complete` 标签（a-1）推迟，试玩数据支持后再向上游提。
4. **relationships 归属**：引擎通用模块槽（非 ruleset_state）。理由：门控与世界书都要跨层读关系数值，ruleset 私有状态是更差的耦合；ADR-0007 模块自持状态为既定架构；可复用于阵营声望、剧本杀。
5. **多人进度方向**：同一张图 + 按 uid 的进度 map + 显式迁移；每玩家子图否决。v1 保持现有整局 flat progress，P3/P4 施工时只需不假设"进度属于全局"。
6. **内容分级**：v1 = manifest 声明 + 安装/创建时明示 + 年龄确认 UI，不做内容级过滤引擎；进公共 catalog 前必须补 catalog 侧分级元数据。
7. **样板包归属**：本仓库测试夹具 + AI 初稿人工审；验证后再考虑 diceframe-content 发布。
8. **优先级**：玩法可玩优先；需要砍就砍范围（攻略对象数 → 天数），"不写恋爱专用 Python 进通用引擎"是死线。
9. **路线**：主循环走 rules/module 数据路径；`game_profiles` 不用于 MVP，留作纯机制版货架。

## 7. 施工期自由度（不另开会）

每轮变化上限数值、阶段门槛数值、事件文案分工与文风、面板具体布局。

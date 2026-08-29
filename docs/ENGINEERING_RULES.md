# DiceFrame Engineering Rules

> 本文规定“如何安全地修改 DiceFrame”，不是冻结当前架构。
>
> 当前实现的架构事实来源仍是：
>
> - `docs/ARCHITECTURE_CN.md`
> - `docs/ARCHITECTURE_EN.md`
>
> 测试与产品关键契约的原则见下方第 15 节。

## 1. 目的

DiceFrame 需要同时支持快速增加功能、长期维护旧数据、多人权限隔离、不同规则系统扩展，以及较大的重构和迁移。

因此本规范保护的是：

- 用户数据
- 权限与隐私
- 持久化 identity
- public / extension contracts
- ruleset mechanics 边界
- multiplayer authority
- migration correctness
- 可验证的产品行为

本规范**不保护**：

- 当前文件路径
- 当前类名和 helper
- 当前内部实现
- 当前模块数量
- 当前 UI 组织方式
- 当前技术方案本身

只要受影响的契约被有意识地处理，DiceFrame 允许拆分、合并、迁移、替换甚至重做现有架构。

---

## 2. 规范用语

本文使用：

- **MUST**：默认不可违反的产品/数据/安全要求。
- **SHOULD**：当前推荐架构或工程做法；有明确理由时可以改变。
- **MAY**：明确允许的做法。

如果某个改动需要改变 SHOULD 级规则，不视为违规；应在 PR 中说明新的边界，并同步更新架构事实来源。

如果确实需要改变 MUST 级契约，应把它视为显式 breaking / product-contract change，提供版本、迁移、兼容或明确拒绝策略，而不是静默改变。

需要区分两类 MUST：

- API、schema、canonical identity、产品行为等**可版本化的产品契约**，可以按上述方式显式 breaking；
- **安全不变量**不能仅因 intentional breaking change 被放宽，包括：

```text
unauthorized data access
private / GM 数据泄露
跨 actor 的未授权状态修改
客户端取代服务端 authority
secret 泄露
```

权限 / authority 架构本身 **MAY** 重构；但新模型 **MUST** 保持等价或更强的授权判定、actor 隔离与服务端 authority。安全不变量上的回归不是 breaking change，而是正确性缺陷——无论 PR 如何描述都必须修复，不能通过 versioning / migration 流程“合法化”。

---

## 3. Architecture is allowed to change

DiceFrame **MAY** 为了新功能、可靠性、性能、安全性、维护性或长期演进：

- 拆分或合并模块；
- 移动职责；
- 替换内部实现；
- 删除已经失去意义的 abstraction；
- 引入新的 abstraction；
- 修改持久化模型；
- 调整 API；
- 重新组织 runtime / services / frontend；
- 拆分仓库、package 或 subsystem；
- 进行跨模块的大型重构。

大型改动不会因为“与当前 `ARCHITECTURE` 不同”而被禁止。

但改动 **MUST** 显式处理它影响到的稳定表面，包括：

- persisted data；
- compatibility；
- public / extension API；
- security / permissions；
- multiplayer authority；
- ruleset mechanics；
- migration；
- tests；
- architecture documentation。

合并后，更新过的 `ARCHITECTURE` 才是新的事实来源。

---

## 4. Stable Surface：按稳定表面判断风险

不要按“改了多少行”判断改动危险程度。按它触碰了什么判断。

### Level 0 — Internal implementation

例如：

- 内部 helper；
- 私有 class；
- 文件/目录布局；
- 未对外暴露的内部函数；
- 内部算法与缓存实现；
- UI 组件拆分。

这些内容 **MAY** 自由重构。

如果行为契约不变，不需要兼容旧内部实现。

### Level 1 — Architectural boundary

例如：

- route / WebAPI / service / core 的职责边界；
- ruleset runtime 边界；
- frontend / backend authority 边界；
- migration / compatibility 组织方式；
- subsystem 或 repository 边界。

这些内容 **MAY** 改变。

发生变化时 **SHOULD**：

- 在 PR 中描述 `Current -> Proposed`；
- 说明为什么现有边界不再合适；
- 更新 `docs/ARCHITECTURE_*.md`；
- 若属于长期、有替代方案争议的重要决策，再增加 ADR。

### Level 2 — Public / extension contract

例如：

- Web API；
- Plugin contract；
- Content V2；
- Ruleset Bundle；
- Adventure Bundle；
- externally consumed schema；
- 对 Bot / client 暴露的稳定字段。

这些内容默认 **SHOULD** 保持兼容。

需要 breaking change 时 **MUST**：

- 显式标注；
- 提供版本边界；
- 给出 migration / adapter / deprecation / rejection strategy 中至少一种合理方案；
- 添加对应测试；
- 更新相关文档。

### Level 3 — Persisted / authority / security contract

例如：

- save；
- SQLite / persisted state；
- canonical persisted identity；
- GM / player / private visibility；
- actor ownership；
- multiplayer turn authority；
- 权威规则状态；
- 权限与认证边界。

这是最高保护级别。

改变这些内容时 **MUST** 优先保证数据正确性、权限正确性和确定性；不能为了“自动兼容”猜测用户数据。

---

## 5. 用户数据与持久化 identity

### 5.1 用户数据不是系统模板的缓存

系统默认模板和用户数据库是两个不同的 authority。

系统 **MUST NOT** 因为当前 bundled template 发生变化，就无条件覆盖已经存在的用户记录。

允许：

```text
能够证明仍是旧官方默认值
→ 有条件升级到新官方默认值
```

禁止：

```text
当前模板
→ 每次启动强制同步/覆盖用户数据库
```

只要无法证明某条数据仍是系统默认状态，就 **MUST** 按用户数据处理并保留。

### 5.2 Persisted Identity Rule

一旦某个 canonical ID 可能进入以下任一表面：

- save；
- database；
- world；
- lorebook；
- character；
- plugin；
- ruleset；
- adventure；
- network payload；
- externally referenced content；

它就不再只是内部命名。

重命名或删除 persisted identity 时 **MUST** 考虑：

- alias；
- migration；
- explicit version boundary；
- deprecation；
- explicit rejection。

**MUST NOT** 仅因为“源码里改名更好看”就让旧数据失去引用。

display name / locale text **MUST NOT** 替代 canonical identity。

---

## 6. Migration

### 6.1 默认边界

当前默认：

```text
persisted schema / persisted state upgrade
→ src/migrations/

historical external/runtime shape compatibility
→ src/compat/ 或明确 adapter 边界
```

这是 **SHOULD**，不是永远不可改变的目录规则。

如果未来重做 migration architecture，可以通过明确的架构改动重新定义。

### 6.2 Migration MUST

Migration **MUST**：

- 幂等；
- 可测试；
- 有明确 source version / identity / digest / snapshot 等安全边界；
- 不无意丢字段；
- 不无意覆盖用户修改；
- 对未知未来版本 fail closed；
- 对部分失败保持可预测行为；
- 尽可能使用明确、可解释的转换，而不是启发式猜测。

### 6.3 Correctness > completeness

> **Migration correctness is more important than migration completeness.**

如果无法可靠判断旧数据的含义：

允许：

```text
无法安全自动迁移
→ 保留 / 拒绝 / 要求用户确认
```

不允许：

```text
“看起来大概是这样”
→ 猜测并重写用户数据
```

无法证明安全迁移时 **MUST** fail closed。

### 6.4 已发布 migration

已发布 migration 的历史语义 **SHOULD NOT** 被静默改写。

需要补救时，优先新增版本化 migration 或明确 repair step，而不是让同一个旧 migration 在不同版本中产生不同结果。

---

## 7. Compatibility 与 Breaking Change

Backward compatibility 是默认策略，不是永恒义务。

DiceFrame **MAY** 在旧兼容包袱明显阻碍正确性、维护性、安全性或长期架构时进行 breaking change。

Breaking change **MUST** 是显式的，而不是偶然发生。

根据影响范围，应提供：

- migration；
- compatibility adapter；
- alias；
- deprecation window；
- major/schema/runtime version boundary；
- 明确的 unsupported / rejection behavior。

兼容逻辑 **SHOULD** 集中在 compatibility / adapter 边界。

**SHOULD NOT** 让大量 legacy `if/else` 永久散落在正常 runtime 业务路径中。

---

## 8. 当前架构默认方向

以下是当前推荐方向，属于 **SHOULD** 级架构约束：

```text
routes
  ↓
WebAPI
  ↓
services
  ↓
core / engine
```

- core / engine **SHOULD NOT** 反向依赖 `src.webui`；
- route **SHOULD** 保持薄层；
- WebAPI **SHOULD** 负责委托与边界转换，而不是重新实现业务规则；
- service 间协作 **SHOULD** 使用明确接口，而不是绕过边界访问内部状态。

如果某次重构要改变这条依赖方向，允许改变，但应按 Level 1 architecture change 处理。

---

## 9. Ruleset isolation

DiceFrame 的 generic engine 是多个规则系统共享的基础。

当前默认方向：

```text
specific ruleset
      ↓
generic runtime / engine primitives
```

而不是：

```text
generic engine
      ↓
specific D&D / CoC implementation
```

因此：

- D&D 专属行为 **SHOULD** 留在 D&D runtime / capability 边界；
- CoC 专属行为 **SHOULD** 留在 CoC 边界；
- generic d20 **SHOULD NOT** 因某一个规则系统的特例而改变通用语义；
- ruleset **MAY** 通过明确 capability / runtime contract 扩展通用体验。

这里保护的是**依赖方向和 mechanics authority**，不是永久锁死某个目录路径。

未来把某个 ruleset 移到 package、独立仓库或新 runtime 结构完全允许。

---

## 10. Canonical identity 与 Locale

Canonical identity **MUST** 与 display text 分离。

例如：

```text
fighter
longsword
npc_innkeeper
```

是 identity；

```text
战士 / Fighter
长剑 / Longsword
老汤姆 / Old Tom
```

是 display text。

Locale **MUST NOT**：

- 改变 canonical ID；
- 改变 mechanics；
- 改变规则技能池；
- 改变权限；
- 增删 canonical entity；
- 用翻译后的字符串充当 runtime identity。

如果未来 localization architecture 改变，这个 identity/mechanics 契约仍应保留，除非明确做 breaking content-model change。

---

## 11. Server authority、Security 与 Privacy

### 11.1 服务端是最终 authority

以下内容 **MUST NOT** 只依赖客户端约束：

- 权限；
- actor ownership；
- GM-only 操作；
- private visibility；
- turn authority；
- resource consumption；
- authoritative mechanics。

前端可以隐藏按钮，但隐藏按钮不是安全边界。

### 11.2 Private data

GM-only / player-private 数据 **MUST NOT** 先发给无权用户再靠 UI 隐藏。

权限过滤应在服务端或更早的 authoritative projection 边界完成。

### 11.3 输入不可信

以下均视为不可信输入：

- browser/client；
- Bot；
- Plugin；
- imported content；
- uploaded save；
- LLM output；
- migration source data。

所有权威状态修改都应经过对应验证边界。

---

## 12. Multiplayer authority

任何会修改多人游戏状态的新功能 **MUST** 明确：

- 当前 `game`；
- `actor`；
- actor ownership；
- turn / phase authority；
- 并发行为；
- 是否允许 GM override；
- failure semantics。

**MUST NOT** 假设：

> “前端正常情况下不会这样调用。”

不同游戏、不同玩家和不同 actor 的数据必须保持隔离。

涉及并发提交、round advance、资源消耗的行为 **SHOULD** 有 integration / concurrency coverage。

---

## 13. LLM 不是权威状态机

LLM 可以：

- 提议；
- 叙事；
- 解析自然语言；
- 生成候选内容；
- 给出 tool / intent candidate。

LLM 输出 **MUST NOT** 绕过 engine / reducer / validator 直接成为权威状态修改。

例如 HP、资源、战役事实、权限、冒险推进、战斗状态等，最终仍应经过确定性或可验证的 authoritative path。

---

## 14. Frontend boundary

Frontend 默认负责：

- interaction；
- presentation；
- local UI state；
- 对 backend authoritative result 的展示。

Frontend **SHOULD NOT** 重复实现一套与 backend 不同的核心 mechanics / permission model。

这不限制：

- Vue 组件如何拆；
- store 怎么组织；
- navigation 怎么重构；
- 页面如何重做；
- 未来是否替换 frontend 技术。

保护的是 authority，不是 UI 实现。

---

## 15. Tests protect contracts, not implementations

测试的目标是保护产品承诺和风险边界，不是冻结当前实现。

测试 **MAY** 因重构被：

- 重写；
- 合并；
- 移动；
- 删除重复覆盖。

前提是对应 contract 的有效覆盖仍然存在。

测试保护行为契约，不维护“某契约必须对应某个具体测试文件名”的人工映射表——测试改名、合并、重构不应要求同步维护一张 Markdown 清单。

### 15.1 Critical testing areas

以下高风险领域的行为契约必须始终有有效测试覆盖；测试可以合并、改写、移动，但覆盖不能消失：

- Authentication / permission / private-data isolation
- Persisted data / save / migration
- Multiplayer actor / game / turn / concurrency isolation
- Ruleset mechanics / canonical identity
- LLM 输出不绕过 authoritative state path
- Plugin / imported content / path safety
- Transport / token / secret leakage
- Upgrade / rollback / integrity

新增高风险产品契约时 **SHOULD** 增加对应测试；改动落在上述领域时，同时确认旧覆盖没有因重构丢失。

不要为了测试而保留一个已经不合理的内部 helper / class / 文件结构。

同时不要通过删除测试来掩盖 regression。

---

## 16. PR 大小：保护完整性，不限制行数

DiceFrame 不设置：

- 最大改动行数；
- 最大文件数；
- 大型 PR 禁令。

原则是：

> **Prefer the smallest coherent change, not the smallest diff.**
>
> 优先最小“完整改动”，而不是最小“代码行数”。

一个完整 migration 可能合理地同时包含：

- migration；
- compatibility；
- backend；
- frontend；
- tests；
- docs。

如果把这些拆开会产生无法独立验证或不安全的中间状态，就不应为了“PR 小”强拆。

反过来，如果两个变化可以：

- 独立产生价值；
- 独立验证；
- 独立回滚；

则 **SHOULD** 分开提交，减少审计噪音。

---

## 17. PR 风险声明

PR 不需要先判断自己属于某个固定等级。

只需识别是否触碰这些影响面：

```text
API
Persisted Data
Migration
Compatibility / Breaking
Security / Permission
Multiplayer
Ruleset Mechanics
Architecture
Plugin / Extension Contract
UI only
```

触碰的风险面越多，review 和测试越应该集中到对应契约。

风险声明的目的不是阻止合并，而是避免“做了高风险改动却没人意识到”。

---

## 18. Design Note 与 ADR

### 普通 bug / 小功能

不需要 ADR。

### 需要在 PR 中写 Design Note 的情况

通常包括：

- 改变 subsystem 边界；
- 改变主要依赖方向；
- 引入新的 persistence model；
- breaking public/extension contract；
- 选择一个会长期影响后续工作的核心 abstraction。

Design Note 可以直接放在 PR description 中，不要求单独文件。

### 需要 ADR 的情况

只有当决策：

- 预计长期存在；
- 有多个长期可行方案；
- 未来维护者很可能问“为什么当初这样做”；
- 涉及 repository split、runtime model、content model、persistence architecture、plugin architecture 等重要方向；

才 **SHOULD** 新增 ADR。

ADR 不是审批凭证；它是长期的“为什么”。

详见 `docs/adr/README.md`。

---

## 19. Dependencies

新依赖不是禁止项。

新增 runtime / security-sensitive / large dependency 时 **SHOULD** 说明：

- 为什么现有能力不足；
- 它进入哪个边界；
- 对镜像体积、平台支持、安全和维护的明显影响。

普通开发依赖无需写长篇论证。

不要为了“零依赖”重复实现已有成熟基础设施，也不要为了一个小 helper 引入过重依赖。

---

## 20. Generated / derived artifacts

如果某文件是从明确 source-of-truth 自动生成的：

- **SHOULD** 修改 source，而不是直接长期维护生成结果；
- 生成方式 **SHOULD** 可复现；
- 若生成文件需要入库，应在文档或文件头说明来源。

运行缓存、本机产物、临时测试结果 **MUST NOT** 作为源码提交。

---

## 21. AI-assisted development

DiceFrame 允许使用 Codex、Claude、ChatGPT 和其他 AI 辅助开发。

AI output 不是 authority。

AI agent 在修改前 **SHOULD**：

- 阅读相关现有架构和附近实现；
- 查证实际字段/API，而不是凭猜测创造；
- 识别是否触碰 persisted / security / multiplayer / ruleset contract；
- 避免无关清理扩大 diff。

AI agent **MAY**：

- 大型重构；
- 删除 obsolete code；
- 修改架构；
- 拆分模块；
- 新增 migration；
- 改 public API。

但必须像人类贡献一样处理相应契约、测试、迁移和文档。

“这是 AI 写的”不能作为不了解代码含义或跳过验证的理由。

---

## 22. Intentional exceptions

这些规则用于避免**无意的架构退化**，不是阻止**有意的架构演进**。

当某个改动确实需要：

- 改变当前 SHOULD 规则；
- 改变当前架构；
- 打破某个稳定 contract；

应：

1. 明确说明变化是 intentional；
2. 解释为什么旧边界不再适合；
3. 处理 migration / compatibility / security / tests；
4. 更新对应 architecture / contract 文档；
5. 重大长期决策必要时增加 ADR。

完成这些后，改变架构本身不是违规。

---

## 23. 最终判断原则

遇到规范没有明确写到的情况，按以下顺序判断：

1. 会不会破坏或泄露用户数据？
2. 会不会破坏权限、私密信息或 multiplayer authority？
3. 会不会让旧持久化 identity / save 无法解释？
4. 会不会无意改变 public / extension contract？
5. 会不会让 specific ruleset 反向污染 generic engine？
6. 有没有可验证的 migration / compatibility / test？
7. 如果以上都处理好了，这个重构是否让系统更清晰、更可靠？

前六项是风险控制。

第七项提醒我们：

> DiceFrame 的架构应该能够继续变得更好，而不是因为规范而停止演进。

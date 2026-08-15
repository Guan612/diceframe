# DiceFrame v2.2.0

## 中文

DiceFrame 2.2.0 为玩家自助成长与 GM 控制补充能力，并修复了浅色模式阅读、被踢玩家重入、世界书条目冗余等一批问题。

### 新增

- **玩家自助分配升级属性点**：升级获得自由属性点后，玩家在游玩页角色面板即可看到「有 X 点属性待分配」并自助加点，无需再请求 GM 代加；GM 端角色管理入口保持不变。
- **GM 指令支持经验修正**：GM 指令新增「给XX加经验100点 / give 100 xp to XX」等写法，直接写入角色经验，符合升级条件的角色将在下一轮结算自动升级（仅对使用经验升级的规则生效；CoC 规则使用技能成长检定，不受影响）。
- **错误消息本地化**：API 错误消息接入稳定错误码（error_code），英文/日文界面下常见错误（未加入本局、房间密码错误、仅 GM 可操作等）显示对应语言文案；未覆盖的错误回退原样显示，不影响任何现有功能。
- **插件兜底 README 按内容语言生成**：内容包未自带 README 时，生成的说明按包的内容语言输出（中文/英文/日文），不再固定中文。

### 修复

- **被踢玩家无法重新加入**：此前玩家被 GM 踢出后，浏览器仍缓存旧身份，再次打开邀请链接会被直接送到游玩页并反复提示「未加入本局」，只能借助隐身窗口恢复。现在加入页与游玩页都会先校验本地身份是否仍是本局成员，失效时自动清理缓存并引导玩家重新创建角色加入；房间密码等加入门槛不受影响。
- **检定结果卡片浅色模式看不清**：检定卡片背景原先固定为深色渐变，切换到浅色主题后深底深字难以辨认。现在卡片与骰面底纹跟随主题变量，深色模式外观不变。
- **编辑页技能区缺少规则提示**：角色管理页编辑技能时，现在会显示当前规则的技能说明（如 CoC 的 d100 阈值、D&D 的熟练项说明）与技能数/技能点/单技能上限，超出上限标红提示；仅提示不拦截，与建卡页一致。
- **内容包世界书条目冗余标签**：内容包导入的世界书条目不再携带「类型：/来源插件：/描述：」前缀——类型与来源插件本就是条目的独立字段，重复拼入内容会挤占生成上下文，英文内容包也会出现中英混杂。主文本改为保真输出。
- **英文界面下的兜底属性名**：升级加点弹窗在规则属性缺失时的兜底属性，英文界面显示 STR/CON 等英文缩写而非中文。

## English

DiceFrame 2.2.0 adds player-driven growth and GM controls, and fixes a batch of issues including light-mode readability, kicked-player rejoin, and redundant lorebook entries.

### New

- **Players can allocate level-up attribute points themselves**: after leveling up, players see "X attribute points to allocate" on their character panel in the play view and can spend them directly; the GM-side management entry is unchanged.
- **GM commands support XP adjustments**: commands like "add 100 xp to XX" now write experience directly to the character sheet; characters meeting the threshold auto-level on the next round resolution (applies to XP-based rules only; CoC uses skill-growth checks and is unaffected).
- **Localized API error messages**: API errors now carry stable error codes; common errors (not in this game, wrong room password, GM only, etc.) show localized text in English/Japanese interfaces, with untranslated errors falling back to the original message — no functional impact.
- **Plugin fallback README follows content language**: when a content pack ships no README, the generated one now uses the pack's content language (Chinese/English/Japanese) instead of hardcoded Chinese.

### Fixes

- **Kicked players could not rejoin**: after a GM removed a player, the browser kept a stale identity, so reopening the invite link jumped straight to the play view and repeatedly showed "not part of this game" until an incognito window was used. Both the join and play views now verify the cached identity against the current roster; expired identities are cleared automatically and the player is guided back to character creation. Room-password gates are unchanged.
- **Check result cards unreadable in light mode**: the card background was a fixed dark gradient, so light-mode text (dark on dark) was hard to read. Cards and the die face now follow theme variables; dark mode looks unchanged.
- **Missing rule hints in the character editor**: editing skills in the character management page now shows the rule's skill explanation (e.g. CoC d100 thresholds, D&D proficiency notes) plus skill count / skill points / per-skill cap, with over-limit values highlighted. Hints only — nothing is blocked, matching the character-creation page.
- **Redundant labels in content-pack lorebook entries**: imported entries no longer carry "类型：/来源插件：/描述：" prefixes — type and source plugin are already dedicated entry fields, the duplicated text wasted generation context and mixed Chinese labels into English packs. Primary text is now output as-is.
- **Fallback attribute names in English UI**: when a rule provides no attribute definitions, the level-up dialog fallback attributes now show STR/CON etc. in English interfaces instead of Chinese.

### Download Guide

- **Regular Windows users**: download `DiceFrame-v2.2.0-windows-portable.zip`.
- **Source-run users**: download `DiceFrame-v2.2.0-windows.zip`.
- `.sha256` files are update checksums; regular users do not need to download them manually.

# DiceFrame v2.1.3

## 中文

DiceFrame 2.1.3 是一次补丁更新，为玩家自助成长与 GM 控制补充能力，并修复浅色模式下的阅读问题。

### 修复

- **被踢玩家无法重新加入（2.1.2）**：此前玩家被 GM 踢出后，浏览器仍缓存旧身份，再次打开邀请链接会被直接送到游玩页并反复提示「未加入本局」，只能借助隐身窗口恢复。现在加入页与游玩页都会先校验本地身份是否仍是本局成员，失效时自动清理缓存并引导玩家重新创建角色加入；房间密码等加入门槛不受影响。
- **检定结果卡片浅色模式看不清**：检定卡片背景原先固定为深色渐变，切换到浅色主题后深底深字难以辨认。现在卡片与骰面底纹跟随主题变量，深色模式外观不变。
- **编辑页技能区缺少规则提示**：角色管理页编辑技能时，现在会显示当前规则的技能说明（如 CoC 的 d100 阈值、D&D 的熟练项说明）与技能数/技能点/单技能上限，超出上限标红提示；仅提示不拦截，与建卡页一致。

### 新增

- **玩家自助分配升级属性点**：升级获得自由属性点后，玩家在游玩页角色面板即可看到「有 X 点属性待分配」并自助加点，无需再请求 GM 代加；GM 端角色管理入口保持不变。
- **GM 指令支持经验修正**：GM 指令新增「给XX加经验100点 / give 100 xp to XX」等写法，直接写入角色经验，符合升级条件的角色将在下一轮结算自动升级（仅对使用经验升级的规则生效；CoC 规则使用技能成长检定，不受影响）。

### 下载指南

- **普通 Windows 用户**：下载 `DiceFrame-v2.1.3-windows-portable.zip`。
- **源码运行用户**：下载 `DiceFrame-v2.1.3-windows.zip`。
- `.sha256` 是更新校验文件，普通用户不需要手动下载。

## English

DiceFrame 2.1.3 is a patch release that improves player-driven growth and GM controls, and fixes readability issues in light mode.

### Fixes

- **Kicked players could not rejoin (2.1.2)**: after a GM removed a player, the browser kept a stale identity, so reopening the invite link jumped straight to the play view and repeatedly showed "not part of this game" until an incognito window was used. Both the join and play views now verify the cached identity against the current roster; expired identities are cleared automatically and the player is guided back to character creation. Room-password gates are unchanged.
- **Check result cards unreadable in light mode**: the card background was a fixed dark gradient, so light-mode text (dark on dark) was hard to read. Cards and the die face now follow theme variables; dark mode looks unchanged.
- **Missing rule hints in the character editor**: editing skills in the character management page now shows the rule's skill explanation (e.g. CoC d100 thresholds, D&D proficiency notes) plus skill count / skill points / per-skill cap, with over-limit values highlighted. Hints only — nothing is blocked, matching the character-creation page.

### New

- **Players can allocate level-up attribute points themselves**: after leveling up, players see "X attribute points to allocate" on their character panel in the play view and can spend them directly; the GM-side management entry is unchanged.
- **GM commands support XP adjustments**: commands like "给XX加经验100点" or "give 100 xp to XX" now write experience directly to the character sheet; characters meeting the threshold auto-level on the next round resolution (applies to XP-based rules only; CoC uses skill-growth checks and is unaffected).

### Download Guide

- **Regular Windows users**: download `DiceFrame-v2.1.3-windows-portable.zip`.
- **Source-run users**: download `DiceFrame-v2.1.3-windows.zip`.
- `.sha256` files are update checksums; regular users do not need to download them manually.

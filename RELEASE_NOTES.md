# DiceFrame v2.1.2

## 中文

DiceFrame 2.1.2 是一次补丁更新，修复多人游戏中被移出对局的玩家无法重新加入的问题。

### 修复

- **被踢玩家无法重新加入**：此前玩家被 GM 踢出后，浏览器仍缓存旧身份，再次打开邀请链接会被直接送到游玩页并反复提示「未加入本局」，只能借助隐身窗口恢复。现在加入页与游玩页都会先校验本地身份是否仍是本局成员，失效时自动清理缓存并引导玩家重新创建角色加入；房间密码等加入门槛不受影响。

## English

DiceFrame 2.1.2 is a patch release that fixes kicked players being unable to rejoin a multiplayer game.

### Fixes

- **Kicked players could not rejoin**: after a GM removed a player, the browser kept a stale identity, so reopening the invite link jumped straight to the play view and repeatedly showed "not part of this game" until an incognito window was used. Both the join and play views now verify the cached identity against the current roster; expired identities are cleared automatically and the player is guided back to character creation. Room-password gates are unchanged.

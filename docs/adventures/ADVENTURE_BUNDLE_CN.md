# Adventure Bundle v1 冒险包格式

Adventure Bundle 是可选、只含数据的剧情包。它不拥有规则机制或世界书；未选择冒险包时，专业规则直接进入标准自由对局。

## 目录与身份

```text
templates/adventures/<directory_id>/
├─ manifest.json
├─ adventure.json
├─ content/**/*.json
└─ locales/<locale>/**/*.json
```

目录名只是安全的本地查找键。权威身份来自 manifest 的 `adventure_id`，当前格式固定为 `diceframe:adventure-graph-v1`。Canonical entity 具有稳定的 `kind:id`；locale 只能覆盖白名单展示字段，不能改变引用、门槛、遭遇或任何 mechanics。

## Manifest 与兼容性

Manifest 必须声明：

- `schema_version = 1`、canonical `adventure_id`、`version` 与 `format`；
- `required_runtime.id` 和 `required_runtime.minimum_version`；
- `world_policy = fixed | portable | agnostic`；
- `fixed` 冒险所需的 `recommended_world_id`；
- default/supported locales。

目录、实体、内部引用、locale target 和禁止执行代码的检查以整个包为原子单位，任一错误都会拒绝加载。包中不得出现 `python`、`javascript`、`script`、`code`、`eval`、`module` 或 `callable` 键。

## 持久化绑定

创建对局时，服务端先验证所选规则 runtime 是否支持该格式及最低版本，并检查世界策略。通过后，将以下精确绑定保存到 `GameInstance.adventure_binding`：

```text
adventure_id
version
format
content_digest
world_id
```

`content_digest` 覆盖 manifest、canonical 内容和全部 locale，并包含相对路径以避免同名文件冲突。重开保留这个绑定；运行时每次加载重新校验，内容被替换、版本不符或 fixed-world 不匹配均拒绝继续。世界切换不能绕过 fixed-world 绑定。

## 运行边界

Adventure Bundle 可以提供一个剧情图，以及其引用的 scene、npc、map_location 和 encounter_catalog。它不能执行代码，不能直接修改角色或战斗状态，也不能向 generic d20 注入行为。D&D runtime 通过明确的适配边界解析剧情门槛和专属遭遇，所有实际状态变化仍必须经过权威 Intent、EventBatch 和 reducer。

叙事同时使用当前冒险步骤和玩家实际选择的 Worldbook。冒险完成后清除剧情门槛并进入同一世界的标准自由对局；前端 Coach 提示只存在于本地展示层，不提交 Intent，也不写入公共时间线。

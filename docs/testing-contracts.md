# DiceFrame Critical Contract Matrix

> 判断一个测试能不能删，看这张表；不看测试文件数量。
> 每一行是一个产品契约，"必须覆盖"列出契约要求的验证层次，"当前测试"是现状映射。
> 契约覆盖可以合并、改写，但不能消失。

| # | Contract（契约） | 必须覆盖 | 当前测试 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 玩家不能调用 GM-only API（危险操作需确认头） | unit + API integration | test_webui_route_permissions、test_turn_service（403/409）、test_gm_identity | ✅ |
| 2 | GM/玩家权限隔离（GM 数据不进玩家响应） | unit + API integration | test_gm_controls（私聊隔离）、test_webui_route_permissions、test_authority_guard | ✅ |
| 3 | 玩家 A 不能读取玩家 B 私有状态 | integration | test_dnd2024_character_lifecycle（403 intruder）、test_kp_questions（私密可见性）、test_gm_controls | ✅ |
| 4 | share mode / share-link 权限边界 | unit + API | test_web_server_bot_auth（share-link 白名单）、test_bridge_links | ✅ |
| 5 | Bot actor 身份校验（玩家代表、非法 actor 拒绝） | unit + API | test_web_server_bot_auth、test_bot_access（token 一次性/轮换） | ✅ |
| 6 | access password / token / SSE 票据边界 | unit + API | test_access_password、test_sse_ticket（单次使用）、test_owner_login | ✅ |
| 7 | 玩家私有信息不进入其他玩家可见面（API 响应/日志视图） | unit + API integration | tests/integration/test_permissions（真实链路）、test_gm_controls、test_webui_route_permissions | ✅（复核：DiceFrame 无独立 hidden lore 条目，隐藏信息由 private_log/info_asymmetry + GM-only 端点构成） |
| 8 | 私有内容不进公开叙事/公开 context | integration | tests/integration/test_permissions（叙事与 get_log 不泄露）、test_authority_guard | ✅ |
| 9 | 不同房间/游戏数据不串（game_id 隔离） | unit + integration | test_sse_cursor（game_key 绑定）、test_game_instance、test_authority_guard | ✅ |
| 10 | 多人状态不串：actor ownership、turn owner | unit | test_combat_check_authority（多人不交叉）、test_turn_service、test_authority_guard | ✅ |
| 11 | 一个玩家操作不修改其他玩家状态 | unit | test_state_update_guard（无检定伤害被丢弃）、test_authority_guard（状态白名单） | ✅ |
| 12 | 老版本存档可读取、别名迁移不丢数据 | migration integration | test_dnd5e_v2_save_aliases、test_dnd2024_adventure_binding_compat、tests/fixtures/legacy_rules（12 份旧规则回归） | ⚠️ 别名用例偏薄，保留并建议补充 |
| 13 | DB schema 迁移幂等、失败回滚、拒绝未来版本 | KEEP_STRICT | test_sqlite_migrations、test_lorebook_store（schema 迁移） | ✅ |
| 14 | reload 后关键状态一致（存档往返） | integration | test_game_instance（序列化往返/增量写）、test_audit_checklist_completion（重启恢复）、tests/integration/test_game_flow（整条链路重建后一致且可继续）、rulesets m6（存档恢复） | ✅ |
| 15 | path traversal / symlink / zip 解压边界 | unit | test_updater、test_docker_launcher、test_avatar_service、test_bot_extension_routes、test_bundle_loader、test_plugin_host | ✅ |
| 16 | 存档上传大小/多文件拒绝（防 DoS） | unit | test_save_upload_limits、test_abuse_guard（速率限制） | ✅ |
| 17 | TLS / 证书安全：自签生命周期、ACME、私钥不泄露、配置不影响游戏业务 | unit + architecture | test_self_signed_certificate、test_acme_client、test_security_transport_routes、test_web_transport_config | ✅ |
| 18 | 插件沙箱权限边界（环境隔离、权限扩展阻止、内容校验） | unit | test_plugin_host、test_marketplace（权限扩展阻止）、test_plugin_provider（fail-closed） | ✅ |
| 19 | 骰子公式与判定表（d20/d100/CoC/bonus/advantage） | KEEP_STRICT 穷举 | test_dice、test_dice_rule_matrix（oracle）、test_advantage_authority | ✅（去重不降覆盖） |
| 20 | HP/伤害/治疗/死亡豁免/战斗核心规则 | KEEP_STRICT | test_death_saves、test_dnd5e_lite_mechanics、test_dnd2024_combat、test_combat_check_authority、test_d_fixes | ✅ |
| 21 | action economy / 回合推进 / luck 原子性 | unit + integration | test_turn_service、test_check_and_gm_command_flow、test_calc_logic、tests/integration/test_multiplayer_concurrency（并发提交只推进一次且 actor 不串） | ✅ |
| 22 | DND / COC 核心规则与 ruleset 隔离（不串 runtime） | unit + integration | test_runtime_registry（绑定解析/重复拒绝）、test_builtin_rules_v2、test_content_v2_contracts（locale 不改 mechanics） | ✅ |
| 23 | locale 不改 canonical identity / mechanics，V2 不新增全文复制式本地化 | KEEP_STRICT + architecture | test_builtin_rules_v2（mechanics_snapshot）、test_content_v2_worlds、test_adventure_bundles、test_world_template_summary、architecture（禁 `_en.json` 副本） | ✅ |
| 24 | 架构依赖方向：engine/rules 不依赖 webui，web_transport 不依赖业务域，compat 不反向侵入 | architecture（AST 级） | tests/architecture/test_dependencies.py（AST import 分析，已负向验证可捕获违规） | ✅ 已重写 |
| 25 | startup 代码不混入 migration 逻辑 | architecture（AST 级） | tests/architecture/test_migration_boundaries.py（AST 字面量扫描，忽略注释措辞） | ✅ 已重写 |
| 26 | Table-talk / KP 提问只读：不消耗 action、不推进 round、不改 state、不泄露隐藏信息 | integration | test_kp_questions（只读语义 + 隔离） | ✅（prompt 文案断言本轮放松，契约保留） |
| 27 | LLM 输出不能绕过 engine 直接改状态（防篡改） | unit | test_state_update_guard、test_parser（sanitize 防泄漏）、test_dnd2024_character_lifecycle（forged HP 重建） | ✅ |
| 28 | 日志/诊断导出脱敏（secret/token/API key 不泄露） | KEEP_STRICT | test_runtime_diagnostics、test_runtime_logging | ✅ |
| 29 | CORS / 安全头 / noindex 稳定 | KEEP_STRICT | test_webui_cors、test_search_engine_blocking | ✅ |
| 30 | 升级/更新安全：checksum、回滚、原子性 | KEEP_STRICT | test_updater、test_system_update、test_docker_updater | ✅ |

状态说明：✅ 已有足够覆盖（允许去重/改写）；⚠️ 有缺口，需要新增测试补齐；🔧 本轮重写。

## 新增测试对契约的补齐

- `tests/integration/test_permissions.py` → 契约 2、3、7、8（私有信息仅投递属主、公开面不泄露、GM 悄悄话玩家范围校验；真实 WebAPI→handler→registry 链路）
- `tests/integration/test_game_flow.py` → 契约 14（创建→行动→存档→整条链路重建→状态一致且可继续推进）
- `tests/integration/test_multiplayer_concurrency.py` → 契约 21（多人同时提交行动，actor/text 保持配对且一个回合只推进一次）

## 使用规则

- 删除/合并任何测试前，先确认其对应契约行仍有覆盖。
- 同一契约允许从「5 层重复」减到「1 个边界 unit + 1 个 API integration」。
- 新增测试前问：它保护表中哪一行？若不属于任何一行且只是锁实现，不写。

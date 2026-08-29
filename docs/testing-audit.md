# DiceFrame 测试体系审计报告（V2 减负方案 · 第一阶段）

- 审计日期：2026-08-29
- 审计基线：`main`（916f1f8），分支 `refactor/test-suite-slimming`
- 基线数据：
  - 后端测试文件 147 个（+ `conftest.py`），pytest 收集 **1540 用例（1539 通过 / 1 跳过）**，全套约 94 秒
  - 前端单元测试文件 76 个，约 332 个用例（Vitest）
  - 前端 e2e spec 10 个（Playwright，CI 仅跑 smoke 子集）
  - 测试基础设施薄弱：`tests/conftest.py` 只做 sys.path 注入，无共享真实链路 harness；多个文件各自重复实现 FakeAPI / FakeRegistry / FakeInstance

## 分类标准

| 分类 | 含义 |
| --- | --- |
| CRITICAL_CONTRACT | 保护关键契约（权限/数据隔离/存档迁移/安全/多人一致性/核心规则），覆盖必须保留，允许去重 |
| KEEP_STRICT | 确定性逻辑（规则、parser、migration、schema、状态机），精确断言合理 |
| KEEP_BEHAVIOR | 功能重要，但断言方式应从内部实现改为可观察行为 |
| RELAX_IMPLEMENTATION | 锁实现细节（源码字符串、内部类名、mock 调用参数），应改写或删除 |
| MERGE_DUPLICATE | 与其他层/文件重复保护同一行为，合并保留最有价值的一份 |
| REMOVE_LOW_VALUE | UI 文案逐字、DOM 结构、prompt 全文、大型快照等，可直接删 |
| CONVERT_TO_INTEGRATION | 业务重要但单元形态价值低，应转为真实链路 integration 测试 |

判断原则：**如果未来彻底重写内部实现但用户可观察行为不变，这个测试还应通过吗？** 应该 → 写成行为测试；不应该 → 必须说明为什么该内部结构本身是架构契约。

`critical` 标记独立于主分类：表示该文件保护关键契约（无论测试风格是否需要整改）。

---

## 一、后端分类明细

### tests/rulesets/（17 个文件）

| 文件 | 分类 | critical | 保护的契约 | 主要问题 | 动作 |
| --- | --- | --- | --- | --- | --- |
| test_bundle_loader | KEEP_STRICT | yes | Bundle 加载安全边界（路径遍历、拒可执行内容、locale 不改 mechanics） | - | 保留 |
| test_dnd2024_advancement_access | KEEP_STRICT | yes | 升级权限隔离、XP 阈值单次触发、entitlement 幂等 | - | 保留 |
| test_dnd2024_campaign | CRITICAL_CONTRACT | yes | session zero 全员同意、party decision、GM-only automation、存档重放幂等 | 部分断言精确 event 结构 | 保留，event 断言放松为关键字段 |
| test_dnd2024_character_builder | KEEP_STRICT | yes | 角色构建确定性、binding 防篡改、legacy 投影不覆盖 canonical | `content_version == "srd-5.2.1+r5"` 锁版本字符串 | 版本断言放宽为存在性检查 |
| test_dnd2024_character_lifecycle | CRITICAL_CONTRACT | yes | legacy 接口拒绝专业角色、forged HP 重建、403 越权、服务端掷骰 | - | 全部保留 |
| test_dnd2024_combat | CRITICAL_CONTRACT | yes | 攻击/法术/死亡豁免/专注/先攻/幂等、catalog 替换 forged 敌人 | 数值依赖种子化 RNG，合理 | 保留 |
| test_dnd2024_director | KEEP_BEHAVIOR | no | Director 分类、combat defer、read-only projection | 断言 text 长度 == 500 锁截断常量 | 改为「不超过上限」 |
| test_dnd2024_director_planner | RELAX_IMPLEMENTATION | no | AI planner 拒绝虚构 choice / 低置信度 | 断言 `kwargs["tools"][0]["function"]["name"]` 内部 tool 名 | 改写为输出行为断言 |
| test_dnd2024_m4_http | CONVERT_TO_INTEGRATION | no | M4 无状态 HTTP 契约 | 与 m5/m6 各自重复构造 API shim | 并入统一 integration harness |
| test_dnd2024_m5_http | CONVERT_TO_INTEGRATION | yes | 身份强制、意图持久化重放、intent 冲突 | 同上 | 同上 |
| test_dnd2024_m6_http | CONVERT_TO_INTEGRATION | yes | session+tutorial+combat 端到端、存档恢复 | `memory.calls` 内部结构断言 | 保留流程，probe 断言改行为级 |
| test_dnd2024_progression | KEEP_STRICT | yes | SRD 进阶表正确性 | `source_ref` 前缀锁版本号 | 前缀断言放宽 |
| test_dnd2024_resting | KEEP_STRICT | no | 短休/长休/力竭规则 | 精确 source_ref 字符串 | 删除 source_ref 断言 |
| test_dnd2024_spells | KEEP_STRICT | no | 法术目录完整性 | 每级数量精确断言（可接受，目录即契约） | 保留 |
| test_event_batches | KEEP_STRICT | yes | 事件批处理原子性/版本控制/重试幂等/回滚 | - | 保留 |
| test_ruleset_automation | KEEP_BEHAVIOR | no | automation 失败回滚、narration summary | 逐字断言中英文 summary 文案 | 改为包含关键词 |
| test_runtime_registry | KEEP_STRICT | yes | runtime 绑定解析、版本兼容、重复拒绝、legacy fallback | - | 保留 |

### tests/ 顶层（130 个文件）

| 文件 | 分类 | critical | 保护的契约 | 主要问题 | 动作 |
| --- | --- | --- | --- | --- | --- |
| test_abuse_guard | KEEP_STRICT | yes | 速率限制与 AI 并发防护 | 错误文案子串断言 | 保留 429 行为，去文案匹配 |
| test_access_password | CRITICAL_CONTRACT | yes | 访问密码哈希验证 | `deleted == [True]` 锁 monkeypatch 副作用 | 改为断言文件不存在 |
| test_acme_client | KEEP_BEHAVIOR | yes | TLS 证书签发与续期 | - | 保留（已是行为级集成） |
| test_active_rule_and_combat_guard | CRITICAL_CONTRACT | yes | 战斗/检定规则、非战斗误伤防护 | 与 advantage_authority 部分重叠 | 去重协助/优势用例 |
| test_advantage_authority | CRITICAL_CONTRACT | yes | 优劣势判定权威 | - | 保留 |
| test_adventure_bundles | CRITICAL_CONTRACT | yes | 冒险包 locale 不改 identity/mechanics、拒执行内容 | - | 保留 |
| test_adventure_management | KEEP_BEHAVIOR | yes | 冒险 CRUD/导入导出/绑定保护 | filename 精确匹配 | 放宽文件名格式 |
| test_ai_check_planner | KEEP_STRICT | no | 检定规划归一化、DC 上限、安全网 | - | 保留 |
| test_ai_providers | KEEP_BEHAVIOR | yes | 凭据隔离、密钥不落盘、运行时重建 | monkeypatch `_build_subsystems` 捕获内部参数 | 改为公开 API 输出断言 |
| test_announcements | KEEP_BEHAVIOR | no | 公告缓存/离线降级/语言隔离 | 锁内部函数 `_file_for_language` | 改为端点行为测试 |
| test_architecture_boundaries | RELAX_IMPLEMENTATION | yes* | 模块依赖方向约束 | 9 个测试中 7 个是源码子串扫描；`"RuleBundleLoader" in source` 类名锁 | 重写为 AST import 分析，搬到 tests/architecture/（详见专项） |
| test_asr | KEEP_STRICT | no | ASR 请求构建、content-type 归一化 | - | 保留 |
| test_asr_routes | KEEP_BEHAVIOR | yes | ASR 路由权限、错误码映射 | `api.calls == [...]` 锁调用参数 | 改断言响应 |
| test_assistant | KEEP_BEHAVIOR | no | 流式回复、脱敏日志、截断重试 | 断言 prompt 文案子串（"官方文档助手"等） | 保留事件结构，去文案 |
| test_assistant_knowledge | KEEP_BEHAVIOR | no | 知识检索、失败缓存 TTL | 断言内部常量 `_CONTENT_DOC_PATHS` | 改为返回结果断言 |
| test_attribute_display | REMOVE_LOW_VALUE | no | 属性格式化逐字输出 | 整文件只测一个格式化函数 | **删除** |
| test_audit_checklist_completion | CRITICAL_CONTRACT | yes | 创建→回合→支付→重启→重置全链路 | - | 保留（golden path） |
| test_authority_guard | CRITICAL_CONTRACT | yes | 多人状态白名单、GM 指令隔离 | - | 保留 |
| test_avatar_service | KEEP_BEHAVIOR | no | 头像上传裁剪、路径遍历防护 | - | 保留 |
| test_bot_access | CRITICAL_CONTRACT | yes | Bot 绑定 token 一次性验证与轮换失效 | - | 保留 |
| test_bot_extension_routes | KEEP_BEHAVIOR | yes | bridge 可信 caller 注入、卡片物化、路径遍历 | 访问 `response._path` 私有属性 | 改读 body |
| test_bridge_card_renderer | KEEP_BEHAVIOR | no | 卡片渲染换行/截断/缓存 | 测私有函数但行为可观察 | 保留 |
| test_bridge_i18n | KEEP_STRICT | yes | bridge 多语言绑定、平台中立命令前缀 | - | 保留 |
| test_bridge_links | KEEP_STRICT | no | join link URL 编码、反向代理路径 | - | 保留 |
| test_build_portable | KEEP_STRICT | no | portable 构建 SHA-256 校验 | - | 保留 |
| test_builtin_rules_v2 | CRITICAL_CONTRACT | yes | 多 locale mechanics_snapshot 一致、legacy 兼容 | - | 保留 |
| test_calc_logic | CRITICAL_CONTRACT | yes | GOLD/PAY/SAN/LUCK 标签解析、回滚恢复 | swipe 测试直接构造内部 dict | 保留，改走公开 API |
| test_character_cards | KEEP_BEHAVIOR | no | 角色卡导入导出往返、NPC lorebook 幂等 | content 字符串子串锁格式 | 改结构化字段检查 |
| test_check_and_gm_command_flow | CRITICAL_CONTRACT | yes | 检定流程、luck 原子性、GM 指令隔离、叙事清洗 | sanitize 输出精确字符串断言 | 放松为「不含系统块标记」 |
| test_combat_check_authority | CRITICAL_CONTRACT | yes | CheckResult 权威绑定、多人不交叉、重入幂等 | - | 保留（战斗安全核心） |
| test_combat_integration | MERGE_DUPLICATE | no | 伤害计算、大失败零伤、narrative 模式 | 与 combat_check_authority 大量重叠 | 独有叙事用例并入 authority 后删除 |
| test_config_runtime_reload | RELAX_IMPLEMENTATION | no | 配置热重载替换/复用/回滚 | 全篇 monkeypatch `_build_subsystems` + `is` 身份断言 | 改写为行为测试（配置生效后行为变化） |
| test_connection_test_timeout | KEEP_STRICT | no | 超时参数校验与钳制 | - | 保留 |
| test_content_v2_contracts | CRITICAL_CONTRACT | yes | ResourceRef 解析、locale overlay 拒绝篡改 mechanics | - | 保留 |
| test_content_v2_worlds | CRITICAL_CONTRACT | yes | 世界模板 locale 保持 canonical identity | - | 保留 |
| test_context_builder | KEEP_BEHAVIOR | no | 上下文窗口收缩优先级、极端输入不超窗 | 硬编码模型名→字符数映射 | 删模型映射用例，保留收缩行为 |
| test_contract_snapshot | RELAX_IMPLEMENTATION | no | 后端返回字段 ⊆ 前端 TS interface | 正则解析 Python 源码提取 return dict key | 改为运行时 schema 比对或删除 |
| test_d_fixes | KEEP_STRICT | yes | B2 难度不叠加、lethal_narrative、存档原子写 | - | 保留 |
| test_death_saves | CRITICAL_CONTRACT | yes | D&D 死亡豁免状态机 | - | 保留 |
| test_dice | KEEP_STRICT | yes | d20/d100/CoC/bonus 骰解析与判定 | 与 dice_rule_matrix 穷举重叠（判定表部分） | 保留 parser，判定用例去重 |
| test_dice_campaign_audit | KEEP_BEHAVIOR | no | 战役级骰子分布审计 | 断言精确 scenario 名称集合 | 放松为 ok + error_count=0 |
| test_dice_rule_matrix | KEEP_STRICT | yes | CoC/d20 判定表穷举 oracle | - | 保留（规则黄金测试） |
| test_dnd2024_adventure_binding_compat | KEEP_STRICT | yes | 未发布冒险绑定迁移兼容 | - | 保留 |
| test_dnd5e_lite_mechanics | KEEP_STRICT | yes | 5e 伤害/护甲/暴击核心规则、多语言一致 | - | 保留 |
| test_dnd5e_v2 | KEEP_STRICT | no | V2 canonical id、locale 显示分离 | 断言原始 JSON 字段值 | 改走 mechanics_snapshot |
| test_dnd5e_v2_save_aliases | KEEP_STRICT | yes | 老存档别名→canonical id 迁移 | 仅 1 用例，覆盖薄 | 保留并补充 |
| test_docker_launcher | KEEP_STRICT | yes | 更新包路径穿越/symlink 防护、回滚、TLS 钉扎 | monkeypatch 大量内部方法 | 保留安全/回滚，health 细节放松 |
| test_docker_release_validation | KEEP_STRICT | no | Docker runtime 依赖完整性 | - | 保留 |
| test_docker_updater | KEEP_BEHAVIOR | no | Docker 更新下载/checksum/staging | 断言 signal JSON 内部字段 | 改行为断言 |
| test_freeform_sandbox | KEEP_STRICT | no | sandbox 模板为空、deprecated 不 seed | - | 保留 |
| test_game_instance | KEEP_STRICT | yes | GameInstance 状态机、序列化、增量存档、rollback、import 安全 | 1041 行多子领域 | 保留，后续可拆分 |
| test_game_list_order | KEEP_BEHAVIOR | no | 游戏列表排序、max_players 透传 | - | 保留 |
| test_generation_creator | KEEP_BEHAVIOR | no | 生成内容禁用词清洗、属性压缩 | - | 保留 |
| test_gm_controls | KEEP_BEHAVIOR | yes | GM 私聊隔离、删角色清理、solo、视角持久化 | DummyAPI 手工构造耦合内部接口 | 保留核心隔离测试 |
| test_gm_identity | KEEP_STRICT | yes | GM 身份判定、403 权限边界 | - | 保留 |
| test_hub_client | KEEP_BEHAVIOR | no | Hub 连接/熔断/身份轮换/遥测开关 | fake server + monkeypatch 内部 | 保留关键行为，精简缓存细节 |
| test_imagegen_routes | MERGE_DUPLICATE | no | 图片生成路由权限/校验 | 与 imagegen_service 双层测同一 generate 流程 | routes 只留权限+状态码映射 |
| test_imagegen_service | KEEP_BEHAVIOR | no | 生成服务、purpose 尺寸、provider 重试 | - | 保留 |
| test_intents_table | KEEP_STRICT | no | 检定意图词表映射 | - | 保留 |
| test_kp_question_route | MERGE_DUPLICATE | no | KP 提问路由（channel/限流） | 与 kp_questions 双层测同一 ask 流程 | route 只留 HTTP 契约 |
| test_kp_questions | KEEP_BEHAVIOR | yes | KP 提问只读、不消耗行动、数据隔离 | 断言 prompt 文案（"不得推进时间"）与 LLM 调用参数 | 保留契约，去 prompt 文案/参数断言 |
| test_language_support | KEEP_STRICT | no | 语言归一化、回退链、prompt 组装 | prompt 片段子串断言、调用顺序断言 | 改结构化字段检查 |
| test_legal | KEEP_STRICT | yes | 法律文档版本化、哈希防降级 | - | 保留 |
| test_llm_client | KEEP_BEHAVIOR | yes | 截断重试、provider fallback、tool calling 协议 | 断言请求体 JSON/header 细节（anthropic-version 等） | 保留行为，请求体断言抽契约 fixture |
| test_login_audit | KEEP_STRICT | yes | 登录审计持久化与容错 | - | 保留 |
| test_lorebook_matcher | KEEP_STRICT | yes | lorebook 匹配引擎（regex/NOT/group） | - | 保留 |
| test_lorebook_store | CRITICAL_CONTRACT | yes | SQLite schema 迁移、数据不丢失、CRUD | 访问 `store._conn` 私有属性、PRAGMA 版本号 | 保留迁移测试，封装私有访问 |
| test_map_backgrounds | KEEP_BEHAVIOR | no | 地图背景上传、去重、校验 | - | 保留 |
| test_marketplace | KEEP_BEHAVIOR | yes | 插件市场权限扩展阻止、下载完整性 | URL 拼接细节断言 | 保留权限策略，弱化 URL 断言 |
| test_memory_edit | KEEP_BEHAVIOR | no | memory 编辑/遗忘 | 可与 memory_store 合并 | 合并 |
| test_memory_store | KEEP_BEHAVIOR | no | delta 应用、分页、session 隔离 | 测内部方法 `get_unembedded` | 改走公开接口，与 memory_edit 合并 |
| test_migration_boundaries | RELAX_IMPLEMENTATION | yes | 防 startup 代码混入 migration 逻辑 | 全文 `marker.lower() in text.lower()` 源码扫描 | 重写为 AST 级检查 |
| test_model_request_timeout | KEEP_STRICT | no | timeout 配置校验 | - | 保留 |
| test_network_proxy | KEEP_STRICT | no | proxy URL 校验/mask | - | 保留 |
| test_owner_login | CRITICAL_CONTRACT | yes | 认证隔离、公开/受保护路由、登录审计 | - | 保留（认证黄金测试，走真实 HTTP） |
| test_parser | KEEP_STRICT | yes | LLM 输出解析、sanitize 防泄漏、标签归一化 | - | 保留 |
| test_person_key_item_guard | KEEP_STRICT | no | KEY_ITEM 警告不丢数据 | - | 保留 |
| test_plugin_bridge_sdk | KEEP_STRICT | no | bridge SDK JSON-RPC 协议 | - | 保留 |
| test_plugin_host | CRITICAL_CONTRACT | yes | 插件沙箱、路径穿越、zip bomb、世代文件、content pack | 2896 行；约 30% 断言私有属性/模块常量 | 拆分 ≥4 文件，私有断言改公开行为 |
| test_plugin_provider | KEEP_STRICT | yes | provider capability 校验、RPC 往返、fail-closed | - | 保留 |
| test_plugin_tool_routes | KEEP_BEHAVIOR | no | tool route confirm header、delegation | `api.calls == [...]` 锁调用参数 | 改断言响应 |
| test_plugin_tool_sdk | KEEP_STRICT | no | tool SDK JSON-RPC 协议 | 与 plugin_host 内 stdio RPC 用例重叠 | 保留协议，host 侧去重 |
| test_portable_lock | KEEP_STRICT | yes | requirements lock 完整性、hash 校验 | - | 保留 |
| test_provider_model_catalog | KEEP_STRICT | no | model list URL/response 提取 | - | 保留 |
| test_puzzle | KEEP_STRICT | no | 谜题状态机、序列化往返 | - | 保留 |
| test_qq_napcat_builtin_sync | RELAX_IMPLEMENTATION | no | 内置 QQ 插件不退回手动掷骰 | 全文对 adapter 源码做 10 个字符串包含/排除断言 | 改为行为测试（消息→自动判定输出） |
| test_recall | KEEP_STRICT | no | 记忆召回实体提取、LIKE 粗筛 | `【相关记忆】` 文案断言 | 放宽文案，保留提取逻辑 |
| test_release_build | KEEP_STRICT | no | 发布包目录排除规则 | - | 保留 |
| test_resource_tags_triggers | KEEP_STRICT | yes | 资源标签解析、触发器一次性、状态播报 | 状态消息用例与 state_change_messages 重叠 | 状态消息用例并入对方 |
| test_round_helpers | KEEP_BEHAVIOR | no | multi-step 触发边界 | 锁中文日志措辞 | 改返回值断言 |
| test_round_llm_compression | KEEP_BEHAVIOR | no | 超长叙事压缩、标签可解析 | 锁 `max_tokens` 与 prompt 子串 | 保留压缩结果，删调用参数断言 |
| test_round_llm_streaming | KEEP_STRICT | yes | 流式过滤协议标签、骰子矛盾重试、降级 | 断言私有属性 `_tag_fail_streak` | 改经 health_events 间接断言 |
| test_round_summary_defer | KEEP_BEHAVIOR | no | 摘要延后不阻塞回合 | 断言内部集合 `_pending_summary_tasks` | 改为时序+最终结果断言 |
| test_rule_audit | KEEP_STRICT | no | 内容包规则文件发现、引用完整性 | - | 保留 |
| test_rule_system | KEEP_STRICT | yes | 安全表达式求值、规则继承、核心公式、标签白名单 | 测私有 `_skill_base_value` | 保留，私有测试改经 validate_character |
| test_runtime_asyncio | KEEP_STRICT | no | Windows Proactor 断开误报过滤 | - | 保留 |
| test_runtime_diagnostics | KEEP_STRICT | yes | 日志导出脱敏（secret/token 不泄露） | - | 保留 |
| test_runtime_env | KEEP_STRICT | no | .env 不覆盖已有环境变量 | - | 保留 |
| test_runtime_log_routes | KEEP_BEHAVIOR | no | 日志清除确认头、导出 | `body == b"zip-content"` 精确匹配 | 改断言状态码与 content_type |
| test_runtime_logging | KEEP_STRICT | no | 日志轮转只删 diceframe.log、不暴露路径 | - | 保留 |
| test_save_upload_limits | CRITICAL_CONTRACT | yes | 存档上传大小限制、多文件拒绝（防 DoS） | - | 保留 |
| test_scene_image_round | KEEP_BEHAVIOR | no | 场景图调度、回滚跳过、失败不崩回合 | 请求对象字段精确断言 | 保留调度/容错，弱化字段断言 |
| test_scene_images | KEEP_BEHAVIOR | no | 上传归一化去重、默认图优先级 | 与 scene_image_round 层次不同，不算重复 | 保留 |
| test_search_engine_blocking | KEEP_STRICT | yes | 安全头、robots.txt、noindex meta | robots.txt 逐字（内容即契约，可接受） | 保留 |
| test_security_transport_routes | CRITICAL_CONTRACT | yes | TLS 传输事务契约（prepare/activate/token 一次性） | - | 保留 |
| test_self_signed_certificate | CRITICAL_CONTRACT | yes | 自签证书生命周期、私钥不泄露、损坏自愈 | - | 保留 |
| test_speech_routes | KEEP_BEHAVIOR | no | TTS 路由权限隔离、公开文本限制 | `api.calls` 精确参数断言 | 保留 403，弱化调用参数 |
| test_sqlite_migrations | CRITICAL_CONTRACT | yes | 迁移幂等、失败回滚版本、拒绝未来版本 | - | 保留 |
| test_sse_cursor | KEEP_STRICT | yes | SSE 游标、重连基线、连接泄漏防护 | 测内部哈希函数（确定性，可接受） | 保留 |
| test_sse_refresh | KEEP_STRICT | no | 回滚后 public signature 变化 | - | 保留 |
| test_sse_ticket | CRITICAL_CONTRACT | yes | SSE 票据绑定 game_key、单次使用 | - | 保留 |
| test_state_change_messages | KEEP_BEHAVIOR | no | 回合状态变动播报 | 逐字文案断言 | 改结构化断言 |
| test_state_update_guard | CRITICAL_CONTRACT | yes | 无检定结果的伤害被丢弃（防 LLM 篡改 HP） | - | 保留 |
| test_static_lore_highlight_contract | RELAX_IMPLEMENTATION | no | lore 高亮支持各条目类型 | 对前端 TS 源码做字符串断言 | **删除**（前端组件测试已覆盖渲染）或转前端行为测试 |
| test_story_recap | KEEP_BEHAVIOR | no | 回顾只用公开回合、增量生成 | 断言 `total_llm_calls` 与 prompt 子串 | 保留结果断言，放宽 prompt |
| test_system_update | KEEP_STRICT | no | semver 比较、频道选择 | monkeypatch 内部 fetch 符号 | 弱化对内部函数依赖 |
| test_template_catalog | KEEP_STRICT | yes | 模板同步不覆盖用户自定义、迁移兼容 | - | 保留 |
| test_tts | KEEP_BEHAVIOR | no | TTS 缓存、音色管理、公开文本过滤 | 精确比对 edge-tts 构造参数 | 保留行为，去 kwargs 比对 |
| test_tunnel_routes | CRITICAL_CONTRACT | yes | tunnel publish 鉴权、owner-only | 直接注入 `owner_authenticated` 绕过中间件 | status 检查改走真实中间件 |
| test_tunnel_service | KEEP_STRICT | yes | publish/release 状态机、HTTPS 校验、回滚原子性 | - | 保留 |
| test_turn_service | CRITICAL_CONTRACT | yes | 回合推进权限、状态门、force advance、行动队列 | FakeInstance 复制大量内部属性 | 保留契约，抽共享 harness |
| test_updater | KEEP_STRICT | yes | SHA-256 校验、zip 路径穿越、状态机、备份回滚 | - | 保留 |
| test_updater_routes | KEEP_BEHAVIOR | no | restart 确认头、重复拒绝、boot_id | monkeypatch 私有符号、断言内部字典键 | 保留状态码，去内部状态断言 |
| test_web_server_bot_auth | CRITICAL_CONTRACT | yes | bot token 鉴权、玩家代表校验、share-link 白名单 | 混入 generation_defaults 迁移测试 | 拆出迁移用例 |
| test_web_transport_config | KEEP_STRICT | yes | TLS 模式解析、ACME 校验、脱敏 | - | 保留 |
| test_webui_cors | KEEP_STRICT | yes | CORS preflight、credentials、Vary 稳定 | - | 保留 |
| test_webui_create_flow | KEEP_BEHAVIOR | yes | 创建游戏/角色/支付/重开/规则生成/原子回滚 | 2073 行；部分锁 prompt 文案与 LLM kwargs | 保留契约，去 prompt 断言；后续拆分 |
| test_webui_route_permissions | CRITICAL_CONTRACT | yes | GM-only 确认头、越权删除、批量鉴权 | - | 保留 |
| test_world_gallery_backend | KEEP_BEHAVIOR | no | 世界克隆、ID 唯一、GM style 归一化 | `.index()` 断言 prompt 五段顺序 | 改为必要 section 存在性断言 |
| test_world_template_summary | KEEP_STRICT | no | recommended_rules 清洗、locale 不改 identity | - | 保留 |

---

## 二、前端分类明细（frontend-v2/tests，76 个文件）

| 分类 | 数量 | 代表文件 |
| --- | --- | --- |
| CRITICAL_CONTRACT | 11 | apiClientPeerBoundary、joinIdentity、connection（URL 防 XSS）、StartupPrivacyChoice、apiClientConnectionRecovery、generatedImages（game-scoped+auth）、peerApi、peerGameBridge、peerProtocol、renderSafeMarkdown（XSS）、routerAccess |
| KEEP_STRICT | 19 | gameSse、gameContext、SettingsUpdateAutoDownload、appNavigation、assistantApi、characterCards、contentLanguage、mapBackgrounds、mapLayout、marketplaceUpdate、modelConfiguration、peerInvite、portraits、recommendedRules、ruleSchema、rulesetsApi、saveSorting、sceneImages、shareLink |
| KEEP_BEHAVIOR | 40 | 各面板/视图组件测试（ActionComposer、CheckRevealCard、Dnd2024* 系列等），普遍问题是锁 CSS class / DOM 层级 / 精确文案，应改为 role/text 行为断言（渐进整改，不阻塞本轮） |
| RELAX_IMPLEMENTATION | 3 | playLayoutContract（源码字符串）、settingsSections（Vue 模板字符串）、worldsStyleContract（CSS 正则）→ **本轮删除** |
| MERGE_DUPLICATE | 1 | pluginMarketplace（与 marketplaceUpdate 重复）→ **并入后删除** |
| REMOVE_LOW_VALUE | 1 | NapcatGuide（纯文案）→ **本轮删除** |
| CONVERT_TO_E2E | 1 | RulesetExperienceIntegration（重度 mock，e2e 已覆盖）→ **本轮删除** |

e2e（10 spec）已覆盖：登录/分享路由、单人转多人、GM+玩家同局、无密码邀请创角、P2P 直连、D&D 工作台与新手 builder 全流程、破坏性操作确认、插件布局、多视口响应式。

---

## 三、最严重的实现锁（Top 15）

1. `test_architecture_boundaries.py:122-124` — `assert "RuleBundleLoader" in rules_service`、`assert "rule_name_en" not in create_view`（类名/字段名字符串锁）
2. `test_architecture_boundaries.py:25-26` 等 7 处 — 源码子串扫描判依赖方向（注释/字符串都会误报）
3. `test_migration_boundaries.py:12-21` — 对 `src/**/*.py` 做 `marker.lower() in text.lower()` 扫描
4. `test_qq_napcat_builtin_sync.py:27-44` — 对 adapter 源码 10 个字符串包含/排除断言
5. `test_static_lore_highlight_contract.py:14-28` — 对前端 TS 源码断言接口名与 CSS 类名
6. `test_contract_snapshot.py:15-47` — 正则解析 Python 源码提取 `return {...}` 的 key
7. `test_config_runtime_reload.py:44-102` — monkeypatch `_build_subsystems` + 对象身份断言
8. `test_plugin_host.py:1908/2407/2544` — 调用私有方法、读 `_host_generation`、改模块级私有常量
9. `test_round_llm_streaming.py:367/395/418` — 断言私有属性 `_tag_fail_streak`
10. `test_dnd2024_director_planner.py:148/185` — 断言 `kwargs["tools"][0]["function"]["name"]`
11. `test_llm_client.py:192-198` — 锁 anthropic-version header 与 system prompt 文案
12. `test_kp_questions.py:247-255` — 断言 prompt 文案子串与 LLM temperature 参数
13. `test_webui_create_flow.py:558-559` — 锁 prompt 拼接文案
14. `test_world_gallery_backend.py:298-303` — `.index()` 锁 prompt 段落顺序
15. 前端 `playLayoutContract/worldsStyleContract/settingsSections` — 读源码字符串匹配

## 四、主要重复组

| 重复组 | 涉及文件 | 处理 |
| --- | --- | --- |
| 战斗伤害管线 | combat_integration + combat_check_authority + d_fixes | integration 独有叙事用例并入 authority |
| 骰子判定表 | dice + dice_rule_matrix + check_and_gm_command_flow | matrix 为权威，dice 删重叠判定用例 |
| CoC fumble 阈值 | dice / dice_rule_matrix / combat_check_authority 三处 | 保留 matrix + authority |
| 优劣势管道 | active_rule_and_combat_guard + advantage_authority | 保留 authority |
| 图片生成双层 | imagegen_routes + imagegen_service | routes 只留权限/状态码 |
| KP 提问双层 | kp_question_route + kp_questions | route 只留 HTTP 契约 |
| plugin stdio RPC | plugin_host + plugin_provider + plugin_tool_sdk + plugin_bridge_sdk | SDK 留协议，host 去重 |
| content-pack sync | plugin_host 内 5 个用例 | 合并为 1 个参数化用例 |
| memory | memory_edit + memory_store | 合并 |
| 状态变动消息 | state_change_messages + resource_tags_triggers | 合并 |
| HTTP API shim | rulesets m4/m5/m6 各自造 shim | 抽共享 harness |
| 插件版本比较 | 前端 pluginMarketplace + marketplaceUpdate | 合并 |
| D&D builder 流程 | 前端 Builder 单元 + RulesetExperienceIntegration + e2e | 删重复单元，e2e 为准 |

## 五、统计汇总

后端 147 个文件（主分类）：

| 分类 | 数量 |
| --- | --- |
| CRITICAL_CONTRACT | 30 |
| KEEP_STRICT | 62 |
| KEEP_BEHAVIOR | 41 |
| RELAX_IMPLEMENTATION | 7 |
| MERGE_DUPLICATE | 3 |
| REMOVE_LOW_VALUE | 1 |
| CONVERT_TO_INTEGRATION | 3 |

其中标记 `critical: yes`（保护关键契约）的后端文件约 77 个；前端 11 个。

前端 76 个文件：CRITICAL_CONTRACT 11、KEEP_STRICT 19、KEEP_BEHAVIOR 40、RELAX_IMPLEMENTATION 3、MERGE_DUPLICATE 1、REMOVE_LOW_VALUE 1、CONVERT_TO_E2E 1。

## 六、第一阶段执行结果（分支 `refactor/test-suite-slimming`）

基线：后端 1539 通过 / 1 跳过；前端 332 用例。完成后：后端 **1528 通过 / 1 跳过**，前端 **308 用例全过**，ruff 通过。

**已删除（低价值/实现锁）**
- `tests/test_attribute_display.py`（格式化逐字）
- `tests/test_static_lore_highlight_contract.py`（对前端 TS 源码做字符串断言）
- `tests/test_qq_napcat_builtin_sync.py`（源码/README 字符串扫描；主程序 CI 无法导入插件代码，防漂移契约归插件仓库 CI）
- `tests/test_architecture_boundaries.py`、`tests/test_migration_boundaries.py`（被 `tests/architecture/` 的 AST 级重写取代）
- 前端：`NapcatGuide.test.ts`、`playLayoutContract.test.ts`、`worldsStyleContract.test.ts`、`settingsSections.test.ts`、`RulesetExperienceIntegration.test.ts`、`pluginMarketplace.test.ts`（用例并入 marketplaceUpdate）

**已合并**
- `test_combat_integration.py` 的 4 个独有行为用例（叙事模式/徒手/击杀钳制/缺检定 fail-closed）并入 `test_combat_check_authority.py`，文件删除
- 前端 `pluginMarketplace` 的版本比较用例并入 `marketplaceUpdate`
- 复核后**不合并**（审计中的 MERGE 怀疑经逐文件复核不成立）：`imagegen_routes/imagegen_service`、`kp_question_route/kp_questions` 实际各测一层、无实质重复；`test_dice.py` 按 §14（确定性规则单测便宜高价值）保留

**已改写（放松实现锁）**
- `tests/architecture/test_dependencies.py`：依赖方向改为 AST import 分析（含相对导入解析），负向验证可捕获新违规
- `tests/architecture/test_migration_boundaries.py`：改为 AST 字符串字面量/调用扫描（忽略注释与文档措辞）
- `tests/architecture/test_content_boundaries.py`：冒险包改为真实加载行为验证；规则 locale 改为 materialize 行为验证（替代 `"RuleBundleLoader" in source` 类名锁）
- `test_contract_snapshot.py`：后端字段提取改为 AST 分析 return 字典字面量
- 放松断言：`kp_questions`（prompt 文案/LLM kwargs）、`world_gallery_backend`（prompt 顺序→存在性）、`ruleset_automation`（逐字文案→语言区分）、`dnd2024_director`（截断常量→上限）、`webui_create_flow`（prompt 文案→持久化状态）、`round_llm_compression`（LLM kwargs）、`language_support`（prompt 文案/调用顺序）
- `test_config_runtime_reload.py`：保留轻量重建矩阵，并把模型热重载主路径改成真实 subsystem factory + API facade，验证 live registry/store 复用、模型切换与旧 HTTP session 关闭

**已新增（真实链路 integration）**
- `tests/integration/conftest.py`：共享真实链路 harness（真实 registry/handler/lorebook/回合管线，仅 LLM 脚本化）
- `tests/integration/test_permissions.py`：私有消息仅投递属主、公开叙事与日志视图不泄露、GM 悄悄话玩家范围校验、隔离跨存档重载保持（补齐契约 2/3 的 integration 层）
- `tests/integration/test_game_flow.py`：创建→双人行动→真实回合→存档→**整条链路重建（模拟进程重启）**→状态一致且可继续推进（契约 14）

## 七、第二轮执行结果与遗留项

第二轮已完成：

1. **第二批实现锁放松**：`test_assistant`（角色文案→插件清单/本地化行为）、`test_state_change_messages`（逐字→实体与数值存在性）、`test_character_cards`（格式前缀→值存在性）、`test_round_helpers`（日志措辞→行为+全量日志脱敏检查）、`test_access_password`（mock 副作用→真实临时文件的存留断言）。`test_story_recap` 复核后保留：其断言是夹具数据驱动的隐私契约（公开回合入选、私密内容排除），不是文案锁。
2. **存档别名契约补强**：`test_dnd5e_v2_save_aliases` 从 1 例扩到 8 例（NPC 归一、既有 canonical id 不覆盖、未知名称不发明、裸 actor、schema 版本保持、畸形负载、空白/大小写/多语言别名）。
3. **更多 Golden Path**：`tests/integration/test_check_pipeline.py`（行动→服务端掷骰→结构化检定入状态，骰值可被固定种子复现 = 服务端权威）、`tests/integration/test_ruleset_isolation.py`（d20 与 d100 两局并存，各自骰制与状态不串）。
4. **大文件拆分**：
   - `test_webui_create_flow.py`（2073 行，78 用例）→ `webapi_harness.py` + characters(29)/rules_worlds(21)/create_flow(15)/lorebook(4)/payments(9) 五文件。
   - `test_plugin_host.py`（2896 行）→ `plugin_host_common.py` + content_pack(40)/security(12)/lifecycle(23)/host_core(16) 四文件。
5. **m4/m5/m6 API shim 抽共享**：`tests/rulesets/dnd2024_http_common.py`（GameplayApiShim + quick_character），M5/M6 shim 变薄子类，M4 复用角色构建。

第二轮后基线：后端 **1537 通过 / 1 跳过**。

## 八、第三轮执行结果与遗留项

第三轮已完成：

1. **多人并发 Golden Path**：新增 `tests/integration/test_multiplayer_concurrency.py`，经真实 WebAPI/handler/registry 链路并发提交两名玩家行动，验证 actor/text 不串、只发生一次推进、下一轮队列干净。
2. **配置热重载行为化**：模型切换测试不再 mock `_build_subsystems` / `_make_api`，改用真实 factory 与 API facade，验证 registry、lorebook、memory store 复用和旧客户端连接关闭；其余矩阵仍保留便宜的边界 seam。
3. **插件宿主公开行为**：世代唯一性从读取 `_host_generation` 改为启动真实插件后读取 runtime 世代文件；环境隔离与 AI provider 注入从调用 `_build_process_env` 改为由真实子进程记录实际收到的环境；删除人工篡改私有字段/私有方法的重复路径测试。
4. **前端实现锁继续减负**：ActionComposer、CharacterPanel、CheckRevealCard、MultiplayerPanel、SectionWorkspaceShell、KpQuestionDialog、PlayHelpCenter、GameTimeline、MapGraph、MapWorkspace、AdventuresView、Dnd2024AdvancementPanel 等改按文本、ARIA、输入状态和事件验证；删除 SectionWorkspaceShell 的 CSS 文件正则测试。

第三轮后基线：后端 **1536 通过 / 1 跳过**；前端 **69 个文件、307 个用例全过**；前端 typecheck、ESLint 与目标测试 Ruff 全过。

仍遗留（有意不做/留给后续）：

1. 其余前端 KEEP_BEHAVIOR 组件测试的 CSS class / DOM 层级依赖继续渐进去除；D&D campaign/combat 大面板宜随相关功能 PR 分段调整，避免一次性重写掩盖契约回归。
2. 剩余 Golden Path：bot actor 端到端、transport（HTTP/自签 HTTPS 启动）；二者需要额外进程/网络基础设施，单独任务更合适。
3. `tests/` 完整目录迁移（unit/security/e2e 分层）与 CI 分层（当前全套约 80–90 秒，暂无分层必要）。

## 九、已知差距说明（复核修正）

- DiceFrame 没有独立的 "hidden lore 条目" 模型（lorebook 只有 core/background/archived）；隐藏信息契约实际由 `private_log`/`info_asymmetry`（玩家私有）与 GM-only 端点构成。integration/permissions 已覆盖私有消息隔离；GM-only 面由 `webui_route_permissions` + `gm_controls` 覆盖。
- 共享真实链路 harness 已在 `tests/integration/conftest.py` 起步，后续应把散落的 FakeAPI/FakeRegistry 逐步收敛过来。

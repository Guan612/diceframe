# DiceFrame Architecture Source of Truth

This document describes the current implementation, not a roadmap. The dependency direction is `routes -> WebAPI -> services -> core`; core code must not import `src.webui`, WebAPI methods are delegates, and cross-service calls go through API delegates.

## Content V2

Inputs cross a compatibility boundary before entering the current canonical model:

```text
Legacy / V1 Rule / Plugin / Save / World / Character
                    ↓
              Compatibility
                    ↓
          Canonical Current Model
                    ↓
            Runtime Mechanics
                    ↓
             Typed Locale
                    ↓
                   UI
```

Canonical identity is a stable reference key: `fighter`, `longsword`, `chain_mail`, `athletics`, `str`, and `npc_innkeeper`. `战士 / Fighter`, `长剑 / Longsword / ロングソード`, and `老汤姆 / Old Tom` are display text only. Changing language never changes an ID.

Canonical rule/content data is the mechanics authority for normal V2 runtime. Legacy tables such as `ARMOR_LITE`, `WEAPON_DAMAGE`, and `WEAPON_DAMAGE_DICE` are compatibility fallbacks for old saves or V1 input only.

## Rule Locale

The rule core owns `dice_system`, `damage_dice`, `ac_base`, `dex_cap`, `attribute_points`, `proficiency`, `combat_model`, `skill_pools`, `item_categories`, damage/death mechanics, permissions, capabilities, and scripts. Profession skill pools use canonical class and skill IDs. Typed locales may translate their display names but cannot replace skill pools or item classifiers. Unknown or mechanics-shaped nested fields are rejected.

## World Locale

The world core owns `world_id`, `default_rule`, `recommended_rules`, `suggested_difficulty`, and the starter lorebook entry set/order, IDs, types, tiers, `unreliable`, `sync_on_enter`, `triggers_recursive`, `visible_to`, `match_mode`, `sticky`, `cooldown`, `delay`, `order`, `probability`, `group`, `group_weight`, `connected_to`, and other deterministic fields.

World locale may change only `world_name`, `description`, `world_setting`, `starter_scene`, and `name`, `keywords`, or `content` for a canonical lore entry ID. World Locale cannot replace `starter_lorebook` entries. Language changes cannot add, remove, or rename canonical lore identities.

For example, core ID `npc_innkeeper` may have `npc_innkeeper.name = 老汤姆` in Chinese and `npc_innkeeper.name = Old Tom` in English. The identity remains `npc_innkeeper`.

The lorebook database stores canonical/core entries. Keyword matching, prompt construction, and puzzle initialization build a read-only localized view for each `GameInstance.language`; translated text is never written back to the shared database.

## Plugin Content V2

The manifest currently supports `schema_version = 1`, `content_schema_version = 1 or 2`, `locale_schema_version = 1`, and `default_locale` as the package locale fallback. Locale fallback is exact requested locale -> base locale -> package/default locale -> base(default locale) -> canonical/core display fallback.

`ResourceRef` examples are `core:item:longsword` and `plugin:my-pack:item:moon_blade`. Ordinary V2 item/class/spell/npc/character_template resources can coexist through namespaces. Rules and worlds still primarily use plain `rule_id` / `world_id`, so duplicate Rule/World IDs across V2 plugins are explicitly rejected; there is no first-wins or last-wins behavior.

V2 resource IDs must already be canonical. The registry never silently normalizes case, spaces, or non-ASCII IDs on a plugin's behalf. When V2 locale or content validation fails, catalog APIs return `CONTENT_VALIDATION_FAILED`; they do not omit the broken resource or fall back to unlocalized content. The in-app content-pack exporter always emits a Content V2 core plus typed-locale layout. V1 full copies remain supported only through import adapters.

## Migration and Compatibility

`src/migrations/` performs persisted schema upgrades. `src/compat/` adapts old external/runtime shapes to the current canonical model. V1 packages are read through adapters; compatibility branches do not move into normal business logic.

## Frontend and Rule Boundaries

The backend materializes V2 locales and the frontend renders the returned payload; the frontend does not reimplement Content V2 locale architecture. D&D using d20 is not the same as changing generic d20 behavior. D&D-specific behavior remains inside the D&D boundary.

## D&D 2024 Authoritative Play State

`core:dnd2024` combat, Session 0, campaign records, and the guided adventure share `GameInstance.ruleset_state.version` and one EventBatch ledger. Combat and campaign events have separate reducers; the runtime composition root dispatches explicit intent types without making the generic engine import D&D code.

The mechanics authority for a professional character is `ruleset_character`. Creation, shared-library import/edit, joining a game, in-game profile editing, advancement, and rest all go through the `character_lifecycle` capability; legacy top-level character fields are compatibility projections only. Profile edits cannot overwrite abilities, HP, AC, advancement history, or runtime/content/state versions. Mechanical changes are revalidated or replayed from canonical choices and history.

Every Session 0 revision clears stale consent and can be locked only after all current players accept. Tasks, clues, facts, important items, and relationships enter a pending proposal before a separate GM intent confirms or rejects them. Chapter summaries are deterministic projections of confirmed events and are copied to long-term memory only after the authoritative save succeeds.

Professional rules accept free-text adventure actions through the `narrative_adventure` capability. Session 0 and tutorial state control when input is available, and provider preflight failures do not append an action record. The LLM receives only a read-only authoritative view and may narrate actions or resolved events; it cannot create campaign facts, spend resources, or advance tutorial steps.

The frontend dynamically loads a D&D professional-rules play area from runtime capabilities. Its “1 Start Here”, “2 Combat When Needed”, and “3 Review the Story (Optional)” tabs explain the current objective and next step, mount only the active panel, pause polling while the document is hidden, and scroll inside a bounded workspace without changing legacy-rule layouts or creation paths. Direct-connect player intents use an explicit field allowlist.

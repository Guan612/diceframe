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

The rule core owns `dice_system`, `damage_dice`, `ac_base`, `dex_cap`, `attribute_points`, `proficiency`, `combat_model`, damage/death mechanics, permissions, capabilities, and scripts. Typed locale overlays provide display and language fields only; unknown or mechanics-shaped nested fields are rejected.

## World Locale

The world core owns `world_id`, `default_rule`, `recommended_rules`, `suggested_difficulty`, and the starter lorebook entry set/order, IDs, types, tiers, `unreliable`, `sync_on_enter`, `triggers_recursive`, `visible_to`, `match_mode`, `sticky`, `cooldown`, `delay`, `order`, `probability`, `group`, `group_weight`, `connected_to`, and other deterministic fields.

World locale may change only `world_name`, `description`, `world_setting`, `starter_scene`, and `name`, `keywords`, or `content` for a canonical lore entry ID. World Locale cannot replace `starter_lorebook` entries. Language changes cannot add, remove, or rename canonical lore identities.

For example, core ID `npc_innkeeper` may have `npc_innkeeper.name = 老汤姆` in Chinese and `npc_innkeeper.name = Old Tom` in English. The identity remains `npc_innkeeper`.

## Plugin Content V2

The manifest currently supports `schema_version = 1`, `content_schema_version = 1 or 2`, `locale_schema_version = 1`, and `default_locale` as the package locale fallback. Locale fallback is exact requested locale -> base locale -> package/default locale -> base(default locale) -> canonical/core display fallback.

`ResourceRef` examples are `core:item:longsword` and `plugin:my-pack:item:moon_blade`. Ordinary V2 item/class/spell/npc/character_template resources can coexist through namespaces. Rules and worlds still primarily use plain `rule_id` / `world_id`, so duplicate Rule/World IDs across V2 plugins are explicitly rejected; there is no first-wins or last-wins behavior.

## Migration and Compatibility

`src/migrations/` performs persisted schema upgrades. `src/compat/` adapts old external/runtime shapes to the current canonical model. V1 packages are read through adapters; compatibility branches do not move into normal business logic.

## Frontend and Rule Boundaries

The backend materializes V2 locales and the frontend renders the returned payload; the frontend does not reimplement Content V2 locale architecture. D&D using d20 is not the same as changing generic d20 behavior. D&D-specific behavior remains inside the D&D boundary.

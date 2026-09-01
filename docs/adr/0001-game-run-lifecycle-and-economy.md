# ADR 0001: Game run lifecycle and authoritative economy

- Status: Accepted
- Date: 2026-09-01

## Context

`GameInstance` is the authoritative aggregate for one table, but a table may be
reset, restarted, recovered after a process restart, or imported as a new save.
Historically these paths cleared fields individually. Long-term memory was keyed
only by `game_key`, and narrative `GOLD` tags could mutate balances directly.
That made new persisted features easy to omit from reset/restart and allowed a
model response to act as an economic authority.

## Decision

Every playable run has a persisted `run_id` distinct from the stable
`game_key`. Process recovery preserves it; reset and restart rotate it. Delayed
work must carry the run identity and may not write to a different run.

Persisted state is classified as game identity, character state, run state, or
ephemeral process state. Reset and restart construct and validate a candidate
aggregate before replacing the active instance. Ruleset-owned opaque state is
reset through runtime capabilities rather than generic imports.

Long-term memory uses a persisted `memory_namespace`. Existing saves retain the
legacy namespace on migration; a new run receives a new namespace, so old
memory is unreachable without requiring destructive deletion first.

Economy changes use server-side proposals and committed transactions. LLM,
worldbook, adventure prose, and locale are proposal sources, never balance
authorities. A transaction is permission-checked, idempotent, atomic with its
item effects, persisted, and auditable. `currency.amount` is the canonical
balance; `gold` remains a compatibility projection during migration.

## Consequences

- New persisted domains must declare lifecycle behavior once at their owner.
- Reset/restart, migration, Bot, multiplayer, swipe, and recovery require
  behavior-level contract tests.
- Old `GOLD` tags are compatibility input only and cannot directly deduct money.
- The stable table key can continue to back links and Bot bindings while stale
  actions from an earlier run are rejected.
- Old memory rows may be cleaned later; isolation does not depend on cleanup.

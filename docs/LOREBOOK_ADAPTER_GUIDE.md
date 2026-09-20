# Lorebook adapter guide

Adapters are pure format boundaries under `src/lorebook/adapters/`. They convert external
payloads to `LorebookDraft` and must not write the store, mutate WorldState, evaluate macros,
or execute regex through another runtime. New formats must support tolerant reads, preserve
unknown fields, and report warnings through import preview.

The canonical path is:

```text
detect → draft → preview → commit_lorebook_import
```

Use `lorebook_v3` for standards-oriented export. Keep DiceFrame legacy fields in explicit
extensions/provenance rather than adding format branches to `LorebookStore`.

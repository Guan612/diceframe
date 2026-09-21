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

## Three concepts that are never derived from each other

Primary matching, the secondary-key gate, and how secondary keys combine are separate:

- `match_mode` — DiceFrame legacy primary matching (`any`/`all`/`not_any`/`not_all`).
- `selective` — canonical boolean: do `secondary_keys` gate activation at all.
- `selective_logic` — SillyTavern logic for combining secondary keys
  (`AND_ANY`/`NOT_ALL`/`NOT_ANY`/`AND_ALL`).

The primary key must match before the secondary gate is consulted. `selective=false` keeps the
secondary keys as data but must not filter, which is why it is its own canonical column rather
than something the matcher infers from the entry's source format.

## Regex compatibility

SillyTavern and Character Card regexes are JavaScript; DiceFrame executes Python `re`. Only the
safely-mappable subset runs. A pattern that is not valid in Python is preserved verbatim in the
import, reported as an `unsupported regex` preview warning, and never executed — it simply never
matches. Patterns that compile but diverge in semantics (JavaScript's `\d`/`\w`/`\s`/`\b` are
ASCII-only while Python's are Unicode-aware) are reported as a `regex mismatch` warning and kept
as-is. Adapters never rewrite, translate, or evaluate a pattern through a JavaScript runtime.

## Character Card and Tavern entry points

Every Character Card / Tavern route funnels into one canonical commit: the card body import is
separate, and an embedded `character_book` always goes adapter → preview → canonical commit →
binding. Binding precedence is canonical character uid, then the current world, then unbound.
The legacy `/api/import-tavern-card` route is a facade over the same path.

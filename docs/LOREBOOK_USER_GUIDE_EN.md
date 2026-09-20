# Lorebook v2 User Guide

Lorebooks are prompt knowledge: they provide relevant setting material and never replace
current facts owned by WorldState.

Import is preview-first: choose a file, detect the format, review warnings, choose a binding
scope, then confirm. Unknown extensions are preserved as data; unsupported fields are never
silently executed. SillyTavern timed effects show a warning because they are message-based,
while DiceFrame advances authoritative turn ticks.

The left Sidebar switches between multiple books bound to the current world. New entries,
imports, edits, and exports target the selected book instead of silently writing to the primary
world book. Export uses the native `lorebook_v3` shape and preserves book/entry settings;
`/api/lorebooks/{book_id}/entries` exposes the canonical CRUD path.

The default editor focuses on name, content, keys, and visibility. Matching, recursion,
probability, groups, and token budgets remain available under Advanced settings. Semantic modes
are `off`, `hybrid`, and `vector_only`, with entry overrides taking precedence over book defaults.
Player views never expose hidden entry names, counts, or rejection reasons; GM users can inspect
the current dry-run activation trace.

# Lorebook migration notes

Migration v5 creates `lorebooks` and `lorebook_bindings`, rebuilds entries with nullable
`book_id`/`world_id`, and creates one deterministic `world:<world_id>` primary book per world.
Existing worlds, entry IDs, plugin provenance, connected links, and embedding cache rows remain
usable. Reopening is idempotent and `list_entries(world_id)` reads only the primary book.

Migration v7 adds `lorebooks.revision`, a monotonic counter bumped by every entry mutation. It
exists so a cached matcher fingerprint is invalidated by book content changing, instead of
relying on a timestamp that a same-second edit can hide. Legacy `ensure_world` scoping still
reads the primary world book, and its cache key carries that book's revision.

Migration v8 adds `lorebook_entries.selective`, the canonical boolean deciding whether
`secondary_keys` gates activation at all. It defaults to `1` so existing rows keep their current
behaviour, where present secondary keys implied the gate. It is a separate column from
`secondary_keys` (the data) and `selective_logic` (how the secondary keys combine) because the
three are independent concepts.

Both columns are added with `ensure_column`, so v7/v8 do not rewrite the v5 table definitions.
A fresh database walks v1 through v8; `PRAGMA user_version` ends at 8.

Legacy timer state is converted at load/save boundaries from `{status, remaining}` to independent
`sticky_remaining` and `cooldown_remaining` counters. Ambiguous delayed state is not guessed;
the entry's delay setting controls future eligibility.

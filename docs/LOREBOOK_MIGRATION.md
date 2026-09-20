# Lorebook migration notes

Migration v5 creates `lorebooks` and `lorebook_bindings`, rebuilds entries with nullable
`book_id`/`world_id`, and creates one deterministic `world:<world_id>` primary book per world.
Existing worlds, entry IDs, plugin provenance, connected links, and embedding cache rows remain
usable. Reopening is idempotent and `list_entries(world_id)` reads only the primary book.

Legacy timer state is converted at load/save boundaries from `{status, remaining}` to independent
`sticky_remaining` and `cooldown_remaining` counters. Ambiguous delayed state is not guessed;
the entry's delay setting controls future eligibility.

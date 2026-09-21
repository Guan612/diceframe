import { describe, expect, it } from 'vitest'
import type { LoreEntry } from '../src/api/types'
import {
  DEFAULT_LORE_ENTRY_FILTERS,
  filterLoreEntries,
  isLoreEntryFilterActive,
  loreEntryActivationOptions,
  loreEntryEnabled,
  loreEntrySource,
  loreEntrySourceOptions,
  matchesLoreEntryFilters,
} from '../src/features/lorebook/entryFilters'

function entry(overrides: Partial<LoreEntry> & Record<string, unknown> = {}): LoreEntry {
  return { id: 'e1', name: '城门守卫', type: 'npc', content: '公开背景', ...overrides } as LoreEntry
}

const ENTRIES: LoreEntry[] = [
  entry({ id: 'a', name: '城门守卫', type: 'npc', content: '公开背景', keywords: ['城门'], visible_to: ['*'], enabled: 1, match_mode: 'any' }),
  entry({ id: 'b', name: '秘血教派', type: 'faction', content: '莱拉的私人线索', keywords: ['血', '教派'], visible_to: ['u1'], enabled: 0, match_mode: 'all' }),
  entry({ id: 'c', name: '幕后黑手', type: 'npc', content: 'GM 秘密', visible_to: [], source_plugin: 'demo_plugin', match_mode: 'not_any' }),
]

function ids(rows: LoreEntry[]) {
  return rows.map(row => row.id)
}

describe('lore entry search', () => {
  it('matches name, content, and keywords case-insensitively', () => {
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, search: '城门' }))).toEqual(['a'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, search: '私人线索' }))).toEqual(['b'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, search: '教派' }))).toEqual(['b'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, search: 'GM 秘密' }))).toEqual(['c'])
  })

  it('ignores surrounding whitespace and keeps everything when empty', () => {
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, search: '   ' }))).toEqual(['a', 'b', 'c'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, search: ' 血 ' }))).toEqual(['b'])
  })
})

describe('lore entry filters', () => {
  it('filters by canonical type', () => {
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, type: 'npc' }))).toEqual(['a', 'c'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, type: 'faction' }))).toEqual(['b'])
  })

  it('classifies visibility with the shared normalizer', () => {
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, visibility: 'public' }))).toEqual(['a'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, visibility: 'characters' }))).toEqual(['b'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, visibility: 'gm' }))).toEqual(['c'])
  })

  it('treats a missing enabled flag as enabled and 0 as disabled', () => {
    expect(loreEntryEnabled(ENTRIES[0])).toBe(true)
    expect(loreEntryEnabled(ENTRIES[1])).toBe(false)
    expect(loreEntryEnabled(ENTRIES[2])).toBe(true)
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, state: 'disabled' }))).toEqual(['b'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, state: 'enabled' }))).toEqual(['a', 'c'])
  })

  it('filters by canonical activation mode', () => {
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, activation: 'all' }))).toEqual(['b'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, activation: 'not_any' }))).toEqual(['c'])
    expect(loreEntryActivationOptions(ENTRIES)).toEqual(['any', 'all', 'not_any'])
  })

  it('reads the source from source_plugin and provenance', () => {
    expect(loreEntrySource(ENTRIES[0])).toBe('')
    expect(loreEntrySource(ENTRIES[2])).toBe('demo_plugin')
    expect(loreEntrySource(entry({ provenance: { source: 'sillytavern' } }))).toBe('sillytavern')
    expect(loreEntrySource(entry({ provenance: '{"kind":"import"}' }))).toBe('import')
    expect(loreEntrySourceOptions(ENTRIES)).toEqual(['demo_plugin'])
    expect(ids(filterLoreEntries(ENTRIES, { ...DEFAULT_LORE_ENTRY_FILTERS, source: 'demo_plugin' }))).toEqual(['c'])
  })

  it('combines every filter with AND', () => {
    const filters = { ...DEFAULT_LORE_ENTRY_FILTERS, type: 'npc', state: 'enabled' as const, search: '秘密' }
    expect(ids(filterLoreEntries(ENTRIES, filters))).toEqual(['c'])
    expect(ids(filterLoreEntries(ENTRIES, { ...filters, visibility: 'public' }))).toEqual([])
  })

  it('reports whether any filter is narrowing the list', () => {
    expect(isLoreEntryFilterActive(DEFAULT_LORE_ENTRY_FILTERS)).toBe(false)
    expect(isLoreEntryFilterActive({ ...DEFAULT_LORE_ENTRY_FILTERS, type: 'npc' })).toBe(false)
    expect(isLoreEntryFilterActive({ ...DEFAULT_LORE_ENTRY_FILTERS, search: 'x' })).toBe(true)
    expect(isLoreEntryFilterActive({ ...DEFAULT_LORE_ENTRY_FILTERS, state: 'disabled' })).toBe(true)
  })

  it('keeps the entry when only the search text matches nothing', () => {
    expect(matchesLoreEntryFilters(ENTRIES[0], DEFAULT_LORE_ENTRY_FILTERS)).toBe(true)
    expect(matchesLoreEntryFilters(ENTRIES[0], { ...DEFAULT_LORE_ENTRY_FILTERS, search: 'zzz' })).toBe(false)
  })
})

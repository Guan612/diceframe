// 世界书条目列表的搜索 / 筛选：纯粹在「已经加载的条目」上计算，
// 不新增查询接口、也不改 fetch 载荷——服务端过滤会让分页与激活预览失真。
import type { LoreEntry } from '@/api/types'
import { visibilityModeOf, type LoreVisibilityMode } from './visibility'

export const LORE_TYPE_ORDER = [
  'npc', 'location', 'faction', 'item', 'event', 'puzzle', 'spell', 'class', 'other',
] as const

export const LORE_ACTIVATION_MODES = ['any', 'all', 'not_any', 'not_all'] as const

export type LoreEntryStateFilter = 'all' | 'enabled' | 'disabled'
export type LoreEntryVisibilityFilter = 'all' | LoreVisibilityMode

export interface LoreEntryFilters {
  search: string
  /** 类型过滤与分类 tab 共用同一个 canonical 值：'all' 或 LORE_TYPE_ORDER 之一。 */
  type: string
  visibility: LoreEntryVisibilityFilter
  state: LoreEntryStateFilter
  /**
   * canonical match_mode，空串表示不过滤。
   * 这里不能用 'all' 当哨兵：'all'（所有触发词命中）本身就是合法的 match_mode。
   */
  activation: string
  /** canonical 来源标签：'all' 或 loreEntrySource() 的取值。 */
  source: string
}

export const DEFAULT_LORE_ENTRY_FILTERS: LoreEntryFilters = {
  search: '',
  type: 'all',
  visibility: 'all',
  state: 'all',
  activation: '',
  source: 'all',
}

function rowOf(entry: LoreEntry): Record<string, unknown> {
  return entry as unknown as Record<string, unknown>
}

export function normalizeLoreEntryType(type: unknown): string {
  const text = String(type || 'other')
  return (LORE_TYPE_ORDER as readonly string[]).includes(text) ? text : 'other'
}

/** 后端把 enabled 存成 0/1；字段缺失按 canonical 默认视为启用。 */
export function loreEntryEnabled(entry: LoreEntry): boolean {
  const raw = rowOf(entry).enabled
  if (raw === undefined || raw === null) return true
  if (typeof raw === 'boolean') return raw
  if (typeof raw === 'number') return raw !== 0
  const text = String(raw).trim().toLowerCase()
  return !(text === '' || text === '0' || text === 'false')
}

export function loreEntryActivation(entry: LoreEntry): string {
  return String(rowOf(entry).match_mode || 'any')
}

/** 条目的来源标签：优先插件来源，其次 provenance（对象或 JSON 字符串）。 */
export function loreEntrySource(entry: LoreEntry): string {
  const row = rowOf(entry)
  const plugin = String(row.source_plugin || '').trim()
  if (plugin) return plugin
  const provenance = row.provenance
  if (provenance && typeof provenance === 'object' && !Array.isArray(provenance)) {
    const data = provenance as Record<string, unknown>
    return String(data.source || data.source_id || data.kind || '').trim()
  }
  const text = String(provenance || '').trim()
  if (!text) return ''
  try {
    const parsed = JSON.parse(text) as Record<string, unknown>
    return String(parsed.source || parsed.source_id || parsed.kind || '').trim()
  } catch {
    return text
  }
}

export function loreEntryVisibility(entry: LoreEntry): LoreVisibilityMode {
  return visibilityModeOf(rowOf(entry).visible_to)
}

/** 搜索命中范围：名称、内容、触发词（以及可读的摘要/描述）。 */
export function loreEntrySearchText(entry: LoreEntry): string {
  const row = rowOf(entry)
  const keywords = Array.isArray(entry.keywords) ? entry.keywords : []
  return [entry.name, entry.content, entry.summary, entry.description, row.secondary_keys, ...keywords]
    .flatMap(value => Array.isArray(value) ? value : [value])
    .map(value => String(value ?? ''))
    .join('\n')
    .toLowerCase()
}

export function matchesLoreEntrySearch(entry: LoreEntry, search: string): boolean {
  const needle = String(search || '').trim().toLowerCase()
  if (!needle) return true
  return loreEntrySearchText(entry).includes(needle)
}

export function matchesLoreEntryFilters(entry: LoreEntry, filters: LoreEntryFilters): boolean {
  if (filters.type !== 'all' && normalizeLoreEntryType(entry.type) !== filters.type) return false
  if (filters.visibility !== 'all' && loreEntryVisibility(entry) !== filters.visibility) return false
  if (filters.state === 'enabled' && !loreEntryEnabled(entry)) return false
  if (filters.state === 'disabled' && loreEntryEnabled(entry)) return false
  if (filters.activation && loreEntryActivation(entry) !== filters.activation) return false
  if (filters.source !== 'all' && loreEntrySource(entry) !== filters.source) return false
  return matchesLoreEntrySearch(entry, filters.search)
}

export function filterLoreEntries(entries: LoreEntry[], filters: LoreEntryFilters): LoreEntry[] {
  return entries.filter(entry => matchesLoreEntryFilters(entry, filters))
}

export function loreEntrySourceOptions(entries: LoreEntry[]): string[] {
  return [...new Set(entries.map(loreEntrySource).filter(Boolean))].sort()
}

export function loreEntryActivationOptions(entries: LoreEntry[]): string[] {
  const present = new Set(entries.map(loreEntryActivation))
  return LORE_ACTIVATION_MODES.filter(mode => present.has(mode))
}

export function isLoreEntryFilterActive(filters: LoreEntryFilters): boolean {
  return filters.visibility !== 'all'
    || filters.state !== 'all'
    || filters.activation !== ''
    || filters.source !== 'all'
    || !!String(filters.search || '').trim()
}

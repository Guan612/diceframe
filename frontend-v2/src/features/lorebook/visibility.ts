// 世界书条目可见性（编辑端）。
// 判定的单一事实来源在后端 src/knowledge/visibility.py；此处仅做编辑表单的
// 档位归类。canonical 公开标记是语言无关的 "*"，中英文写法只是识别别名——
// Locale 不得影响 mechanics。
export const PUBLIC_VISIBILITY_MARKERS = [
  '*', 'all', 'everyone', 'public', 'party', 'players',
  '公开', '所有人', '全体玩家',
] as const

export type LoreVisibilityMode = 'gm' | 'public' | 'characters'

export function visibilityModeOf(values: readonly string[] | undefined): LoreVisibilityMode {
  const list = (values || [])
    .map(value => String(value).trim().toLowerCase())
    .filter(Boolean)
  if (!list.length) return 'gm'
  const markers = new Set(PUBLIC_VISIBILITY_MARKERS.map(marker => marker.toLowerCase()))
  return list.some(value => markers.has(value)) ? 'public' : 'characters'
}

// 「指定角色」档不允许混入 public marker：手输 * / public / 公开 会被剥掉，
// UI 档位与真实权限保持一致。trim、去空、大小写不敏感去重。
export function sanitizeCharacterVisibility(values: readonly string[] | undefined): string[] {
  const markers = new Set(PUBLIC_VISIBILITY_MARKERS.map(marker => marker.toLowerCase()))
  const out: string[] = []
  for (const raw of values || []) {
    const value = String(raw).trim()
    if (!value || markers.has(value.toLowerCase())) continue
    if (out.some(existing => existing.toLowerCase() === value.toLowerCase())) continue
    out.push(value)
  }
  return out
}

import { computed, ref, watch, type Ref } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { LorePreviewResponse, LoreProjection, Player } from '@/api/types'
import { activePeerGameClient } from '@/peer/game/bridge'

const GM_VIEWER = 'gm'
const PARTY_VIEWER = 'party'
const STANDALONE_STORAGE_KEY = 'lore_viewer_standalone'

/**
 * 世界书视角状态：唯一读写投影接口的地方。
 * 前端不复制可见性算法，只渲染后端投影结果。
 */
export function useLorePerspective(
  worldId: Ref<string>,
  gameKey: Ref<string>,
  players: Ref<Player[]>,
) {
  const viewer = ref(GM_VIEWER)
  const preview = ref<LorePreviewResponse | null>(null)
  const loading = ref(false)
  const previewError = ref('')
  let requestSeq = 0

  // 角色视角需要游戏上下文派生角色名；无存档或 P2P 直连局不可用。
  const characterViewerLocked = computed(() => !gameKey.value || Boolean(activePeerGameClient()))

  const effectiveViewer = computed(() => {
    const selected = viewer.value
    if (selected === GM_VIEWER || selected === PARTY_VIEWER) return selected
    if (characterViewerLocked.value) return GM_VIEWER
    return players.value.some(p => p.user_id === selected) ? selected : GM_VIEWER
  })

  const viewerFallback = computed(() => viewer.value !== effectiveViewer.value)

  function storageKey(): string {
    return gameKey.value ? `lore_viewer_${gameKey.value}` : STANDALONE_STORAGE_KEY
  }

  function setViewer(next: string) {
    viewer.value = next
    try { localStorage.setItem(storageKey(), next) } catch { /* 隐私模式下忽略 */ }
  }

  function restoreViewer() {
    viewer.value = localStorage.getItem(storageKey()) || GM_VIEWER
  }

  async function fetchPreview() {
    const wid = worldId.value
    if (!wid) { preview.value = null; return }
    const seq = ++requestSeq
    loading.value = true
    previewError.value = ''
    const effective = effectiveViewer.value
    const params = new URLSearchParams({ viewer: effective })
    if (effective !== GM_VIEWER && effective !== PARTY_VIEWER) params.set('game_key', gameKey.value)
    try {
      const r = await api<LorePreviewResponse>(`/lorebook/${encodeURIComponent(wid)}/preview?${params.toString()}`)
      if (seq === requestSeq) preview.value = r
    } catch (e: unknown) {
      if (seq === requestSeq) { preview.value = null; previewError.value = errorMessage(e) }
    } finally {
      if (seq === requestSeq) loading.value = false
    }
  }

  function projectionOf(entryId: string | undefined): LoreProjection | null {
    if (!entryId) return null
    return preview.value?.projections?.[entryId] || null
  }

  watch(gameKey, restoreViewer, { immediate: true })
  watch([worldId, effectiveViewer], fetchPreview)

  return { viewer, effectiveViewer, viewerFallback, characterViewerLocked, setViewer, preview, loading, previewError, projectionOf, refreshPreview: fetchPreview }
}

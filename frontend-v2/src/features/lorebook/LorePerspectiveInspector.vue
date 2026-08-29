<script setup lang="ts">
import type { LoreEntry, LorePreviewResponse, LoreProjection, Player } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import LoreVisibilityBadge from './LoreVisibilityBadge.vue'

defineProps<{
  players: Player[]
  viewer: string
  viewerFallback: boolean
  characterViewerLocked: boolean
  lockedReason: 'standalone' | 'peer' | ''
  preview: LorePreviewResponse | null
  previewError: string
  selectedEntry: LoreEntry | null
  selectedProjection: LoreProjection | null
}>()

const emit = defineEmits<{ (e: 'select-viewer', viewer: string): void; (e: 'close'): void }>()
const { t } = useLocale()

function playerLabel(p: Player): string {
  return String(p.character_name || p.user_id)
}
</script>

<template>
  <aside class="lore-perspective-inspector">
    <header class="lore-inspector-head">
      <h2>{{ t('lorePerspectiveTitle') }}</h2>
      <button class="lore-inspector-close" @click="emit('close')" :aria-label="t('close')">×</button>
    </header>

    <section class="lore-inspector-block">
      <span class="lore-inspector-label">{{ t('loreViewerLabel') }}</span>
      <div class="lore-viewer-options">
        <button :class="{ active: viewer === 'gm' }" @click="emit('select-viewer', 'gm')">{{ t('loreViewerGm') }}</button>
        <button :class="{ active: viewer === 'party' }" @click="emit('select-viewer', 'party')">{{ t('loreViewerParty') }}</button>
        <button
          v-for="p in players"
          :key="p.user_id"
          :class="{ active: viewer === p.user_id }"
          :disabled="characterViewerLocked"
          @click="emit('select-viewer', p.user_id)"
        >{{ playerLabel(p) }}</button>
      </div>
      <p v-if="characterViewerLocked" class="muted small">{{ t(lockedReason === 'peer' ? 'loreViewerLockedPeer' : 'loreViewerLockedStandalone') }}</p>
      <p v-else-if="viewerFallback" class="muted small">{{ t('loreViewerFallbackHint') }}</p>
    </section>

    <section class="lore-inspector-block">
      <span class="lore-inspector-label">{{ t('loreVisibilitySummary') }}</span>
      <p v-if="previewError" class="error-banner">{{ previewError }}</p>
      <ul v-else-if="preview?.summary" class="lore-summary-list">
        <li><span>{{ t('loreSummaryVisible') }}</span><strong>{{ preview.summary.visible }} / {{ preview.summary.total }}</strong></li>
        <li><span>{{ t('loreAudiencePublic') }}</span><strong>{{ preview.summary.public }}</strong></li>
        <li><span>{{ t('loreAudienceCharacterOnlyShort') }}</span><strong>{{ preview.summary.character_only }}</strong></li>
        <li><span>{{ t('loreAudienceGmSecret') }}</span><strong>{{ preview.summary.gm_secret }}</strong></li>
      </ul>
      <p v-else class="muted small">{{ t('loreProjectionPending') }}</p>
    </section>

    <section class="lore-inspector-block">
      <span class="lore-inspector-label">{{ t('loreSelectedEntry') }}</span>
      <template v-if="selectedEntry">
        <strong class="lore-selected-name">{{ selectedEntry.name || t('unnamedLoreEntry') }}</strong>
        <template v-if="selectedProjection">
          <LoreVisibilityBadge :projection="selectedProjection" />
          <p class="muted small">{{ selectedProjection.visible ? t('loreVisibleInCurrentViewer') : t('loreHiddenInCurrentViewer') }}</p>
        </template>
        <p v-else class="muted small">{{ t('loreProjectionPending') }}</p>
      </template>
      <p v-else class="muted small">{{ t('loreSelectedEntryHint') }}</p>
    </section>
  </aside>
</template>

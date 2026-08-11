<script setup lang="ts">
import { computed } from 'vue'
import { NModal } from 'naive-ui'
import { useLocale } from '@/composables/useLocale'
import { useAnnouncements } from '@/composables/useAnnouncements'
import { renderSafeMarkdown } from '@/utils/markdown'

defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()
const { t } = useLocale()
const { content, stale } = useAnnouncements()

const html = computed(() => {
  return renderSafeMarkdown(content.value || '')
})
</script>
<template>
  <NModal
    :show="show"
    preset="card"
    :title="t('officialAnnouncement')"
    style="max-width: 520px;"
    @update:show="(v: boolean) => emit('update:show', v)"
  >
    <div v-if="html" class="announcement-panel-body" v-html="html" />
    <p v-else class="muted">{{ t('noAnnouncement') }}</p>
    <p v-if="stale && html" class="cached-hint">{{ t('announcementCached') }}</p>
  </NModal>
</template>

<style scoped>
.announcement-panel-body {
  line-height: 1.7;
  font-size: 14px;
}
.announcement-panel-body :deep(h1) { font-size: 18px; margin: 0 0 8px; }
.announcement-panel-body :deep(h2) { font-size: 16px; margin: 14px 0 6px; }
.announcement-panel-body :deep(h3) { font-size: 15px; margin: 12px 0 4px; }
.announcement-panel-body :deep(ul),
.announcement-panel-body :deep(ol) { padding-left: 20px; margin: 6px 0; }
.announcement-panel-body :deep(p) { margin: 6px 0; }
.announcement-panel-body :deep(a) { color: var(--df-accent-strong); }
.announcement-panel-body :deep(code) {
  background: color-mix(in srgb, var(--df-interactive) 12%, transparent);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 0.92em;
}
.announcement-panel-body :deep(pre) {
  background: color-mix(in srgb, var(--df-surface-2) 80%, transparent);
  padding: 10px;
  border-radius: 6px;
  overflow-x: auto;
}
.cached-hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: #8a8a8a;
}
</style>

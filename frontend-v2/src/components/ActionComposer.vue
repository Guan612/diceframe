<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/api/client'
import type { ActionSubmitResponse, GameDetail } from '@/api/types'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{ gameKey: string; userId: string; detail: GameDetail; disabled?: boolean }>()
const emit = defineEmits<{ refresh: []; processing: [value: boolean] }>()
const { t } = useLocale()

const text = ref(''), busy = ref(false), notice = ref('')

const own = computed(() => props.detail.multiplayer?.submitted_actions?.find(a => a.user_id === props.userId))
const hint = computed(() => props.detail.solo_mode ? t('soloHint') : own.value ? t('submittedHint', { count: own.value.revision_count || 1 }) : t('defaultHint'))
const defaultQuickActions = computed(() => [t('quickObserve'), t('quickExplore'), t('quickTalk'), t('quickPrepareCombat')])
const quickActions = computed(() => (props.detail.quick_actions?.length ? props.detail.quick_actions : defaultQuickActions.value) as string[])
const locked = computed(() => props.disabled || busy.value)

function resetSubmissionState() {
  notice.value = ''
}

const ownSignature = computed(() => own.value
  ? JSON.stringify([own.value.text, own.value.revision_count])
  : '')

watch(
  [() => props.detail.round_number, ownSignature],
  ([roundNumber, signature], [previousRoundNumber, previousSignature]) => {
    if (roundNumber !== previousRoundNumber || (previousSignature && !signature)) {
      resetSubmissionState()
    }
  },
)

async function submit() {
  const action = text.value.trim()
  if (!action || locked.value) return
  busy.value = true; notice.value = ''; emit('processing', true)
  try {
    const r = await api<ActionSubmitResponse>(`/games/${encodeURIComponent(props.gameKey)}/action`, { method: 'POST', body: JSON.stringify({ text: action }) })
    text.value = ''
    notice.value = r.phase === 'luck' ? t('luckDecisionRequired') : t('actionRecorded')
    emit('refresh')
  } catch (e: unknown) { notice.value = e instanceof Error ? e.message : String(e) } finally { busy.value = false; emit('processing', false) }
}
</script>

<template>
  <div class="composer">
    <div class="composer-head">
      <div class="composer-title-row">
        <strong>{{ t('composerTitle') }}</strong>
        <span v-if="hint" class="composer-hint">{{ hint }}</span>
      </div>
    </div>
    <div class="quick-actions" :aria-label="t('quickActions')">
      <button v-for="action in quickActions" :key="action" :disabled="locked" @click="text = action">{{ action }}</button>
    </div>
    <div class="composer-row">
      <textarea v-model="text" :disabled="locked" :placeholder="t('actionPlaceholder')" @keydown.ctrl.enter.prevent="submit()" />
      <button class="primary" @click="submit()" :disabled="locked || !text.trim()">{{ busy ? t('processing') : t('action') }}</button>
    </div>
    <div v-if="notice" class="notice">{{ notice }}</div>
  </div>
</template>

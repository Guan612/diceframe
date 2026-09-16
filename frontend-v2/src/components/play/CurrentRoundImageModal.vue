<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { GameDetail, LogEntry, Player } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import Modal from '@/components/ui/Modal.vue'

const props = defineProps<{ open: boolean; gameKey: string; detail: GameDetail; log: LogEntry[]; players?: Player[] }>()
const emit = defineEmits<{
  close: []
  generate: [payload: { prompt: string; round: number; panels: unknown[]; use_avatar_references: boolean }]
}>()
const { t } = useLocale()
const prompt = ref('')
const targetRound = ref(0)
const useAvatarReferences = ref(false)

const uploadAvatarIds = computed(() => new Set(
  (props.players || [])
    .filter(player => {
      const portrait = player.character_sheet?.portrait
        || (player as Player & { portrait?: { kind?: string; asset_id?: string } }).portrait
      return portrait?.kind === 'upload' && !!portrait.asset_id
    })
    .map(player => player.user_id),
))
const canUseAvatarReferences = computed(() => uploadAvatarIds.value.size > 0)

// Mirrors the server-side narration truncation in
// src/webui/services/generated_images.py generate_current_round().
const NARRATION_LIMIT = 1600

function draftPrompt(): string {
  const latest = [...props.log].reverse().find(item => String(item.gm_response || '').trim())
  const round = Number(latest?.round ?? Math.max(0, Number(props.detail.round_number || 0) - 1))
  targetRound.value = round
  useAvatarReferences.value = false
  const scene = String(props.detail.scene || t('unknownScene'))
  const narration = String(latest?.gm_response || '').replace(/\s+/g, ' ').slice(0, NARRATION_LIMIT)
  // Content only: style and composition wording is composed server-side from
  // imagegen_style_prefix / imagegen_manual_rules / imagegen_manual_prompt.
  return [scene, narration].map(part => part.trim()).filter(Boolean).join('\n')
}

watch(() => props.open, (open) => {
  if (!open) return
  prompt.value = draftPrompt()
}, { immediate: true })

function generate() {
  if (!props.gameKey || !prompt.value.trim()) return
  emit('generate', {
    prompt: prompt.value.trim(),
    round: targetRound.value,
    // Empty panels asks the server to infer simultaneous public locations
    // from this round's narration and actions.
    panels: [],
    use_avatar_references: useAvatarReferences.value && canUseAvatarReferences.value,
  })
}

function close() {
  emit('close')
}
</script>

<template>
  <Modal v-if="open" :title="t('generateRoundImage')" @close="close">
    <p class="muted">{{ t('roundImagePromptHint') }}</p>
    <textarea v-model="prompt" rows="8" :placeholder="t('roundImagePromptPlaceholder')" />
    <label class="avatar-reference-toggle">
      <input v-model="useAvatarReferences" type="checkbox" :disabled="!canUseAvatarReferences">
      <span>{{ t('useAvatarReferences') }}</span>
    </label>
    <p class="muted avatar-reference-hint">{{ t('avatarReferenceUploadNotice') }}</p>
    <p class="muted smart-storyboard-hint">{{ t('storyboardAutoHint') }}</p>
    <template #actions>
      <button @click="close">{{ t('close') }}</button>
      <button class="primary" :disabled="!prompt.trim()" @click="generate">{{ t('generateImage') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
textarea { width: 100%; min-height: 150px; resize: vertical; }
.avatar-reference-toggle { display: inline-flex; align-items: center; gap: 8px; margin-top: 10px; }
.avatar-reference-hint { margin: 2px 0 0; font-size: 0.85em; }
.smart-storyboard-hint { margin: 10px 0 0; }
</style>

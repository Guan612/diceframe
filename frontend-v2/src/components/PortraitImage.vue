<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { CharacterPortrait } from '@/api/types'
import { uploadedAvatarUrl } from '@/api/avatars'
import { builtinPortraits, initials, resolveBuiltinPortrait } from '@/utils/portraits'

const props = withDefaults(defineProps<{
  portrait?: CharacterPortrait | null
  ruleId?: string
  seed?: string
  name?: string
  size?: number
}>(), { size: 48 })

const uploadUrl = ref('')
const uploadFailed = ref(false)
// 内置头像只有显式选择且 id 有效才显示；未选择时不按名字/规则自动分配。
const hasValidBuiltin = computed(() => {
  const portrait = props.portrait
  if (!portrait || portrait.kind !== 'builtin') return false
  const [storedRule, rawIndex] = String(portrait.id || '').split(':')
  const options = builtinPortraits(storedRule)
  const index = Number(rawIndex)
  return Number.isInteger(index) && index >= 0 && index < options.length
})
const builtin = computed(() => resolveBuiltinPortrait(props.portrait, props.ruleId, props.seed || props.name))
const isUpload = computed(() => props.portrait?.kind === 'upload' && !!props.portrait.asset_id && !uploadFailed.value)
const pluginUrl = computed(() => {
  const portrait = props.portrait
  if (portrait?.kind !== 'plugin' || !portrait.plugin_id || !portrait.path || uploadFailed.value) return ''
  const path = portrait.path.split('/').map(encodeURIComponent).join('/')
  return `/api/plugins/assets/${encodeURIComponent(portrait.plugin_id)}/${path}`
})
const hasImage = computed(() => isUpload.value || Boolean(pluginUrl.value))
const boxStyle = computed(() => ({ width: `${props.size}px`, height: `${props.size}px` }))
const builtinStyle = computed(() => ({
  width: '100%',
  height: '100%',
  backgroundImage: `url("${builtin.value.image}")`,
  backgroundPosition: builtin.value.position,
  backgroundSize: 'cover',
}))

watch(
  () => props.portrait?.kind === 'upload' ? props.portrait.asset_id : '',
  async (assetId) => {
    uploadUrl.value = ''
    uploadFailed.value = false
    if (!assetId) return
    try { uploadUrl.value = await uploadedAvatarUrl(assetId) }
    catch { uploadFailed.value = true }
  },
  { immediate: true },
)
watch(
  () => props.portrait?.kind === 'plugin' ? `${props.portrait.plugin_id || ''}:${props.portrait.path || ''}` : '',
  () => { uploadFailed.value = false },
)
</script>

<template>
  <span class="portrait-image" :class="{ 'portrait-empty': !hasValidBuiltin && !hasImage }" :style="boxStyle" :title="name" role="img" :aria-label="name || 'avatar'">
    <img v-if="isUpload && uploadUrl" :src="uploadUrl" alt="" @error="uploadFailed = true">
    <img v-else-if="pluginUrl" :src="pluginUrl" alt="" @error="uploadFailed = true">
    <span v-else-if="hasValidBuiltin" class="portrait-builtin" :style="builtinStyle"><i>{{ initials(name) }}</i></span>
    <span v-else class="portrait-empty-text">{{ initials(name) }}</span>
  </span>
</template>

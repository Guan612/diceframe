<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '@/api/client'
import type { AdventuresResponse, GmStyle, SceneImageRef, WorldCloneResponse, WorldListResponse, WorldSummary, WorldTemplateSummary, WorldTemplatesResponse } from '@/api/types'
import { resolveSceneImageUrl, revokeSceneImageUrl } from '@/api/sceneImages'
import { ruleSceneUrl } from '@/composables/useBackgroundImages'
import { useConfirm } from '@/composables/useConfirm'
import { useToast } from '@/composables/useToast'
import { useLocale } from '@/composables/useLocale'
import { filterByContentLanguage } from '@/utils/contentLanguage'
import Modal from '@/components/ui/Modal.vue'

type GalleryCard = {
  id: string
  name: string
  description: string
  language: string
  source: 'builtin' | 'user' | 'plugin'
  lorebookCount: number
  defaultRule: string
  sceneImage?: SceneImageRef
  gmStyle: GmStyle | null
  adventureName: string
}

const DEFAULT_STYLE: GmStyle = { tone: '', verbosity: 'normal', custom_instructions: '' }

const { locale, t } = useLocale()
const router = useRouter()
const toast = useToast()
const { confirm } = useConfirm()

const cards = ref<GalleryCard[]>([])
const coverUrls = ref<Record<string, string>>({})
const error = ref('')
const busy = ref(false)
const previewCard = ref<GalleryCard | null>(null)
const styleForm = ref<GmStyle>({ ...DEFAULT_STYLE })
const styleBusy = ref(false)

function templateCard(template: WorldTemplateSummary): GalleryCard | null {
  const id = String(template.world_id || template.id || '')
  // 对局临时模板（*_copy_* / *_blank_*）不属于画廊内容。
  if (!id || template.game_scoped) return null
  const source = template.source === 'plugin' ? 'plugin' : template.source === 'user' ? 'user' : 'builtin'
  return {
    id,
    name: String(template.world_name || template.name || id),
    description: String(template.description || ''),
    language: String(template.active_locale || template.language || ''),
    source,
    lorebookCount: Number(template.lorebook_count || 0),
    defaultRule: String(template.default_rule || ''),
    sceneImage: template.scene_image,
    gmStyle: template.gm_style ?? null,
    adventureName: '',
  }
}

function worldCard(world: WorldSummary): GalleryCard | null {
  const id = String(world.id || world.world_id || '')
  if (!id) return null
  return {
    id,
    name: String(world.name || world.world_name || id),
    description: String(world.description || ''),
    language: String(world.language || ''),
    source: 'user',
    lorebookCount: Number(world.entry_count || 0),
    defaultRule: '',
    gmStyle: world.gm_style ?? null,
    adventureName: '',
  }
}

async function load() {
  error.value = ''
  try {
    const [templateData, worldData, adventureData] = await Promise.all([
      api<WorldTemplatesResponse>(`/world-templates?language=${encodeURIComponent(locale.value)}`),
      api<WorldListResponse>('/worlds'),
      api<AdventuresResponse>(`/adventures?language=${encodeURIComponent(locale.value)}`).catch(() => ({ ok: true, adventures: [] } as AdventuresResponse)),
    ])
    const adventureByWorld = new Map<string, string>()
    for (const adventure of adventureData.adventures || []) {
      const worldId = String(adventure.recommended_world_id || '')
      if (worldId && !adventureByWorld.has(worldId)) adventureByWorld.set(worldId, String(adventure.name || ''))
    }
    const seen = new Set<string>()
    const merged: GalleryCard[] = []
    for (const template of templateData.templates || []) {
      const card = templateCard(template)
      if (!card) continue
      seen.add(card.id)
      card.adventureName = adventureByWorld.get(card.id) || ''
      merged.push(card)
    }
    // lore 世界按内容语言过滤：避免 zh 界面混入 *_en 等异语世界卡。
    for (const world of filterByContentLanguage(worldData.worlds || [], locale.value)) {
      const card = worldCard(world)
      if (!card || seen.has(card.id)) continue
      card.adventureName = adventureByWorld.get(card.id) || ''
      merged.push(card)
    }
    cards.value = merged
    void loadCovers(merged)
  } catch (cause: unknown) {
    error.value = errorMessage(cause)
  }
}

let coverSequence = 0
async function loadCovers(list: GalleryCard[]) {
  const sequence = ++coverSequence
  const previous = coverUrls.value
  const next: Record<string, string> = {}
  await Promise.all(list.map(async card => {
    try {
      next[card.id] = await resolveSceneImageUrl(card.sceneImage, card.defaultRule)
    } catch {
      next[card.id] = ruleSceneUrl(card.defaultRule)
    }
  }))
  if (sequence !== coverSequence) {
    Object.values(next).forEach(revokeSceneImageUrl)
    return
  }
  coverUrls.value = next
  for (const url of Object.values(previous)) {
    if (!Object.values(next).includes(url)) revokeSceneImageUrl(url)
  }
}

onMounted(load)
watch(locale, load)
onBeforeUnmount(() => Object.values(coverUrls.value).forEach(revokeSceneImageUrl))

function useForGame(card: GalleryCard) {
  void router.push({ name: 'create', query: { world: card.id } })
}

async function cloneWorld(card: GalleryCard) {
  busy.value = true
  try {
    const result = await api<WorldCloneResponse>('/worlds/clone-from-template', {
      method: 'POST',
      body: JSON.stringify({ template_id: card.id }),
    })
    if (!result.ok) throw new Error(result.error || 'clone-failed')
    toast.success(t('worldsCloned'))
    await load()
  } catch (cause: unknown) {
    toast.error(errorMessage(cause))
  } finally {
    busy.value = false
  }
}

async function deleteWorld(card: GalleryCard) {
  const agreed = await confirm({
    type: 'error',
    title: t('worldsActionDelete'),
    content: t('worldsDeleteConfirm', { name: card.name }),
  })
  if (!agreed) return
  try {
    const result = await api<{ ok: boolean; error?: string }>(`/worlds/${encodeURIComponent(card.id)}`, { method: 'DELETE' })
    if (!result.ok) throw new Error(result.error || 'delete-failed')
    toast.success(t('worldsDeleted'))
    previewCard.value = null
    await load()
  } catch (cause: unknown) {
    toast.error(errorMessage(cause))
  }
}

function openPreview(card: GalleryCard) {
  previewCard.value = card
  styleForm.value = { ...(card.gmStyle || DEFAULT_STYLE) }
}

async function saveStyle() {
  if (!previewCard.value) return
  styleBusy.value = true
  try {
    const result = await api<{ ok: boolean; error?: string; gm_style?: GmStyle }>(
      `/worlds/${encodeURIComponent(previewCard.value.id)}/gm-style`,
      { method: 'PUT', body: JSON.stringify({ gm_style: styleForm.value }) },
    )
    if (!result.ok) throw new Error(result.error || 'save-failed')
    toast.success(t('worldsGmStyleSaved'))
    previewCard.value = null
    await load()
  } catch (cause: unknown) {
    toast.error(errorMessage(cause))
  } finally {
    styleBusy.value = false
  }
}

function resetStyle() {
  styleForm.value = { ...DEFAULT_STYLE }
}

const canEditStyle = computed(() => Boolean(previewCard.value && previewCard.value.gmStyle))

function languageLabel(card: GalleryCard): string {
  const language = card.language.toLowerCase()
  if (language.startsWith('ja')) return '日本語'
  if (language.startsWith('en')) return t('english')
  return t('chinese')
}

function sourceLabel(card: GalleryCard): string {
  if (card.source === 'plugin') return t('worldsSourcePlugin')
  if (card.source === 'user') return t('worldsSourceUser')
  return t('worldsSourceBuiltin')
}

function coverStyle(card: GalleryCard): Record<string, string> {
  const url = coverUrls.value[card.id] || ''
  return url ? { '--df-world-cover': `url("${url.replace(/"/g, '%22')}")` } : {}
}
</script>

<template>
  <section class="view archive-page worlds-page">
    <header class="view-title archive-hero">
      <div>
        <span class="section-kicker">{{ t('worldsKicker') }}</span>
        <h1>{{ t('navWorlds') }}</h1>
        <p class="muted">{{ t('worldsIntro') }}</p>
      </div>
    </header>

    <p v-if="error" class="notice">{{ error }}</p>

    <div class="worlds-grid">
      <article v-for="card in cards" :key="card.id" class="world-card">
        <div class="world-card-cover" :style="coverStyle(card)" />
        <div class="world-card-badges">
          <span class="world-card-badge" :class="`world-card-badge-${card.source}`">{{ sourceLabel(card) }}</span>
          <span v-if="card.adventureName" class="world-card-badge world-card-badge-pack">{{ t('worldsAdventurePack', { name: card.adventureName }) }}</span>
        </div>
        <div class="world-card-body">
          <h2 :title="card.name">{{ card.name }}</h2>
          <p v-if="card.description" class="world-card-desc">{{ card.description }}</p>
          <p class="world-card-meta">
            {{ languageLabel(card) }} · {{ t('worldsEntryCount', { count: card.lorebookCount }) }}
          </p>
          <div class="world-card-actions">
            <button class="primary" :disabled="busy" @click="useForGame(card)">{{ t('worldsActionUse') }}</button>
            <button @click="openPreview(card)">{{ t('worldsActionPreview') }}</button>
            <button class="world-card-clone" :disabled="busy || card.source === 'user'" @click="cloneWorld(card)">
              {{ t('worldsActionClone') }}
            </button>
          </div>
        </div>
      </article>
    </div>

    <Modal v-if="previewCard" :title="previewCard.name" @close="previewCard = null">
      <p v-if="previewCard.description" class="muted">{{ previewCard.description }}</p>
      <p class="muted">
        {{ sourceLabel(previewCard) }} · {{ languageLabel(previewCard) }} · {{ t('worldsEntryCount', { count: previewCard.lorebookCount }) }}
      </p>

      <div class="world-style-editor">
        <h3>{{ t('worldsGmStyle') }}</h3>
        <template v-if="canEditStyle">
          <label>
            <span>{{ t('worldsGmStyleTone') }}</span>
            <input v-model="styleForm.tone" type="text" maxlength="120">
            <small class="muted">{{ t('worldsGmStyleToneHint') }}</small>
          </label>
          <label>
            <span>{{ t('worldsGmStyleVerbosity') }}</span>
            <select v-model="styleForm.verbosity">
              <option value="brief">{{ t('worldsVerbosityBrief') }}</option>
              <option value="normal">{{ t('worldsVerbosityNormal') }}</option>
              <option value="detailed">{{ t('worldsVerbosityDetailed') }}</option>
            </select>
          </label>
          <label>
            <span>{{ t('worldsGmStyleCustom') }}</span>
            <textarea v-model="styleForm.custom_instructions" rows="5" maxlength="2000" />
            <small class="muted">{{ t('worldsGmStyleCustomHint') }}</small>
          </label>
        </template>
        <p v-else class="notice">{{ t('worldsGmStyleLocked') }}</p>
      </div>

      <template #actions>
        <button @click="previewCard = null">{{ t('close') }}</button>
        <button v-if="previewCard && previewCard.source === 'user'" class="danger" @click="deleteWorld(previewCard)">
          {{ t('worldsActionDelete') }}
        </button>
        <template v-if="canEditStyle">
          <button @click="resetStyle">{{ t('worldsGmStyleReset') }}</button>
          <button class="primary" :disabled="styleBusy" @click="saveStyle">{{ t('worldsGmStyleSave') }}</button>
        </template>
      </template>
    </Modal>
  </section>
</template>

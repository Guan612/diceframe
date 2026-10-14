<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '@/api/client'
import type { AdventuresResponse, GmStyle, SceneImageRef, WorldCloneResponse, WorldListResponse, WorldSummary, WorldTemplateSummary, WorldTemplatesResponse } from '@/api/types'
import { resolveSceneImageUrl, revokeSceneImageUrl, SCENE_IMAGE_ACCEPT, uploadSceneImage } from '@/api/sceneImages'
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

const DEFAULT_STYLE: GmStyle = { tone: '', verbosity: 'normal', pace: 'normal', custom_instructions: '' }

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
const coverInput = ref<HTMLInputElement | null>(null)
const coverTargetId = ref('')

// 用户世界的头图：走创建页同一条 /scene-images 上传 + 模板写回路径
function changeCover(card: GalleryCard) {
  coverTargetId.value = card.id
  coverInput.value?.click()
}

async function onCoverFilePicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  const worldId = coverTargetId.value
  if (!file || !worldId || busy.value) return
  busy.value = true
  try {
    const sceneImage = await uploadSceneImage(file)
    const result = await api<{ ok: boolean; error?: string }>('/worlds/user-scene-image', {
      method: 'POST',
      body: JSON.stringify({ world_id: worldId, scene_image: sceneImage }),
    })
    if (!result.ok) throw new Error(result.error || 'cover-save-failed')
    toast.success(t('worldsCoverUpdated'))
    await load()
  } catch (cause: unknown) {
    toast.error(errorMessage(cause))
  } finally {
    busy.value = false
  }
}

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

// 排序 + 客户端翻页：世界数量在几十量级，前端分页足够
type WorldsSortMode = 'default' | 'user-first' | 'builtin-first' | 'name' | 'entries'
const WORLDS_PAGE_SIZE = 12
const worldsSort = ref<WorldsSortMode>('default')
const worldsPage = ref(1)

const SOURCE_RANK_USER_FIRST: Record<GalleryCard['source'], number> = { user: 0, plugin: 1, builtin: 2 }
const SOURCE_RANK_BUILTIN_FIRST: Record<GalleryCard['source'], number> = { builtin: 0, plugin: 1, user: 2 }

const sortedCards = computed(() => {
  const list = [...cards.value]
  if (worldsSort.value === 'name') list.sort((a, b) => a.name.localeCompare(b.name, locale.value))
  if (worldsSort.value === 'entries') list.sort((a, b) => b.lorebookCount - a.lorebookCount || a.name.localeCompare(b.name, locale.value))
  if (worldsSort.value === 'user-first') list.sort((a, b) => SOURCE_RANK_USER_FIRST[a.source] - SOURCE_RANK_USER_FIRST[b.source])
  if (worldsSort.value === 'builtin-first') list.sort((a, b) => SOURCE_RANK_BUILTIN_FIRST[a.source] - SOURCE_RANK_BUILTIN_FIRST[b.source])
  return list
})
const worldsTotalPages = computed(() => Math.max(1, Math.ceil(sortedCards.value.length / WORLDS_PAGE_SIZE)))
const pagedCards = computed(() => {
  const page = Math.min(Math.max(1, worldsPage.value), worldsTotalPages.value)
  return sortedCards.value.slice((page - 1) * WORLDS_PAGE_SIZE, page * WORLDS_PAGE_SIZE)
})

watch(worldsSort, () => { worldsPage.value = 1 })
watch(worldsTotalPages, total => {
  if (worldsPage.value > total) worldsPage.value = total
})

function onWorldsSortChange(event: Event) {
  worldsSort.value = (event.target as HTMLSelectElement).value as WorldsSortMode
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
  if (language.startsWith('de')) return t('german')
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

    <div class="worlds-toolbar">
      <label class="worlds-sort">
        <span>{{ t('worldsSortLabel') }}</span>
        <select :value="worldsSort" @change="onWorldsSortChange">
          <option value="default">{{ t('worldsSortDefault') }}</option>
          <option value="user-first">{{ t('worldsSortUserFirst') }}</option>
          <option value="builtin-first">{{ t('worldsSortBuiltinFirst') }}</option>
          <option value="name">{{ t('worldsSortName') }}</option>
          <option value="entries">{{ t('worldsSortEntries') }}</option>
        </select>
      </label>
    </div>
    <div class="worlds-grid">
      <article v-for="card in pagedCards" :key="card.id" class="world-card">
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
            <button v-if="card.source === 'user'" :disabled="busy" @click="changeCover(card)">
              {{ t('worldsActionChangeCover') }}
            </button>
          </div>
        </div>
      </article>
    </div>

    <div v-if="worldsTotalPages > 1" class="worlds-pager">
      <button type="button" :disabled="worldsPage <= 1" @click="worldsPage--">{{ t('worldsPagePrev') }}</button>
      <span>{{ t('worldsPageOf', { page: Math.min(Math.max(1, worldsPage), worldsTotalPages), total: worldsTotalPages }) }}</span>
      <button type="button" :disabled="worldsPage >= worldsTotalPages" @click="worldsPage++">{{ t('worldsPageNext') }}</button>
    </div>

    <input
      ref="coverInput"
      type="file"
      :accept="SCENE_IMAGE_ACCEPT"
      style="display: none"
      @change="onCoverFilePicked"
    >

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
            <span>{{ t('gmStylePace') }}</span>
            <select v-model="styleForm.pace">
              <option value="slow">{{ t('gmStylePaceSlow') }}</option>
              <option value="normal">{{ t('gmStylePaceNormal') }}</option>
              <option value="fast">{{ t('gmStylePaceFast') }}</option>
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

<style scoped>
/* 世界画廊（/worlds）：全幅封面卡片、来源/冒险包徽章、GM 风格编辑区。 */

.worlds-toolbar {
  display: flex;
  justify-content: flex-end;
  margin: 0 0 10px;
}

.worlds-sort {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--df-text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.worlds-sort select {
  min-height: 32px;
  padding: 0 8px;
  border: 1px solid var(--df-border-soft);
  border-radius: 8px;
  color: var(--df-text);
  background: var(--df-control-bg);
  font-size: 12px;
  cursor: pointer;
}

.worlds-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-top: 14px;
}

.worlds-pager button {
  padding: 6px 14px;
  border: 1px solid var(--df-border-soft);
  border-radius: 8px;
  color: var(--df-text);
  background: var(--df-surface-1);
  cursor: pointer;
  font-size: 12px;
}

.worlds-pager button:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--df-interactive) 45%, transparent);
}

.worlds-pager button:disabled {
  opacity: 0.45;
  cursor: default;
}

.worlds-pager span {
  color: var(--df-text-muted);
  font-size: 12px;
}

.worlds-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
  align-items: stretch;
}

.world-card {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 340px;
  overflow: hidden;
  isolation: isolate;
  border: 1px solid color-mix(in srgb, var(--df-border-soft) 78%, transparent);
  border-radius: 16px;
  background: var(--df-surface-1);
  box-shadow:
    0 22px 52px -34px rgba(0, 0, 0, 0.78),
    0 8px 20px -16px rgba(0, 0, 0, 0.68),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
  transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
}

/* 整卡连续遮罩：信息区不再是一块独立的半透明黑面板。 */
.world-card::after {
  content: "";
  position: absolute;
  z-index: 0;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(110% 62% at 8% 100%, color-mix(in srgb, var(--df-accent) 18%, transparent), transparent 58%),
    linear-gradient(180deg, transparent 32%, rgba(5, 7, 11, 0.08) 45%, rgba(5, 7, 11, 0.62) 72%, rgba(3, 5, 9, 0.96) 100%);
}

/* 封面铺满整卡，文字区用渐变遮罩压暗保证可读性。 */
.world-card-cover {
  position: absolute;
  inset: 0;
  background-color: color-mix(in srgb, var(--df-accent) 14%, var(--df-surface-2));
  background-image: var(--df-world-cover, none);
  background-size: cover;
  background-position: center;
  transition: transform 420ms cubic-bezier(0.2, 0.7, 0.2, 1), filter 220ms ease;
}

.world-card-badges {
  position: relative;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 10px 0;
}

.world-card-badge {
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11px;
  color: #fff;
  background: rgba(8, 10, 14, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(4px);
}

.world-card-badge-user {
  color: color-mix(in srgb, var(--df-accent) 60%, #fff);
}

.world-card-badge-pack {
  color: rgba(255, 255, 255, 0.92);
}

.world-card-body {
  position: relative;
  z-index: 1;
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 72px 14px 14px;
  background: transparent;
  color: #fff;
}

.world-card-body h2 {
  margin: 0;
  /* 跟随皮肤主题色；与白色混合后在暗色封面和亮色主题下都保持足够对比。 */
  color: color-mix(in srgb, var(--df-accent) 78%, #fff);
  font-size: 17px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-shadow: 0 1px 10px rgba(0, 0, 0, 0.85), 0 0 2px rgba(0, 0, 0, 0.7);
}

/* 亮色模式的全局 accent 为深色，适合浅色画布却不适合封面；封面标题固定用高亮金。 */
:root[data-mode="light"] .world-card-body h2 {
  color: #e8c66f;
  text-shadow: 0 2px 12px rgba(0, 0, 0, 0.92), 0 0 3px rgba(0, 0, 0, 0.78);
}

.world-card-desc {
  margin: 0;
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.84);
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.55);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.world-card-meta {
  margin: 0;
  font-size: 11.5px;
  color: rgba(255, 255, 255, 0.72);
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.55);
}

/* 两列等宽按钮网格；克隆按钮仅当排在末位（内置/插件卡的第三个按钮）时整行，
   用户世界四按钮（用它开团/预览/克隆/更换头图）构成整齐的 2×2。 */
.world-card-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 8px;
}

.world-card-actions button {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.11), rgba(255, 255, 255, 0.055));
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.18);
  box-shadow: 0 8px 18px -14px rgba(0, 0, 0, 0.9), inset 0 1px 0 rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(8px);
}

.world-card-actions button.primary {
  background: color-mix(in srgb, var(--df-accent) 72%, rgba(10, 12, 16, 0.6));
  border-color: transparent;
}

.world-card-actions button:disabled {
  opacity: 0.45;
}

.world-card-clone:last-child {
  grid-column: 1 / -1;
}

@media (hover: hover) {
  .world-card:hover {
    transform: translateY(-3px);
    border-color: color-mix(in srgb, var(--df-accent) 30%, var(--df-border-soft));
    box-shadow:
      0 30px 66px -36px rgba(0, 0, 0, 0.9),
      0 14px 30px -20px color-mix(in srgb, var(--df-accent) 34%, transparent),
      inset 0 1px 0 rgba(255, 255, 255, 0.11);
  }

  .world-card:hover .world-card-cover {
    transform: scale(1.025);
    filter: saturate(1.06) contrast(1.025);
  }
}

@media (prefers-reduced-motion: reduce) {
  .world-card,
  .world-card-cover {
    transition: none;
  }
}

.world-style-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.world-style-editor h3 {
  margin: 0;
  font-size: 14px;
}

.world-style-editor label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}

.world-style-editor input,
.world-style-editor select,
.world-style-editor textarea {
  width: 100%;
}
</style>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { CharacterListResponse, GameSummary, GamesResponse, LorebookResponse, LoreEntry, LoreGenerateResponse, Player, WorldCreateResponse, WorldListResponse, WorldSummary } from '@/api/types'
import { readCurrentGame } from '@/stores/gameContext'
import { activePeerGameClient } from '@/peer/game/bridge'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { useLocale, type Locale } from '@/composables/useLocale'
import type { MessageKey } from '@/i18n'
import { contentLanguageOf, filterByContentLanguage } from '@/utils/contentLanguage'
import Modal from '@/components/ui/Modal.vue'
import LorePerspectiveInspector from './LorePerspectiveInspector.vue'
import LoreVisibilityBadge from './LoreVisibilityBadge.vue'
import { useLorePerspective } from './useLorePerspective'
import { PUBLIC_VISIBILITY_MARKERS, visibilityModeOf, type LoreVisibilityMode } from './visibility'

interface LoreEdit extends LoreEntry {
  tier?: string
  content?: string
  match_mode?: string
  unreliable?: boolean
  sync_on_enter?: boolean
  is_constant?: boolean
  triggers_recursive?: string[]
  visible_to?: string[]
  connected_to?: string[]
  sticky?: number
  cooldown?: number
  delay?: number
  order?: number
  probability?: number
  group?: string
  group_weight?: number
}

const toast = useToast()
const { confirm } = useConfirm()
const { locale, t } = useLocale()

const game = ref(readCurrentGame())
const worlds = ref<WorldSummary[]>([])
const worldLanguage = ref<Locale>(locale.value)
const currentWorldId = ref('')
const data = ref<LorebookResponse>({ entries: [] })
const error = ref('')
const busy = ref(false)
const loreEdit = ref<LoreEdit | null>(null)
const generatePrompt = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const showNewWorld = ref(false)
const players = ref<Player[]>([])
const newWorld = ref({ name: '', description: '', language: locale.value })
const entries = computed(() => data.value.entries || [])
const languageWorlds = computed(() => filterByContentLanguage(worlds.value, worldLanguage.value))
const currentWorld = computed(() => worlds.value.find(w => worldIdOf(w) === currentWorldId.value))
const activeLoreType = ref('all')
const loreTypeOrder = ['npc', 'location', 'faction', 'item', 'event', 'puzzle', 'spell', 'class', 'other'] as const

const { viewer, viewerFallback, characterViewerLocked, setViewer, preview, previewError, projectionOf, refreshPreview } = useLorePerspective(currentWorldId, game, players)
const lockedReason = computed<'standalone' | 'peer' | ''>(() => {
  if (!characterViewerLocked.value) return ''
  return game.value && activePeerGameClient() ? 'peer' : 'standalone'
})

const selectedEntryId = ref('')
const selectedEntry = computed(() => entries.value.find(e => e.id && e.id === selectedEntryId.value) || null)
const selectedProjection = computed(() => projectionOf(selectedEntryId.value))
function toggleEntrySelection(entry: LoreEntry) {
  if (!entry.id) return
  selectedEntryId.value = selectedEntryId.value === entry.id ? '' : entry.id
}

const perspectiveFilter = ref<'all' | 'visible' | 'hidden'>('all')
const perspectiveFilters = computed(() => [
  { id: 'all' as const, label: t('loreFilterAll') },
  { id: 'visible' as const, label: t('loreSummaryVisible') },
  { id: 'hidden' as const, label: t('loreFilterHidden') },
])
function matchesPerspectiveFilter(entry: LoreEntry): boolean {
  if (perspectiveFilter.value === 'all') return true
  const visible = projectionOf(entry.id)?.visible || false
  return perspectiveFilter.value === 'visible' ? visible : !visible
}

function resolveInspectorOpen(): boolean {
  const saved = localStorage.getItem('lore_inspector_open')
  if (saved) return saved === '1'
  // 宽屏常驻展开；窄屏默认收起，避免一进页面就被抽屉盖住一半。
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true
  return !window.matchMedia('(max-width: 1100px)').matches
}
const inspectorOpen = ref(resolveInspectorOpen())
function toggleInspector() {
  inspectorOpen.value = !inspectorOpen.value
  localStorage.setItem('lore_inspector_open', inspectorOpen.value ? '1' : '0')
}

function worldIdOf(w: WorldSummary | undefined): string { return String(w?.id || w?.world_id || '') }
function worldNameOf(w: WorldSummary | undefined): string { return String(w?.name || w?.world_name || w?.id || '') }
function cloneLore(entry: LoreEntry): LoreEdit { return JSON.parse(JSON.stringify(entry)) as LoreEdit }

function toggleNewWorld() {
  showNewWorld.value = !showNewWorld.value
  if (showNewWorld.value) newWorld.value.language = worldLanguage.value
}

async function loadWorlds() {
  error.value = ''
  try {
    const r = await api<WorldListResponse>('/worlds')
    worlds.value = r.worlds || []
    if (game.value) {
      const [games, characters] = await Promise.all([
        api<GamesResponse>('/games'),
        api<CharacterListResponse>(`/games/${encodeURIComponent(game.value)}/characters`).catch(() => ({ players: [] } as CharacterListResponse)),
      ])
      players.value = characters.players || []
      const cur = (games.games || []).find((g: GameSummary) => g.game_key === game.value)
      if (cur?.world_id) {
        currentWorldId.value = cur.world_id
        const activeWorld = worlds.value.find(w => worldIdOf(w) === cur.world_id)
        worldLanguage.value = activeWorld
          ? contentLanguageOf(activeWorld)
          : contentLanguageOf({ language: cur.language })
      }
    }
    if (!languageWorlds.value.some(w => worldIdOf(w) === currentWorldId.value)) {
      currentWorldId.value = worldIdOf(languageWorlds.value[0])
    }
  } catch (e: unknown) { error.value = errorMessage(e) }
}

watch(currentWorldId, () => { if (currentWorldId.value) loadLore() })
watch(worldLanguage, () => {
  if (languageWorlds.value.some(w => worldIdOf(w) === currentWorldId.value)) return
  currentWorldId.value = worldIdOf(languageWorlds.value[0])
  if (!currentWorldId.value) data.value = { entries: [] }
})
watch(locale, next => { if (!game.value) worldLanguage.value = next })

async function loadLore() {
  if (!currentWorldId.value) { data.value = { entries: [] }; return }
  error.value = ''; data.value = { entries: [] }
  try {
    data.value = await api<LorebookResponse>(`/lorebook/${encodeURIComponent(currentWorldId.value)}`)
  } catch (e: unknown) { error.value = errorMessage(e) }
}

onMounted(loadWorlds)

function openLore(entry?: LoreEntry) {
  loreEdit.value = entry ? cloneLore(entry) : {
    name: '', type: 'npc', tier: 'background', keywords: [], content: '',
    match_mode: 'any', unreliable: false, sync_on_enter: false, is_constant: false,
    triggers_recursive: [], visible_to: [], connected_to: [], sticky: 0,
    cooldown: 0, delay: 0, order: 100, probability: 100, group: '', group_weight: 1,
  }
  visibilityMode.value = visibilityModeOf(loreEdit.value.visible_to)
}

// 编辑表单的可见性三档：GM 秘密 / 全队公开 / 指定角色。
// 切档直接改写 visible_to；「指定角色」保留点名条目、剥离公开标记，
// 避免 ["*"] 被带进角色文本框造成档位与内容不一致。
const visibilityMode = ref<LoreVisibilityMode>('gm')
function setVisibilityMode(mode: LoreVisibilityMode) {
  visibilityMode.value = mode
  if (!loreEdit.value) return
  if (mode === 'public') {
    loreEdit.value.visible_to = ['*']
  } else if (mode === 'gm') {
    loreEdit.value.visible_to = []
  } else {
    const markers = new Set(PUBLIC_VISIBILITY_MARKERS.map(marker => marker.toLowerCase()))
    loreEdit.value.visible_to = loreEdit.value.visible_to.filter(
      value => !markers.has(String(value).trim().toLowerCase()),
    )
  }
}

// 指定角色：队员直接点选（写入 canonical uid），文本框兜底手动添加外部角色。
function characterLabel(p: Player) { return String(p.character_name || p.user_id) }
function isVisibleToPlayer(p: Player) {
  if (!loreEdit.value) return false
  const current = new Set(loreEdit.value.visible_to.map(value => value.trim().toLowerCase()))
  const uid = String(p.user_id).trim().toLowerCase()
  const name = String(p.character_name || '').trim().toLowerCase()
  return current.has(uid) || (name !== '' && current.has(name))
}
function toggleCharacterVisible(p: Player) {
  if (!loreEdit.value) return
  const uid = String(p.user_id).trim()
  const name = String(p.character_name || '').trim().toLowerCase()
  const norm = (value: string) => value.trim().toLowerCase()
  const kept = loreEdit.value.visible_to.filter(
    value => norm(value) !== uid.toLowerCase() && (name === '' || norm(value) !== name),
  )
  const wasSelected = kept.length !== loreEdit.value.visible_to.length
  loreEdit.value.visible_to = wasSelected ? kept : [...kept, uid]
}

function arrText(a: unknown) { return Array.isArray(a) ? a.join(t('listSeparator')) : '' }
function normalizeLoreType(type: unknown): string {
  const text = String(type || 'other')
  return loreTypeOrder.includes(text as (typeof loreTypeOrder)[number]) ? text : 'other'
}
function typeLabel(type: string | undefined) {
  const labels: Record<string, MessageKey> = { npc: 'contentGroupNpc', location: 'loreTypeLocation', faction: 'loreTypeFaction', item: 'contentGroupItem', event: 'loreTypeEvent', puzzle: 'loreTypePuzzle', spell: 'loreTypeSpell', class: 'loreTypeClass', other: 'loreTypeOther' }
  const key = labels[String(type || '')]
  return key ? t(key) : String(type || t('loreEntry'))
}
function tierLabel(tier: string | undefined) {
  const labels: Record<string, MessageKey> = { core: 'core', background: 'background', archived: 'archived' }
  const key = labels[String(tier || '')]
  return key ? t(key) : String(tier || t('background'))
}
function loreBody(entry: LoreEntry) { return String(entry.content || '').trim() || t('noContent') }
function loreKeywords(entry: LoreEntry) { return arrText(entry.keywords).slice(0, 80) }
function loreConnections(entry: LoreEntry) { return arrText((entry as LoreEdit).connected_to).slice(0, 80) }
function loreTypeCount(type: string) { return entries.value.filter(entry => normalizeLoreType(entry.type) === type).length }
const loreTypeTabs = computed(() => [
  { type: 'all', label: t('allLoreTypes'), count: entries.value.length },
  ...loreTypeOrder.map(type => ({ type, label: typeLabel(type), count: loreTypeCount(type) })),
])
const loreSections = computed(() => {
  const selected = activeLoreType.value
  const types = selected === 'all' ? [...loreTypeOrder] : [selected]
  return types
    .map(type => ({
      type,
      label: typeLabel(type),
      entries: entries.value.filter(entry => normalizeLoreType(entry.type) === type && matchesPerspectiveFilter(entry)),
    }))
    .filter(section => selected !== 'all' || section.entries.length)
})
function setArr(field: keyof LoreEdit, e: Event) {
  const v = (e.target as HTMLInputElement).value.split(/[,，、]/).map(x => x.trim()).filter(Boolean)
  if (loreEdit.value) (loreEdit.value as Record<string, unknown>)[field] = v
}

async function saveLore() {
  if (!loreEdit.value) return
  const entry: LoreEdit = { ...loreEdit.value, world_id: currentWorldId.value }
  const path = entry.id ? `/lorebook/${encodeURIComponent(entry.id)}` : '/lorebook'
  try {
    await api<unknown>(path, { method: entry.id ? 'PUT' : 'POST', body: JSON.stringify(entry) })
    toast.success(entry.id ? t('updated') : t('created'))
    loreEdit.value = null
    await loadLore()
    await loadWorlds()
    await refreshPreview()
  } catch (e: unknown) { error.value = errorMessage(e) }
}

async function deleteLore(entry: LoreEntry) {
  if (!entry.id) return
  const ok = await confirm({ title: t('deleteLoreEntryTitle'), content: t('deleteLoreEntryContent', { name: entry.name || t('unnamedLoreEntry') }), positiveText: t('deleteLoreEntryAction'), type: 'error' })
  if (!ok) return
  try {
    await api<unknown>(`/lorebook/${encodeURIComponent(entry.id)}`, { method: 'DELETE' })
    toast.success(t('deleted'))
    if (selectedEntryId.value === entry.id) selectedEntryId.value = ''
    await loadLore()
    await loadWorlds()
    await refreshPreview()
  } catch (e: unknown) { error.value = errorMessage(e) }
}

async function generateLore() {
  if (!generatePrompt.value.trim()) { toast.error(t('enterGenerationPrompt')); return }
  busy.value = true
  try {
    const r = await api<LoreGenerateResponse>(`/lorebook/${encodeURIComponent(currentWorldId.value)}/generate`, {
      method: 'POST',
      body: JSON.stringify({ prompt: generatePrompt.value, language: currentWorld.value?.language || locale.value }),
    })
    toast.success(t('aiGeneratedEntries', { count: r.count || (r.entries?.length || 0) }))
    generatePrompt.value = ''
    await loadLore()
    await loadWorlds()
    await refreshPreview()
  } catch (e: unknown) { error.value = errorMessage(e) } finally { busy.value = false }
}

async function createWorld() {
  if (!newWorld.value.name.trim()) { toast.error(t('enterWorldName')); return }
  busy.value = true
  try {
    const createdLanguage = contentLanguageOf({ language: newWorld.value.language })
    const r = await api<WorldCreateResponse>('/worlds', { method: 'POST', body: JSON.stringify({ name: newWorld.value.name, description: newWorld.value.description, language: newWorld.value.language }) })
    if (!r.ok) throw new Error(r.error || t('createFailed'))
    toast.success(t('worldCreated'))
    newWorld.value = { name: '', description: '', language: locale.value }
    showNewWorld.value = false
    await loadWorlds()
    worldLanguage.value = createdLanguage
    if (r.world_id || r.id) currentWorldId.value = String(r.world_id || r.id)
  } catch (e: unknown) { error.value = errorMessage(e) } finally { busy.value = false }
}

async function deleteWorld() {
  if (!currentWorldId.value) return
  const w = worlds.value.find(x => worldIdOf(x) === currentWorldId.value)
  const ok = await confirm({ title: t('deleteWorldTitle'), content: t('deleteWorldContent', { name: worldNameOf(w) || currentWorldId.value }), positiveText: t('deleteWorldAction'), type: 'error' })
  if (!ok) return
  try {
    await api<unknown>(`/worlds/${encodeURIComponent(currentWorldId.value)}`, { method: 'DELETE' })
    toast.success(t('worldDeleted'))
    currentWorldId.value = ''
    selectedEntryId.value = ''
    await loadWorlds()
    if (languageWorlds.value.length) currentWorldId.value = worldIdOf(languageWorlds.value[0])
    else data.value = { entries: [] }
  } catch (e: unknown) { error.value = errorMessage(e) }
}

function exportLore() {
  const list = data.value.entries || []
  const blob = new Blob([JSON.stringify(list, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `lorebook_${currentWorldId.value}.json`
  a.click()
  URL.revokeObjectURL(url)
  toast.success(t('exported'))
}

async function importLore(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const text = await file.text()
    const imported = JSON.parse(text) as unknown
    if (!Array.isArray(imported)) throw new Error(t('jsonArrayRequired'))
    for (const en of imported) {
      if (!en || typeof en !== 'object') continue
      await api<unknown>('/lorebook', { method: 'POST', body: JSON.stringify({ ...en, world_id: currentWorldId.value, id: undefined }) })
    }
    toast.success(t('importedEntries', { count: imported.length }))
    await loadLore()
    await loadWorlds()
    await refreshPreview()
  } catch (err: unknown) { error.value = `${t('importFailed')}: ${errorMessage(err)}` } finally {
    if (fileInput.value) fileInput.value.value = ''
  }
}
</script>

<template>
  <section class="view archive-page lorebook-page">
    <div class="lorebook-shell" :class="{ 'inspector-open': inspectorOpen }">
      <main class="lorebook-workspace">
    <header class="view-title archive-hero">
      <div>
        <span class="section-kicker">{{ t('lorebookKicker') }}</span>
        <h1>{{ t('navLorebook') }}</h1>
        <p v-if="game">{{ t('currentSave') }}: {{ game }}</p>
        <p v-else class="muted">{{ t('standaloneLorebookHint') }}</p>
      </div>
      <div class="lore-header-actions">
        <button @click="toggleInspector">{{ t('loreInspectorToggle') }}</button>
        <button @click="loadWorlds">{{ t('refresh') }}</button>
      </div>
    </header>

    <p v-if="error" class="error-banner">{{ error }}</p>

    <div class="lore-world-bar">
      <label class="lore-language-filter">
        <span>{{ t('contentLanguage') }}</span>
        <select v-model="worldLanguage">
          <option value="zh-CN">{{ t('chinese') }}</option>
          <option value="en">{{ t('english') }}</option>
        </select>
      </label>
      <select v-model="currentWorldId">
        <option value="" disabled>{{ t('chooseWorldEllipsis') }}</option>
        <option v-for="w in languageWorlds" :key="worldIdOf(w)" :value="worldIdOf(w)">{{ worldNameOf(w) }} ({{ t('entriesCount', { count: w.entry_count || 0 }) }})</option>
      </select>
      <button class="success" @click="toggleNewWorld">+ {{ t('newWorld') }}</button>
      <button v-if="currentWorldId" class="danger" @click="deleteWorld" :disabled="busy">{{ t('deleteWorldAction') }}</button>
    </div>

    <details v-if="showNewWorld" class="ai-block" open>
      <summary>{{ t('newWorld') }}</summary>
      <label>{{ t('worldName') }}<input v-model="newWorld.name" :placeholder="t('nameNewWorld')"></label>
      <label>{{ t('contentLanguage') }}
        <select v-model="newWorld.language">
          <option value="zh-CN">{{ t('chinese') }}</option>
          <option value="en">{{ t('english') }}</option>
        </select>
      </label>
      <label>{{ t('description') }}<textarea rows="2" v-model="newWorld.description"></textarea></label>
      <div class="actions"><button @click="showNewWorld = false">{{ t('cancel') }}</button><button class="primary" :disabled="busy" @click="createWorld">{{ t('create') }}</button></div>
    </details>

    <div class="lore-tools">
      <button class="success" :disabled="!currentWorldId" @click="openLore()">{{ t('addLoreEntry') }}</button>
      <input v-model="generatePrompt" :placeholder="t('generateLorePlaceholder')">
      <button @click="generateLore" :disabled="busy || !currentWorldId">{{ t('aiGenerate') }}</button>
      <button @click="exportLore" :disabled="!data?.entries?.length">{{ t('export') }}</button>
      <button @click="fileInput?.click()" :disabled="!currentWorldId">{{ t('import') }}</button>
      <input ref="fileInput" type="file" accept="application/json" @change="importLore" hidden>
    </div>

    <p class="memory-meta" v-if="currentWorldId">
      {{ worldNameOf(currentWorld) || currentWorldId }} · {{ worldLanguage === 'en' ? t('english') : t('chinese') }} · {{ t('lorebookEntryCount', { count: entries.length }) }}
    </p>

    <div v-if="entries.length" class="lore-type-tabs">
      <button
        v-for="tab in loreTypeTabs"
        :key="tab.type"
        :class="{ active: activeLoreType === tab.type }"
        @click="activeLoreType = tab.type"
      >
        <span>{{ tab.label }}</span>
        <strong>{{ tab.count }}</strong>
      </button>
    </div>

    <div v-if="entries.length" class="lore-viewer-filter" role="group" :aria-label="t('loreViewerLabel')">
      <button
        v-for="f in perspectiveFilters"
        :key="f.id"
        :class="{ active: perspectiveFilter === f.id }"
        @click="perspectiveFilter = f.id"
      >{{ f.label }}</button>
    </div>

    <div v-if="loreSections.length" class="lore-categories">
      <section v-for="section in loreSections" :key="section.type" class="lore-category-section">
        <header class="lore-category-head">
          <h2>{{ section.label }}</h2>
          <span>{{ t('loreCategoryCount', { count: section.entries.length }) }}</span>
        </header>
        <div class="memory-list lore-list">
          <article
            v-for="e in section.entries"
            :key="e.id || e.name"
            class="memory-row lore-row"
            :class="{ selected: e.id && e.id === selectedEntryId }"
            @click="toggleEntrySelection(e)"
          >
            <div class="memory-row-main">
              <div class="memory-row-head">
                <strong>{{ e.name || t('unnamedLoreEntry') }}</strong>
                <LoreVisibilityBadge :projection="projectionOf(e.id)" />
                <span class="badge">{{ typeLabel(e.type) }}</span>
                <span class="badge" :class="{ low: e.tier === 'archived' }">{{ tierLabel(e.tier) }}</span>
                <span v-if="e.unreliable" class="badge low">{{ t('unreliable') }}</span>
                <span v-if="e.is_constant" class="badge">{{ t('constant') }}</span>
              </div>
              <p class="memory-row-body">{{ loreBody(e) }}</p>
              <p v-if="loreKeywords(e) || loreConnections(e)" class="muted small lore-row-extra">
                <span v-if="loreKeywords(e)">{{ t('keywords') }}: {{ loreKeywords(e) }}</span>
                <span v-if="loreConnections(e)">{{ t('connections') }}: {{ loreConnections(e) }}</span>
              </p>
            </div>
            <div class="memory-row-actions">
              <button @click.stop="openLore(e)">{{ t('edit') }}</button>
              <button class="danger" @click.stop="deleteLore(e)">{{ t('delete') }}</button>
            </div>
          </article>
        </div>
      </section>
    </div>

    <section v-else-if="entries.length" class="empty-panel">
      <h2>{{ t('emptyLoreCategory') }}</h2>
      <p class="muted">{{ t('chooseAnotherLoreCategory') }}</p>
    </section>

    <section v-else-if="currentWorldId && !busy" class="empty-panel">
      <h2>{{ t('noLoreEntries') }}</h2>
      <p class="muted">{{ t('noLoreEntriesHint') }}</p>
    </section>

    <section v-else-if="!currentWorldId && !busy && !showNewWorld" class="empty-panel">
      <h2>{{ t('chooseWorldEllipsis') }}</h2>
      <p class="muted">{{ t('standaloneLorebookHint') }}</p>
    </section>

    <Modal v-if="loreEdit" :title="loreEdit.id ? t('editLoreEntry') : t('newLoreEntry')" @close="loreEdit = null">
      <label>{{ t('name') }}<input v-model="loreEdit.name"></label>
      <label>{{ t('type') }}<select v-model="loreEdit.type"><option v-for="tp in loreTypeOrder" :key="tp" :value="tp">{{ typeLabel(tp) }}</option></select></label>
      <label>{{ t('tier') }}<select v-model="loreEdit.tier"><option value="core">{{ t('core') }}</option><option value="background">{{ t('background') }}</option><option value="archived">{{ t('archived') }}</option></select></label>
      <label>{{ t('keywords') }}<input :value="arrText(loreEdit.keywords)" @input="setArr('keywords', $event)" :placeholder="t('keywordsPlaceholder')"></label>
      <label>{{ t('content') }}<textarea rows="6" v-model="loreEdit.content"></textarea></label>
      <label>{{ t('keywordMatchMode') }}<select v-model="loreEdit.match_mode"><option value="any">{{ t('matchAny') }}</option><option value="all">{{ t('matchAll') }}</option><option value="not_any">{{ t('matchNotAny') }}</option><option value="not_all">{{ t('matchNotAll') }}</option></select></label>
      <div class="check-row"><label><input type="checkbox" v-model="loreEdit.unreliable">{{ t('unreliableMemory') }}</label><label><input type="checkbox" v-model="loreEdit.sync_on_enter">{{ t('syncOnEnter') }}</label><label><input type="checkbox" v-model="loreEdit.is_constant">{{ t('constant') }}</label></div>
      <label>{{ t('recursiveTrigger') }}<input :value="arrText(loreEdit.triggers_recursive)" @input="setArr('triggers_recursive', $event)" :placeholder="t('recursiveTriggerPlaceholder')"></label>
      <label>{{ t('loreVisibilityLabel') }}</label>
      <div class="lore-filter-options" role="radiogroup" :aria-label="t('loreVisibilityLabel')">
        <button type="button" :class="{ active: visibilityMode === 'gm' }" @click="setVisibilityMode('gm')">{{ t('loreAudienceGmSecret') }}</button>
        <button type="button" :class="{ active: visibilityMode === 'public' }" @click="setVisibilityMode('public')">{{ t('loreVisibilityPublic') }}</button>
        <button type="button" :class="{ active: visibilityMode === 'characters' }" @click="setVisibilityMode('characters')">{{ t('loreVisibilityCharacters') }}</button>
      </div>
      <template v-if="visibilityMode === 'characters'">
        <div v-if="players.length" class="lore-filter-options" role="group" :aria-label="t('visibleCharacters')">
          <button v-for="p in players" :key="p.user_id" type="button" :class="{ active: isVisibleToPlayer(p) }" @click="toggleCharacterVisible(p)">{{ characterLabel(p) }}</button>
        </div>
        <label>{{ t('visibleCharacters') }}<input :value="arrText(loreEdit.visible_to)" @input="setArr('visible_to', $event)" :placeholder="t('visibleCharactersPlaceholder')"></label>
      </template>
      <label>{{ t('connectedEntries') }}<input :value="arrText(loreEdit.connected_to)" @input="setArr('connected_to', $event)" :placeholder="t('connectedEntriesPlaceholder')"></label>
      <div class="grid-2"><label>{{ t('stickyRounds') }}<input type="number" v-model.number="loreEdit.sticky"></label><label>{{ t('cooldown') }}<input type="number" v-model.number="loreEdit.cooldown"></label></div>
      <div class="grid-2"><label>{{ t('delay') }}<input type="number" v-model.number="loreEdit.delay"></label><label>{{ t('order') }}<input type="number" v-model.number="loreEdit.order"></label></div>
      <div class="grid-2"><label>{{ t('probabilityPercent') }}<input type="number" v-model.number="loreEdit.probability"></label><label>{{ t('group') }}<input v-model="loreEdit.group"></label></div>
      <label>{{ t('groupWeight') }}<input type="number" v-model.number="loreEdit.group_weight"></label>
      <template #actions><button @click="loreEdit = null">{{ t('cancel') }}</button><button class="primary" @click="saveLore">{{ t('saveAction') }}</button></template>
    </Modal>
      </main>
      <div v-if="inspectorOpen" class="lore-inspector-backdrop" @click="inspectorOpen = false"></div>
      <LorePerspectiveInspector
        v-if="inspectorOpen"
        :players="players"
        :viewer="viewer"
        :viewer-fallback="viewerFallback"
        :character-viewer-locked="characterViewerLocked"
        :locked-reason="lockedReason"
        :preview="preview"
        :preview-error="previewError"
        :selected-entry="selectedEntry"
        :selected-projection="selectedProjection"
        @select-viewer="setViewer"
        @close="inspectorOpen = false"
      />
    </div>
  </section>
</template>

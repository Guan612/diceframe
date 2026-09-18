<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, apiBlob } from '@/api/client'
import type { CharacterCard, CharacterCardsResponse, CharacterItem, CharacterListResponse, CharacterPortrait, CharacterSchemaResponse, CharacterSheet, CharacterSkill, JsonObject, Player, RuleMeta, RulesResponse, RuleSummary, SkillSpec, WorldListResponse, WorldSummary } from '@/api/types'
import { readCurrentGame } from '@/stores/gameContext'
import { importTavernCard } from '@/utils/characterImport'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { useLocale } from '@/composables/useLocale'
import Modal from '@/components/ui/Modal.vue'
import CharacterWizard from '@/components/admin/CharacterWizard.vue'
import SkillEditor from '@/components/admin/SkillEditor.vue'
import LevelUpDialog from '@/components/admin/LevelUpDialog.vue'
import ItemEditor from '@/components/admin/ItemEditor.vue'
import PortraitImage from '@/components/PortraitImage.vue'
import PortraitPicker from '@/components/admin/PortraitPicker.vue'
import RulesetAdvancementHost from '@/features/rulesets/RulesetAdvancementHost.vue'
import RulesetExperienceHost from '@/features/rulesets/RulesetExperienceHost.vue'
import RulesetCharacterCenterHost from '@/features/rulesets/RulesetCharacterCenterHost.vue'
import {
  identitySchema, identityLabel, getIdentityValue, setIdentityUpdate,
  currencyLabel, getCurrencyAmount, getResourceValue,
  isAutoHpRule, calcAutoHp, attrDisplayName,
  type IdentityField, type RuleAttr,
} from '@/utils/ruleSchema'
import { currencyAmountToInputText, currencyEditableUnitLabel, currencyInputStep, parseCurrencyInput } from '@/utils/currency'

interface CharacterData extends CharacterListResponse { cards: CharacterCard[] }
interface ResourceEdit { current: number; max: number }
interface CharacterEditForm {
  player: import('@/api/types').Player
  user_id: string
  character_name: string
  level: number
  hp: ResourceEdit
  gold: number
  goldText: string
  attributes: Record<string, number>
  skills: CharacterSkill[]
  background: string
  equipment: CharacterItem[]
  inventory: CharacterItem[]
  keyText: string
  fields: IdentityField[]
  identityValues: Record<string, string>
  portrait?: CharacterPortrait | null
}
interface LevelUpState { player: import('@/api/types').Player; levelUpPoints: number }
interface NpcPortraitEdit { npcId: string; name: string; portrait?: CharacterPortrait | null }
interface CardEditForm {
  card_id: string
  character_name: string
  race: string
  class: string
  skills: CharacterSkill[]
  background: string
  gold: number
  goldText: string
  portrait?: CharacterPortrait | null
  rule_id?: string
}
interface CharacterCardPatch extends JsonObject {
  character_name: string
  race: string
  class: string
  skills: CharacterSkill[]
  background: string
  gold: number
  portrait?: CharacterPortrait | null
}
interface ProfessionalEditTarget {
  runtimeId: string
  target: 'game' | 'card'
  character: CharacterSheet
  ruleId: string
  gameKey?: string
  userId?: string
  cardId?: string
}
interface UpdateCharacterPayload extends JsonObject {
  character_name: string
  level: number
  gold: number
  currency: { amount: number }
  progression: { level: number; xp: unknown }
  attributes: Record<string, number>
  skills: CharacterSkill[]
  background: string
  hp: number
  max_hp: number
  resources: { hp: { current: number; max: number; min: number } }
  identity?: Record<string, string>
  equipment?: CharacterItem[]
  inventory?: CharacterItem[]
  key_items?: CharacterItem[]
  portrait?: CharacterPortrait | null
}

const toast = useToast()
const { confirm } = useConfirm()
const { locale, t } = useLocale()

const game = ref(readCurrentGame())
const data = ref<CharacterData | null>(null)
const error = ref('')
const busy = ref(false)
const edit = ref<CharacterEditForm | null>(null)
const editLevelUp = ref<LevelUpState | null>(null)
const editCard = ref<CardEditForm | null>(null)
const editNpcPortrait = ref<NpcPortraitEdit | null>(null)
const advancementCard = ref<CharacterCard | null>(null)
const advancementPlayer = ref<Player | null>(null)
const professionalEdit = ref<ProfessionalEditTarget | null>(null)
const showWizard = ref(false)
const characterSearch = ref('')
const characterSort = ref<'name' | 'rule'>('name')
const libraryView = ref<'grid' | 'list'>('grid')
const filteredCards = computed(() => {
  const keyword = characterSearch.value.trim().toLocaleLowerCase()
  const cards = [...(data.value?.cards || [])]
  const filtered = keyword
    ? cards.filter(card => [card.character_name, card.race, card.class, card.rule_name, card.rule_id].some(value => String(value || '').toLocaleLowerCase().includes(keyword)))
    : cards
  return filtered.sort((a, b) => {
    if (characterSort.value === 'rule') return cardRuleLabel(a).localeCompare(cardRuleLabel(b))
    return String(a.character_name || '').localeCompare(String(b.character_name || ''))
  })
})

const rules = ref<RuleSummary[]>([])
const ruleMeta = ref<RuleMeta>({})
const ruleAttrs = ref<RuleAttr[]>([])
const ruleAttrsTotal = ref(60)
const ruleId = ref('')
const ruleDetail = ref<{ skill_pool?: Array<string | SkillSpec>; skills?: Array<string | SkillSpec> } | null>(null)
const ruleSchemaLoading = ref(false)

const skillPool = computed<Array<string | SkillSpec>>(() => {
  const detail = ruleDetail.value || {}
  return detail.skill_pool || detail.skills || []
})
const editRuleAttrs = computed<RuleAttr[]>(() => {
  if (!edit.value) return ruleAttrs.value
  if (ruleAttrs.value.length) return ruleAttrs.value
  const attrs = edit.value.attributes || {}
  return Object.keys(attrs).map(key => ({ key, name: key, min: 0, max: Math.max(100, Number(attrs[key]) || 100) }))
})

function errorMessage(err: unknown): string { return err instanceof Error ? err.message : String(err || t('operationFailed')) }
function toSkillList(input: CharacterSheet['skills']): CharacterSkill[] {
  return (input || []).map(s => {
    if (typeof s === 'string') return { name: s, value: 20 }
    const row: CharacterSkill = { name: s.name || '', value: s.value || 20 }
    const effect = String(s.effect || '').trim()
    if (effect) row.effect = effect
    return row
  })
}

/** 保存侧技能投影：effect 是玩家说明文本，编辑路径不得丢失。 */
function toSkillPayload(skills: CharacterSkill[]): CharacterSkill[] {
  return skills
    .filter(s => s.name?.trim())
    .map(s => {
      const row: CharacterSkill = { name: s.name.trim(), value: Number(s.value) || 0 }
      const effect = String(s.effect || '').trim().slice(0, 500)
      if (effect) row.effect = effect
      return row
    })
}
function itemLines(items: CharacterItem[] | undefined, fields: Array<keyof CharacterItem>, defaults: Record<string, string | number>): string {
  return (items || []).map(item => fields.map(field => String(item[field] ?? defaults[String(field)] ?? '')).join('|')).join('\n')
}
function parseLines<T extends CharacterItem>(text: string, fn: (p: string[]) => T): T[] {
  const t = text.trim()
  if (!t) return []
  return t.split('\n').map(l => fn(l.split('|').map(x => x.trim())))
}
function cardId(card: CharacterCard): string { return String(card.card_id || card.id || '') }
function ruleNameOf(rule: RuleSummary): string {
  const lang = String(locale.value || '').toLowerCase()
  if (lang.startsWith('zh')) {
    return String(rule.rule_name || rule.rule_name_en || rule.rule_id)
  }
  // de/ja 等非中文界面回退英文名，而不是中文 canonical 名（#277 followup）。
  return String(rule.rule_name_en || rule.rule_name || rule.rule_id)
}
function cardRuleLabel(card: CharacterCard): string {
  if (!card.rule_id) return t('unboundRule')
  const rule = rules.value.find(candidate => candidate.rule_id === card.rule_id)
  return rule ? ruleNameOf(rule) : String(card.rule_name || card.rule_id)
}
function hasRulesAwareLifecycle(capabilities: unknown): boolean {
  if (!capabilities || typeof capabilities !== 'object' || Array.isArray(capabilities)) return false
  return (capabilities as JsonObject).character_lifecycle === 'rules_aware'
}
function isProfessionalCard(card: CharacterCard): boolean {
  return hasRulesAwareLifecycle(card.ruleset_runtime?.capabilities)
}
function isProfessionalGame(): boolean {
  return hasRulesAwareLifecycle(data.value?.ruleset_runtime?.capabilities)
}
function isSelectedProfessionalRule(): boolean {
  const rule = rules.value.find(candidate => candidate.rule_id === ruleId.value)
  return hasRulesAwareLifecycle(rule?.ruleset_runtime?.capabilities)
}
function professionalLevel(card: CharacterSheet): number {
  const canonical = card.ruleset_character as JsonObject | undefined
  const build = canonical?.build as JsonObject | undefined
  return Number(build?.level || card.level || 1)
}
function liveAdvancementRow(userId: string) {
  return data.value?.advancement?.players.find(row => row.user_id === userId)
}
function currentRuleBinding(): Pick<CharacterCard, 'rule_id' | 'rule_name' | 'rule_version' | 'mechanics' | 'language'> {
  const rule = rules.value.find(candidate => candidate.rule_id === ruleId.value)
  return {
    rule_id: ruleId.value,
    rule_name: String(ruleMeta.value.rule_name || rule?.rule_name || ruleId.value),
    rule_version: String(ruleMeta.value.rule_version || ''),
    mechanics: String(ruleMeta.value.mechanics || ''),
    language: String(locale.value),
  }
}
function levelUpPoints(player: import('@/api/types').Player): number { return Number(player.character_sheet?.level_up_points || 0) }
function npcKey(card: CharacterCard): string { return String(card.npc_id || card.id || card.card_id || card.name || card.character_name || Math.random()) }
function npcSummary(card: CharacterCard): string {
  return [
    card.relation ? `${t('relationshipPrefix')} ${card.relation}` : '',
    card.status ? `${t('statusPrefix')} ${card.status}` : '',
    card.first_seen_round ? `${t('firstSeenRound')} ${card.first_seen_round}` : '',
  ].filter(Boolean).join(' · ')
}

function hpPercent(player: import('@/api/types').Player): number {
  const current = Number(player.character_sheet?.hp || 0)
  const maximum = Math.max(1, Number(player.character_sheet?.max_hp || 1))
  return Math.max(0, Math.min(100, (current / maximum) * 100))
}

watch([ruleId, locale], async ([id]) => {
  if (!id) { ruleDetail.value = null; return }
  ruleSchemaLoading.value = true
  try {
    const schema = await api<CharacterSchemaResponse>(
      `/rules/${encodeURIComponent(String(id))}/character-schema?language=${encodeURIComponent(String(locale.value))}`,
    )
    if (!schema.ok) throw new Error(schema.error || t('ruleLoadFailed'))
    if (!game.value) {
      ruleMeta.value = schema.rule_meta || {}
      ruleAttrs.value = schema.rule_attrs || []
      ruleAttrsTotal.value = Number(schema.rule_attrs_total || 60)
    }
    ruleDetail.value = { skill_pool: schema.skill_pool || [] }
  } catch (e: unknown) {
    ruleDetail.value = null
    error.value = errorMessage(e)
  } finally { ruleSchemaLoading.value = false }
})

async function load() {
  error.value = ''; data.value = null
  try {
    if (game.value) {
      const [chars, cards, availableRules] = await Promise.all([
        api<CharacterListResponse>(`/games/${encodeURIComponent(game.value)}/characters`),
        api<CharacterCardsResponse>('/character-cards'),
        api<RulesResponse>('/rules'),
      ])
      rules.value = availableRules.rules || []
      data.value = { ...chars, cards: cards.cards || [] }
      ruleMeta.value = chars.rule_meta || {}
      ruleAttrs.value = chars.rule_attrs || []
      ruleAttrsTotal.value = chars.rule_attrs_total || 60
      ruleId.value = String(ruleMeta.value.rule_id || '')
    } else {
      const [cards, availableRules] = await Promise.all([
        api<CharacterCardsResponse>('/character-cards'),
        api<RulesResponse>('/rules'),
      ])
      rules.value = availableRules.rules || []
      data.value = { players: [], cards: cards.cards || [] }
      if (!ruleId.value || !rules.value.some(rule => rule.rule_id === ruleId.value)) {
        ruleId.value = rules.value[0]?.rule_id || ''
      }
    }
  } catch (e: unknown) { error.value = errorMessage(e) }
}
const route = useRoute()
const tavernInput = ref<HTMLInputElement | null>(null)
const diceframeInput = ref<HTMLInputElement | null>(null)
const tavernImportOpen = ref(false)
const tavernTarget = ref<'npc' | 'character_card'>('npc')
const tavernWorlds = ref<WorldSummary[]>([])
const tavernWorldId = ref('')

async function openTavernImport() {
  tavernTarget.value = 'npc'
  tavernWorldId.value = ''
  tavernImportOpen.value = true
  try {
    const r = await api<WorldListResponse>('/worlds')
    tavernWorlds.value = r.worlds || []
    if (tavernWorlds.value.length && !tavernWorldId.value) {
      const first = tavernWorlds.value[0]
      tavernWorldId.value = String(first.id || first.world_id || '')
    }
  } catch (err: unknown) { toast.error(errorMessage(err)) }
}

function confirmTavernChoice() {
  if (tavernTarget.value === 'npc' && !tavernWorldId.value) {
    toast.error(t('tavernImportPickWorld'))
    return
  }
  tavernImportOpen.value = false
  tavernInput.value?.click()
}

async function onImportDiceframe(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  busy.value = true
  try {
    const r = await importTavernCard(file, { target: 'character_card' })
    toast.success(t('importedCharacter', { name: r.card?.character_name || file.name }))
    if (r.nsfw_warning) toast.warning(t('tavernImportNsfwWarning'))
    await load()
  } catch (err: unknown) { toast.error(errorMessage(err)) } finally { busy.value = false; input.value = '' }
}

const selectedCardIds = ref<Set<string>>(new Set())

function toggleCardSelect(id: string) {
  const next = new Set(selectedCardIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedCardIds.value = next
}

async function exportCards(ids: string[]) {
  if (!ids.length) return
  try {
    const res = await apiBlob('/character-cards/export', {
      method: 'POST',
      body: JSON.stringify({ card_ids: ids }),
    })
    const blob = await res.blob()
    const dispo = res.headers.get('Content-Disposition') || ''
    const m = dispo.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i)
    const filename = m ? decodeURIComponent(m[1]) : 'characters.json'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
    toast.success(t('exportedCards'))
  } catch (err: unknown) { toast.error(errorMessage(err)) }
}

async function exportSingleCard(card: CharacterCard) {
  await exportCards([cardId(card)])
}

async function exportSelected() {
  await exportCards([...selectedCardIds.value])
}

async function deleteSelectedCards() {
  const ids = [...selectedCardIds.value]
  if (!ids.length) return
  const ok = await confirm({
    title: t('deleteSelectedCards'),
    content: t('deleteSelectedCardsConfirm', { count: ids.length }),
    positiveText: t('delete'),
    type: 'error',
  })
  if (!ok) return
  busy.value = true
  try {
    const results = await Promise.allSettled(
      ids.map(id => api<{ ok?: boolean }>(`/character-cards/${encodeURIComponent(id)}`, { method: 'DELETE' })),
    )
    const failed = results.filter(r => r.status === 'rejected' || (r.status === 'fulfilled' && !(r.value as { ok?: boolean })?.ok)).length
    const success = ids.length - failed
    const next = new Set(selectedCardIds.value)
    ids.forEach(id => next.delete(id))
    selectedCardIds.value = next
    if (success > 0) {
      await load()
      toast.success(t('deleteSelectedCardsResult', { count: success }))
    }
    if (failed > 0) toast.error(t('deleteSelectedCardsFailed', { count: failed }))
  } catch (e: unknown) { error.value = errorMessage(e) } finally { busy.value = false }
}

onMounted(async () => {
  await load()
  const uid = route.query.edit_user ? String(route.query.edit_user) : ''
  if (uid && data.value?.players?.length) {
    const p = data.value.players.find(x => x.user_id === uid)
    if (p) openPlayerEditor(p)
  }
})

async function onImportTavern(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const target = tavernTarget.value
  const worldId = target === 'npc' ? tavernWorldId.value : ''
  busy.value = true
  try {
    const r = await importTavernCard(file, { target, worldId })
    if (target === 'npc') {
      toast.success(t('importedTavernNpc', { name: r.npc_name || file.name, world: worldId, count: r.lorebook_entries || 0 }))
    } else {
      toast.success(t('importedCharacter', { name: r.card?.character_name || file.name }))
    }
    if (r.nsfw_warning) toast.warning(t('tavernImportNsfwWarning'))
    await load()
  } catch (err: unknown) { toast.error(errorMessage(err)) } finally { busy.value = false; input.value = '' }
}

function openEdit(p: import('@/api/types').Player) {
  const cs = p.character_sheet || {}
  const fields = identitySchema(ruleMeta.value).filter((f: IdentityField) => f.key !== 'background')
  const attrs: Record<string, number> = { ...(cs.attributes || {}) }
  ruleAttrs.value.forEach(a => { if (attrs[a.key] === undefined) attrs[a.key] = Math.floor((a.min + a.max) / 2) })
  if (!Object.keys(attrs).length) attrs.str = attrs.con = attrs.dex = attrs.int = attrs.wis = attrs.cha = 50
  edit.value = {
    player: p, user_id: p.user_id,
    character_name: String(cs.character_name || p.character_name || ''),
    level: Number(cs.level || 1),
    hp: getResourceValue(cs, 'hp') as ResourceEdit,
    gold: getCurrencyAmount(cs),
    goldText: currencyAmountToInputText(getCurrencyAmount(cs), ruleMeta.value.currency_system || null),
    attributes: attrs,
    skills: toSkillList(cs.skills),
    background: String(cs.background || ''),
    equipment: (cs.equipment || []).map(it => ({ ...it })),
    inventory: (cs.inventory || []).map(it => ({ ...it })),
    keyText: itemLines(cs.key_items, ['name', 'category', 'note'], { category: 'key_item', note: '' }),
    fields,
    identityValues: Object.fromEntries(fields.map((f: IdentityField) => [f.key, getIdentityValue(cs, f)])),
    portrait: cs.portrait ? { ...cs.portrait } : undefined,
  }
}

function openPlayerEditor(p: import('@/api/types').Player) {
  if (isProfessionalGame()) {
    professionalEdit.value = {
      runtimeId: String(data.value?.ruleset_runtime?.id || ''),
      target: 'game',
      character: { ...(p.character_sheet || {}), character_name: p.character_name },
      ruleId: ruleId.value,
      gameKey: game.value,
      userId: p.user_id,
    }
    return
  }
  openEdit(p)
}

const attrSum = computed(() => {
  const attrs = edit.value?.attributes || {}
  return Object.values(attrs).reduce((sum, value) => sum + (parseInt(String(value)) || 0), 0)
})
const attrPoints = computed(() => Math.max(ruleAttrsTotal.value, attrSum.value) - attrSum.value)
const editableUnitSuffix = computed(() => {
  // 编辑框实际解析单位（可与顶层货币名不同，如 rate=3 时回退铜币）。
  const name = currencyEditableUnitLabel(ruleMeta.value.currency_system || null)
  return name ? `（${name}）` : ''
})
const autoHp = computed(() => isAutoHpRule(ruleMeta.value))
const autoHpValue = computed(() => calcAutoHp(edit.value?.attributes || {}, ruleMeta.value))

async function saveCharacter() {
  const e = edit.value
  if (!e) return
  const cs = e.player.character_sheet || {}
  busy.value = true
  try {
    const level = parseInt(String(e.level)) || 1
    const parsedGold = parseCurrencyInput(e.goldText, ruleMeta.value.currency_system || null, { allowZero: true })
    if (parsedGold === null) throw new Error(t('invalidAmount'))
    const gold = parsedGold
    const hpCurrent = parseInt(String(e.hp.current)) || 0
    const hpMax = parseInt(String(e.hp.max)) || 50
    const updates: UpdateCharacterPayload = {
      character_name: e.character_name,
      level,
      gold,
      currency: { amount: gold },
      progression: { level, xp: cs.xp || 0 },
      attributes: e.attributes,
      skills: toSkillPayload(e.skills),
      background: e.background,
      hp: hpCurrent,
      max_hp: hpMax,
      resources: { hp: { current: hpCurrent, max: hpMax, min: 0 } },
      portrait: e.portrait ? { ...e.portrait } : null,
    }
    e.fields.forEach((f: IdentityField) => setIdentityUpdate(updates, f, e.identityValues[f.key]))
    updates.identity = updates.identity || {}
    updates.identity.background = e.background
    updates.equipment = e.equipment.filter(it => String(it.name || '').trim()).map(it => ({ name: String(it.name).trim(), type: it.type || 'weapon', damage: Number(it.damage) || 0, slot: it.slot || 'main_hand', quality: it.quality || 'common' }))
    updates.inventory = e.inventory.filter(it => String(it.name || '').trim()).map(it => ({ name: String(it.name).trim(), qty: Number(it.qty) || 1, effect: it.effect || '' }))
    updates.key_items = parseLines(e.keyText, p => p.length >= 3 ? { name: p[0], category: p[1] || 'key_item', note: p[2] } : p.length >= 2 ? { name: p[0], category: p[1] || 'key_item' } : { name: p[0] || '', category: 'key_item' })
    await api(`/games/${encodeURIComponent(game.value)}/character/${encodeURIComponent(e.user_id)}`, { method: 'PUT', body: JSON.stringify(updates) })
    edit.value = null
    await load()
    toast.success(t('characterSaved'))
  } catch (e: unknown) { error.value = errorMessage(e) } finally { busy.value = false }
}

async function deleteCharacter(p: import('@/api/types').Player) {
  const ok = await confirm({ title: t('removeCharacterTitle'), content: t('removeCharacterContent', { name: p.character_name }), positiveText: t('removeCharacterAction'), type: 'warning' })
  if (!ok) return
  try {
    await api(`/games/${encodeURIComponent(game.value)}/character/${encodeURIComponent(p.user_id)}`, { method: 'DELETE' })
    await load()
    toast.success(t('removed'))
  } catch (e: unknown) { error.value = errorMessage(e) }
}

async function saveToCard(p: import('@/api/types').Player) {
  const cs = p.character_sheet || {}
  try {
    await api('/character-cards', { method: 'POST', body: JSON.stringify({ character_name: p.character_name, ...cs, ...currentRuleBinding() }) })
    await load()
    toast.success(t('savedToSharedLibrary'))
  } catch (e: unknown) { error.value = errorMessage(e) }
}

function openLevelUp(p: import('@/api/types').Player) {
  editLevelUp.value = { player: p, levelUpPoints: Number(p.character_sheet?.level_up_points || 0) }
}
async function saveLevelUp(attrs: Record<string, number>) {
  const p = editLevelUp.value?.player
  if (!p) return
  busy.value = true
  try {
    await api(`/games/${encodeURIComponent(game.value)}/character/${encodeURIComponent(p.user_id)}`, { method: 'PUT', body: JSON.stringify({ attributes: attrs }) })
    editLevelUp.value = null
    await load()
    toast.success(t('attributePointsAllocated'))
  } catch (e: unknown) { error.value = errorMessage(e) } finally { busy.value = false }
}

function openCardEdit(c: CharacterCard) {
  editCard.value = {
    card_id: cardId(c),
    character_name: c.character_name || '',
    race: c.race || '',
    class: c.class || '',
    skills: toSkillList(c.skills),
    background: c.background || '',
    gold: Number(c.gold ?? 30),
    goldText: currencyAmountToInputText(Number(c.gold ?? 30), ruleMeta.value.currency_system || null),
    portrait: c.portrait ? { ...c.portrait } : undefined,
    rule_id: c.rule_id,
  }
}
function openCardEditor(c: CharacterCard) {
  if (isProfessionalCard(c)) {
    professionalEdit.value = {
      runtimeId: String(c.ruleset_runtime?.id || ''),
      target: 'card',
      character: c,
      ruleId: String(c.rule_id || ''),
      cardId: cardId(c),
    }
    return
  }
  openCardEdit(c)
}
async function saveCardEdit() {
  const e = editCard.value
  if (!e) return
  const parsedGold = parseCurrencyInput(e.goldText, ruleMeta.value.currency_system || null, { allowZero: true })
  if (parsedGold === null) {
    toast.error(t('invalidAmount'))
    return
  }
  busy.value = true
  try {
    const patch: CharacterCardPatch = {
      character_name: e.character_name.trim() || t('unnamed'),
      race: e.race.trim() || t('human'),
      class: e.class.trim() || t('adventurer'),
      skills: toSkillPayload(e.skills),
      background: e.background.trim(),
      gold: parsedGold,
      portrait: e.portrait ? { ...e.portrait } : null,
    }
    const r = await api<{ ok?: boolean; error?: string }>(`/character-cards/${encodeURIComponent(e.card_id)}`, { method: 'PUT', body: JSON.stringify(patch) })
    if (!r.ok) throw new Error(r.error || t('saveFailed'))
    editCard.value = null
    await load()
    toast.success(t('characterCardUpdated'))
  } catch (e: unknown) { error.value = errorMessage(e) } finally { busy.value = false }
}

async function onCardAdvanced() {
  busy.value = true
  try {
    advancementCard.value = null
    await load()
    toast.success(String(locale.value).startsWith('zh') ? '角色升级已完成。' : 'Character advanced.')
  } catch (cause: unknown) {
    error.value = errorMessage(cause)
  } finally { busy.value = false }
}

async function onLiveCharacterAdvanced() {
  busy.value = true
  try {
    advancementPlayer.value = null
    await load()
    toast.success(String(locale.value).startsWith('zh') ? '角色升级已完成。' : 'Character advanced.')
  } catch (cause: unknown) {
    error.value = errorMessage(cause)
  } finally { busy.value = false }
}

async function onProfessionalSaved(_character?: CharacterSheet, reason?: 'profile' | 'rest') {
  professionalEdit.value = null
  await load()
  toast.success(reason === 'rest'
    ? (String(locale.value).startsWith('zh') ? '休息已按规则结算。' : 'Rest completed.')
    : (String(locale.value).startsWith('zh') ? '人物资料已安全保存。' : 'Character profile saved.'))
}

async function deleteCard(c: CharacterCard) {
  const ok = await confirm({ title: t('deleteCharacterCardTitle'), content: t('deleteCharacterCardContent', { name: c.character_name || t('unnamed') }), positiveText: t('deleteCharacterCardAction'), type: 'error' })
  if (!ok) return
  try {
    await api(`/character-cards/${encodeURIComponent(cardId(c))}`, { method: 'DELETE' })
    await load()
    toast.success(t('deleted'))
  } catch (e: unknown) { error.value = errorMessage(e) }
}

function openNpcPortrait(npc: CharacterCard) {
  editNpcPortrait.value = {
    npcId: npcKey(npc),
    name: String(npc.character_name || npc.name || t('unnamed')),
    portrait: npc.portrait ? { ...npc.portrait } : undefined,
  }
}

async function saveNpcPortrait() {
  const npc = editNpcPortrait.value
  if (!npc || !game.value) return
  busy.value = true
  try {
    const result = await api<{ ok?: boolean; error?: string }>(
      `/games/${encodeURIComponent(game.value)}/npc/${encodeURIComponent(npc.npcId)}/portrait`,
      { method: 'PUT', body: JSON.stringify({ portrait: npc.portrait ?? null }) },
    )
    if (!result.ok) throw new Error(result.error || t('saveFailed'))
    editNpcPortrait.value = null
    await load()
    toast.success(t('characterSaved'))
  } catch (e: unknown) { error.value = errorMessage(e) } finally { busy.value = false }
}

async function onWizardSubmit(c: CharacterSheet) {
  busy.value = true
  try {
    await api('/character-cards', {
      method: 'POST',
      body: JSON.stringify({
        ...c,
        character_name: String(c.character_name || t('unnamed')),
        ...currentRuleBinding(),
      }),
    })
    showWizard.value = false
    await load()
    toast.success(t('characterCardCreated'))
  } catch (e: unknown) { error.value = errorMessage(e) } finally { busy.value = false }
}
</script>

<template>
  <section class="view archive-page characters-page" data-testid="characters-page">
    <header class="view-title archive-hero">
      <div>
        <span class="section-kicker">{{ t('charactersKicker') }}</span>
        <h1>{{ t('characterManagement') }}</h1>
        <p v-if="game">{{ t('currentSave') }}: {{ game }}</p>
        <p v-else class="muted">{{ t('noSaveSelectedHint') }}</p>
      </div>
      <div class="actions">
        <label v-if="!game" class="standalone-rule-select">
          <span>{{ t('characterCardRule') }}</span>
          <select v-model="ruleId" :disabled="ruleSchemaLoading">
            <option v-for="rule in rules" :key="rule.rule_id" :value="rule.rule_id">{{ ruleNameOf(rule) }}</option>
          </select>
        </label>
        <button class="success" :disabled="!ruleId || ruleSchemaLoading" @click="showWizard = true">+ {{ t('newCharacterCard') }}</button>
        <button @click="load">{{ t('refresh') }}</button>
      </div>
    </header>

    <p v-if="error" class="error-banner">{{ error }}</p>

    <section v-if="game" class="character-section current-character-section">
      <header class="character-section-head"><h2>{{ t('currentGameCharacters') }}</h2><span>{{ data?.players?.length || 0 }}</span></header>
      <div class="current-character-grid">
      <article v-for="p in data?.players || []" :key="p.user_id" class="char-card current-character-card" data-testid="current-character-card">
        <div class="current-character-identity">
          <button type="button" class="portrait-edit-button" :title="t('clickToChangeAvatar')" @click="openPlayerEditor(p)">
            <PortraitImage :portrait="p.character_sheet?.portrait" :rule-id="ruleId" :seed="p.user_id" :name="p.character_name" :size="96" />
            <span>{{ t('clickToChangeAvatar') }}</span>
          </button>
          <div class="current-character-copy">
            <div class="character-name-line"><h2>{{ p.character_name }}</h2><span class="badge badge-active">{{ t('playerSlot') }}</span></div>
            <div class="character-identity-chips">
              <span>{{ p.user_id }}</span>
              <span>{{ t('level') }} {{ p.character_sheet?.level || 1 }}</span>
              <span v-if="p.character_sheet?.race">{{ p.character_sheet.race }}</span>
              <span v-if="p.character_sheet?.class">{{ p.character_sheet.class }}</span>
            </div>
            <div class="character-resource-line">
              <span>HP</span>
              <div class="character-resource-track"><i :style="{ width: `${hpPercent(p)}%` }" /></div>
              <strong>{{ p.character_sheet?.hp }}/{{ p.character_sheet?.max_hp }}</strong>
            </div>
            <p v-if="levelUpPoints(p) > 0" class="warn character-level-notice">
              {{ t('pointsToAllocate', { points: levelUpPoints(p) }) }}
            </p>
            <p v-if="isProfessionalGame() && liveAdvancementRow(p.user_id)" class="muted character-level-notice">
              <template v-if="liveAdvancementRow(p.user_id)?.entitled">{{ t('advancementGranted', { level: liveAdvancementRow(p.user_id)?.target_level || 0 }) }}</template>
              <template v-else-if="data?.advancement?.mode === 'xp'">XP {{ liveAdvancementRow(p.user_id)?.xp || 0 }} / {{ liveAdvancementRow(p.user_id)?.next_level_xp || 0 }}</template>
              <template v-else>{{ t('advancementWaiting') }}</template>
            </p>
          </div>
        </div>
        <div class="actions current-character-actions" data-testid="current-character-actions">
          <button class="success" @click="openPlayerEditor(p)">{{ isProfessionalGame() ? (String(locale).startsWith('zh') ? '高级角色中心' : 'Character center') : t('edit') }}</button>
          <button v-if="isProfessionalGame() && p.character_sheet && professionalLevel(p.character_sheet) < 20 && liveAdvancementRow(p.user_id)?.entitled" class="primary" @click="advancementPlayer = p">{{ String(locale).startsWith('zh') ? '职业升级' : 'Class advancement' }}</button>
          <button v-if="!isProfessionalGame() && levelUpPoints(p) > 0" class="primary" @click="openLevelUp(p)">{{ t('allocateAttributePointsWithCount', { points: levelUpPoints(p) }) }}</button>
          <button @click="saveToCard(p)">{{ t('saveToSharedLibrary') }}</button>
          <button class="danger" @click="deleteCharacter(p)">{{ t('remove') }}</button>
        </div>
      </article>
      <p v-if="!data?.players?.length" class="muted">{{ t('noCharacters') }}</p>
      </div>
    </section>

    <section v-if="data?.npcs?.length" class="character-section npc-section">
      <header class="character-section-head"><h2>{{ t('currentGameNpcs') }}</h2><span>{{ data.npcs.length }}</span></header>
      <div class="npc-strip">
        <article v-for="n in data.npcs" :key="npcKey(n)" class="char-card npc-mini-card">
          <button type="button" class="portrait-edit-button" :title="t('clickToChangeAvatar')" @click="openNpcPortrait(n)">
            <PortraitImage v-if="n.portrait" :portrait="n.portrait" :rule-id="ruleId" :seed="npcKey(n)" :name="String(n.character_name || n.name || '')" :size="54" />
            <span v-else class="portrait-image npc-portrait-empty" aria-hidden="true">＋</span>
            <span>{{ t('clickToChangeAvatar') }}</span>
          </button>
          <div>
            <h2>{{ n.character_name || n.name || t('unnamed') }}<small v-if="n.tier === 'core'" class="badge">{{ t('core') }}</small></h2>
            <p class="muted">{{ npcSummary(n) }}</p>
          </div>
        </article>
      </div>
    </section>

    <section class="character-section shared-character-section" data-testid="shared-character-section">
      <header class="character-section-head shared-character-head">
        <div><h2>{{ t('sharedCharacterLibrary') }}</h2><span>{{ data?.cards?.length || 0 }}</span></div>
      </header>
    <input ref="tavernInput" type="file" accept=".json,application/json" @change="onImportTavern" hidden>
    <input ref="diceframeInput" type="file" accept=".json,application/json" @change="onImportDiceframe" hidden>
    <Modal v-if="tavernImportOpen" :title="t('importTavernCard')" @close="tavernImportOpen = false">
      <label>{{ t('tavernImportAs') }}</label>
      <div class="check-row">
        <label><input type="radio" value="npc" v-model="tavernTarget"> {{ t('tavernImportAsNpc') }}</label>
        <label><input type="radio" value="character_card" v-model="tavernTarget"> {{ t('tavernImportAsCard') }}</label>
      </div>
      <p class="muted">{{ t('tavernImportAsNpcHint') }}</p>
      <div v-if="tavernTarget === 'npc'">
        <label>{{ t('tavernImportTargetWorld') }}</label>
        <select v-model="tavernWorldId">
          <option v-for="w in tavernWorlds" :key="w.id || w.world_id" :value="w.id || w.world_id">{{ w.name || w.world_name }}</option>
        </select>
        <p v-if="!tavernWorlds.length" class="muted">{{ t('tavernImportNoWorlds') }}</p>
      </div>
      <template #actions>
        <button @click="tavernImportOpen = false">{{ t('cancel') }}</button>
        <button class="primary" :disabled="tavernTarget === 'npc' && !tavernWorldId" @click="confirmTavernChoice">{{ t('chooseFile') }}</button>
      </template>
    </Modal>
      <div class="character-library-toolbar">
        <input v-model="characterSearch" :placeholder="t('characterLibrarySearch')">
        <select v-model="characterSort"><option value="name">{{ t('characterSortName') }}</option><option value="rule">{{ t('characterSortRule') }}</option></select>
        <div class="character-view-switch"><button :class="{ active: libraryView === 'grid' }" @click="libraryView = 'grid'">▦</button><button :class="{ active: libraryView === 'list' }" @click="libraryView = 'list'">☷</button></div>
        <div class="actions character-import-actions"><button class="danger" :disabled="busy || !selectedCardIds.size" @click="exportSelected">{{ t('exportSelected') }}</button><button class="danger" :disabled="busy || !selectedCardIds.size" @click="deleteSelectedCards">{{ t('deleteSelectedCards') }}</button><button class="success" :disabled="busy" @click="diceframeInput?.click()">{{ t('importDiceframeCard') }}</button><button :disabled="busy" @click="openTavernImport">{{ t('importTavernCard') }}</button></div>
      </div>
    <div class="card-grid character-library-grid" :class="`view-${libraryView}`">
      <article v-for="c in filteredCards" :key="c.card_id || c.id" class="char-card library-character-card">
        <div class="character-card-summary">
          <input type="checkbox" :checked="selectedCardIds.has(cardId(c))" @change="toggleCardSelect(cardId(c))" class="card-select" :title="t('selectCard')">
          <button type="button" class="portrait-edit-button" :title="t('clickToChangeAvatar')" @click="openCardEditor(c)">
            <PortraitImage :portrait="c.portrait" :rule-id="c.rule_id" :seed="cardId(c) || c.character_name" :name="c.character_name" :size="64" />
            <span>{{ t('clickToChangeAvatar') }}</span>
          </button>
          <div>
          <h2>{{ c.character_name }}</h2>
          <p class="muted card-rule"><span class="badge" :title="cardRuleLabel(c)">{{ cardRuleLabel(c) }}</span></p>
          <p class="muted card-identity">{{ c.race }} · {{ c.class }}<span v-if="c.source"> · {{ t('source') }} {{ c.source }}</span></p>
          <p v-if="c.background" class="muted card-bg" :title="String(c.background)">{{ String(c.background).slice(0, 80) }}</p>
          </div>
        </div>
        <div class="actions">
          <button v-if="isProfessionalCard(c) && professionalLevel(c) < 20" class="success" @click="advancementCard = c">{{ String(locale).startsWith('zh') ? '职业升级' : 'Level up' }}</button>
          <button @click="openCardEditor(c)">{{ isProfessionalCard(c) ? (String(locale).startsWith('zh') ? '高级角色中心' : 'Character center') : t('editCard') }}</button>
          <button @click="exportSingleCard(c)">{{ t('export') }}</button>
          <button class="danger" @click="deleteCard(c)">{{ t('delete') }}</button>
        </div>
      </article>
      <p v-if="!filteredCards.length" class="muted">{{ data?.cards?.length ? t('characterLibraryNoMatches') : t('noSharedCards') }}</p>
    </div>
    </section>

    <Modal v-if="edit" :title="t('editCharacter')" @close="edit = null">
      <label>{{ t('characterName') }}<input v-model="edit.character_name"></label>
      <PortraitPicker v-model="edit.portrait" :rule-id="ruleId" :seed="edit.user_id" :name="edit.character_name" />
      <label v-for="f in edit.fields" :key="f.key">{{ identityLabel(f) }}<input v-model="edit.identityValues[f.key]"></label>
      <label>{{ t('level') }}<input type="number" v-model.number="edit.level"></label>
      <label>HP / {{ t('maxHp') }}
        <div class="row">
          <input type="number" v-model.number="edit.hp.current" placeholder="HP">
          <input type="number" v-model.number="edit.hp.max" :placeholder="t('maxHp')">
        </div>
      </label>
      <p v-if="autoHp" class="form-hint">{{ t('ruleSuggestedHp') }}: <strong>{{ autoHpValue }}</strong>{{ t('manualHpStillAllowed') }}</p>
      <label>{{ currencyEditableUnitLabel(ruleMeta.currency_system || null, currencyLabel(ruleMeta)) }}<input type="text" inputmode="decimal" v-model="edit.goldText" :step="currencyInputStep(ruleMeta.currency_system || null)"></label>
      <label>{{ t('attributes') }} <span class="attr-points">{{ t('pointsRemaining', { points: attrPoints }) }}</span></label>
      <div class="attr-sliders">
        <div v-for="a in editRuleAttrs" :key="a.key" class="attr-row">
          <span class="attr-name">{{ attrDisplayName(a) }}</span>
          <input type="range" :min="a.min" :max="a.max * 2" v-model.number="edit.attributes[a.key]">
          <input type="number" class="attr-val" :min="a.min" v-model.number="edit.attributes[a.key]">
        </div>
      </div>
      <label>{{ t('skills') }}</label>
      <SkillEditor v-model="edit.skills" :pool="skillPool" :meta="ruleMeta" />
      <label>{{ t('backgroundStory') }}<textarea rows="3" v-model="edit.background"></textarea></label>
      <ItemEditor v-model:equipment="edit.equipment" v-model:inventory="edit.inventory" />
      <label>{{ t('keyItemsLineHelp') }}<textarea rows="3" v-model="edit.keyText"></textarea></label>
      <template #actions>
        <button @click="edit = null">{{ t('cancel') }}</button>
        <button class="primary" :disabled="busy" @click="saveCharacter">{{ t('saveAction') }}</button>
      </template>
    </Modal>

    <LevelUpDialog
      v-if="editLevelUp"
      :rule-attrs="ruleAttrs"
      :rule-meta="ruleMeta"
      :character="editLevelUp.player"
      :level-up-points="editLevelUp.levelUpPoints"
      @submit="saveLevelUp"
      @cancel="editLevelUp = null"
    />

    <Modal v-if="editCard" :title="t('editCharacterCard')" @close="editCard = null">
      <label>{{ t('characterName') }}<input v-model="editCard.character_name"></label>
      <PortraitPicker v-model="editCard.portrait" :rule-id="editCard.rule_id || ruleId" :seed="editCard.card_id" :name="editCard.character_name" />
      <label>{{ t('originIdentity') }}<input v-model="editCard.race"></label>
      <label>{{ t('classRole') }}<input v-model="editCard.class"></label>
      <label>{{ t('skills') }}</label>
      <SkillEditor v-model="editCard.skills" :pool="skillPool" :meta="ruleMeta" />
      <label>{{ t('background') }}<textarea rows="4" v-model="editCard.background"></textarea></label>
      <label>{{ t('initialMoney') }}{{ editableUnitSuffix }}<input type="text" inputmode="decimal" v-model="editCard.goldText" :step="currencyInputStep(ruleMeta.currency_system || null)"></label>
      <template #actions>
        <button @click="editCard = null">{{ t('cancel') }}</button>
        <button class="primary" :disabled="busy" @click="saveCardEdit">{{ t('saveAction') }}</button>
      </template>
    </Modal>

    <RulesetAdvancementHost
      v-if="advancementCard"
      :runtime-id="String(advancementCard.ruleset_runtime?.id || '')"
      :rule-id="String(advancementCard.rule_id || ruleId)"
      :character="advancementCard"
      :card-id="cardId(advancementCard)"
      :revision="Number(advancementCard.ruleset_revision || 0)"
      :language="String(advancementCard.language || locale)"
      @applied="onCardAdvanced"
      @cancel="advancementCard = null"
    />

    <RulesetAdvancementHost
      v-if="advancementPlayer?.character_sheet"
      :runtime-id="String(data?.ruleset_runtime?.id || '')"
      :rule-id="ruleId"
      :character="advancementPlayer.character_sheet"
      :game-key="game"
      :user-id="advancementPlayer.user_id"
      :revision="Number(advancementPlayer.character_sheet.ruleset_revision || 0)"
      :language="String(locale)"
      @applied="onLiveCharacterAdvanced"
      @cancel="advancementPlayer = null"
    />

    <Modal v-if="professionalEdit" dialog-class="professional-character-dialog" :title="String(locale).startsWith('zh') ? '高级角色中心' : 'Advanced character center'" @close="professionalEdit = null">
      <RulesetCharacterCenterHost
        :runtime-id="professionalEdit.runtimeId"
        :character="professionalEdit.character"
        :target="professionalEdit.target"
        :rule-id="professionalEdit.ruleId"
        :language="String(locale)"
        :game-key="professionalEdit.gameKey"
        :user-id="professionalEdit.userId"
        :card-id="professionalEdit.cardId"
        @saved="onProfessionalSaved"
        @cancel="professionalEdit = null"
      />
    </Modal>

    <Modal v-if="editNpcPortrait" :title="`${editNpcPortrait.name} · ${t('characterAvatar')}`" @close="editNpcPortrait = null">
      <PortraitPicker v-model="editNpcPortrait.portrait" :rule-id="ruleId" :seed="editNpcPortrait.npcId" :name="editNpcPortrait.name" />
      <template #actions>
        <button @click="editNpcPortrait = null">{{ t('cancel') }}</button>
        <button class="primary" :disabled="busy" @click="saveNpcPortrait">{{ t('saveAction') }}</button>
      </template>
    </Modal>

    <RulesetExperienceHost
      v-if="showWizard && isSelectedProfessionalRule()"
      :rule-id="ruleId"
      :language="String(locale)"
      @submit="onWizardSubmit"
      @cancel="showWizard = false"
    />
    <CharacterWizard
      v-else-if="showWizard"
      :rule-meta="ruleMeta"
      :rule-attrs="ruleAttrs"
      :attr-total="ruleAttrsTotal"
      :skill-pool="skillPool"
      :rule-id="ruleId"
      :language="String(locale)"
      @submit="onWizardSubmit"
      @cancel="showWizard = false"
    />
  </section>
</template>

<style scoped>
/* Character archive: featured current sheets, NPC rail, dense reusable library.
   页宽约束原是 5 个页面共享的一条规则，拆分后每个组件各自持有自己那一份
   （见 RulesView.vue / MemoryView.vue / LorebookView.vue / LogsView.vue）。 */
.characters-page {
  width: min(1540px, 100%);
}

.character-section {
  display: grid;
  gap: 11px;
  margin-top: 18px;
}

.character-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 34px;
  padding: 0 3px 7px;
  border-bottom: 1px solid var(--df-border-soft);
}

.character-section-head h2,
.character-section-head > div > h2 {
  margin: 0;
  font-size: 18px;
}

.character-section-head > span,
.character-section-head > div > span {
  min-width: 26px;
  padding: 2px 7px;
  border: 1px solid var(--df-border-soft);
  border-radius: 999px;
  color: var(--df-accent-strong);
  background: var(--df-control-bg);
  font-size: 11px;
  text-align: center;
}

.current-character-grid {
  display: grid;
  gap: 12px;
}

.current-character-card {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: stretch;
  gap: 12px;
  min-height: 142px;
  padding: 15px 20px;
  overflow: hidden;
  border-color: color-mix(in srgb, var(--df-accent) 38%, var(--df-border-soft));
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--df-accent) 8%, transparent), transparent 46%),
    radial-gradient(circle at 73% 30%, color-mix(in srgb, var(--df-interactive) 7%, transparent), transparent 34%),
    var(--df-surface-1);
}

.current-character-card::after {
  position: absolute;
  right: 23%;
  width: 310px;
  height: 310px;
  border: 1px solid var(--df-border-soft);
  border-radius: 50%;
  content: "";
  opacity: .12;
  transform: translateY(-22%);
  box-shadow: inset 0 0 0 24px transparent, inset 0 0 0 25px var(--df-border-soft);
}

.current-character-card > * {
  position: relative;
  z-index: 1;
}

.current-character-identity {
  display: flex;
  align-items: center;
  gap: 20px;
  min-width: 0;
}

.current-character-card .portrait-edit-button {
  min-width: 96px;
  min-height: 96px;
}

.current-character-card .portrait-image {
  border-color: color-mix(in srgb, var(--df-accent) 55%, var(--df-border-soft));
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--df-canvas) 68%, transparent), 0 12px 30px rgba(0, 0, 0, .32);
}

.current-character-copy {
  display: grid;
  gap: 9px;
  min-width: 0;
}

.character-name-line {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.character-name-line h2 {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  font-size: 24px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.character-name-line .badge {
  flex: 0 0 auto;
}

.character-identity-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.character-identity-chips > span {
  padding: 3px 8px;
  border: 1px solid var(--df-border-soft);
  border-radius: 4px;
  color: var(--df-text-muted);
  background: color-mix(in srgb, var(--df-control-bg) 76%, transparent);
  font-size: 11px;
}

.character-resource-line {
  display: grid;
  grid-template-columns: 28px minmax(110px, 260px) auto;
  align-items: center;
  gap: 9px;
  color: var(--df-danger-strong);
  font-size: 11px;
}

.character-resource-track {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--df-danger) 13%, var(--df-control-bg));
}

.character-resource-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--df-danger), var(--df-danger-strong));
  box-shadow: 0 0 10px color-mix(in srgb, var(--df-danger-strong) 40%, transparent);
}

.character-resource-line strong {
  color: var(--df-text-secondary);
  font-family: var(--df-font-mono);
  font-size: 11px;
}

.character-level-notice {
  margin: 0;
  font-size: 11px;
}

.current-character-actions {
  display: grid !important;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  width: min(100%, 560px);
  min-width: 0;
  justify-self: end;
  gap: 6px;
}

.current-character-actions button {
  min-width: 0;
  min-height: 38px;
  height: auto;
  padding: 7px 9px;
  white-space: normal;
  overflow-wrap: anywhere;
  line-height: 1.25;
  text-align: center;
}

.npc-strip {
  display: grid;
  grid-auto-columns: minmax(230px, 1fr);
  grid-auto-flow: column;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 5px;
  scroll-snap-type: x proximity;
}

.npc-mini-card {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 92px;
  padding: 12px;
  scroll-snap-align: start;
  background:
    radial-gradient(circle at 0 50%, color-mix(in srgb, var(--df-accent) 8%, transparent), transparent 48%),
    var(--df-surface-1);
}

.npc-mini-card h2 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 5px;
  font-size: 15px;
}

.npc-mini-card p {
  max-width: 210px;
  margin: 0;
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shared-character-head > div:first-child {
  display: flex;
  align-items: center;
  gap: 8px;
}

.character-library-grid {
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 11px;
}

.library-character-card {
  min-height: 156px;
  padding: 13px;
  background: linear-gradient(145deg, var(--df-surface-2), var(--df-surface-1));
}

/* 职业卡（5E 2024 等）比普通卡多「职业升级/高级角色中心」按钮，动作区会折行；
   把动作区钉在卡片底部，折行向上生长，各卡的按钮行保持同一底边。 */
.library-character-card .actions {
  margin-top: auto;
}

.characters-page .library-character-card .actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.characters-page .library-character-card .actions button {
  flex: 1 1 120px;
  min-width: 0;
  height: auto;
  min-height: 36px;
  white-space: normal;
  overflow-wrap: anywhere;
  line-height: 1.25;
  text-align: center;
}

@media (max-width: 520px) {
  .current-character-actions {
    grid-template-columns: minmax(0, 1fr);
    width: 100%;
  }
}

.library-character-card .character-card-summary {
  align-items: flex-start;
}

.library-character-card h2 {
  margin: 1px 0 5px;
  font-size: 16px;
}

.library-character-card .card-bg {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

@media (max-width: 800px) {
  .current-character-card {
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }

  .shared-character-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .shared-character-head .actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: 100%;
  }
}

@media (max-width: 520px) {
  .current-character-card { padding: 14px; }
  .current-character-identity { align-items: flex-start; gap: 13px; }
  .current-character-card .portrait-edit-button { min-width: 76px; min-height: 76px; }
  .current-character-card .portrait-image { width: 76px !important; height: 76px !important; }
  .character-name-line { align-items: flex-start; flex-direction: column; gap: 4px; }
  .character-name-line h2 { font-size: 20px; }
  .character-resource-line { grid-template-columns: 24px minmax(70px, 1fr); }
  .character-resource-line strong { grid-column: 2; }
  .current-character-actions { grid-template-columns: minmax(0, 1fr); }
  .character-library-grid { grid-template-columns: minmax(0, 1fr); }
}

.characters-page .npc-mini-card {
  flex-direction: row;
}

.characters-page .npc-mini-card h2,
.characters-page .current-character-card h2 {
  min-height: 0;
}

/* --- moved from styles/v2/roster.css --- */
/* Character roster: campaign hero, horizontal NPC rail, searchable library. */
.characters-page .archive-hero {
  margin-bottom: 14px;
}

.characters-page .character-section {
  margin-top: 11px;
  padding: 0;
  overflow: visible;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.characters-page .character-section-head {
  min-height: 46px;
  padding: 10px 3px;
  border-bottom: 1px solid var(--df-border-soft);
  background: transparent;
}

.characters-page .current-character-grid {
  grid-template-columns: repeat(auto-fit, minmax(430px, 1fr));
  gap: 12px;
  padding: 0;
}

.characters-page .current-character-card {
  min-height: 132px;
  gap: 14px;
  padding: 14px;
  border-radius: var(--df-radius-md);
  background:
    radial-gradient(circle at 0 50%, color-mix(in srgb, var(--df-interactive) 8%, transparent), transparent 48%),
    linear-gradient(145deg, var(--df-surface-2), var(--df-surface-1));
}

.characters-page .current-character-card::after {
  display: none;
}

.characters-page .current-character-card .portrait-image {
  width: 78px !important;
  height: 92px !important;
  border-radius: 7px;
}

.characters-page .current-character-card .portrait-edit-button {
  min-width: 78px;
  min-height: 92px;
}

.characters-page .current-character-actions {
  align-content: center;
  grid-template-columns: repeat(3, minmax(86px, 1fr));
  min-width: 0;
  gap: 6px;
}

.characters-page .current-character-actions:has(> button:nth-child(4)) {
  grid-template-columns: repeat(2, minmax(96px, 1fr));
  min-width: 0;
}

@media (min-width: 801px) {
  .characters-page .current-character-card:only-child {
    grid-template-columns: minmax(0, 1fr) minmax(360px, auto);
    align-items: center;
  }

  .characters-page .current-character-card:only-child .current-character-actions {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    width: min(100%, 520px);
  }

  .characters-page .current-character-card:only-child .current-character-actions:has(> button:nth-child(4)) {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.characters-page .npc-strip {
  padding: 11px 13px 14px;
}

.characters-page .npc-mini-card {
  min-width: 215px;
  border: 1px solid var(--df-border-soft);
  border-radius: var(--df-radius-md);
}

.character-library-toolbar {
  display: grid;
  grid-template-columns: minmax(210px, 1fr) 160px auto minmax(280px, auto);
  gap: 8px;
  margin-top: 12px;
  padding: 10px;
  border: 1px solid var(--df-border-soft);
  border-radius: var(--df-radius-md);
  background: color-mix(in srgb, var(--df-surface-2) 62%, transparent);
}

.character-view-switch {
  display: flex;
  gap: 4px;
}

.character-view-switch button {
  width: 39px;
  padding: 0;
  font-size: 18px;
}

.character-view-switch button.active {
  border-color: var(--df-interactive);
  color: var(--df-interactive-strong);
  background: var(--df-hover);
}

.character-import-actions {
  justify-content: flex-end;
}

.characters-page .character-library-grid {
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 14px;
  padding: 14px 0 0;
}

.characters-page .library-character-card {
  position: relative;
  display: flex;
  min-height: 304px;
  flex-direction: column;
  gap: 12px;
  padding: 11px;
}

.characters-page .library-character-card .character-card-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 10px;
}

.characters-page .library-character-card .portrait-image {
  width: 100% !important;
  height: 132px !important;
  border-radius: 7px;
}

.characters-page .library-character-card .portrait-edit-button {
  width: 100%;
  min-width: 0;
  min-height: 132px;
}

.characters-page .library-character-card .card-select {
  position: absolute;
  z-index: 2;
  top: 19px;
  right: 19px;
  width: 17px;
  height: 17px;
  margin: 0;
  border-radius: 4px;
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--df-canvas) 58%, transparent);
}

.characters-page .library-character-card .actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-top: auto;
}

.characters-page .library-character-card .actions button {
  min-width: 0;
  padding-inline: 5px;
  font-size: 10px;
}

.characters-page .character-library-grid.view-list {
  grid-template-columns: minmax(0, 1fr);
}

.characters-page .view-list .library-character-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  min-height: 104px;
}

.characters-page .view-list .library-character-card .actions {
  align-self: center;
  margin: 0;
}

/* 移动端底栏遮挡：拆分自 light.css 的跨页共享规则（原是 5 个页面组合选择器）。 */
@media (max-width: 800px) {
  .characters-page {
    padding-bottom: calc(92px + env(safe-area-inset-bottom));
  }
}

/* 拆分自 play-cinematic.css 的 characters-page 响应式覆盖。
   注意：选择器必须保留 .characters-page 前缀原样——Vue scoped 编译只给复合选择器
   最后一节加 data-v 属性，简化前缀会意外降低特异性，导致覆盖不了 roster.css 那份基础规则。 */
@media (max-width: 800px) {
  .characters-page .current-character-card {
    background:
      radial-gradient(circle at 0 50%, color-mix(in srgb, var(--df-interactive) 8%, transparent), transparent 48%),
      linear-gradient(145deg, var(--df-surface-2), var(--df-surface-1));
  }

  .characters-page .character-library-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .characters-page .character-library-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    padding: 12px 0 0;
  }

  .characters-page .library-character-card {
    min-height: 278px;
    padding: 9px;
  }

  .characters-page .library-character-card .character-card-summary {
    grid-template-columns: minmax(0, 1fr);
  }

  .characters-page .library-character-card .portrait-edit-button {
    grid-column: auto;
  }

  .characters-page .library-character-card .portrait-image {
    width: 100% !important;
    height: 108px !important;
  }

  .characters-page .library-character-card .actions { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

/* 拆分自 play-panels.css 的 characters-page 响应式覆盖。 */
@media (max-width: 800px) {
  .characters-page {
    width: 100%;
    max-width: 100%;
    overflow-x: clip;
  }

  .characters-page .current-character-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .characters-page .current-character-card {
    grid-template-columns: minmax(0, 1fr);
    min-width: 0;
  }

  .characters-page .current-character-identity {
    width: 100%;
    min-width: 0;
  }

  .characters-page .current-character-actions,
  .characters-page .current-character-actions:has(> button:nth-child(4)) {
    width: 100%;
    min-width: 0;
  }

  .characters-page .current-character-actions {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .characters-page .current-character-actions:has(> button:nth-child(4)) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .characters-page .character-library-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .characters-page .current-character-identity {
    display: grid;
    grid-template-columns: 76px minmax(0, 1fr);
    align-items: start;
  }
}
</style>

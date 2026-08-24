<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { api, errorMessage } from '@/api/client'
import type { CharacterPortrait, CharacterSheet, JsonObject } from '@/api/types'
import PortraitPicker from '@/components/admin/PortraitPicker.vue'
import { resolveLiveCharacterRest } from '@/features/rulesets/dnd2024/api'

const props = withDefaults(defineProps<{
  character: CharacterSheet
  target: 'game' | 'card'
  ruleId: string
  language?: string
  gameKey?: string
  userId?: string
  cardId?: string
}>(), { language: 'zh-CN', gameKey: '', userId: '', cardId: '' })
const emit = defineEmits<{
  saved: [character: CharacterSheet, reason?: 'profile' | 'rest']
  cancel: []
}>()

type Tab = 'overview' | 'profile' | 'build' | 'magic'
const activeTab = ref<Tab>('overview')
const busy = ref(false)
const failure = ref('')
const zh = computed(() => !props.language.toLowerCase().startsWith('en'))
const text = (cn: string, en: string) => zh.value ? cn : en
const canonical = computed<JsonObject>(() => {
  const value = props.character.ruleset_character
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as JsonObject
    : {}
})
const identity = computed(() => (canonical.value.identity as JsonObject | undefined) || {})
const build = computed(() => (canonical.value.build as JsonObject | undefined) || {})
const abilities = computed(() => (canonical.value.abilities as JsonObject | undefined) || {})
const resources = computed(() => (canonical.value.resources as JsonObject | undefined) || {})
const derived = computed(() => (canonical.value.derived as JsonObject | undefined) || {})
const spellcasting = computed(() => (canonical.value.spellcasting as JsonObject | undefined) || {})
const classMagic = computed(() => (spellcasting.value.class as JsonObject | undefined) || {})
const progression = computed(() => (canonical.value.progression as JsonObject | undefined) || {})
const classLevels = computed(() => (build.value.class_levels as JsonObject[] | undefined) || [])
const hp = computed(() => Number(resources.value.hp || props.character.hp || 0))
const maxHp = computed(() => Number(resources.value.max_hp || props.character.max_hp || 0))
const restType = ref<'short' | 'long'>('short')
const restConfirmed = ref(false)
const restHitDice = reactive<Record<string, number>>({})
const hitDiceRows = computed(() => Object.entries(
  (resources.value.hit_dice as Record<string, number> | undefined) || {},
).map(([die, available]) => ({ die, available: Number(available || 0) })))

const form = reactive<{
  character_name: string
  portrait: CharacterPortrait | null
  profile: Record<string, string>
}>({
  character_name: '',
  portrait: null,
  profile: {},
})

watch(
  () => props.character,
  character => {
    const nested = character.ruleset_character as JsonObject | undefined
    const nestedIdentity = (nested?.identity as JsonObject | undefined) || {}
    const profile = (nested?.profile as JsonObject | undefined) || {}
    form.character_name = String(nestedIdentity.name || character.character_name || '')
    form.portrait = character.portrait?.kind ? { ...character.portrait } : null
    form.profile = Object.fromEntries(
      ['pronouns', 'appearance', 'personality', 'backstory', 'ideals', 'bonds', 'flaws', 'notes']
        .map(key => [key, String(profile[key] || '')]),
    )
  },
  { immediate: true, deep: true },
)

const abilityLabels: Record<string, [string, string]> = {
  str: ['力量', 'Strength'], dex: ['敏捷', 'Dexterity'], con: ['体质', 'Constitution'],
  int: ['智力', 'Intelligence'], wis: ['感知', 'Wisdom'], cha: ['魅力', 'Charisma'],
}
const alignmentLabels: Record<string, [string, string]> = {
  lawful_good: ['守序善良', 'Lawful Good'], neutral_good: ['中立善良', 'Neutral Good'],
  chaotic_good: ['混乱善良', 'Chaotic Good'], lawful_neutral: ['守序中立', 'Lawful Neutral'],
  true_neutral: ['绝对中立', 'True Neutral'], neutral: ['中立', 'Neutral'],
  chaotic_neutral: ['混乱中立', 'Chaotic Neutral'], lawful_evil: ['守序邪恶', 'Lawful Evil'],
  neutral_evil: ['中立邪恶', 'Neutral Evil'], chaotic_evil: ['混乱邪恶', 'Chaotic Evil'],
}
function refName(value: unknown): string {
  return String(value || '').split(':').at(-1)?.replaceAll('_', ' ') || '—'
}
function alignmentName(value: unknown): string {
  const key = String(value || '')
  const label = alignmentLabels[key]
  return label ? (zh.value ? `${label[0]}（${label[1]}）` : label[1]) : refName(value)
}
function abilityName(key: string): string {
  const label = abilityLabels[key]
  return label ? (zh.value ? `${label[0]}（${key.toUpperCase()}）` : label[1]) : key.toUpperCase()
}
function modifier(score: unknown): string {
  const value = Math.floor((Number(score || 10) - 10) / 2)
  return value >= 0 ? `+${value}` : String(value)
}
function spellRefs(key: string): string[] {
  return ((classMagic.value[key] as string[] | undefined) || []).map(refName)
}

async function save(): Promise<void> {
  busy.value = true
  failure.value = ''
  try {
    const path = props.target === 'card'
      ? `/character-cards/${encodeURIComponent(props.cardId)}/profile`
      : `/games/${encodeURIComponent(props.gameKey)}/character/${encodeURIComponent(props.userId)}/profile`
    const response = await api<{ ok: boolean; character?: CharacterSheet; card?: CharacterSheet; error?: string }>(path, {
      method: 'PATCH',
      body: JSON.stringify({
        character_name: form.character_name,
        portrait: form.portrait,
        profile: form.profile,
      }),
    })
    if (!response.ok) throw new Error(response.error || text('保存失败', 'Save failed'))
    emit('saved', response.character || response.card || props.character, 'profile')
  } catch (cause: unknown) {
    failure.value = errorMessage(cause)
  } finally { busy.value = false }
}

function operationId(prefix: string): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

async function completeRest(): Promise<void> {
  if (props.target !== 'game' || !props.gameKey || !props.userId || !restConfirmed.value) return
  busy.value = true
  failure.value = ''
  try {
    const spend = Object.fromEntries(
      hitDiceRows.value.map(({ die, available }) => [
        die,
        Math.max(0, Math.min(available, Number(restHitDice[die] || 0))),
      ]),
    )
    const response = await resolveLiveCharacterRest(
      props.gameKey,
      props.userId,
      restType.value,
      spend,
      Number(props.character.ruleset_revision || 0),
      operationId('rest'),
    )
    emit('saved', response.character as CharacterSheet, 'rest')
  } catch (cause: unknown) {
    failure.value = errorMessage(cause)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="professional-character-center">
    <header class="center-hero">
      <div>
        <span>5E · 2024 · SRD</span>
        <h2>{{ form.character_name || text('未命名冒险者', 'Unnamed adventurer') }}</h2>
        <p>{{ text('这里把“人物资料”和“规则数据”分开：你可以放心写人物，职业、属性和法术不会被误改。', 'Profile writing is separated from rules data, so your build, abilities, and spells cannot be overwritten by accident.') }}</p>
      </div>
    </header>

    <nav class="center-tabs" :aria-label="text('角色资料分类', 'Character sections')">
      <button :class="{ active: activeTab === 'overview' }" @click="activeTab = 'overview'">{{ text('一眼看懂', 'Overview') }}</button>
      <button :class="{ active: activeTab === 'profile' }" @click="activeTab = 'profile'">{{ text('人物资料', 'Profile') }}</button>
      <button :class="{ active: activeTab === 'build' }" @click="activeTab = 'build'">{{ text('构筑与成长', 'Build & growth') }}</button>
      <button :class="{ active: activeTab === 'magic' }" @click="activeTab = 'magic'">{{ text('法术与资源', 'Magic & resources') }}</button>
    </nav>

    <div v-if="activeTab === 'overview'" class="center-panel overview-panel">
      <div class="vital-grid">
        <article><small>{{ text('等级', 'Level') }}</small><strong>{{ build.level || props.character.level || 1 }}</strong><span>{{ refName(classLevels[0]?.class_ref || props.character.class) }}</span></article>
        <article><small>{{ text('生命值', 'Hit Points') }}</small><strong>{{ hp }}/{{ maxHp }}</strong><span>{{ text('归零会陷入濒死', 'At zero, you begin dying') }}</span></article>
        <article><small>{{ text('护甲等级', 'Armor Class') }}</small><strong>{{ derived.armor_class || '—' }}</strong><span>{{ text('敌人通常要达到此数值才能命中', 'Enemies usually need this result to hit') }}</span></article>
        <article><small>{{ text('熟练加值', 'Proficiency') }}</small><strong>+{{ derived.proficiency_bonus || 0 }}</strong><span>{{ text('你擅长的检定会加上它', 'Added to things you are trained in') }}</span></article>
      </div>
      <div class="newbie-callout">
        <b>{{ text('第一次玩，先记住三件事', 'First game? Remember three things') }}</b>
        <ol>
          <li>{{ text('描述你想做什么，不必先背规则。', 'Describe what you want to do; you do not need to know the rule first.') }}</li>
          <li>{{ text('需要掷骰时，界面会告诉你用哪个数值。', 'When a roll is needed, the interface tells you which number to use.') }}</li>
          <li>{{ text('职业升级、战斗资源等规则数据请使用专门按钮，不在人物资料里手填。', 'Use dedicated actions for advancement and combat resources instead of typing over rule data.') }}</li>
        </ol>
      </div>
      <div class="ability-grid">
        <article v-for="(score, key) in abilities" :key="String(key)">
          <small>{{ abilityName(String(key)) }}</small><strong>{{ score }}</strong><span>{{ modifier(score) }}</span>
        </article>
      </div>
    </div>

    <form v-else-if="activeTab === 'profile'" class="center-panel profile-panel" @submit.prevent="save">
      <p class="safe-edit-note">{{ text('以下都是叙事资料，可随时修改；不会重算属性、装备、生命值或法术。', 'Everything here is narrative profile data and never recalculates abilities, equipment, HP, or spells.') }}</p>
      <label>{{ text('角色名', 'Character name') }}<input v-model="form.character_name" maxlength="120" required></label>
      <PortraitPicker v-model="form.portrait" :rule-id="ruleId" :seed="cardId || userId || form.character_name" :name="form.character_name" />
      <div class="profile-grid">
        <label>{{ text('称谓 / 代词', 'Pronouns') }}<input v-model="form.profile.pronouns" :placeholder="text('例如：她 / he / they', 'For example: she / he / they')"></label>
        <label>{{ text('外貌特征', 'Appearance') }}<textarea v-model="form.profile.appearance" rows="3" :placeholder="text('别人第一眼会注意到什么？', 'What do people notice first?')"></textarea></label>
        <label>{{ text('性格与习惯', 'Personality') }}<textarea v-model="form.profile.personality" rows="3" :placeholder="text('紧张时、开心时会怎么做？', 'How do they act when nervous or happy?')"></textarea></label>
        <label>{{ text('人物经历', 'Backstory') }}<textarea v-model="form.profile.backstory" rows="5" :placeholder="text('从哪里来？为什么踏上冒险？', 'Where did they come from, and why do they adventure?')"></textarea></label>
        <label>{{ text('理想', 'Ideals') }}<textarea v-model="form.profile.ideals" rows="2" :placeholder="text('最相信什么？', 'What do they believe in most?')"></textarea></label>
        <label>{{ text('牵绊', 'Bonds') }}<textarea v-model="form.profile.bonds" rows="2" :placeholder="text('最在意的人、地点或承诺', 'A person, place, or promise that matters')"></textarea></label>
        <label>{{ text('弱点', 'Flaws') }}<textarea v-model="form.profile.flaws" rows="2" :placeholder="text('什么会让他做出不理智的选择？', 'What leads them into bad decisions?')"></textarea></label>
        <label>{{ text('仅供自己记录', 'Personal notes') }}<textarea v-model="form.profile.notes" rows="2"></textarea></label>
      </div>
    </form>

    <div v-else-if="activeTab === 'build'" class="center-panel read-only-panel">
      <p class="locked-note">{{ text('这些字段共同决定角色规则能力。为避免角色失效，此处只读；升级请使用“职业升级”。', 'These fields determine the legal build and are read-only here. Use Class advancement to level up safely.') }}</p>
      <dl>
        <div><dt>{{ text('物种', 'Species') }}</dt><dd>{{ refName(identity.species_ref) }}</dd></div>
        <div><dt>{{ text('背景', 'Background') }}</dt><dd>{{ refName(identity.background_ref) }}</dd></div>
        <div><dt>{{ text('阵营', 'Alignment') }}</dt><dd>{{ alignmentName(identity.alignment) }}</dd></div>
        <div><dt>{{ text('体型', 'Size') }}</dt><dd>{{ refName(identity.size) }}</dd></div>
        <div><dt>{{ text('职业', 'Class') }}</dt><dd>{{ classLevels.map(row => `${refName(row.class_ref)} Lv.${row.level}`).join(' / ') || '—' }}</dd></div>
        <div><dt>{{ text('升级方式', 'Progression') }}</dt><dd>{{ refName(progression.mode) }}</dd></div>
      </dl>
      <h3>{{ text('熟练项', 'Proficiencies') }}</h3>
      <div class="tag-list"><span v-for="skill in ((canonical.proficiencies as JsonObject)?.skill_refs as string[]) || []" :key="skill">{{ refName(skill) }}</span></div>
      <h3>{{ text('规则来源', 'Rules source') }}</h3>
      <code>{{ (canonical.rule_binding as JsonObject)?.content_version || '—' }}</code>
    </div>

    <div v-else class="center-panel read-only-panel">
      <p class="locked-note">{{ text('法术位和职业资源会在战斗、休息与升级时由规则引擎更新，不需要手工计算。', 'Spell slots and class resources are updated by combat, rest, and advancement rules.') }}</p>
      <dl>
        <div><dt>{{ text('施法关键属性', 'Spellcasting ability') }}</dt><dd>{{ abilityName(String(classMagic.ability || '')) }}</dd></div>
        <div><dt>{{ text('法术攻击', 'Spell attack') }}</dt><dd>+{{ derived.spell_attack_bonus || 0 }}</dd></div>
        <div><dt>{{ text('法术豁免 DC', 'Spell save DC') }}</dt><dd>{{ derived.spell_save_dc || '—' }}</dd></div>
        <div><dt>{{ text('法术位（当前 / 上限）', 'Spell slots (current / max)') }}</dt><dd>{{ JSON.stringify(classMagic.slots_current || {}) }} / {{ JSON.stringify(classMagic.slots_max || {}) }}</dd></div>
      </dl>
      <h3>{{ text('戏法', 'Cantrips') }}</h3><div class="tag-list"><span v-for="spell in spellRefs('cantrip_refs')" :key="spell">{{ spell }}</span><i v-if="!spellRefs('cantrip_refs').length">{{ text('此职业当前没有职业戏法', 'No class cantrips at this level') }}</i></div>
      <h3>{{ text('已准备法术', 'Prepared spells') }}</h3><div class="tag-list"><span v-for="spell in spellRefs('prepared_spell_refs')" :key="spell">{{ spell }}</span><i v-if="!spellRefs('prepared_spell_refs').length">{{ text('此职业当前没有准备法术', 'No prepared spells at this level') }}</i></div>
      <section v-if="target === 'game'" class="rest-center">
        <div><h3>{{ text('需要恢复？在这里完成休息', 'Need to recover? Complete a rest here') }}</h3><p>{{ text('你只选择休息类型和要花几颗生命骰；实际骰点、生命值、法术位和职业资源都由服务端计算。', 'Choose the rest type and how many Hit Dice to spend. The server rolls and updates HP, spell slots, and class resources.') }}</p></div>
        <div class="rest-types">
          <label><input v-model="restType" type="radio" value="short"> <span><b>{{ text('短休', 'Short Rest') }}</b><small>{{ text('花生命骰回血，并恢复部分职业资源', 'Spend Hit Dice and recover some class resources') }}</small></span></label>
          <label><input v-model="restType" type="radio" value="long"> <span><b>{{ text('长休', 'Long Rest') }}</b><small>{{ text('回满生命值、生命骰、法术位与大部分资源', 'Restore HP, Hit Dice, spell slots, and most resources') }}</small></span></label>
        </div>
        <div v-if="restType === 'short' && hitDiceRows.length" class="hit-dice-grid">
          <label v-for="row in hitDiceRows" :key="row.die"><span>{{ row.die }} · {{ text(`可用 ${row.available}`, `${row.available} available`) }}</span><input v-model.number="restHitDice[row.die]" type="number" min="0" :max="row.available"></label>
        </div>
        <p v-if="restType === 'short'" class="server-roll-note">{{ text('不用自己填骰点：DiceFrame 会在服务端掷生命骰，刷新或重试也不会重复结算。', 'Do not enter roll results: DiceFrame rolls on the server, and retries cannot apply the rest twice.') }}</p>
        <label class="rest-confirm"><input v-model="restConfirmed" type="checkbox"> {{ text('我确认游戏内时间会随本次休息推进', 'I understand that in-game time advances during this rest') }}</label>
        <button type="button" class="primary" :disabled="busy || !restConfirmed" @click="completeRest">{{ busy ? text('结算中…', 'Resolving…') : text('确认并结算休息', 'Confirm and resolve rest') }}</button>
      </section>
    </div>

    <p v-if="failure" class="center-error" role="alert">{{ failure }}</p>
    <footer>
      <button type="button" @click="emit('cancel')">{{ text('关闭', 'Close') }}</button>
      <button v-if="activeTab === 'profile'" type="button" class="primary" :disabled="busy || !form.character_name.trim()" @click="save">{{ busy ? text('保存中…', 'Saving…') : text('保存人物资料', 'Save profile') }}</button>
    </footer>
  </section>
</template>

<style scoped>
.professional-character-center { display: grid; gap: 16px; width: 100%; min-width: 0; min-height: 0; overflow-x: hidden; overflow-y: auto; color: var(--text-primary, #edf3fa); }
.center-hero { display: flex; justify-content: space-between; gap: 18px; padding: 4px 2px; }
.center-hero span { color: #d8a94e; font-size: 12px; letter-spacing: .14em; }
.center-hero h2 { margin: 4px 0; font: 700 30px/1.15 Georgia, serif; }
.center-hero p { max-width: 720px; margin: 0; color: var(--text-muted, #aeb9c7); }
.center-hero > button { align-self: start; width: 44px; min-width: 44px; border-radius: 50%; font-size: 22px; }
.center-tabs { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; position: sticky; top: 0; z-index: 2; padding: 6px; border-radius: 14px; background: color-mix(in srgb, var(--card-bg, #151c27) 92%, transparent); backdrop-filter: blur(12px); }
.center-tabs button.active { border-color: #d8a94e; background: rgb(216 169 78 / 16%); color: #f3d89c; }
.center-panel { display: grid; gap: 16px; min-height: 320px; }
.vital-grid, .ability-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.vital-grid article, .ability-grid article { display: grid; gap: 4px; padding: 14px; border: 1px solid var(--border-color, #3d4a5f); border-radius: 14px; background: color-mix(in srgb, var(--card-bg, #151c27) 90%, #d8a94e 4%); }
.vital-grid strong { font-size: 24px; }.ability-grid strong { font-size: 22px; }
.vital-grid small, .ability-grid small, .vital-grid span { color: var(--text-muted, #aeb9c7); }
.ability-grid { grid-template-columns: repeat(6, 1fr); }.ability-grid article { text-align: center; }
.newbie-callout, .safe-edit-note, .locked-note { padding: 14px 16px; border-left: 4px solid #65c9b7; border-radius: 8px; background: rgb(71 176 157 / 11%); }
.newbie-callout ol { margin: 8px 0 0; padding-left: 22px; }.newbie-callout li + li { margin-top: 6px; }
.profile-panel label { display: grid; gap: 6px; }.profile-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }.profile-grid label:nth-child(n+4) { grid-column: 1 / -1; }
.profile-panel input, .profile-panel textarea { width: 100%; }
.read-only-panel dl { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 0; }.read-only-panel dl div { padding: 12px; border: 1px solid var(--border-color, #3d4a5f); border-radius: 10px; }.read-only-panel dt { color: var(--text-muted, #aeb9c7); }.read-only-panel dd { margin: 4px 0 0; font-weight: 700; }
.tag-list { display: flex; flex-wrap: wrap; gap: 8px; }.tag-list span { padding: 5px 9px; border: 1px solid var(--border-color, #3d4a5f); border-radius: 999px; }.tag-list i { color: var(--text-muted, #aeb9c7); }
.rest-center { display: grid; gap: 12px; margin-top: 8px; padding: 16px; border: 1px solid #80693f; border-radius: 14px; background: rgb(205 159 72 / 8%); }.rest-center h3, .rest-center p { margin: 0; }.rest-center p { color: var(--text-muted, #aeb9c7); }.rest-types { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }.rest-types label { display: flex; align-items: flex-start; gap: 9px; padding: 12px; border: 1px solid var(--border-color, #3d4a5f); border-radius: 10px; }.rest-types span { display: grid; gap: 3px; }.rest-types small { color: var(--text-muted, #aeb9c7); }.hit-dice-grid { display: flex; flex-wrap: wrap; gap: 9px; }.hit-dice-grid label { display: grid; gap: 5px; min-width: 150px; }.hit-dice-grid input { width: 100%; }.server-roll-note { font-size: 12px; }.rest-confirm { display: flex; align-items: center; gap: 8px; }.rest-center > button { justify-self: end; }
.center-error { padding: 10px; border-radius: 8px; background: rgb(190 62 62 / 16%); color: #ffb5b5; }.professional-character-center footer { display: flex; justify-content: flex-end; gap: 10px; position: sticky; bottom: 0; padding: 10px 0; background: color-mix(in srgb, var(--card-bg, #151c27) 94%, transparent); }
@media (max-width: 720px) { .professional-character-center { width: 100%; }.center-tabs { grid-template-columns: 1fr 1fr; }.vital-grid { grid-template-columns: 1fr 1fr; }.ability-grid { grid-template-columns: repeat(3, 1fr); }.profile-grid, .read-only-panel dl, .rest-types { grid-template-columns: 1fr; }.profile-grid label:nth-child(n+4) { grid-column: auto; } }
</style>

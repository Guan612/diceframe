<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  fetchRulesetAvailableActions,
  resolveRulesetDecision,
  submitRulesetIntent,
} from '@/features/rulesets/dnd2024/api'
import type {
  JsonObject,
  RulesetCombatSpell,
  RulesetCombatTarget,
  RulesetCombatWeapon,
  RulesetGameplayResponse,
  RulesetPendingDecision,
} from '@/api/types'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{
  gameKey: string
  actorId: string
  isGm: boolean
  refreshKey?: number
}>()
const emit = defineEmits<{
  refresh: []
  navigate: [target: 'campaign']
}>()
const { locale } = useLocale()

const data = ref<RulesetGameplayResponse | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const selectedPresetId = ref('')
const selectedWeaponId = ref('')
const selectedSpellRef = ref('')
const selectedSlot = ref(0)
const selectedTargetId = ref('')
const movementDistance = ref(5)
const staged = ref<JsonObject | null>(null)
const confirmCard = ref<HTMLElement | null>(null)
let pollTimer: number | undefined
let returnFocus: HTMLElement | null = null

const copy = computed(() => locale.value.startsWith('zh') ? {
  title: '专业规则战斗台', authority: '命中、豁免、伤害与资源均由服务器结算',
  loading: '正在同步权威状态…', refresh: '刷新', start: '开始战斗',
  chooseEncounter: '选择遭遇预设', noCombat: '当前没有进行中的战斗。GM 可从已验证预设开场。',
  storyBridge: '剧情继续', storyPurpose: '这不是额外关卡，而是刚才冒险故事中的下一步。', storyAction: '现在启动这场剧情遭遇；开始后，敌方由服务器自动行动，每位玩家只操作自己的角色。',
  guidedEncounter: '剧情指定遭遇', guidedStart: '开始遭遇', waitingForGm: '请等待 GM 启动这场剧情中的遭遇。启动后，这里会显示先攻、目标和可用动作。', guidedOnly: '这场战斗由当前剧情指定，玩家不需要选择其他遭遇。',
  narrativeRequest: '公共剧情已经进入交战态势。请选择符合当前敌情的遭遇预设，启动后切换到权威先攻与行动流程。',
  round: '轮次', current: '当前行动者', position: '位置', hp: '生命值', ac: '护甲等级',
  action: '动作', bonus: '附赠动作', movement: '移动', reaction: '反应',
  attack: '攻击', cast: '施放法术', target: '目标', weapon: '武器', spell: '法术', slot: '法术位',
  move: '移动', feet: '尺', dash: '疾走', dodge: '闪避', disengage: '撤离',
  endTurn: '结束回合', endCombat: '结束战斗', deathSave: '死亡豁免', stabilize: '稳定伤者',
  confirm: '确认并交给服务器结算', cancel: '取消', resolve: '发动反应', decline: '放弃反应',
  legalOnly: '这里只显示当前合法动作；若状态已经变化，服务器会拒绝过期请求并说明原因。',
  waiting: '尚未轮到你的角色。', waitingForTeammate: '等待队友行动', enemyActing: '敌方正在由服务器自动行动…', ended: '战斗已经结束。', conditions: '状态',
  lastResult: '最近结算', none: '无', economy: '本回合资源', available: '可用', spent: '已用',
  inRange: '可用', longRange: '远距攻击（劣势）', tooFar: '距离不足',
  targetDistance: '你与目标相距', autoWeapon: '已优先选择当前距离可用的武器。',
  moveCloser: '当前武器都够不到目标。请先移动靠近，或改用射程更远的武器。',
  tacticalTrack: '战术距离带', chooseDestination: '每格 5 尺；轮到你时可点击可达格选择移动距离。',
} : {
  title: 'Professional Combat Console', authority: 'The server resolves rolls, saves, damage, and resources',
  loading: 'Synchronizing authoritative state…', refresh: 'Refresh', start: 'Start Combat',
  chooseEncounter: 'Choose an encounter preset', noCombat: 'No combat is active. The GM can start from a validated preset.',
  storyBridge: 'Continue the story', storyPurpose: 'This is not an extra level; it is the next scene in the adventure you just played.', storyAction: 'Start this story encounter. The server operates enemies automatically, while each player controls only their own character.',
  guidedEncounter: 'Story-selected encounter', guidedStart: 'Start encounter', waitingForGm: 'Wait for the GM to start this story encounter. The combat tool will then show initiative, targets, and legal actions.', guidedOnly: 'This encounter is selected by the current story. Players do not need to choose another preset.',
  narrativeRequest: 'The shared story has entered an engagement. Choose the preset that matches the opposition, then switch to authoritative initiative and actions.',
  round: 'Round', current: 'Current actor', position: 'Position', hp: 'HP', ac: 'Armor Class',
  action: 'Action', bonus: 'Bonus Action', movement: 'Movement', reaction: 'Reaction',
  attack: 'Attack', cast: 'Cast Spell', target: 'Target', weapon: 'Weapon', spell: 'Spell', slot: 'Slot',
  move: 'Move', feet: 'ft', dash: 'Dash', dodge: 'Dodge', disengage: 'Disengage',
  endTurn: 'End Turn', endCombat: 'End Combat', deathSave: 'Death Save', stabilize: 'Stabilize',
  confirm: 'Confirm and let the server resolve', cancel: 'Cancel', resolve: 'Use Reaction', decline: 'Decline',
  legalOnly: 'Only currently legal actions are shown. The server rejects stale requests with a reason.',
  waiting: 'Waiting for your character’s turn.', waitingForTeammate: 'Waiting for teammate', enemyActing: 'The enemy is acting automatically…', ended: 'Combat has ended.', conditions: 'Conditions',
  lastResult: 'Latest Resolution', none: 'None', economy: 'Turn Resources', available: 'Available', spent: 'Spent',
  inRange: 'In range', longRange: 'Long range (disadvantage)', tooFar: 'Out of range',
  targetDistance: 'Distance to target', autoWeapon: 'A weapon usable at this distance is selected first.',
  moveCloser: 'None of your weapons can reach this target. Move closer or use a longer-ranged weapon.',
  tacticalTrack: 'Tactical distance track', chooseDestination: 'Each cell is 5 ft. On your turn, select a reachable cell to set movement.',
})

const gameplay = computed(() => data.value?.gameplay)
const combat = computed(() => gameplay.value?.combat)
const actions = computed(() => data.value?.available_actions || [])
const action = (type: string) => actions.value.find(item => item.type === type)
const currentActor = computed(() => combat.value?.actors.find(
  actor => actor.actor_id === combat.value?.current_actor_id,
))
const selectedPreset = computed(() => gameplay.value?.encounter_presets.find(
  preset => preset.id === selectedPresetId.value,
))
const guidedCombatStep = computed(() => {
  const step = gameplay.value?.campaign?.tutorial?.current_step
  return step?.requires === 'combat_ended' && step.encounter_preset_id ? step : null
})
const guidedCombatPreset = computed(() => guidedCombatStep.value
  ? gameplay.value?.encounter_presets.find(preset => preset.id === guidedCombatStep.value?.encounter_preset_id)
  : undefined)
const narrativeCombatPending = computed(() => gameplay.value?.encounter_request?.status === 'pending')
const attackAction = computed(() => action('attack'))
const spellAction = computed(() => action('cast_spell'))
const moveAction = computed(() => action('move'))
const pendingDecision = computed(() => (
  action('decision.resolve')?.decisions?.[0]
  || combat.value?.pending_decisions?.find(item => item.assigned_to === props.actorId)
))
const selectedWeapon = computed(() => attackAction.value?.weapons?.find(
  item => (item.weapon_ref || item.id) === selectedWeaponId.value,
))
const attackDistance = computed(() => distanceTo(selectedTargetId.value))
const selectedWeaponRange = computed(() => selectedWeapon.value
  ? weaponRangeState(selectedWeapon.value, selectedTargetId.value)
  : null)
const hasUsableWeapon = computed(() => (attackAction.value?.weapons || []).some(
  weapon => weaponRangeState(weapon, selectedTargetId.value).usable,
))
const selectedSpell = computed(() => spellAction.value?.spells?.find(
  item => item.spell_ref === selectedSpellRef.value,
))
const selectedTarget = computed(() => targetsFor(selectedSpell.value).find(
  item => item.actor_id === selectedTargetId.value,
))
const latestEvents = computed(() => {
  const batches = data.value?.result?.resolved_event_batches
  if (Array.isArray(batches)) {
    return batches.flatMap(batch => (
      Array.isArray(batch.events) ? batch.events as JsonObject[] : []
    )).filter(event => event.type !== 'intent.submitted')
  }
  const batch = data.value?.result?.event_batch
  return Array.isArray(batch?.events) ? batch.events as JsonObject[] : []
})
const waitingText = computed(() => {
  const current = String(combat.value?.current_actor_id || '')
  if (!current) return copy.value.waiting
  if (current.startsWith('enemy:')) return copy.value.enemyActing
  if (current === `player:${props.actorId}`) return copy.value.waiting
  return `${copy.value.waitingForTeammate}：${targetName(current)}`
})
const trackMin = computed(() => {
  const positions = combat.value?.actors.map(actor => Number(actor.position || 0)) || [0]
  const movement = Number(moveAction.value?.movement_remaining || 0)
  return Math.floor((Math.min(0, ...positions) - movement) / 5) * 5
})
const trackMax = computed(() => {
  const positions = combat.value?.actors.map(actor => Number(actor.position || 0)) || [0]
  const movement = Number(moveAction.value?.movement_remaining || 0)
  return Math.ceil((Math.max(30, ...positions) + movement) / 5) * 5
})
const trackTicks = computed(() => Array.from(
  { length: Math.max(1, (trackMax.value - trackMin.value) / 5 + 1) },
  (_, index) => trackMin.value + index * 5,
))
const selectedDestination = computed(() => (
  currentActor.value ? Number(currentActor.value.position || 0) + Number(movementDistance.value || 0) : null
))

function canReachPosition(position: number): boolean {
  if (!moveAction.value || !currentActor.value) return false
  const distance = position - Number(currentActor.value.position || 0)
  return distance !== 0 && Math.abs(distance) <= Number(moveAction.value.movement_remaining || 0)
}

function chooseTrackPosition(position: number): void {
  if (!canReachPosition(position) || !currentActor.value) return
  movementDistance.value = position - Number(currentActor.value.position || 0)
}

function tokenTrackStyle(position: number, index: number): Record<string, string> {
  const span = Math.max(5, trackMax.value - trackMin.value)
  return {
    left: `${(Number(position || 0) - trackMin.value) / span * 100}%`,
    top: `${8 + (index % 3) * 30}px`,
  }
}

function localizedTerm(value: unknown): string {
  const key = String(value || '')
  const labels: Record<string, [string, string]> = {
    tutorial: ['教学', 'Tutorial'], standard: ['标准', 'Standard'], challenging: ['挑战', 'Challenging'], lethal: ['致命', 'Lethal'],
    opportunity_attack: ['借机攻击', 'Opportunity Attack'], attack: ['攻击检定', 'Attack'], spell_attack: ['法术攻击检定', 'Spell Attack'],
    saving_throw: ['豁免检定', 'Saving Throw'], death_save: ['死亡豁免', 'Death Save'], medicine: ['医药检定', 'Medicine Check'], concentration: ['专注检定', 'Concentration Check'],
    blessed: ['祝福', 'Blessed'], hexed: ['受诅咒', 'Hexed'], shield_of_faith: ['虔诚护盾', 'Shield of Faith'],
    dodging: ['闪避', 'Dodging'], disengaged: ['已撤离', 'Disengaged'], stable: ['伤势稳定', 'Stable'], unconscious: ['昏迷', 'Unconscious'],
    dead: ['死亡', 'Dead'], defeated: ['已击败', 'Defeated'], death_saves: ['死亡豁免记录', 'Death Saves'],
    slowed_10: ['速度降低 10 尺', 'Speed reduced by 10 ft'], next_attack_advantage: ['下次攻击有优势', 'Next attack has advantage'],
    next_attack_disadvantage: ['下次攻击有劣势', 'Next attack has disadvantage'], faerie_fire: ['妖火标记', 'Faerie Fire'],
  }
  const pair = labels[key]
  return pair ? (locale.value.startsWith('zh') ? pair[0] : pair[1]) : key.replaceAll('_', ' ')
}

function targetName(actorId: string): string {
  return combat.value?.actors.find(actor => actor.actor_id === actorId)?.name || actorId || copy.value.none
}

function distanceTo(targetId: string): number {
  if (!currentActor.value || !targetId) return 0
  const target = combat.value?.actors.find(actor => actor.actor_id === targetId)
    || attackAction.value?.targets?.find(actor => actor.actor_id === targetId)
  return Math.abs(Number(currentActor.value.position || 0) - Number(target?.position || 0))
}

function weaponRangeState(weapon: RulesetCombatWeapon, targetId: string) {
  const distance = distanceTo(targetId)
  const normal = Number(weapon.thrown_range ?? weapon.range ?? 5)
  const maximum = Number(weapon.long_range ?? normal)
  return {
    distance,
    normal,
    maximum,
    usable: distance <= maximum,
    disadvantage: distance > normal && distance <= maximum,
  }
}

function weaponRangeLabel(weapon: RulesetCombatWeapon): string {
  const state = weaponRangeState(weapon, selectedTargetId.value)
  const status = !state.usable ? copy.value.tooFar : state.disadvantage ? copy.value.longRange : copy.value.inRange
  const limit = state.disadvantage ? state.maximum : state.normal
  return `${status}（${state.distance}/${limit} ${copy.value.feet}）`
}

function chooseUsableWeapon(): void {
  const weapons = attackAction.value?.weapons || []
  if (!weapons.length || !selectedTargetId.value) {
    selectedWeaponId.value = weapons[0]?.weapon_ref || weapons[0]?.id || ''
    return
  }
  const current = weapons.find(item => (item.weapon_ref || item.id) === selectedWeaponId.value)
  if (current && weaponRangeState(current, selectedTargetId.value).usable) return
  const best = [...weapons].sort((left, right) => {
    const leftState = weaponRangeState(left, selectedTargetId.value)
    const rightState = weaponRangeState(right, selectedTargetId.value)
    const score = (state: ReturnType<typeof weaponRangeState>) => !state.usable ? 2 : state.disadvantage ? 1 : 0
    return score(leftState) - score(rightState)
  })[0]
  selectedWeaponId.value = best?.weapon_ref || best?.id || ''
}

function friendlyCombatError(cause: unknown): string {
  const message = cause instanceof Error ? cause.message : String(cause)
  if (!locale.value.startsWith('zh')) return message
  const outOfRange = message.match(/target is out of range \((\d+) > (\d+) feet\)/i)
  if (outOfRange) {
    return `目标距离为 ${outOfRange[1]} 尺，这个武器最远只能攻击 ${outOfRange[2]} 尺。请换远程武器，或先移动靠近。`
  }
  if (/not your turn|requested actor is not the current actor/i.test(message)) return '现在还没轮到这个角色。请等待当前行动者结束回合。'
  if (/already been spent|action is not available/i.test(message)) return '这个动作资源本回合已经用掉了。请选择仍可用的动作，或结束回合。'
  if (/state version|stale|expected_version/i.test(message)) return '战斗状态刚刚发生变化，界面已为你刷新。请按最新状态再试一次。'
  return message
}

function targetsFor(spell?: RulesetCombatSpell): RulesetCombatTarget[] {
  const targets = spellAction.value?.targets || attackAction.value?.targets || []
  if (!spell || !currentActor.value) return targets
  const allied = spell.mode === 'healing' || spell.mode === 'buff'
  return targets.filter(target => allied
    ? target.kind === currentActor.value?.kind
    : target.kind !== currentActor.value?.kind)
}

function resetSelections(): void {
  const guidedPresetId = guidedCombatStep.value?.encounter_preset_id
  const preset = guidedCombatPreset.value || gameplay.value?.encounter_presets[0]
  if (guidedPresetId && guidedCombatPreset.value) selectedPresetId.value = guidedPresetId
  else if (!selectedPresetId.value && preset) selectedPresetId.value = preset.id
  const spell = spellAction.value?.spells?.[0]
  selectedSpellRef.value = spell?.spell_ref || ''
  selectedSlot.value = spell?.available_slot_levels?.[0] ?? 0
  const targets = spell ? targetsFor(spell) : attackAction.value?.targets || []
  selectedTargetId.value = targets[0]?.actor_id || ''
  chooseUsableWeapon()
  movementDistance.value = Math.min(5, Number(moveAction.value?.movement_remaining || 5))
}

async function load(silent = false): Promise<void> {
  if (!props.gameKey || (busy.value && silent)) return
  if (!silent) busy.value = true
  try {
    data.value = await fetchRulesetAvailableActions(props.gameKey)
    error.value = ''
    resetSelections()
  } catch (cause: unknown) {
    if (!silent || !data.value) error.value = friendlyCombatError(cause)
  } finally {
    if (!silent) busy.value = false
  }
}

function intentId(): string {
  return globalThis.crypto?.randomUUID?.() || `intent-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function stage(payload: JsonObject): void {
  returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  staged.value = {
    ...payload,
    intent_id: intentId(),
    expected_version: gameplay.value?.state_version ?? 0,
  }
  void nextTick(() => confirmCard.value?.focus())
}

async function submit(payload: JsonObject): Promise<void> {
  busy.value = true
  try {
    data.value = await submitRulesetIntent(props.gameKey, payload)
    staged.value = null
    error.value = ''
    notice.value = latestEvents.value.map(describeEvent).filter(Boolean).join(' · ')
    resetSelections()
    emit('refresh')
    if (payload.type === 'combat.end') emit('navigate', 'campaign')
  } catch (cause: unknown) {
    error.value = friendlyCombatError(cause)
    await load(true)
  } finally { busy.value = false }
}

async function confirmStaged(): Promise<void> {
  if (staged.value) await submit(staged.value)
}

function cancelStaged(): void {
  staged.value = null
  void nextTick(() => returnFocus?.focus())
}

function stageAttack(): void {
  const weapon = selectedWeapon.value
  if (!weapon || !selectedTargetId.value || !attackAction.value) return
  stage({
    type: 'attack', actor_id: attackAction.value.actor_id,
    target_id: selectedTargetId.value,
    ...(weapon.weapon_ref ? { weapon_ref: weapon.weapon_ref } : { attack_id: weapon.id }),
  })
}

function stageSpell(): void {
  const spell = selectedSpell.value
  if (!spell || !selectedTargetId.value || !spellAction.value) return
  stage({
    type: 'cast_spell', actor_id: spellAction.value.actor_id,
    target_id: selectedTargetId.value, spell_ref: spell.spell_ref,
    slot_level: selectedSlot.value,
  })
}

function stageMove(): void {
  if (!moveAction.value || !movementDistance.value) return
  stage({
    type: 'move', actor_id: moveAction.value.actor_id,
    distance: Number(movementDistance.value),
  })
}

function stageSimple(type: string): void {
  const item = action(type)
  if (!item) return
  stage({ type, actor_id: item.actor_id })
}

async function startCombat(): Promise<void> {
  if (!selectedPreset.value) return
  await submit({
    intent_id: intentId(), type: 'combat.start',
    expected_version: gameplay.value?.state_version ?? 0,
    encounter_preset_id: selectedPreset.value.id,
    encounter_instance_id: action('combat.start')?.encounter_instance_id,
    enemies: selectedPreset.value.enemies,
  })
}

async function decide(decision: RulesetPendingDecision, option: string): Promise<void> {
  busy.value = true
  try {
    const payload = {
      type: 'decision.resolve', decision_id: decision.decision_id,
      intent_id: intentId(), expected_version: gameplay.value?.state_version ?? 0, option,
    }
    data.value = await resolveRulesetDecision(props.gameKey, decision.decision_id, payload)
    error.value = ''
    emit('refresh')
  } catch (cause: unknown) {
    error.value = friendlyCombatError(cause)
    await load(true)
  } finally { busy.value = false }
}

function describeEvent(event: JsonObject): string {
  const type = String(event.type || '')
  if (type === 'check.resolved') {
    const success = event.success ? '✓' : '✕'
    return `${success} ${localizedTerm(event.kind)} ${event.total ?? event.natural ?? ''}`
  }
  if (type === 'resource.changed') {
    return `${targetName(String(event.target_id || ''))} HP ${Number(event.delta || 0) > 0 ? '+' : ''}${event.delta}`
  }
  return type.replace(/^dnd2024\./, '')
}

watch(selectedSpellRef, () => {
  const spell = selectedSpell.value
  selectedSlot.value = spell?.available_slot_levels?.[0] ?? 0
  selectedTargetId.value = targetsFor(spell)[0]?.actor_id || ''
})
watch(selectedTargetId, () => chooseUsableWeapon())
watch(() => props.gameKey, () => void load())
watch(() => props.refreshKey, () => void load(true))
onMounted(() => {
  void load()
  pollTimer = window.setInterval(() => {
    if (document.visibilityState !== 'hidden') void load(true)
  }, 5000)
})
onBeforeUnmount(() => { if (pollTimer) window.clearInterval(pollTimer) })
</script>

<template>
  <section class="dnd-combat" aria-labelledby="dnd-combat-title">
    <header class="combat-header">
      <div>
        <p class="eyebrow">5E 2024 SRD · {{ copy.authority }}</p>
        <h2 id="dnd-combat-title">{{ copy.title }}</h2>
      </div>
      <button :disabled="busy" @click="load()">{{ copy.refresh }}</button>
    </header>

    <p v-if="busy && !data" class="combat-state" role="status">{{ copy.loading }}</p>
    <p v-if="error" class="combat-error" role="alert">{{ error }}</p>
    <p class="combat-authority">{{ copy.legalOnly }}</p>

    <template v-if="gameplay">
      <section v-if="combat?.status !== 'active'" class="encounter-start">
        <div v-if="narrativeCombatPending && !guidedCombatStep" class="story-bridge">
          <span class="story-bridge-label">{{ copy.storyBridge }}</span>
          <p>{{ copy.narrativeRequest }}</p>
        </div>
        <template v-if="guidedCombatStep && combat?.status !== 'ended'">
          <div class="story-bridge">
            <span class="story-bridge-label">{{ copy.storyBridge }}</span>
            <h3>{{ guidedCombatStep.title }}</h3>
            <p>{{ guidedCombatStep.narration }}</p>
            <aside><b>{{ copy.storyPurpose }}</b> {{ copy.storyAction }}</aside>
          </div>
        </template>
        <p v-else>{{ combat?.status === 'ended' ? copy.ended : copy.noCombat }}</p>
        <template v-if="isGm && action('combat.start')">
          <div v-if="guidedCombatStep" class="guided-preset">
            <span>{{ copy.guidedEncounter }}</span>
            <strong>{{ guidedCombatPreset?.name || guidedCombatStep.encounter_preset_id }}</strong>
            <p>{{ guidedCombatPreset?.description }}</p>
            <small>{{ copy.guidedOnly }}</small>
          </div>
          <label v-else>
            <span>{{ copy.chooseEncounter }}</span>
            <select v-model="selectedPresetId">
              <option v-for="preset in gameplay.encounter_presets" :key="preset.id" :value="preset.id">
                {{ preset.name }} · {{ localizedTerm(preset.difficulty) }}
              </option>
            </select>
          </label>
          <p v-if="!guidedCombatStep" class="preset-description">{{ selectedPreset?.description }}</p>
          <button class="combat-primary" :disabled="busy || !selectedPreset" @click="startCombat">{{ guidedCombatStep ? copy.guidedStart : copy.start }}</button>
        </template>
        <p v-else-if="(guidedCombatStep || narrativeCombatPending) && combat?.status !== 'ended'" class="combat-state">{{ copy.waitingForGm }}</p>
      </section>

      <template v-else>
        <div class="combat-summary">
          <span><small>{{ copy.round }}</small><strong>{{ combat.round }}</strong></span>
          <span><small>{{ copy.current }}</small><strong>{{ targetName(combat.current_actor_id) }}</strong></span>
          <span><small>{{ copy.movement }}</small><strong>{{ combat.economy.movement ?? 0 }} {{ copy.feet }}</strong></span>
          <span><small>{{ copy.reaction }}</small><strong>{{ combat.economy.reaction ? copy.available : copy.spent }}</strong></span>
        </div>

        <ol class="initiative" :aria-label="copy.current">
          <li
            v-for="actorIdValue in combat.initiative"
            :key="actorIdValue"
            :class="{ current: actorIdValue === combat.current_actor_id }"
            :aria-current="actorIdValue === combat.current_actor_id ? 'step' : undefined"
          >
            {{ targetName(actorIdValue) }}
          </li>
        </ol>

        <section class="tactical-track" :aria-label="copy.tacticalTrack">
          <header><strong>{{ copy.tacticalTrack }}</strong><span>{{ copy.chooseDestination }}</span></header>
          <div class="track-surface">
            <div class="track-cells" :style="{ gridTemplateColumns: `repeat(${trackTicks.length}, minmax(34px, 1fr))` }">
              <button
                v-for="position in trackTicks"
                :key="position"
                type="button"
                :class="{ reachable: canReachPosition(position), selected: selectedDestination === position }"
                :disabled="!canReachPosition(position)"
                :aria-label="`${copy.position} ${position} ${copy.feet}`"
                @click="chooseTrackPosition(position)"
              ><span>{{ position }}</span></button>
            </div>
            <span
              v-for="(actor, index) in combat.actors"
              :key="`track-${actor.actor_id}`"
              :class="['track-token', actor.kind, { current: actor.actor_id === combat.current_actor_id }]"
              :style="tokenTrackStyle(actor.position, index)"
              :title="`${actor.name} · ${actor.position} ${copy.feet}`"
            >{{ actor.name.slice(0, 2) }}</span>
          </div>
        </section>

        <div class="actor-grid">
          <article v-for="actor in combat.actors" :key="actor.actor_id" :class="['actor-card', actor.kind]">
            <header><strong>{{ actor.name }}</strong><span>{{ actor.position }} {{ copy.feet }}</span></header>
            <div
              class="hp-track"
              role="progressbar"
              :aria-label="`${actor.name} ${copy.hp}`"
              aria-valuemin="0"
              :aria-valuemax="actor.max_hp"
              :aria-valuenow="actor.hp"
            ><i :style="{ width: `${Math.max(0, Math.min(100, actor.hp / Math.max(1, actor.max_hp) * 100))}%` }" /></div>
            <p>{{ copy.hp }} {{ actor.hp }}/{{ actor.max_hp }} · {{ copy.ac }} {{ actor.armor_class }}</p>
            <small v-if="Object.keys(actor.conditions || {}).length">
              {{ copy.conditions }}: {{ Object.keys(actor.conditions || {}).map(localizedTerm).join('、') }}
            </small>
          </article>
        </div>

        <section v-if="pendingDecision" class="decision-card" aria-live="assertive">
          <strong>{{ copy.reaction }} · {{ localizedTerm(pendingDecision.kind) }}</strong>
          <div>
            <button class="combat-primary" :disabled="busy" @click="decide(pendingDecision, 'resolve')">{{ copy.resolve }}</button>
            <button :disabled="busy" @click="decide(pendingDecision, 'decline')">{{ copy.decline }}</button>
          </div>
        </section>

        <div v-else-if="actions.length" class="combat-actions">
          <section v-if="attackAction" class="action-card">
            <h3>{{ copy.action }} · {{ copy.attack }}</h3>
            <label>{{ copy.weapon }}
              <select v-model="selectedWeaponId">
                <option
                  v-for="weaponItem in attackAction.weapons"
                  :key="weaponItem.weapon_ref || weaponItem.id"
                  :value="weaponItem.weapon_ref || weaponItem.id"
                  :disabled="!weaponRangeState(weaponItem, selectedTargetId).usable"
                >
                  {{ weaponItem.name || weaponItem.id }} · {{ weaponItem.damage }} · {{ weaponRangeLabel(weaponItem) }}
                </option>
              </select>
            </label>
            <label>{{ copy.target }}
              <select v-model="selectedTargetId">
                <option v-for="targetItem in attackAction.targets" :key="targetItem.actor_id" :value="targetItem.actor_id">
                  {{ targetItem.name }} · {{ targetItem.hp }}/{{ targetItem.max_hp }} HP
                </option>
              </select>
            </label>
            <p v-if="selectedTargetId" :class="['range-guide', { blocked: !hasUsableWeapon }]">
              {{ copy.targetDistance }} {{ attackDistance }} {{ copy.feet }}。
              {{ hasUsableWeapon ? copy.autoWeapon : copy.moveCloser }}
            </p>
            <button :disabled="busy || !selectedWeapon || !selectedTargetId || !selectedWeaponRange?.usable" @click="stageAttack">{{ copy.attack }}</button>
          </section>

          <section v-if="spellAction" class="action-card">
            <h3>{{ copy.action }} / {{ copy.bonus }} · {{ copy.cast }}</h3>
            <label>{{ copy.spell }}
              <select v-model="selectedSpellRef">
                <option v-for="spellItem in spellAction.spells" :key="spellItem.spell_ref" :value="spellItem.spell_ref">
                  {{ spellItem.name }} · {{ spellItem.casting_time }}
                </option>
              </select>
            </label>
            <label v-if="selectedSpell?.level">{{ copy.slot }}
              <select v-model.number="selectedSlot">
                <option v-for="level in selectedSpell.available_slot_levels" :key="level" :value="level">{{ level }}</option>
              </select>
            </label>
            <label>{{ copy.target }}
              <select v-model="selectedTargetId">
                <option v-for="targetItem in targetsFor(selectedSpell)" :key="targetItem.actor_id" :value="targetItem.actor_id">
                  {{ targetItem.name }} · {{ targetItem.hp }}/{{ targetItem.max_hp }} HP
                </option>
              </select>
            </label>
            <button :disabled="busy || !selectedSpell || !selectedTarget" @click="stageSpell">{{ copy.cast }}</button>
          </section>

          <section v-if="moveAction" class="action-card">
            <h3>{{ copy.movement }}</h3>
            <label>{{ copy.move }}
              <input v-model.number="movementDistance" type="number" :min="-Number(moveAction.movement_remaining || 0)" :max="Number(moveAction.movement_remaining || 0)" step="5">
              <small>± {{ moveAction.movement_remaining }} {{ copy.feet }}</small>
            </label>
            <button :disabled="busy || !movementDistance" @click="stageMove">{{ copy.move }}</button>
          </section>

          <section class="action-card compact-actions">
            <h3>{{ copy.economy }}</h3>
            <button v-if="action('dash')" @click="stageSimple('dash')">{{ copy.dash }}</button>
            <button v-if="action('dodge')" @click="stageSimple('dodge')">{{ copy.dodge }}</button>
            <button v-if="action('disengage')" @click="stageSimple('disengage')">{{ copy.disengage }}</button>
            <button v-if="action('death_save')" @click="stageSimple('death_save')">{{ copy.deathSave }}</button>
            <button v-if="action('end_turn')" @click="stageSimple('end_turn')">{{ copy.endTurn }}</button>
            <button v-if="action('combat.end')" class="danger" @click="stageSimple('combat.end')">{{ copy.endCombat }}</button>
          </section>
        </div>
        <p v-else class="combat-state">{{ waitingText }}</p>

        <section v-if="staged" ref="confirmCard" class="confirm-card" role="group" :aria-label="copy.confirm" tabindex="-1">
          <strong>{{ copy.confirm }}</strong>
          <code>{{ staged.type }} · {{ targetName(String(staged.target_id || '')) }}</code>
          <div>
            <button :disabled="busy" @click="cancelStaged">{{ copy.cancel }}</button>
            <button class="combat-primary" :disabled="busy" @click="confirmStaged">{{ copy.confirm }}</button>
          </div>
        </section>

        <section v-if="latestEvents.length || notice" class="resolution-log" aria-live="polite">
          <h3>{{ copy.lastResult }}</h3>
          <ul>
            <li v-for="(event, index) in latestEvents" :key="index">{{ describeEvent(event) }}</li>
            <li v-if="!latestEvents.length && notice">{{ notice }}</li>
          </ul>
        </section>
      </template>
    </template>
  </section>
</template>

<style scoped>
.dnd-combat { display: grid; gap: 14px; margin: 14px 0; padding: 16px; border: 1px solid #806339; border-radius: 16px; background: linear-gradient(145deg, rgb(23 20 19 / 96%), rgb(19 27 35 / 96%)); color: #f2eadc; box-shadow: 0 18px 48px rgb(0 0 0 / 24%); }
.combat-header, .actor-card header, .decision-card, .confirm-card { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.combat-header h2 { margin: 2px 0 0; font: 700 clamp(19px, 2vw, 25px)/1.2 Georgia, serif; }
.eyebrow { margin: 0; color: #d7b873; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
.combat-authority, .preset-description, .combat-state { margin: 0; color: #bcb5aa; font-size: 13px; }
.combat-error { margin: 0; padding: 9px 11px; border: 1px solid #b85151; border-radius: 9px; background: rgb(115 28 28 / 25%); color: #ffd6d6; }
.story-bridge { display: grid; gap: 8px; padding: 14px; border: 1px solid #a17b3f; border-radius: 12px; background: linear-gradient(135deg, rgb(91 62 26 / 42%), rgb(27 30 34 / 88%)); }
.story-bridge-label { color: #f0c975; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
.story-bridge h3, .story-bridge p { margin: 0; }
.story-bridge p { color: #e3d9c6; line-height: 1.6; }
.story-bridge aside { padding: 9px 11px; border-left: 3px solid #d5a64f; background: rgb(14 20 24 / 56%); color: #f2e6cf; line-height: 1.55; }
.guided-preset { display: grid; gap: 5px; padding: 11px 12px; border: 1px solid #a17b3f; border-radius: 10px; background: rgb(91 62 26 / 24%); }.guided-preset span, .guided-preset small { color: #f0c975; font-size: 12px; }.guided-preset strong { font-size: 17px; }.guided-preset p { margin: 0; color: #e3d9c6; line-height: 1.5; }
.combat-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.combat-summary span { display: grid; gap: 3px; padding: 9px 11px; border: 1px solid #394551; border-radius: 10px; background: #151c23; }
.combat-summary small { color: #9ca6ae; }
.initiative { display: flex; gap: 6px; margin: 0; padding: 0; overflow-x: auto; list-style: none; }
.initiative li { min-width: max-content; padding: 5px 9px; border: 1px solid #3b4650; border-radius: 999px; color: #aeb8c0; }
.initiative li.current { border-color: #d2a855; background: #362b19; color: #ffe5a8; }
.tactical-track { display: grid; gap: 7px; padding: 11px; border: 1px solid #3b4650; border-radius: 12px; background: #0e151c; }
.tactical-track > header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.tactical-track > header span { color: #aeb8c0; font-size: 12px; }
.track-surface { position: relative; min-height: 112px; padding-top: 76px; overflow-x: auto; overflow-y: hidden; }
.track-cells { display: grid; min-width: max-content; }
.track-cells button { min-width: 34px; min-height: 34px; padding: 0; border-radius: 0; border-color: #35414b; color: #89949c; background: #151e26; font-size: 10px; }
.track-cells button.reachable { border-color: #97783d; color: #f0cf8b; background: #2c261b; cursor: pointer; }
.track-cells button.selected { border-color: #e4b75e; background: #5c421d; box-shadow: inset 0 0 0 2px #e4b75e; }
.track-cells button:disabled { opacity: 1; cursor: default; }
.track-token { position: absolute; z-index: 1; display: grid; place-items: center; width: 28px; height: 28px; margin-left: -14px; border: 2px solid #6ba2be; border-radius: 50%; background: #173347; color: #eef9ff; font-size: 10px; font-weight: 800; box-shadow: 0 4px 9px rgb(0 0 0 / 38%); }
.track-token.enemy { border-color: #c56b6b; background: #55292b; }
.track-token.current { outline: 3px solid #e4b75e; outline-offset: 2px; }
.actor-grid, .combat-actions { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }
.actor-card, .action-card { display: grid; gap: 8px; padding: 12px; border: 1px solid #3b4650; border-radius: 12px; background: #111820; }
.actor-card.enemy { border-color: #664446; }
.actor-card p, .action-card h3 { margin: 0; }
.range-guide { margin: 0; color: #b8d7bc; font-size: 12px; line-height: 1.5; }
.range-guide.blocked { color: #f0b3a7; }
.actor-card small { color: #c5aa83; }
.hp-track { height: 6px; overflow: hidden; border-radius: 999px; background: #3a3030; }
.hp-track i { display: block; height: 100%; background: linear-gradient(90deg, #8d3030, #d77055); }
.action-card label, .encounter-start label { display: grid; gap: 5px; color: #c8c2b8; font-size: 12px; }
button, select, input { min-height: 44px; font: inherit; }
.action-card select, .action-card input, .encounter-start select { width: 100%; min-height: 44px; padding-inline: 10px; border: 1px solid #4a5560; border-radius: 8px; background: #0d1319; color: #f3eee7; }
.compact-actions { align-content: start; }
.decision-card, .confirm-card { padding: 12px; border: 1px solid #c2974a; border-radius: 12px; background: #322716; }
.decision-card div, .confirm-card div { display: flex; gap: 7px; flex-wrap: wrap; }
.confirm-card { position: sticky; bottom: 12px; z-index: 2; box-shadow: 0 12px 36px rgb(0 0 0 / 45%); }
.confirm-card code { color: #efd195; }
.combat-primary { border-color: #c59443; background: #a56f24; color: white; }
.resolution-log h3 { margin: 0 0 7px; }
.resolution-log ul { display: flex; gap: 6px; flex-wrap: wrap; margin: 0; padding: 0; list-style: none; }
.resolution-log li { padding: 4px 8px; border-radius: 7px; background: #202b34; color: #cdd7df; font-size: 12px; }
button:focus-visible, select:focus-visible, input:focus-visible, .confirm-card:focus-visible { outline: 3px solid #e4b75e; outline-offset: 2px; }
:global(body.light .dnd-combat) { border-color: #9b743a; background: linear-gradient(145deg, #fffaf0, #f1f6f7); color: #27231e; box-shadow: 0 14px 34px rgb(76 59 29 / 12%); }
:global(body.light .dnd-combat .story-bridge) { border-color: #aa8546; background: #fff7e7; }
:global(body.light .dnd-combat .story-bridge p), :global(body.light .dnd-combat .story-bridge aside) { color: #403728; }
:global(body.light .dnd-combat .actor-card), :global(body.light .dnd-combat .action-card), :global(body.light .dnd-combat .combat-summary span) { border-color: #b8b2a6; background: #fff; }
:global(body.light .dnd-combat .tactical-track) { border-color: #b8b2a6; background: #f7f9fa; }
:global(body.light .dnd-combat .action-card select), :global(body.light .dnd-combat .action-card input), :global(body.light .dnd-combat .encounter-start select) { border-color: #908779; background: #fff; color: #211e1a; }
:global(body.light .dnd-combat .combat-authority), :global(body.light .dnd-combat .preset-description), :global(body.light .dnd-combat .combat-state), :global(body.light .dnd-combat .combat-summary small) { color: #514b43; }
:global(body.light .dnd-combat .resolution-log li) { background: #e8eef0; color: #27383e; }
@media (max-width: 700px) {
  .dnd-combat { margin-inline: 0; padding: 12px; border-radius: 12px; }
  .combat-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .combat-header, .decision-card, .confirm-card { align-items: stretch; flex-direction: column; }
}
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; transition: none !important; } }
</style>

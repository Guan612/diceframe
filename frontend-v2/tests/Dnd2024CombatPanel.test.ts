import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(), submit: vi.fn(), decide: vi.fn(),
}))

vi.mock('../src/features/rulesets/dnd2024/api', () => ({
  fetchRulesetAvailableActions: mocks.fetch,
  submitRulesetIntent: mocks.submit,
  resolveRulesetDecision: mocks.decide,
}))
vi.mock('../src/composables/useLocale', () => ({
  useLocale: () => ({ locale: ref('en') }),
}))

import Dnd2024CombatPanel from '../src/features/rulesets/dnd2024/combat/Dnd2024CombatPanel.vue'

function response(status: 'none' | 'active' = 'none') {
  const active = status === 'active'
  return {
    ok: true,
    game_key: 'web|combat|bot',
    rule_id: 'dnd2024_srd',
    ruleset_runtime: {
      id: 'core:dnd2024', version: 1, requested_minimum_version: 1,
      capabilities: {
        experience_profile: 'dnd2024', character_builder: 'professional',
        authoritative_intents: true, deterministic_combat: true,
        versioned_state: true, session_zero: false, tutorial_coach: false,
      },
    },
    gameplay: {
      state_schema_version: 1,
      state_version: active ? 1 : 0,
      encounter_presets: [{
        id: 'first_skirmish', name: 'First Skirmish', description: 'Tutorial encounter',
        difficulty: 'tutorial', enemies: [{ id: 'goblin-1', hp: 7 }],
      }],
      combat: {
        status, round: active ? 1 : 0, turn_index: 0,
        current_actor_id: active ? 'player:gm' : '',
        initiative: active ? ['player:gm', 'enemy:goblin-1'] : [],
        position_mode: 'theater',
        economy: active ? { action: 1, bonus_action: 1, movement: 30, reaction: 1 } : {},
        reactions: {}, pending_decisions: [],
        actors: active ? [
          { actor_id: 'player:gm', kind: 'player', name: 'Guardian', hp: 12, max_hp: 12, position: 0, armor_class: 16, conditions: {} },
          { actor_id: 'enemy:goblin-1', kind: 'enemy', name: 'Goblin', hp: 7, max_hp: 7, position: 5, armor_class: 12, conditions: {} },
        ] : [],
      },
    },
    available_actions: active ? [{
      type: 'attack', label: 'Attack', actor_id: 'player:gm', expected_version: 1,
      weapons: [{ id: 'greatsword', weapon_ref: 'item:greatsword', damage: '2d6' }],
      targets: [{ actor_id: 'enemy:goblin-1', kind: 'enemy', name: 'Goblin', hp: 7, max_hp: 7, position: 5 }],
    }, {
      type: 'move', label: 'Move', actor_id: 'player:gm', expected_version: 1,
      movement_remaining: 30,
    }, {
      type: 'end_turn', label: 'End Turn', actor_id: 'player:gm', expected_version: 1,
    }] : [{
      type: 'combat.start', label: 'Start Combat', expected_version: 0, requires: ['enemies'],
    }],
  }
}

describe('D&D 2024 combat panel', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mocks.fetch.mockReset().mockResolvedValue(response('none'))
    mocks.submit.mockReset().mockResolvedValue(response('active'))
    mocks.decide.mockReset().mockResolvedValue(response('active'))
  })

  it('starts only from a server-provided encounter preset', async () => {
    const wrapper = mount(Dnd2024CombatPanel, {
      props: { gameKey: 'web|combat|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('First Skirmish')
    await wrapper.get('.encounter-start .combat-primary').trigger('click')
    await flushPromises()

    expect(mocks.submit).toHaveBeenCalledOnce()
    const payload = mocks.submit.mock.calls[0][1]
    expect(payload).toMatchObject({
      type: 'combat.start', expected_version: 0,
      encounter_preset_id: 'first_skirmish',
      enemies: [{ id: 'goblin-1', hp: 7 }],
    })
    expect(payload).not.toHaveProperty('submitted_by')
    wrapper.unmount()
  })

  it('explains when the shared narrative requested authoritative combat', async () => {
    const requested = response('none') as any
    requested.gameplay.encounter_request = { status: 'pending', source: 'narrative', round: 3 }
    mocks.fetch.mockResolvedValueOnce(requested)
    const wrapper = mount(Dnd2024CombatPanel, {
      props: { gameKey: 'web|combat|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('The shared story has entered an engagement')
    expect(wrapper.text()).toContain('Choose an encounter preset')
    expect(wrapper.find('.encounter-start .combat-primary').exists()).toBe(true)
    wrapper.unmount()
  })

  it('carries the selected adventure into its story encounter and selects its preset', async () => {
    const guided = response('none') as any
    guided.gameplay.campaign = {
      session_zero: { status: 'locked', revision: 1, responses: {} },
      session_zero_defaults: {}, proposals: [], entities: {}, chapter_summaries: [],
      tutorial: {
        status: 'active', coach_enabled: true, history: [], hints_used: {},
        adventure: { id: 'lanterns_of_greymoor', name: 'The Lost Lanterns', summary: '', estimated_minutes: 90, chapter_count: 3 },
        current_step: {
          id: 'thorn_ambush', chapter_id: 'thorn_glade', title: 'The First Encounter',
          narration: 'A goblin notices you in the grove.', objective: 'Learn initiative and take one action.',
          hint: 'Move or shoot.', requires: 'combat_ended', encounter_preset_id: 'first_skirmish', choices: [],
        }, requirement_met: false,
      },
    }
    mocks.fetch.mockResolvedValueOnce(guided)
    const wrapper = mount(Dnd2024CombatPanel, {
      props: { gameKey: 'web|combat|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Continue the story')
    expect(wrapper.text()).toContain('A goblin notices you in the grove.')
    expect(wrapper.text()).toContain('Start this story encounter')
    expect(wrapper.get('.guided-preset strong').text()).toBe('First Skirmish')
    expect(wrapper.find('.encounter-start select').exists()).toBe(false)
    wrapper.unmount()
  })

  it('stages an attack for confirmation before submitting it', async () => {
    mocks.fetch.mockResolvedValueOnce(response('active'))
    const wrapper = mount(Dnd2024CombatPanel, {
      props: { gameKey: 'web|combat|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    await wrapper.get('.action-card button').trigger('click')
    expect(wrapper.find('.confirm-card').exists()).toBe(true)
    expect(mocks.submit).not.toHaveBeenCalled()
    await wrapper.get('.confirm-card .combat-primary').trigger('click')
    await flushPromises()

    expect(mocks.submit).toHaveBeenCalledOnce()
    expect(mocks.submit.mock.calls[0][1]).toMatchObject({
      type: 'attack', actor_id: 'player:gm', target_id: 'enemy:goblin-1',
      weapon_ref: 'item:greatsword', expected_version: 1,
    })
    wrapper.unmount()
  })

  it('selects an in-range weapon first and blocks weapons that cannot reach the target', async () => {
    const distant = response('active')
    const attack = distant.available_actions[0] as unknown as {
      weapons: Array<Record<string, unknown>>
      targets: Array<{ position: number }>
    }
    attack.weapons = [
      { id: 'greatsword', weapon_ref: 'item:greatsword', damage: '2d6', range: 5 },
      { id: 'javelin', weapon_ref: 'item:javelin', damage: '1d6', thrown_range: 30, long_range: 120 },
    ]
    attack.targets[0].position = 25
    distant.gameplay.combat.actors[1].position = 25
    mocks.fetch.mockResolvedValueOnce(distant)
    const wrapper = mount(Dnd2024CombatPanel, {
      props: { gameKey: 'web|combat|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    const weaponSelect = wrapper.get('.action-card select')
    expect((weaponSelect.element as HTMLSelectElement).value).toBe('item:javelin')
    const options = weaponSelect.findAll('option')
    expect(options[0].attributes('disabled')).toBeDefined()
    expect(options[0].text()).toContain('Out of range')
    expect(options[1].text()).toContain('In range')
    expect(wrapper.text()).toContain('Distance to target 25 ft')

    await wrapper.get('.action-card button').trigger('click')
    await wrapper.get('.confirm-card .combat-primary').trigger('click')
    await flushPromises()
    expect(mocks.submit.mock.calls[0][1]).toMatchObject({ weapon_ref: 'item:javelin' })
    wrapper.unmount()
  })

  it('uses the tactical track to select an authoritative movement distance', async () => {
    mocks.fetch.mockResolvedValueOnce(response('active'))
    const wrapper = mount(Dnd2024CombatPanel, {
      props: { gameKey: 'web|combat|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    expect(wrapper.findAll('.track-token')).toHaveLength(2)
    const destination = wrapper.get('button[aria-label="Position 20 ft"]')
    expect(destination.classes()).toContain('reachable')
    await destination.trigger('click')

    const movementInput = wrapper.get('.action-card input[type="number"]')
    expect((movementInput.element as HTMLInputElement).value).toBe('20')
    expect(destination.classes()).toContain('selected')
    wrapper.unmount()
  })

  it('shows a waiting state when the server exposes no action', async () => {
    const waiting = response('active')
    waiting.available_actions = []
    mocks.fetch.mockResolvedValueOnce(waiting)
    const wrapper = mount(Dnd2024CombatPanel, {
      props: { gameKey: 'web|combat|bot', actorId: 'player-two', isGm: false },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Waiting for teammate：Guardian')
    expect(wrapper.find('.combat-actions').exists()).toBe(false)
    wrapper.unmount()
  })

  it('focuses explicit confirmation and returns to the campaign after combat ends', async () => {
    const ending = response('active')
    ;(ending.available_actions as unknown as Array<Record<string, unknown>>).push({
      type: 'combat.end', label: 'End Combat', actor_id: 'player:gm', expected_version: 1,
    })
    mocks.fetch.mockResolvedValueOnce(ending)
    mocks.submit.mockResolvedValue(response('none'))
    const wrapper = mount(Dnd2024CombatPanel, {
      attachTo: document.body,
      props: { gameKey: 'web|combat|bot', actorId: 'gm', isGm: true },
    })
    await flushPromises()

    await wrapper.get('.compact-actions .danger').trigger('click')
    await flushPromises()
    expect(wrapper.get('.confirm-card').element).toBe(document.activeElement)
    expect(wrapper.get('.confirm-card').attributes('role')).toBe('group')
    await wrapper.get('.confirm-card .combat-primary').trigger('click')
    await flushPromises()

    expect(mocks.submit.mock.calls[0][1]).toMatchObject({ type: 'combat.end' })
    expect(wrapper.emitted('navigate')).toEqual([['campaign']])
    wrapper.unmount()
  })
})

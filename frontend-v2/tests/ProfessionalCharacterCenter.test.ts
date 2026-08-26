import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ api: vi.fn() }))

vi.mock('../src/api/client', () => ({
  api: mocks.api,
  errorMessage: (cause: unknown) => String((cause as Error)?.message || cause),
}))

import ProfessionalCharacterCenter from '../src/features/rulesets/ProfessionalCharacterCenter.vue'

const character = {
  character_name: 'Arden',
  portrait: {},
  hp: 12,
  max_hp: 12,
  attributes: { str: 16, dex: 12, con: 14, int: 10, wis: 13, cha: 8 },
  ruleset_character: {
    rule_binding: { runtime_id: 'core:dnd2024', content_version: 'srd-test' },
    identity: {
      name: 'Arden', species_ref: 'species:human', background_ref: 'background:guard',
      alignment: 'lawful_good', size: 'medium',
    },
    build: {
      level: 1,
      class_levels: [{ class_ref: 'class:fighter', level: 1 }],
    },
    abilities: { str: 16, dex: 12, con: 14, int: 10, wis: 13, cha: 8 },
    resources: { hp: 12, max_hp: 12, hit_dice: { d10: 1 } },
    derived: { armor_class: 18, proficiency_bonus: 2 },
    proficiencies: { skill_refs: ['skill:athletics'] },
    progression: { mode: 'single_class' },
  },
}

describe('ProfessionalCharacterCenter', () => {
  beforeEach(() => {
    mocks.api.mockReset().mockResolvedValue({
      ok: true,
      card: { ...character, character_name: 'Arden Vale' },
    })
  })

  it('teaches the basic mental model and only submits profile fields', async () => {
    const wrapper = mount(ProfessionalCharacterCenter, {
      props: {
        character,
        target: 'card',
        cardId: 'card-1',
        ruleId: 'dnd2024_srd',
        language: 'zh-CN',
      },
      global: {
        stubs: {
          PortraitPicker: {
            props: ['modelValue'],
            template: '<div data-test="portrait-picker" />',
          },
        },
      },
    })

    expect(wrapper.text()).toContain('第一次玩，先记住三件事')
    expect(wrapper.text()).toContain('描述你想做什么，不必先背规则')
    await wrapper.get('.center-tabs button:nth-child(2)').trigger('click')
    await wrapper.get('input[required]').setValue('Arden Vale')
    const textareas = wrapper.findAll('textarea')
    await textareas[2].setValue('Left home to protect a frontier town.')
    await wrapper.get('footer .primary').trigger('click')
    await flushPromises()

    expect(mocks.api).toHaveBeenCalledOnce()
    const [path, request] = mocks.api.mock.calls[0]
    expect(path).toBe('/character-cards/card-1/profile')
    const body = JSON.parse(request.body)
    expect(body.character_name).toBe('Arden Vale')
    expect(body.profile.backstory).toContain('frontier town')
    expect(body.portrait).toBeNull()
    expect(body).not.toHaveProperty('hp')
    expect(body).not.toHaveProperty('attributes')
    expect(body).not.toHaveProperty('ruleset_character')
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('submits live rest intent with hit-die counts, confirmation, and revision', async () => {
    mocks.api.mockResolvedValueOnce({
      ok: true,
      character: { ...character, hp: 12, ruleset_revision: 4 },
      rest: 'short',
      events: [],
      revision: 4,
    })
    const wrapper = mount(ProfessionalCharacterCenter, {
      props: {
        character: { ...character, ruleset_revision: 3 },
        target: 'game',
        gameKey: 'web|room|bot',
        userId: 'player/1',
        ruleId: 'dnd2024_srd',
        language: 'zh-CN',
      },
      global: { stubs: { PortraitPicker: true } },
    })

    await wrapper.get('.center-tabs button:nth-child(4)').trigger('click')
    await wrapper.get('.hit-dice-grid input').setValue(1)
    await wrapper.get('.rest-confirm input').setValue(true)
    await wrapper.get('.rest-center > button').trigger('click')
    await flushPromises()

    const [path, request] = mocks.api.mock.calls[0]
    expect(path).toBe('/games/web%7Croom%7Cbot/character/player%2F1/rest')
    const body = JSON.parse(request.body)
    expect(body).toMatchObject({
      rest: 'short', hit_dice: { d10: 1 }, confirm_elapsed_time: true,
      expected_revision: 3,
    })
    expect(body.operation_id).toEqual(expect.any(String))
    expect(body).not.toHaveProperty('hit_die_rolls')
    expect(wrapper.emitted('saved')?.[0]?.[1]).toBe('rest')
  })

  it('keeps long profile text readable and renders spell slots as level cards', async () => {
    const detailedCharacter = {
      ...character,
      ruleset_character: {
        ...character.ruleset_character,
        profile: {
          ideals: '保护每一个在边境线上努力生活的人，不让任何人再次独自面对战争。',
        },
        spellcasting: {
          class: {
            ability: 'int',
            slots_current: { '1': 2, '2': 1 },
            slots_max: { '1': 4, '2': 2 },
            cantrip_refs: ['spell:light'],
            prepared_spell_refs: ['spell:shield'],
          },
        },
      },
    }
    const wrapper = mount(ProfessionalCharacterCenter, {
      props: {
        character: detailedCharacter,
        target: 'card',
        cardId: 'card-1',
        ruleId: 'dnd2024_srd',
        language: 'zh-CN',
      },
      global: { stubs: { PortraitPicker: true } },
    })

    await wrapper.get('.center-tabs button:nth-child(2)').trigger('click')
    expect((wrapper.findAll('textarea')[3].element as HTMLTextAreaElement).value).toContain('保护每一个')
    await wrapper.get('.center-tabs button:nth-child(4)').trigger('click')
    expect(wrapper.findAll('.spell-slot-card')).toHaveLength(2)
    expect(wrapper.text()).toContain('1 环')
    expect(wrapper.text()).toContain('2 / 4')
    expect(wrapper.text()).not.toContain('slots_current')
  })
})

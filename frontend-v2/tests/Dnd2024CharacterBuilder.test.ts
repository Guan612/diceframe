import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  choices: vi.fn(), validate: vi.fn(), derive: vi.fn(), finalize: vi.fn(),
}))

vi.mock('../src/features/rulesets/dnd2024/api', () => ({
  fetchRulesetBuilderChoices: mocks.choices,
  validateRulesetBuilderDraft: mocks.validate,
  deriveRulesetBuilderCharacter: mocks.derive,
  finalizeRulesetBuilderCharacter: mocks.finalize,
}))

import Dnd2024CharacterBuilder from '../src/features/rulesets/dnd2024/create/Dnd2024CharacterBuilder.vue'

const legalDraft = {
  class_ref: 'class:fighter', species_ref: 'species:human', background_ref: 'background:soldier',
  species_size: 'medium', species_skill_refs: ['skill:acrobatics'], species_feat_refs: ['feat:alert'],
  class_skill_refs: ['skill:perception', 'skill:survival'], class_tool_refs: [],
  equipment_package_ref: 'equipment_package:fighter_a',
  background_equipment_package_ref: 'equipment_package:soldier_a',
  ability_method: 'standard_array',
  base_abilities: { str: 15, dex: 14, con: 13, int: 8, wis: 10, cha: 12 },
  background_ability_bonuses: { str: 2, con: 1 },
  language_refs: ['language:common', 'language:dwarvish', 'language:elvish'],
  alignment: 'neutral_good',
}

const choices = {
  ability_methods: [{ id: 'standard_array', values: [15, 14, 13, 12, 10, 8] }],
  classes: [], species: [], backgrounds: [], class_skills: [], class_skill_count: 0,
  equipment_packages: [], background_equipment_packages: [], background_ability_refs: [],
  species_sizes: [], species_choices: [], species_skills: [], species_skill_count: 0,
  species_feats: [], species_feat_count: 0, class_tools: [], class_tool_count: 0,
  recommended_base_abilities: {}, skills: [], languages: [], origin_feats: [],
  class_spells: {}, recommended_class_spells: {}, feat_choices: [],
  quick_presets: [{
    ref: 'quick_character_preset:guardian', id: 'guardian', name: '可靠守护者',
    summary: '直观而坚韧。', recommendation_reason: '适合第一次进入战斗。',
    automation_level: 'deterministic', source_ref: 'diceframe-original:test',
    difficulty: 'beginner', fantasy_tags: ['melee', 'durable'], draft: legalDraft,
  }],
}

describe('D&D 2024 professional character builder', () => {
  beforeEach(() => {
    localStorage.clear()
    mocks.choices.mockReset().mockResolvedValue({ ok: true, rule_id: 'dnd2024_srd', choices })
    mocks.validate.mockReset().mockResolvedValue({ ok: true, valid: true, errors: [] })
    mocks.derive.mockReset().mockResolvedValue({ ok: true, character: {} })
    mocks.finalize.mockReset().mockResolvedValue({
      ok: true, rule_id: 'dnd2024_srd', character: {
        character_name: '阿岚', rule_id: 'dnd2024_srd', ruleset_character: { rule_binding: {} },
      },
    })
  })

  it('finishes a server-validated quick preset with only a required name', async () => {
    const wrapper = mount(Dnd2024CharacterBuilder, {
      global: { plugins: [createPinia()] },
      props: {
        ruleId: 'dnd2024_srd', language: 'zh-CN',
        experience: {
          profile: 'dnd2024', builder_mode: 'professional',
          modes: ['quick', 'guided', 'expert'], content_version: 'srd-5.2.1+r2', locale: 'zh-CN',
        },
      },
    })
    await flushPromises()

    await wrapper.get('.preset-card').trigger('click')
    await wrapper.get('.name-field input').setValue('阿岚')
    await wrapper.get('.quick-actions .primary').trigger('click')
    await flushPromises()

    expect(mocks.validate).toHaveBeenCalledOnce()
    const submittedDraft = mocks.validate.mock.calls[0]?.[1]
    expect(submittedDraft).toMatchObject({ ...legalDraft, name: '阿岚', locale: 'zh-CN' })
    expect(mocks.finalize).toHaveBeenCalledOnce()
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({
      character_name: '阿岚', rule_id: 'dnd2024_srd',
    })
  })

  it('exposes quick, guided, and expert modes without loading arbitrary components', async () => {
    const wrapper = mount(Dnd2024CharacterBuilder, {
      global: { plugins: [createPinia()] },
      props: {
        ruleId: 'dnd2024_srd', language: 'zh-CN',
        experience: {
          profile: 'dnd2024', builder_mode: 'professional',
          modes: ['quick', 'guided', 'expert'], content_version: 'srd-5.2.1+r2', locale: 'zh-CN',
        },
      },
    })
    await flushPromises()

    const labels = wrapper.findAll('.mode-tabs button').map(button => button.text())
    expect(labels).toEqual(['快速创建', '引导创建', '专家创建'])
    await wrapper.findAll('.mode-tabs button')[2].trigger('click')
    expect(wrapper.find('.guided-builder').exists()).toBe(true)
  })

  it('explains standard alignment abbreviations and localizes common builder enums', async () => {
    const wrapper = mount(Dnd2024CharacterBuilder, {
      global: { plugins: [createPinia()] },
      props: {
        ruleId: 'dnd2024_srd', language: 'zh-CN',
        experience: {
          profile: 'dnd2024', builder_mode: 'professional',
          modes: ['quick', 'guided', 'expert'], content_version: 'srd-5.2.1+r4', locale: 'zh-CN',
        },
      },
    })
    await flushPromises()
    expect(wrapper.get('.preset-card small').text()).toBe('新手友好')

    ;(wrapper.vm as unknown as { mode: string; step: number }).mode = 'guided'
    ;(wrapper.vm as unknown as { mode: string; step: number }).step = 1
    await wrapper.vm.$nextTick()
    const alignment = wrapper.findAll('label').find(item => item.text().includes('阵营（'))!
    expect(alignment.findAll('option').map(item => item.text())).toEqual([
      'LG · 守序善良', 'NG · 中立善良', 'CG · 混乱善良',
      'LN · 守序中立', 'N · 绝对中立', 'CN · 混乱中立',
    ])
    expect(alignment.get('.field-help').text()).toContain('缩写与常见 D&D 资料一致')

    ;(wrapper.vm as unknown as { mode: string; step: number }).step = 2
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.ability-methods').text()).toContain('标准数组')
  })

  it('exposes keyboard-operable builder tabs with an explicit active mode', async () => {
    const wrapper = mount(Dnd2024CharacterBuilder, {
      attachTo: document.body,
      global: { plugins: [createPinia()] },
      props: {
        ruleId: 'dnd2024_srd', language: 'zh-CN',
        experience: {
          profile: 'dnd2024', builder_mode: 'professional',
          modes: ['quick', 'guided', 'expert'], content_version: 'srd-5.2.1+r4', locale: 'zh-CN',
        },
      },
    })
    await flushPromises()

    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs[0].attributes('aria-selected')).toBe('true')
    ;(tabs[0].element as HTMLButtonElement).focus()
    await tabs[0].trigger('keydown', { key: 'ArrowRight' })
    await wrapper.vm.$nextTick()

    expect(tabs[1].attributes('aria-selected')).toBe('true')
    expect(tabs[1].element).toBe(document.activeElement)
    expect(wrapper.get('[role="tabpanel"]').attributes('aria-labelledby')).toBe('builder-mode-guided')
    wrapper.unmount()
  })

  it('disables conflicting and excess proficiency choices at their exact limits', async () => {
    mocks.choices.mockResolvedValue({
      ok: true,
      rule_id: 'dnd2024_srd',
      choices: {
        ...choices,
        class_skills: [
          { ref: 'skill:perception', id: 'perception', name: '察觉' },
          { ref: 'skill:survival', id: 'survival', name: '求生' },
        ],
        class_skill_count: 1,
        species_skills: [
          { ref: 'skill:perception', id: 'perception', name: '察觉' },
          { ref: 'skill:acrobatics', id: 'acrobatics', name: '杂技' },
        ],
        species_skill_count: 1,
      },
    })
    const wrapper = mount(Dnd2024CharacterBuilder, {
      global: { plugins: [createPinia()] },
      props: {
        ruleId: 'dnd2024_srd', language: 'zh-CN',
        experience: {
          profile: 'dnd2024', builder_mode: 'professional',
          modes: ['quick', 'guided', 'expert'], content_version: 'srd-5.2.1+r4', locale: 'zh-CN',
        },
      },
    })
    await flushPromises()
    ;(wrapper.vm as unknown as { mode: string; step: number }).mode = 'guided'
    ;(wrapper.vm as unknown as { mode: string; step: number }).step = 3
    await wrapper.vm.$nextTick()

    const fieldsets = wrapper.findAll('fieldset')
    const classSkills = fieldsets.find(item => item.text().includes('职业技能'))!
    const speciesSkills = fieldsets.find(item => item.text().includes('物种技能'))!
    const classInputs = classSkills.findAll('input')
    await classInputs[0].setValue(true)

    expect((classInputs[0].element as HTMLInputElement).disabled).toBe(false)
    expect((classInputs[1].element as HTMLInputElement).disabled).toBe(true)
    expect((speciesSkills.findAll('input')[0].element as HTMLInputElement).disabled).toBe(true)
    expect((speciesSkills.findAll('input')[1].element as HTMLInputElement).disabled).toBe(false)

    await speciesSkills.findAll('input')[1].setValue(true)
    expect(speciesSkills.text()).toContain('1/1')
    expect((speciesSkills.findAll('input')[1].element as HTMLInputElement).disabled).toBe(false)
  })

  it('keeps wizard prepared spells inside the selected spellbook', async () => {
    mocks.choices.mockResolvedValue({
      ok: true,
      rule_id: 'dnd2024_srd',
      choices: {
        ...choices,
        class_spells: {
          requirements: {
            class_ref: 'class:wizard', level: 1, cantrip_count: 1,
            prepared_spell_count: 1, spellbook_minimum: 2, maximum_spell_level: 1,
            slot_profile: 'full', spell_slots: { 1: 2 },
          },
          cantrips: [{
            ref: 'spell:light', id: 'light', name: 'Light', level: 0,
            school: 'evocation', class_refs: ['class:wizard'], casting_time: 'Action',
            range: 'Touch', components: ['V'], ritual: false, concentration: false,
            duration: '1 hour', source_ref: 'srd-5.2.1:p200:light',
          }],
          leveled_spells: [
            { ref: 'spell:sleep', id: 'sleep', name: 'Sleep', level: 1, school: 'enchantment', class_refs: ['class:wizard'], casting_time: 'Action', range: '60 feet', components: ['V'], ritual: false, concentration: true, duration: '1 minute', source_ref: 'srd-5.2.1:p300:sleep' },
            { ref: 'spell:shield', id: 'shield', name: 'Shield', level: 1, school: 'abjuration', class_refs: ['class:wizard'], casting_time: 'Reaction', range: 'Self', components: ['V'], ritual: false, concentration: false, duration: '1 round', source_ref: 'srd-5.2.1:p299:shield' },
          ],
        },
        recommended_class_spells: {
          cantrip_ids: ['light'], spellbook_ids: ['sleep', 'shield'], prepared_spell_ids: ['sleep'],
        },
      },
    })
    const wrapper = mount(Dnd2024CharacterBuilder, {
      global: { plugins: [createPinia()] },
      props: {
        ruleId: 'dnd2024_srd', language: 'en',
        initial: {
          character_name: 'Arden', ruleset_character: {
            locale: 'en', identity: { name: 'Arden' },
            build: {
              class_levels: [{ class_ref: 'class:wizard', level: 1 }],
              class_spell_choices: {
                cantrip_refs: ['spell:light'], spellbook_refs: ['spell:sleep', 'spell:shield'],
                prepared_spell_refs: ['spell:sleep'],
              },
            },
          },
        },
        experience: {
          profile: 'dnd2024', builder_mode: 'professional',
          modes: ['quick', 'guided', 'expert'], content_version: 'srd-5.2.1+r2', locale: 'en',
        },
      },
    })
    await flushPromises()
    ;(wrapper.vm as unknown as { step: number }).step = 3
    await wrapper.vm.$nextTick()

    const spellbookBoxes = wrapper.findAll('.spell-group').find(group => group.text().includes('Spellbook'))!.findAll('input')
    await spellbookBoxes[0].setValue(false)

    const prepared = wrapper.findAll('.spell-group').find(group => group.text().includes('Prepared spells'))!
    expect((prepared.findAll('input')[0].element as HTMLInputElement).disabled).toBe(true)
    expect(prepared.findAll('input')[0].element.checked).toBe(false)
  })
})

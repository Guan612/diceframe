import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LoreEntryAdvanced, { type LoreEntryAdvancedModel } from '../src/features/lorebook/LoreEntryAdvanced.vue'
import { i18n } from '../src/i18n'

const model: LoreEntryAdvancedModel = {
  secondary_keys: [], selective_logic: 'any', use_regex: false, case_sensitive: false,
  match_whole_words: false, vector_activation: 'off', scan_depth: 0, priority: 0,
  probability: 100, prompt_slot: '', groups: [], group_weight: 1, group_scoring: '',
  sticky: 0, cooldown: 0, delay: 0, order: 100, prioritize_inclusion: false, non_recursable: false,
  prevent_further_recursion: false, delay_until_recursion: false, recursion_level: 0,
}

function mountAdvanced(modelValue: LoreEntryAdvancedModel = model) {
  return mount(LoreEntryAdvanced, { props: { modelValue }, global: { plugins: [i18n] } })
}

describe('LoreEntryAdvanced', () => {
  it('emits updates for advanced matching, activation, timing, and recursion controls', async () => {
    const wrapper = mountAdvanced()

    await wrapper.find('[data-field="secondary_keys"] input').setValue('tower, gate')
    await wrapper.find('[data-field="match_whole_words"] input').setValue(true)
    await wrapper.find('[data-field="vector_activation"] select').setValue('vector_only')
    await wrapper.find('[data-field="groups"] input').setValue('magic, rare')
    await wrapper.find('[data-field="group_weight"] input').setValue('2.5')
    await wrapper.find('[data-field="sticky"] input').setValue('3')
    await wrapper.find('[data-field="recursion_level"] input').setValue('2')
    await wrapper.find('[data-field="prompt_slot"] input').setValue('system')
    await wrapper.find('[data-field="delay_until_recursion"] input').setValue(true)

    const updates = (wrapper.emitted('update:modelValue') || []).map(([value]) => value as LoreEntryAdvancedModel)
    expect(updates.some(value => value.secondary_keys.join(',') === 'tower,gate')).toBe(true)
    expect(updates.some(value => value.match_whole_words)).toBe(true)
    expect(updates.some(value => value.vector_activation === 'vector_only')).toBe(true)
    expect(updates.some(value => value.groups.join(',') === 'magic,rare')).toBe(true)
    expect(updates.some(value => value.group_weight === 2.5)).toBe(true)
    expect(updates.some(value => value.sticky === 3)).toBe(true)
    expect(updates.some(value => value.recursion_level === 2)).toBe(true)
    expect(updates.some(value => value.prompt_slot === 'system')).toBe(true)
    expect(updates.some(value => value.delay_until_recursion)).toBe(true)
  })

  it('starts folded and exposes prioritize_inclusion plus canonical insertion order', async () => {
    const wrapper = mountAdvanced()
    const details = wrapper.get('details.lore-entry-advanced')
    expect((details.element as HTMLDetailsElement).open).toBe(false)

    await wrapper.find('[data-field="order"] input').setValue('7')
    await wrapper.find('[data-field="prioritize_inclusion"] input').setValue(true)

    const updates = (wrapper.emitted('update:modelValue') || []).map(([value]) => value as LoreEntryAdvancedModel)
    expect(updates.some(value => value.order === 7)).toBe(true)
    expect(updates.some(value => value.prioritize_inclusion === true)).toBe(true)
  })

  it('keeps every advanced field bound to a canonical payload key', () => {
    const wrapper = mountAdvanced()
    const fields = wrapper.findAll('[data-field]').map(node => node.attributes('data-field'))
    expect(fields).toEqual(expect.arrayContaining([
      'tier', 'order', 'prioritize_inclusion', 'connected_to', 'triggers_recursive',
      'unreliable', 'sync_on_enter', 'is_constant', 'secondary_keys', 'selective_logic',
      'use_regex', 'case_sensitive', 'match_whole_words', 'vector_activation', 'scan_depth',
      'priority', 'probability', 'groups', 'group_weight', 'group_scoring', 'sticky',
      'cooldown', 'delay', 'non_recursable', 'prevent_further_recursion',
      'delay_until_recursion', 'recursion_level', 'prompt_slot',
    ]))
  })
})

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LoreEntryAdvanced, { type LoreEntryAdvancedModel } from '../src/features/lorebook/LoreEntryAdvanced.vue'

const model: LoreEntryAdvancedModel = {
  secondary_keys: [], selective_logic: 'any', use_regex: false, case_sensitive: false,
  match_whole_words: false, vector_activation: 'off', scan_depth: 0, priority: 0,
  probability: 100, prompt_slot: '', groups: [], group_weight: 1, group_scoring: '',
  sticky: 0, cooldown: 0, delay: 0, non_recursable: false,
  prevent_further_recursion: false, delay_until_recursion: false, recursion_level: 0,
}

describe('LoreEntryAdvanced', () => {
  it('emits updates for advanced matching, activation, timing, and recursion controls', async () => {
    const wrapper = mount(LoreEntryAdvanced, { props: { modelValue: model } })

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
})

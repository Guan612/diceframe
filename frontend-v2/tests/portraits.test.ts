import { describe, expect, it } from 'vitest'
import { builtinPortraits, defaultBuiltinPortrait, resolveBuiltinPortrait } from '../src/utils/portraits'

describe('character portraits', () => {
  it('provides a distinct mixed-style eight-image portrait set for every built-in ruleset', () => {
    const allImages = new Set<string>()
    for (const ruleId of ['dnd5e', 'freeform_coc', 'freeform_cyberpunk', 'freeform_fantasy', 'freeform_wuxia', 'tavern_free']) {
      const options = builtinPortraits(ruleId)
      expect(options).toHaveLength(8)
      expect(options.map(option => option.id)).toEqual([0, 1, 2, 3, 4, 5, 6, 7].map(index => `${ruleId}:${index}`))
      expect(new Set(options.map(option => option.image)).size).toBe(8)
      expect(options.every(option => option.image.includes(`/avatars/v3/${ruleId}/`))).toBe(true)
      expect(options.filter(option => option.style === 'realistic')).toHaveLength(4)
      expect(options.filter(option => option.style === 'anime')).toHaveLength(4)
      expect(options.every(option => option.position === '50% 26%')).toBe(true)
      options.forEach(option => allImages.add(option.image))
    }
    expect(allImages.size).toBe(48)
  })

  it('selects stable defaults from all eight portraits', () => {
    expect(defaultBuiltinPortrait('freeform_coc', 'player_1')).toEqual(defaultBuiltinPortrait('freeform_coc', 'player_1'))
    const selected = new Set(Array.from({ length: 128 }, (_, index) => defaultBuiltinPortrait('freeform_coc', `player_${index}`).index))
    expect(selected).toEqual(new Set([0, 1, 2, 3, 4, 5, 6, 7]))
    expect(resolveBuiltinPortrait(undefined, 'freeform_coc_en', 'player_1').ruleId).toBe('freeform_coc')
  })

  it('resolves the new images without changing stored portrait ids', () => {
    const portrait = resolveBuiltinPortrait({ kind: 'builtin', id: 'freeform_wuxia:6' })
    expect(portrait.index).toBe(6)
    expect(portrait.style).toBe('anime')
    expect(portrait.image).toMatch(/\/avatars\/v3\/freeform_wuxia\/anime-3\.jpg$/)
    expect(portrait.position).toBe('50% 26%')
  })

  it('falls custom rules back to the generic fantasy pack', () => {
    expect(builtinPortraits('my_custom_rule')[0].ruleId).toBe('freeform_fantasy')
  })
})

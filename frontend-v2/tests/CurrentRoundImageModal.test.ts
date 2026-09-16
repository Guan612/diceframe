import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import CurrentRoundImageModal from '../src/components/play/CurrentRoundImageModal.vue'
import type { GameDetail, LogEntry } from '../src/api/types'

function mountModal(detail: Partial<GameDetail>, log: LogEntry[]) {
  return mount(CurrentRoundImageModal, {
    global: { plugins: [i18n], stubs: { Teleport: true } },
    props: { open: true, gameKey: 'web|room|game', detail: detail as GameDetail, log },
  })
}

describe('CurrentRoundImageModal', () => {
  it('drafts the default prompt from scene and narration content only', () => {
    const wrapper = mountModal(
      { scene: '雾港码头', round_number: 5 },
      [{ round: 4, gm_response: 'The party regroups inside the lighthouse.' }],
    )
    const prompt = wrapper.get('textarea').element.value
    expect(prompt).toContain('雾港码头')
    expect(prompt).toContain('The party regroups inside the lighthouse.')
    expect(prompt).not.toContain('第4轮')
  })

  it('keeps style and composition wording out of the client draft', () => {
    const wrapper = mountModal({ scene: '雾港码头', round_number: 5 }, [])
    const prompt = wrapper.get('textarea').element.value
    expect(prompt).toBe('雾港码头')
  })

  it('truncates long narration at the server-side context limit', () => {
    const longNarration = '雾'.repeat(2500)
    const wrapper = mountModal(
      { scene: '雾港码头', round_number: 5 },
      [{ round: 4, gm_response: longNarration }],
    )
    const prompt = wrapper.get('textarea').element.value
    expect(prompt).toBe(`雾港码头\n${'雾'.repeat(1600)}`)
  })

  it('emits the target round and manual payload on generate', async () => {
    const wrapper = mountModal(
      { scene: '雾港码头', round_number: 5 },
      [{ round: 4, gm_response: 'The party regroups inside the lighthouse.' }],
    )
    await wrapper.get('button.primary').trigger('click')
    const payload = wrapper.emitted('generate')?.[0]?.[0] as { prompt: string; round: number; panels: unknown[]; use_avatar_references: boolean }
    expect(payload.round).toBe(4)
    expect(payload.panels).toEqual([])
    expect(payload.use_avatar_references).toBe(false)
    expect(payload.prompt).toContain('The party regroups inside the lighthouse.')
  })
})

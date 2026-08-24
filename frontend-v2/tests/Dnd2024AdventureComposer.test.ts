import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ submit: vi.fn() }))

vi.mock('../src/features/rulesets/dnd2024/api', () => ({
  submitRulesetAdventureAction: mocks.submit,
}))

import Dnd2024AdventureComposer from '../src/features/rulesets/dnd2024/campaign/Dnd2024AdventureComposer.vue'

describe('Dnd2024AdventureComposer', () => {
  beforeEach(() => {
    mocks.submit.mockReset().mockResolvedValue({
      ok: true,
      narration: '守灯人压低声音，请你先看看沾泥的窗沿。',
      gameplay: {},
      available_actions: [],
    })
  })

  it('gives plain-language examples and submits an idempotent declaration', async () => {
    const wrapper = mount(Dnd2024AdventureComposer, {
      props: { gameKey: 'web|adventure|bot', language: 'zh-CN' },
    })

    expect(wrapper.text()).toContain('不用懂术语')
    expect(wrapper.text()).toContain('直接说人话')
    await wrapper.get('.example-row button').trigger('click')
    await wrapper.get('.adventure-submit').trigger('click')
    await flushPromises()

    expect(mocks.submit).toHaveBeenCalledOnce()
    expect(mocks.submit.mock.calls[0][0]).toBe('web|adventure|bot')
    expect(mocks.submit.mock.calls[0][1]).toMatchObject({
      mode: 'act',
      text: '我仔细观察门边有没有脚印。',
    })
    expect(mocks.submit.mock.calls[0][1].operation_id).toBeTruthy()
    expect(wrapper.text()).toContain('守灯人压低声音')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('turns model configuration failures into an actionable settings link', async () => {
    mocks.submit.mockRejectedValueOnce(new Error('尚未配置模型 API，请先前往设置页。'))
    const wrapper = mount(Dnd2024AdventureComposer, {
      props: { gameKey: 'web|adventure|bot', language: 'zh-CN' },
    })

    await wrapper.get('.example-row button').trigger('click')
    await wrapper.get('.adventure-submit').trigger('click')
    await flushPromises()

    expect(wrapper.get('.composer-error').text()).toContain('尚未配置模型 API')
    expect(wrapper.get('.composer-error a').attributes('href')).toBe('#/settings')
    expect(wrapper.get('.composer-error a').text()).toContain('打开设置页')
  })
})

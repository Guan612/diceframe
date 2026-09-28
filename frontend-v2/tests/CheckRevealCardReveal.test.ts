import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import CheckRevealCard from '../src/components/play/CheckRevealCard.vue'
import { i18n } from '../src/i18n'

describe('CheckRevealCard click-to-reveal presentation', () => {
  beforeEach(() => { i18n.global.locale.value = 'zh-CN' })

  it('masks the result and offers the shared reveal button in click mode', async () => {
    const wrapper = mount(CheckRevealCard, {
      global: { plugins: [i18n] },
      props: {
        check: {
          check_id: 'c6', actor_name: '米拉', label: '攻击检定', dice: 'd20',
          roll: 18, rolls: [18], modifier: 5, total: 23, dc: 15,
          verdict: '成功', is_critical: true,
        },
        clickMode: true,
        reveal: null,
        canReveal: true,
      },
    })
    // 未揭示：机械状态已落盘，但表现层遮罩，不显示结果与详情。
    expect(wrapper.text()).toContain('待揭示')
    expect(wrapper.text()).not.toContain('23')
    expect(wrapper.text()).not.toContain('大成功')
    expect(wrapper.find('details').exists()).toBe(false)
    const button = wrapper.get('button')
    expect(button.text()).toContain('点击揭示骰子')
    await button.trigger('click')
    const emitted = wrapper.emitted('reveal')?.[0]?.[0] as { check_id?: string } | undefined
    expect(emitted?.check_id).toBe('c6')
  })

  it('shows a waiting hint instead of a button for non-revealers', () => {
    const wrapper = mount(CheckRevealCard, {
      global: { plugins: [i18n] },
      props: {
        check: { check_id: 'c7', actor_name: '米拉', label: '检定', dice: 'd20', roll: 9, verdict: '失败' },
        clickMode: true,
        reveal: null,
        canReveal: false,
      },
    })
    expect(wrapper.text()).toContain('等待揭示')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('unmasks with a revealed-by caption once the record arrives', async () => {
    const wrapper = mount(CheckRevealCard, {
      global: { plugins: [i18n] },
      props: {
        check: { check_id: 'c8', actor_name: '米拉', label: '检定', dice: 'd20', roll: 9, verdict: '失败' },
        clickMode: true,
        reveal: null,
        canReveal: false,
      },
    })
    expect(wrapper.text()).toContain('待揭示')
    await wrapper.setProps({ reveal: { by: 'gm', at: '2026-09-28T12:00:00Z' }, revealerName: '阿尔登' })
    expect(wrapper.text()).not.toContain('待揭示')
    expect(wrapper.text()).toContain('d20=9')
    expect(wrapper.text()).toContain('由 阿尔登 揭示')
  })

  it('auto mode ignores the reveal state entirely', () => {
    const wrapper = mount(CheckRevealCard, {
      global: { plugins: [i18n] },
      props: {
        check: { check_id: 'c9', actor_name: '米拉', label: '检定', dice: 'd20', roll: 14, total: 14, verdict: '成功' },
      },
    })
    expect(wrapper.text()).toContain('成功')
    expect(wrapper.text()).not.toContain('待揭示')
    expect(wrapper.find('button').exists()).toBe(false)
  })
})

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CheckRevealCard from '../src/components/play/CheckRevealCard.vue'
import { i18n } from '../src/i18n'

describe('CheckRevealCard', () => {
  beforeEach(() => { i18n.global.locale.value = 'zh-CN' })

  it('renders a rule-aware d20 result and details', () => {
    const wrapper = mount(CheckRevealCard, {
      global: { plugins: [i18n] },
      props: {
        check: {
          check_id: 'c1', actor_name: '阿岚', label: '力量检定', dice: 'd20',
          roll: 14, rolls: [14], modifier: 3, total: 17, dc: 15,
          verdict: '成功', is_critical: false, is_fumble: false,
        },
      },
    })
    expect(wrapper.text()).toContain('d20=14 + 3 = 17 / DC 15')
    expect(wrapper.text()).toContain('成功')
    expect(wrapper.get('article').attributes('aria-label')).toContain('阿岚')
    expect(wrapper.find('details').text()).toContain('14')
    expect(wrapper.find('details').text()).toContain('d20=14 + 3 = 17 / DC 15')
  })

  it('reveals the server result after the roll animation', async () => {
    vi.useFakeTimers()
    const wrapper = mount(CheckRevealCard, {
      global: { plugins: [i18n] },
      props: {
        animate: true,
        check: {
          check_id: 'c2', actor_name: '白露', label: '潜行检定', dice: 'd100',
          roll: 1, threshold: 65, verdict: '大成功', is_critical: true,
        },
      },
    })
    expect(wrapper.text()).toContain('掷骰中')
    await vi.advanceTimersByTimeAsync(720)
    expect(wrapper.text()).toContain('d100=1 / 65%')
    expect(wrapper.text()).toContain('大成功')
    vi.useRealTimers()
  })
})

import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import CheckRevealCard from '../src/components/play/CheckRevealCard.vue'

vi.mock('../src/composables/useLocale', () => ({
  useLocale: () => ({
    t: (key: string, params?: Record<string, unknown>) => params ? `${key}:${JSON.stringify(params)}` : key,
  }),
}))

describe('CheckRevealCard', () => {
  it('renders a rule-aware d20 result and details', () => {
    const wrapper = mount(CheckRevealCard, {
      props: {
        check: {
          check_id: 'c1', actor_name: '阿岚', label: '力量检定', dice: 'd20',
          roll: 14, rolls: [14], modifier: 3, total: 17, dc: 15,
          verdict: '成功', is_critical: false, is_fumble: false,
        },
      },
    })
    expect(wrapper.text()).toContain('d20=14 + 3 = 17 / DC 15')
    expect(wrapper.classes()).toContain('success')
    expect(wrapper.text()).toContain('checkSuccess')
    expect(wrapper.find('details').text()).toContain('checkDiceFaces:{"rolls":"14"}')
    expect(wrapper.find('details').text()).toContain('checkCalculation:{"calculation":"d20=14 + 3 = 17 / DC 15"}')
    expect(wrapper.find('details').text()).toContain('checkVerdictDetail:{"verdict":"checkSuccess"}')
  })

  it('reveals the server result after the roll animation', async () => {
    vi.useFakeTimers()
    const wrapper = mount(CheckRevealCard, {
      props: {
        animate: true,
        check: {
          check_id: 'c2', actor_name: '白露', label: '潜行检定', dice: 'd100',
          roll: 1, threshold: 65, verdict: '大成功', is_critical: true,
        },
      },
    })
    expect(wrapper.text()).toContain('diceRolling')
    await vi.advanceTimersByTimeAsync(720)
    expect(wrapper.text()).toContain('d100=1 / 65%')
    expect(wrapper.classes()).toContain('critical')
    vi.useRealTimers()
  })
})

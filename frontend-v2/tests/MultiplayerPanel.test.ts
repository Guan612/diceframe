import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import MultiplayerPanel from '../src/components/play/MultiplayerPanel.vue'

describe('MultiplayerPanel party rest status', () => {
  it('shows shared readiness and opens the character center for a waiting player', async () => {
    i18n.global.locale.value = 'zh-CN'
    const wrapper = mount(MultiplayerPanel, {
      global: { plugins: [i18n] },
      props: {
        players: [
          { user_id: 'hero-1', character_name: '阿刁' },
          { user_id: 'hero-2', character_name: '调调' },
        ],
        detail: {
          game_key: 'web|room|bot',
          gm_uid: 'hero-1',
          solo_mode: false,
          rest_session: {
            active: true,
            status: 'collecting',
            rest: 'short',
            ready_count: 1,
            active_count: 2,
            participants: [
              { user_id: 'hero-1', character_name: '阿刁', status: 'submitted' },
              { user_id: 'hero-2', character_name: '调调', status: 'waiting' },
            ],
          },
        },
        isGm: false,
        currentUserId: 'hero-2',
      },
    })

    const alert = wrapper.get('[role="status"]')
    expect(alert.text()).toContain('队伍短休')
    expect(alert.text()).toContain('已准备 1/2')
    expect(alert.text()).toContain('阿刁 · 已准备')
    expect(alert.text()).toContain('调调 · 等待')
    expect(alert.get('button').text()).toBe('选择生命骰并准备')

    await alert.get('button').trigger('click')
    expect(wrapper.emitted('open-character-center')).toHaveLength(1)
  })

  it('does not add a rest alert outside an active party rest', () => {
    const wrapper = mount(MultiplayerPanel, {
      global: { plugins: [i18n] },
      props: {
        players: [{ user_id: 'hero-1', character_name: '阿刁' }],
        detail: { game_key: 'web|room|bot', solo_mode: false },
        isGm: false,
        currentUserId: 'hero-1',
      },
    })

    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })
})

import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PortraitImage from '../src/components/PortraitImage.vue'

vi.mock('../src/api/avatars', () => ({
  uploadedAvatarUrl: vi.fn(async () => 'blob:mock-avatar'),
}))

describe('PortraitImage', () => {
  it('renders an empty placeholder instead of an auto-assigned portrait when none chosen', () => {
    const wrapper = mount(PortraitImage, {
      props: { name: '爱丽丝', size: 64 },
    })
    expect(wrapper.find('.portrait-empty').exists()).toBe(true)
    expect(wrapper.find('.portrait-empty').text()).toBe('爱丽')
    expect(wrapper.find('.portrait-builtin').exists()).toBe(false)
  })

  it('renders the builtin image for a valid explicit builtin portrait', () => {
    const wrapper = mount(PortraitImage, {
      props: { name: '鲍勃', size: 64, portrait: { kind: 'builtin', id: 'dnd5e:0' }, ruleId: 'dnd5e' },
    })
    expect(wrapper.find('.portrait-builtin').exists()).toBe(true)
    expect(wrapper.find('.portrait-empty').exists()).toBe(false)
    expect(wrapper.find('.portrait-builtin').attributes('style')).toContain('avatars/v3/dnd5e/realistic-1.jpg')
    expect(wrapper.find('.portrait-builtin').attributes('style')).toContain('background-size: cover')
  })

  it('renders an empty placeholder for an invalid builtin id instead of falling back to auto-assignment', () => {
    const wrapper = mount(PortraitImage, {
      props: { name: '卡罗尔', size: 64, portrait: { kind: 'builtin', id: 'dnd5e:999' }, ruleId: 'dnd5e' },
    })
    expect(wrapper.find('.portrait-empty').exists()).toBe(true)
    expect(wrapper.find('.portrait-builtin').exists()).toBe(false)
  })

  it('renders a declared content-pack portrait through the plugin asset endpoint', () => {
    const wrapper = mount(PortraitImage, {
      props: {
        name: 'Mira',
        size: 64,
        portrait: {
          kind: 'plugin',
          plugin_id: 'portrait pack',
          path: 'assets/portraits/mira one.webp',
        },
      },
    })

    expect(wrapper.find('img').attributes('src')).toBe(
      '/api/plugins/assets/portrait%20pack/assets/portraits/mira%20one.webp',
    )
    expect(wrapper.find('.portrait-empty').exists()).toBe(false)
  })
})

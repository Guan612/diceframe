import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PortraitPicker from '../src/components/admin/PortraitPicker.vue'
import { i18n } from '../src/i18n'

vi.mock('../src/api/avatars', () => ({
  uploadAvatar: vi.fn(),
}))

vi.mock('../src/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}))

describe('PortraitPicker', () => {
  it('emits an explicit null when the user chooses not to display an avatar', async () => {
    const wrapper = mount(PortraitPicker, {
      props: {
        modelValue: { kind: 'upload', asset_id: 'old-avatar' },
        name: 'Test Character',
        ruleId: 'freeform_fantasy',
      },
      global: {
        plugins: [i18n],
        stubs: { PortraitImage: true },
      },
    })

    await wrapper.get('.portrait-auto').trigger('click')

    expect(wrapper.emitted('update:modelValue')).toEqual([[null]])
  })
})

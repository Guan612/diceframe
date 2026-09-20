import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LorebookSidebar from '../src/features/lorebook/LorebookSidebar.vue'

describe('LorebookSidebar', () => {
  it('uses the selected active id instead of assuming the primary book', () => {
    const wrapper = mount(LorebookSidebar, {
      props: {
        books: [
          { id: 'primary', name: 'Primary', primary: true },
          { id: 'secondary', name: 'Secondary' },
        ],
        activeId: 'secondary',
      },
    })
    const buttons = wrapper.findAll('button')
    expect(buttons[0].classes()).not.toContain('active')
    expect(buttons[1].classes()).toContain('active')
  })
})

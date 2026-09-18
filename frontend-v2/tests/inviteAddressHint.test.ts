import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { i18n } from '../src/i18n'
import InviteQrModal from '../src/features/play/InviteQrModal.vue'

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))
// 弹窗本体不依赖 NaiveUI 的 MessageProvider；这里只要一个不抛错的 toast。
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))

function render(link: string) {
  return mount(InviteQrModal, {
    // 二维码本身与本文件无关（qrcode-generator 在 jsdom 下不可用），stub 掉。
    global: { plugins: [i18n], stubs: { QrCode: true } },
    props: { link, title: '邀请链接' },
  })
}

describe('invite address guidance', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    push.mockClear()
  })

  it('explains that friends must be able to reach the address', () => {
    const wrapper = render('https://table.example/#/join?game=web%7Croom%7Cbot')

    const hint = wrapper.get('.invite-address-hint')
    // 局域网 / 异地公网或内网穿透 / 分享地址 三个语义都要在。
    expect(hint.text()).toContain('局域网')
    expect(hint.text()).toContain('内网穿透')
    expect(hint.text()).toContain('访问')
  })

  it('links to the existing sharing-address settings', async () => {
    const wrapper = render('https://table.example/#/join?game=web%7Croom%7Cbot')

    await wrapper.get('.invite-address-settings').trigger('click')

    expect(push).toHaveBeenCalledWith({ name: 'settings' })
    // 跳转前先关掉弹窗，避免设置页被盖住。
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('warns only when the link is reachable from this machine alone', () => {
    const local = render('http://localhost:8080/#/join?game=web%7Croom%7Cbot')
    expect(local.find('.invite-address-local').exists()).toBe(true)

    const loopback = render('http://127.0.0.1:8080/#/join?game=web%7Croom%7Cbot')
    expect(loopback.find('.invite-address-local').exists()).toBe(true)

    // 局域网地址是合法用法，不该被警告。
    const lan = render('http://192.168.1.20:8080/#/join?game=web%7Croom%7Cbot')
    expect(lan.find('.invite-address-local').exists()).toBe(false)

    const publicUrl = render('https://table.example/#/join?game=web%7Croom%7Cbot')
    expect(publicUrl.find('.invite-address-local').exists()).toBe(false)
  })

  it('never blocks copying the link', async () => {
    const wrapper = render('http://localhost:8080/#/join?game=web%7Croom%7Cbot')

    // 即使出现"仅本机可访问"的提示，复制按钮仍在，且没有任何强制确认。
    const copyButton = wrapper.get('.actions .primary')
    expect(copyButton.text()).toBe('复制链接')
    expect(copyButton.attributes('disabled')).toBeUndefined()
  })
})

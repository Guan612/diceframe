import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({
  networkAddresses: vi.fn(),
  publicBaseUrl: '',
  backendUrl: '',
  origin: 'https://table.example',
}))

vi.mock('../src/api/pairing', () => ({
  pairingApi: { networkAddresses: mocks.networkAddresses },
}))
vi.mock('../src/api/connection', async (original) => ({
  ...(await original<typeof import('../src/api/connection')>()),
  currentBackendUrl: () => mocks.backendUrl,
}))
// jsdom 的 window.location 不可重定义；前端 origin 从 shareLink 统一读，这里换掉它。
vi.mock('../src/utils/shareLink', async (original) => ({
  ...(await original<typeof import('../src/utils/shareLink')>()),
  currentOrigin: () => mocks.origin,
}))
vi.mock('../src/stores/useSettingsStore', () => ({
  useSettingsStore: () => ({
    config: { public_base_url: mocks.publicBaseUrl },
    loading: false,
    load: vi.fn(),
  }),
}))
const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))
// 弹窗本体不依赖 NaiveUI 的 MessageProvider；这里只要一个不抛错的 toast。
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))

import InviteQrModal from '../src/features/play/InviteQrModal.vue'

async function render(user?: string) {
  const wrapper = mount(InviteQrModal, {
    // 二维码本身与本文件无关（qrcode-generator 在 jsdom 下不可用），stub 掉。
    global: { plugins: [i18n], stubs: { Teleport: true, QrCode: true } },
    props: { gameKey: 'web|room|bot', user, title: '邀请链接' },
  })
  await flushPromises()
  return wrapper
}

function setOrigin(origin: string) {
  mocks.origin = origin
}

describe('invite address guidance', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    push.mockClear()
    mocks.publicBaseUrl = ''
    mocks.backendUrl = ''
    mocks.networkAddresses.mockReset().mockResolvedValue({ addresses: [] })
    setOrigin('https://table.example')
  })

  it('explains that friends must be able to reach the address', async () => {
    const wrapper = await render()

    const hint = wrapper.get('.invite-address-hint')
    // 局域网 / 异地公网或内网穿透 / 分享地址 三个语义都要在。
    expect(hint.text()).toContain('局域网')
    expect(hint.text()).toContain('内网穿透')
    expect(hint.text()).toContain('访问')
  })

  it('links to the existing sharing-address settings', async () => {
    const wrapper = await render()

    await wrapper.get('.invite-address-settings').trigger('click')

    expect(push).toHaveBeenCalledWith({ name: 'settings' })
    // 跳转前先关掉弹窗，避免设置页被盖住。
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('warns only when the selected address is reachable from this machine alone', async () => {
    // 探测不到别的地址时，本机 origin 就是唯一候选。
    setOrigin('http://localhost:8080')
    expect((await render()).find('.invite-address-local').exists()).toBe(true)

    setOrigin('http://127.0.0.1:8080')
    expect((await render()).find('.invite-address-local').exists()).toBe(true)

    // 局域网地址是合法用法，不该被警告。
    setOrigin('http://192.168.1.20:8080')
    expect((await render()).find('.invite-address-local').exists()).toBe(false)

    setOrigin('https://table.example')
    expect((await render()).find('.invite-address-local').exists()).toBe(false)
  })

  it('prefers a reachable LAN address over the local-only origin', async () => {
    // 服务端按「局域网优先、回环垫底」给出 host。
    mocks.networkAddresses.mockResolvedValue({
      addresses: [
        { host: '192.168.1.20', url: 'http://192.168.1.20:8000' },
        { host: '127.0.0.1', url: 'http://127.0.0.1:8000' },
      ],
    })
    setOrigin('http://localhost:5173')

    const wrapper = await render()

    // 端口沿用浏览器打开前端用的那个，只换 host——独立前端与后端不同端口。
    expect(wrapper.get('.invite-link').text()).toContain('http://192.168.1.20:5173/')
    expect(wrapper.find('.invite-address-local').exists()).toBe(false)
  })

  it('keeps an explicitly configured sharing address first', async () => {
    mocks.publicBaseUrl = 'https://trpg.example.com'
    mocks.networkAddresses.mockResolvedValue({
      addresses: [{ host: '192.168.1.20', url: 'http://192.168.1.20:8000' }],
    })
    setOrigin('http://localhost:5173')

    const wrapper = await render()

    expect(wrapper.get('.invite-link').text()).toContain('https://trpg.example.com/')
  })

  it('moves the backend server param onto the same host as the join address', async () => {
    // 独立前端部署：玩家的设备既要打得开前端，也要连得上后端。
    mocks.backendUrl = 'http://localhost:10022'
    mocks.networkAddresses.mockResolvedValue({
      addresses: [{ host: '192.168.1.20', url: 'http://192.168.1.20:10022' }],
    })
    setOrigin('http://localhost:5173')

    const link = (await render()).get('.invite-link').text()

    expect(link).toContain('http://192.168.1.20:5173/')
    expect(decodeURIComponent(link)).toContain('server=http://192.168.1.20:10022')
  })

  it('carries the player id for a takeover link', async () => {
    const link = (await render('player_1')).get('.invite-link').text()

    expect(decodeURIComponent(link)).toContain('user=player_1')
  })

  it('never blocks copying the link', async () => {
    setOrigin('http://localhost:8080')
    const wrapper = await render()

    // 即使出现"仅本机可访问"的提示，复制按钮仍在，且没有任何强制确认。
    const copyButton = wrapper.get('.actions .primary')
    expect(copyButton.text()).toBe('复制链接')
    expect(copyButton.attributes('disabled')).toBeUndefined()
  })

  it('falls back to this machine when the candidate list is refused', async () => {
    // /api/system/network 仅对 owner 会话开放；403 不该让二维码出不来。
    mocks.networkAddresses.mockRejectedValue(new Error('需要管理员会话'))
    setOrigin('http://localhost:5173')

    const wrapper = await render()

    expect(wrapper.get('.invite-link').text()).toContain('http://localhost:5173/')
  })
})

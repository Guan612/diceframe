import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LorebookView from '../src/features/lorebook/LorebookView.vue'
import { i18n } from '../src/i18n'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
}))

vi.mock('../src/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/api/client')>()
  return { ...actual, api: mocks.api, errorMessage: (cause: unknown) => String((cause as Error)?.message || cause) }
})
vi.mock('../src/peer/game/bridge', () => ({
  activePeerGameClient: () => null,
  setActivePeerGameClient: vi.fn(),
}))
vi.mock('../src/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))
vi.mock('../src/composables/useConfirm', () => ({
  useConfirm: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

const worlds = {
  worlds: [{ id: 'w1', name: '测试世界', language: 'zh-CN', entry_count: 3 }],
}

const games = {
  games: [{ game_key: 'g1', world_id: 'w1', language: 'zh-CN' }],
}

const characters = {
  players: [
    { user_id: 'u1', character_name: '莱拉' },
    { user_id: 'u2', character_name: '布兰' },
  ],
  rule_meta: {},
}

const lorebook = {
  entries: [
    { id: 'a', world_id: 'w1', name: '城门守卫', type: 'npc', content: '公开背景', visible_to: ['public'] },
    { id: 'b', world_id: 'w1', name: '秘血教派', type: 'faction', content: '莱拉的私人线索', visible_to: ['莱拉'] },
    { id: 'c', world_id: 'w1', name: '幕后黑手', type: 'npc', content: 'GM 秘密', visible_to: [] },
  ],
}

function previewFor(path: string) {
  const params = new URLSearchParams(path.split('?')[1] || '')
  const viewer = params.get('viewer') || 'gm'
  const projections = {
    a: { visible: true, audience: 'public', subjects: [] },
    b: { visible: viewer === 'gm' || viewer === 'u1', audience: 'character', subjects: ['莱拉'] },
    c: { visible: viewer === 'gm', audience: 'gm', subjects: [] },
  }
  const visible = Object.values(projections).filter(p => p.visible).length
  return {
    ok: true,
    world_id: 'w1',
    viewer: { kind: viewer === 'gm' || viewer === 'party' ? viewer : 'character', uid: viewer },
    projections,
    summary: { total: 3, visible, public: 1, character_only: 1, gm_secret: 1 },
  }
}

function mountView() {
  return mount(LorebookView, { global: { plugins: [i18n] } })
}

describe('LorebookView perspective inspector', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('currentGame', 'g1')
    i18n.global.locale.value = 'zh-CN'
    mocks.api.mockReset()
    mocks.api.mockImplementation(async (path: string) => {
      const p = String(path)
      if (p.includes('/preview')) return previewFor(p)
      if (p.includes('/characters')) return characters
      if (p.includes('/games')) return games
      if (p.includes('/lorebook/')) return lorebook
      if (p.includes('/worlds')) return worlds
      throw new Error(`unexpected path ${p}`)
    })
  })

  afterEach(() => {
    document.body.innerHTML = ''
    vi.unstubAllGlobals()
  })

  function stubNarrowViewport() {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  }

  it('collapses the inspector by default on narrow screens and opens on demand', async () => {
    stubNarrowViewport()
    const wrapper = mountView()
    await flushPromises()
    await flushPromises()

    expect(wrapper.find('.lore-perspective-inspector').exists()).toBe(false)
    expect(wrapper.find('.lore-inspector-backdrop').exists()).toBe(false)

    const toggle = wrapper.findAll('.lore-header-actions button').find(b => b.text() === '视角')
    await toggle!.trigger('click')
    expect(wrapper.find('.lore-perspective-inspector').exists()).toBe(true)
    expect(wrapper.find('.lore-inspector-backdrop').exists()).toBe(true)

    await wrapper.find('.lore-inspector-backdrop').trigger('click')
    expect(wrapper.find('.lore-perspective-inspector').exists()).toBe(false)
  })

  it('renders audience badges and the summary from backend projections only', async () => {
    const wrapper = mountView()
    await flushPromises()
    await flushPromises()

    const badges = wrapper.findAll('.lore-visibility-badge').map(b => b.text())
    expect(badges).toContain('全队已知')
    expect(badges).toContain('仅莱拉可知')
    expect(badges).toContain('GM 秘密')

    const inspector = wrapper.find('.lore-perspective-inspector')
    expect(inspector.text()).toContain('3 / 3')
    const viewerButtons = wrapper.findAll('.lore-viewer-options button').map(b => b.text())
    expect(viewerButtons).toEqual(['GM 全知', '全队', '莱拉', '布兰'])
  })

  it('switches the viewer with canonical ids and game context', async () => {
    const wrapper = mountView()
    await flushPromises()
    await flushPromises()

    const lairaButton = wrapper.findAll('.lore-viewer-options button').find(b => b.text() === '莱拉')
    await lairaButton!.trigger('click')
    await flushPromises()

    const previewCalls = mocks.api.mock.calls.map(call => String(call[0])).filter(p => p.includes('/preview'))
    expect(previewCalls.some(p => p.includes('viewer=u1') && p.includes('game_key=g1'))).toBe(true)
    // 莱拉视角：公开条目 + 自己的条目可见，GM 秘密不可见
    expect(wrapper.find('.lore-summary-list').text()).toContain('2 / 3')

    await wrapper.findAll('.lore-viewer-options button').find(b => b.text() === '全队')!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.lore-summary-list').text()).toContain('1 / 3')
  })

  it('filters the entry list by the current perspective', async () => {
    const wrapper = mountView()
    await flushPromises()
    await flushPromises()

    await wrapper.findAll('.lore-viewer-options button').find(b => b.text() === '全队')!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.lore-row')).toHaveLength(3)

    const filterButtons = wrapper.findAll('.lore-filter-options button')
    await filterButtons.find(b => b.text() === '此视角可见')!.trigger('click')
    expect(wrapper.findAll('.lore-row')).toHaveLength(1)
    expect(wrapper.find('.lore-row').text()).toContain('城门守卫')

    await filterButtons.find(b => b.text() === '此视角未知')!.trigger('click')
    const rows = wrapper.findAll('.lore-row')
    expect(rows).toHaveLength(2)
    expect(rows.map(r => r.text()).join(' ')).not.toContain('城门守卫')
  })

  it('selects an entry and shows its visibility in the inspector', async () => {
    const wrapper = mountView()
    await flushPromises()
    await flushPromises()

    const row = wrapper.findAll('.lore-row').find(r => r.text().includes('秘血教派'))!
    await row.trigger('click')
    const inspectorText = wrapper.find('.lore-perspective-inspector').text()
    expect(inspectorText).toContain('秘血教派')
    expect(inspectorText).toContain('仅莱拉可知')
    expect(inspectorText).toContain('当前视角可见')
  })

  it('locks character viewers in standalone mode', async () => {
    localStorage.setItem('currentGame', '')
    const wrapper = mountView()
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('未连接存档')
    const previewCalls = mocks.api.mock.calls.map(call => String(call[0])).filter(p => p.includes('/preview'))
    expect(previewCalls.length).toBeGreaterThan(0)
    expect(previewCalls.every(p => p.includes('viewer=gm'))).toBe(true)
  })
})

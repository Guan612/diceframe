import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import { readSeatToken } from '../src/utils/seatToken'

const GAME = 'web|room|bot'

const mocks = vi.hoisted(() => ({ api: vi.fn() }))

vi.mock('../src/api/client', () => ({
  api: mocks.api,
  errorMessage: (error: unknown) => String((error as Error)?.message || error),
}))
vi.mock('../src/composables/useConfirm', () => ({
  useConfirm: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import JoinView from '../src/features/player/JoinView.vue'

const Blank = { template: '<div />' }

function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/join', name: 'join', component: JoinView },
      { path: '/play', name: 'play', component: Blank },
      { path: '/', name: 'overview', component: Blank },
    ],
  })
}

function apiByPath(created: Record<string, unknown> = {}) {
  mocks.api.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path === `/games/${encodeURIComponent(GAME)}`) {
      return { game_key: GAME, world_name: 'World', multiplayer: { ready_players: [], waiting_players: [], away_players: [] } }
    }
    if (path.endsWith('/characters')) return { rule_attrs: [], rule_meta: {} }
    if (path.endsWith('/character-cards')) return { cards: [] }
    if (path.endsWith('/players') && init?.method === 'POST') return { ok: true, ...created }
    throw new Error(`unexpected ${path}`)
  })
}

async function mountAt(router: Router, query: Record<string, string>) {
  await router.push({ name: 'join', query })
  await router.isReady()
  const wrapper = mount(JoinView, {
    global: {
      plugins: [i18n, router],
      stubs: { PortraitPicker: true, BrandLogo: true, RulesetExperienceHost: true },
    },
  })
  await flushPromises()
  return wrapper
}

function playersCalls() {
  return mocks.api.mock.calls.filter(([path, init]) => String(path).endsWith('/players') && init?.method === 'POST')
}

describe('JoinView seat token', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    mocks.api.mockReset()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('stores a takeover link token, strips it from the URL, and rejoins with it', async () => {
    apiByPath({ user_id: 'p2', reused: true })
    const router = makeRouter()

    await mountAt(router, { game: GAME, share: '1', seat: 'tok-p2' })

    expect(readSeatToken(GAME)).toBe('tok-p2')
    const [call] = playersCalls()
    expect(call).toBeTruthy()
    expect(JSON.parse(String(call[1].body))).toEqual({ join_as_new: false })
    expect((call[1].headers as Record<string, string>)['X-Seat-Token']).toBe('tok-p2')
    expect(router.currentRoute.value.name).toBe('play')
    expect(router.currentRoute.value.query).toMatchObject({ game: GAME, user: 'p2', share: '1' })
    expect(JSON.stringify(router.currentRoute.value.query)).not.toContain('tok-p2')
    expect(localStorage.getItem('trpg_play_user_' + GAME)).toBe('p2')
  })

  it('treats an old uid-only takeover link as expired instead of rejoining that seat', async () => {
    apiByPath()
    const router = makeRouter()

    const wrapper = await mountAt(router, { game: GAME, share: '1', user: 'p2' })

    expect(playersCalls()).toHaveLength(0)
    expect(wrapper.text()).toContain(String(i18n.global.t('seatLinkExpired')))
    expect(readSeatToken(GAME)).toBe('')
  })

  it('stores the seat token returned for a newly created character', async () => {
    apiByPath({ user_id: 'p9', seat_token: 'tok-new' })
    const router = makeRouter()
    const wrapper = await mountAt(router, { game: GAME, share: '1' })

    await wrapper.get('.player-sheet-form input[maxlength="40"]').setValue('Aria')
    await wrapper.get('.player-sheet-form button.submit').trigger('click')
    await flushPromises()

    expect(readSeatToken(GAME)).toBe('tok-new')
    expect(router.currentRoute.value.query).toMatchObject({ user: 'p9' })
  })

  it('explains a missing seat credential when sent back from the play page', async () => {
    apiByPath()
    const router = makeRouter()

    const wrapper = await mountAt(router, { game: GAME, share: '1', notice: 'seat' })

    expect(wrapper.text()).toContain(String(i18n.global.t('seatTokenMissing')))
  })
})

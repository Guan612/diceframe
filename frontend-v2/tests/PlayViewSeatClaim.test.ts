import { flushPromises, mount } from '@vue/test-utils'
import type { Mock } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import type { GameDetail, Player } from '../src/api/types'
import { gameState } from './helpers/playViewGame'

const GAME_KEY = 'web|combat|bot'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  fetchRulesetAvailableActions: vi.fn(),
  resolveGameSceneImageUrl: vi.fn(),
}))

vi.mock('../src/composables/useGame', async () => {
  const helper = await import('./helpers/playViewGame')
  return { useGame: helper.useGame }
})
vi.mock('../src/api/client', () => ({
  api: mocks.api,
  apiBlob: vi.fn(),
  hasAccessToken: () => false,
  isNotFoundError: (error: unknown) => Boolean((error as { status?: number })?.status === 404),
}))
vi.mock('../src/api/rulesets', () => ({
  fetchRulesetAvailableActions: mocks.fetchRulesetAvailableActions,
}))
vi.mock('../src/api/sceneImages', () => ({
  fileToBase64: vi.fn(),
  resolveGameSceneImageUrl: mocks.resolveGameSceneImageUrl,
  revokeSceneImageUrl: vi.fn(),
  sceneImageStyle: () => ({}),
}))
vi.mock('../src/api/generatedImages', () => ({ generateCurrentRoundImage: vi.fn() }))
vi.mock('../src/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))
vi.mock('../src/composables/useConfirm', () => ({
  useConfirm: () => ({ confirm: vi.fn().mockResolvedValue(false) }),
}))
vi.mock('../src/stores/useSettingsStore', () => ({
  useSettingsStore: () => ({
    config: { public_base_url: '', imagegen_manual_scene: false, imagegen_auto_storyboard: false },
    loading: false,
    load: vi.fn(async () => undefined),
  }),
}))

import PlayView from '../src/features/play/PlayView.vue'

const STUBS = {
  Teleport: true,
  GameSidebar: true,
  KpQuestionDialog: true,
  MapBackgroundSettingsModal: true,
  RulesetPlayHost: true,
  DirectorProposalCard: true,
  GameTimeline: true,
  EconomyProposalCard: true,
  TableTalkFeed: true,
  GmToolbar: true,
  MultiplayerPanel: true,
  HealthPanel: true,
  ManualRollsPanel: true,
  MapWorkspace: true,
  SceneGalleryModal: true,
  CurrentRoundImageModal: true,
  PlayHelpCenter: true,
  InviteQrModal: true,
  GmChargeComposer: true,
  PortraitPicker: true,
  AdventureSceneImagePicker: true,
  RulesetCharacterCenterHost: true,
}

import { readSeatToken, storeSeatToken } from '../src/utils/seatToken'

async function mountPlayView(query: Record<string, string>) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'overview', component: { template: '<div />' } },
      { path: '/join', name: 'join', component: { template: '<div />' } },
      { path: '/characters', name: 'characters', component: { template: '<div />' } },
      { path: '/play', name: 'play', component: PlayView },
    ],
  })
  await router.push({ name: 'play', query })
  await router.isReady()
  const wrapper = mount(PlayView, { global: { plugins: [i18n, router], stubs: STUBS } })
  await flushPromises()
  return { wrapper, router }
}

const CLAIM_PATH = `/games/${encodeURIComponent(GAME_KEY)}/seat-token/claim`
const memberDetail = {
  game_key: GAME_KEY,
  state: 'active_action',
  multiplayer: { ready_players: [{ user_id: 'ally' }], waiting_players: [], away_players: [] },
} as unknown as GameDetail

function claimCalls() {
  return (mocks.api as unknown as Mock).mock.calls.filter(([path]) => path === CLAIM_PATH)
}

describe('PlayView seat token migration', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    gameState.detail.value = memberDetail
    gameState.players.value = [{ user_id: 'ally', character_name: 'Ally' } as Player]
    gameState.isGm.value = false
    gameState.userId.value = 'ally'
    gameState.currentGame.value = GAME_KEY
    ;(mocks.api as unknown as Mock).mockReset().mockImplementation(async (path: string) => {
      if (path === CLAIM_PATH) return { ok: true, user_id: 'ally', seat_token: 'tok-claimed' }
      if (path === `/games/${encodeURIComponent(GAME_KEY)}`) return memberDetail
      return {}
    })
    mocks.fetchRulesetAvailableActions.mockReset().mockResolvedValue({})
    mocks.resolveGameSceneImageUrl.mockReset().mockResolvedValue('')
  })

  afterEach(() => {
    localStorage.clear()
    document.body.innerHTML = ''
  })

  it('claims the seat token once for a player bound before seat tokens existed', async () => {
    const { wrapper, router } = await mountPlayView({ game: GAME_KEY, user: 'ally', share: '1' })

    expect(claimCalls()).toHaveLength(1)
    expect(readSeatToken(GAME_KEY)).toBe('tok-claimed')
    expect(router.currentRoute.value.name).toBe('play')
    wrapper.unmount()
  })

  it('does not claim again when this browser already holds the seat token', async () => {
    storeSeatToken(GAME_KEY, 'tok-existing')

    const { wrapper } = await mountPlayView({ game: GAME_KEY, user: 'ally', share: '1' })

    expect(claimCalls()).toHaveLength(0)
    expect(readSeatToken(GAME_KEY)).toBe('tok-existing')
    wrapper.unmount()
  })

  it('sends the player to join when the seat cannot be claimed here', async () => {
    localStorage.setItem('trpg_play_user_' + GAME_KEY, 'ally')
    ;(mocks.api as unknown as Mock).mockImplementation(async (path: string) => {
      if (path === CLAIM_PATH) throw Object.assign(new Error('exists'), { status: 409, code: 'SEAT_TOKEN_EXISTS' })
      if (path === `/games/${encodeURIComponent(GAME_KEY)}`) return memberDetail
      return {}
    })

    const { wrapper, router } = await mountPlayView({ game: GAME_KEY, user: 'ally', share: '1' })

    expect(router.currentRoute.value.name).toBe('join')
    expect(router.currentRoute.value.query).toMatchObject({ game: GAME_KEY, notice: 'seat' })
    expect(localStorage.getItem('trpg_play_user_' + GAME_KEY)).toBeNull()
    expect(readSeatToken(GAME_KEY)).toBe('')
    wrapper.unmount()
  })
})

import { flushPromises, mount } from '@vue/test-utils'
import type { Mock } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import type { GameDetail, Player } from '../src/api/types'
import { ApiError, errorMessage } from '../src/api/client'
import { cardAdoptionLocked } from '../src/utils/characterCards'
import { gameState } from './helpers/playViewGame'

const GAME_KEY = 'web|combat|bot'
const CARDS_PATH = `/games/${encodeURIComponent(GAME_KEY)}/character-cards`
const ADOPT_PATH = `/games/${encodeURIComponent(GAME_KEY)}/character/ally/adopt-card`

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('../src/composables/useGame', async () => {
  const helper = await import('./helpers/playViewGame')
  return { useGame: helper.useGame }
})
vi.mock('../src/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api/client')>()
  return {
    ApiError: actual.ApiError,
    errorMessage: actual.errorMessage,
    api: mocks.api,
    apiBlob: vi.fn(),
    hasAccessToken: () => false,
    isNotFoundError: () => false,
    retryOnRateLimit: <T>(request: () => Promise<T>) => request(),
  }
})
vi.mock('../src/api/rulesets', () => ({ fetchRulesetAvailableActions: vi.fn(async () => ({})) }))
vi.mock('../src/api/sceneImages', () => ({
  fileToBase64: vi.fn(),
  resolveGameSceneImageUrl: vi.fn(async () => ''),
  revokeSceneImageUrl: vi.fn(),
  sceneImageStyle: () => ({}),
}))
vi.mock('../src/api/generatedImages', () => ({ generateCurrentRoundImage: vi.fn() }))
vi.mock('../src/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: mocks.toastError, info: vi.fn(), warning: vi.fn() }),
}))
vi.mock('../src/composables/useConfirm', () => ({ useConfirm: () => ({ confirm: vi.fn() }) }))
vi.mock('../src/stores/useSettingsStore', () => ({
  useSettingsStore: () => ({
    config: { public_base_url: '', imagegen_manual_scene: false, imagegen_auto_storyboard: false },
    loading: false,
    load: vi.fn(async () => undefined),
  }),
}))

import PlayView from '../src/features/play/PlayView.vue'
import { storeSeatToken } from '../src/utils/seatToken'

const STUBS = {
  Teleport: true, GameSidebar: true, KpQuestionDialog: true, MapBackgroundSettingsModal: true,
  RulesetPlayHost: true, DirectorProposalCard: true, GameTimeline: true, EconomyProposalCard: true,
  TableTalkFeed: true, GmToolbar: true, MultiplayerPanel: true, HealthPanel: true,
  ManualRollsPanel: true, MapWorkspace: true, SceneGalleryModal: true, CurrentRoundImageModal: true,
  PlayHelpCenter: true, InviteQrModal: true, GmChargeComposer: true, PortraitPicker: true,
  AdventureSceneImagePicker: true, RulesetCharacterCenterHost: true,
}

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
  return wrapper
}

async function openCardLibrary(wrapper: Awaited<ReturnType<typeof mountPlayView>>) {
  const button = wrapper.findAll('button.play-secondary-action')
    .find(item => item.text() === i18n.global.t('characters'))
  expect(button).toBeTruthy()
  await button!.trigger('click')
  await flushPromises()
}

function adoptCalls() {
  return (mocks.api as unknown as Mock).mock.calls.filter(([path]) => path === ADOPT_PATH)
}

function detailWith(playStarted: boolean): GameDetail {
  return {
    game_key: GAME_KEY,
    state: playStarted ? 'active_action' : 'created',
    play_started: playStarted,
    gm_uid: 'gm',
    multiplayer: { ready_players: [{ user_id: 'ally' }], waiting_players: [], away_players: [] },
  } as unknown as GameDetail
}

describe('PlayView card adoption', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    gameState.players.value = [{ user_id: 'ally', character_name: 'Ally' } as Player]
    gameState.userId.value = 'ally'
    gameState.currentGame.value = GAME_KEY
    storeSeatToken(GAME_KEY, 'tok-ally')
    mocks.toastError.mockReset()
    ;(mocks.api as unknown as Mock).mockReset().mockImplementation(async (path: string) => {
      if (path === CARDS_PATH) return { cards: [{ id: 'card-1', character_name: 'Refill Hero', race: '人类', class: '游侠' }] }
      if (path === `/games/${encodeURIComponent(GAME_KEY)}`) return gameState.detail.value
      return {}
    })
  })

  afterEach(() => {
    localStorage.clear()
    document.body.innerHTML = ''
  })

  it('disables adoption for a player once the game has started and explains why', async () => {
    gameState.detail.value = detailWith(true)
    gameState.isGm.value = false
    const wrapper = await mountPlayView({ game: GAME_KEY, user: 'ally', share: '1' })

    await openCardLibrary(wrapper)

    const hint = wrapper.find('.adopt-locked-hint')
    expect(hint.exists()).toBe(true)
    expect(hint.text()).toContain('开局后只能由 GM 为角色套用卡片')
    const choice = wrapper.find('button.card-choice')
    expect(choice.attributes('disabled')).toBeDefined()
    await choice.trigger('click')
    await flushPromises()
    expect(adoptCalls()).toHaveLength(0)
    wrapper.unmount()
  })

  it('lets a player adopt in the lobby before the game starts', async () => {
    gameState.detail.value = detailWith(false)
    gameState.isGm.value = false
    const wrapper = await mountPlayView({ game: GAME_KEY, user: 'ally', share: '1' })

    await openCardLibrary(wrapper)

    expect(wrapper.find('.adopt-locked-hint').exists()).toBe(false)
    await wrapper.find('button.card-choice').trigger('click')
    await flushPromises()
    expect(adoptCalls()).toHaveLength(1)
    wrapper.unmount()
  })

  it('keeps adoption for the GM after start and localizes a server refusal', async () => {
    gameState.detail.value = detailWith(true)
    gameState.isGm.value = true
    ;(mocks.api as unknown as Mock).mockImplementation(async (path: string) => {
      if (path === CARDS_PATH) return { cards: [{ id: 'card-1', character_name: 'Refill Hero' }] }
      if (path === ADOPT_PATH) throw new ApiError('server text', 403, 'ADOPT_REQUIRES_GM')
      return {}
    })
    const wrapper = await mountPlayView({ game: GAME_KEY, user: 'ally' })

    await openCardLibrary(wrapper)

    expect(wrapper.find('.adopt-locked-hint').exists()).toBe(false)
    const choice = wrapper.find('button.card-choice')
    expect(choice.attributes('disabled')).toBeUndefined()
    await choice.trigger('click')
    await flushPromises()
    expect(adoptCalls()).toHaveLength(1)
    expect(mocks.toastError).toHaveBeenCalledWith('开局后只能由 GM 为角色套用卡片')
    wrapper.unmount()
  })
})

describe('card adoption rule', () => {
  it('locks only player-side callers after start', () => {
    expect(cardAdoptionLocked({ play_started: false }, { isGm: false })).toBe(false)
    expect(cardAdoptionLocked({ play_started: true }, { isGm: false })).toBe(true)
    expect(cardAdoptionLocked({ play_started: true }, { isGm: true })).toBe(false)
    // The owner previewing a seat with delegate on speaks for that player.
    expect(cardAdoptionLocked({ play_started: true }, { isGm: true, delegate: true })).toBe(true)
    expect(cardAdoptionLocked(null, { isGm: false })).toBe(false)
  })

  it('has a localized ADOPT_REQUIRES_GM message in every locale', () => {
    const previous = i18n.global.locale.value
    try {
      for (const locale of ['zh-CN', 'en', 'ja', 'de'] as const) {
        i18n.global.locale.value = locale
        const message = errorMessage(new ApiError('server text', 403, 'ADOPT_REQUIRES_GM'))
        expect(message).not.toBe('server text')
        expect(message).not.toContain('apiErrors.')
        expect(i18n.global.t('adoptRequiresGmHint')).not.toBe('adoptRequiresGmHint')
      }
    } finally {
      i18n.global.locale.value = previous
    }
  })
})

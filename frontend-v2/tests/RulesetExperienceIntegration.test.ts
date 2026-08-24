import { flushPromises, shallowMount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  professional: true,
  cards: [] as Array<Record<string, unknown>>,
  api: vi.fn(),
  push: vi.fn(),
  replace: vi.fn(),
}))

vi.mock('../src/api/client', () => ({
  api: mocks.api,
  errorMessage: (error: unknown) => String((error as Error)?.message || error),
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.push, replace: mocks.replace }),
  useRoute: () => ({ query: { game: 'web|join-test|web_bot' } }),
}))
vi.mock('../src/stores/useSettingsStore', () => ({
  useSettingsStore: () => ({
    config: { base_url: 'https://example.test', model: 'test', api_key: { configured: true } },
    error: '',
    load: vi.fn().mockResolvedValue(undefined),
  }),
}))
vi.mock('../src/composables/useToast', () => ({
  useToast: () => ({ info: vi.fn(), success: vi.fn(), error: vi.fn() }),
}))
vi.mock('../src/composables/useLocale', async () => {
  const { ref } = await import('vue')
  const locale = ref<'zh-CN' | 'en'>('zh-CN')
  return {
    useLocale: () => ({
      locale,
      setLocale: (next: 'zh-CN' | 'en') => { locale.value = next },
      t: (key: string) => key,
    }),
  }
})
vi.mock('../src/composables/useConfirm', () => ({
  useConfirm: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))
vi.mock('../src/composables/useBackgroundImages', () => ({
  ruleSceneUrl: () => '',
}))
vi.mock('../src/api/sceneImages', () => ({
  resolveSceneImageUrl: vi.fn().mockResolvedValue(''),
  revokeSceneImageUrl: vi.fn(),
  sceneImageStyle: () => ({}),
  uploadSceneImage: vi.fn(),
}))
vi.mock('../src/api/mapBackgrounds', () => ({
  mapBackgroundSelection: vi.fn(),
  uploadMapBackground: vi.fn(),
}))
vi.mock('../src/stores/gameContext', () => ({ rememberCurrentGame: vi.fn() }))
vi.mock('../src/peer/game/bridge', () => ({ activePeerGameClient: () => null }))

import CreateView from '../src/features/create/CreateView.vue'
import JoinView from '../src/features/player/JoinView.vue'

function runtimeMeta() {
  return {
    id: mocks.professional ? 'core:dnd2024' : 'core:legacy',
    version: 1,
    capabilities: {
      character_builder: mocks.professional ? 'professional' : 'legacy',
      versioned_state: mocks.professional,
      authoritative_intents: false,
      deterministic_combat: false,
      session_zero: false,
      tutorial_coach: false,
    },
  }
}

function installApiMock() {
  mocks.api.mockImplementation(async (path: string) => {
    if (path.startsWith('/world-templates')) {
      return { templates: [{ world_id: 'test-world', world_name: 'Test', default_rule: 'test-rule' }] }
    }
    if (path.startsWith('/rules?')) {
      return { rules: [{ rule_id: 'test-rule', rule_name: 'Test Rule', ruleset_runtime: runtimeMeta() }] }
    }
    if (path.startsWith('/rules/test-rule')) {
      return { rule: { rule_id: 'test-rule', attributes: [] }, ruleset_runtime: runtimeMeta() }
    }
    if (path === '/worlds') return { worlds: [] }
    if (path === '/character-cards') return { cards: mocks.cards }
    if (path.startsWith('/games/') && !path.includes('/characters') && !path.includes('/character-cards')) {
      return { game_key: 'web|join-test|web_bot', rule_id: 'test-rule', world_name: 'Test' }
    }
    if (path.includes('/characters')) {
      return {
        rule_attrs: [], rule_attrs_total: 60,
        rule_meta: { rule_id: 'test-rule', rule_name: 'Test Rule' },
        ruleset_runtime: runtimeMeta(),
      }
    }
    if (path.includes('/character-cards')) return { cards: [] }
    throw new Error(`Unexpected API request: ${path}`)
  })
}

describe('ruleset experience host integration', () => {
  beforeEach(() => {
    localStorage.clear()
    mocks.professional = true
    mocks.cards = []
    mocks.api.mockReset()
    mocks.push.mockReset()
    mocks.replace.mockReset()
    installApiMock()
  })

  it('uses the professional host from runtime capability in CreateView', async () => {
    const wrapper = shallowMount(CreateView, { global: { plugins: [createPinia()] } })
    await flushPromises()

    await wrapper.get('.create-actions .primary').trigger('click')
    await wrapper.get('.create-character-actions .primary').trigger('click')
    await flushPromises()

    expect(wrapper.findComponent({ name: 'RulesetExperienceHost' }).exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'CharacterWizard' }).exists()).toBe(false)
  })

  it('enters the created game after a professional character is finalized', async () => {
    const wrapper = shallowMount(CreateView, { global: { plugins: [createPinia()] } })
    await flushPromises()

    await wrapper.get('.create-actions .primary').trigger('click')
    await wrapper.get('.create-character-actions .primary').trigger('click')
    const host = wrapper.findComponent({ name: 'RulesetExperienceHost' })
    host.vm.$emit('submit', {
      character_name: '新手守护者',
      rule_id: 'test-rule',
      ruleset_character: { rule_binding: { runtime_id: 'core:dnd2024' } },
    })
    await wrapper.vm.$nextTick()
    await wrapper.get('.create-actions .primary').trigger('click')
    await wrapper.vm.$nextTick()
    await wrapper.get('.create-actions .primary').trigger('click')
    await flushPromises()

    expect(mocks.api).toHaveBeenCalledWith('/games/create', expect.objectContaining({ method: 'POST' }))
    expect(mocks.push).toHaveBeenLastCalledWith({
      name: 'play', query: { game: 'web|join-test|web_bot' },
    })
  })

  it('preserves a compatible professional card blueprint through game creation', async () => {
    mocks.cards = [{
      id: 'professional-card', character_name: '角色库守护者', rule_id: 'test-rule',
      ruleset_character: {
        rule_binding: { rule_id: 'test-rule', runtime_id: 'core:dnd2024' },
        build: { level: 1 },
      },
      rule_binding: { rule_id: 'test-rule', runtime_id: 'core:dnd2024' },
    }]
    const wrapper = shallowMount(CreateView, { global: { plugins: [createPinia()] } })
    await flushPromises()

    await wrapper.get('.create-actions .primary').trigger('click')
    await wrapper.findAll('.create-character-actions button')[1].trigger('click')
    wrapper.findComponent({ name: 'CharacterCardPicker' }).vm.$emit('pick', mocks.cards[0])
    await wrapper.vm.$nextTick()
    expect(wrapper.findComponent({ name: 'RulesetExperienceHost' }).exists()).toBe(false)

    await wrapper.get('.create-actions .primary').trigger('click')
    await wrapper.get('.create-actions .primary').trigger('click')
    await flushPromises()

    const createCall = mocks.api.mock.calls.find(call => call[0] === '/games/create')
    const body = JSON.parse(String(createCall?.[1]?.body || '{}'))
    expect(body.players[0].ruleset_character.rule_binding).toEqual({
      rule_id: 'test-rule', runtime_id: 'core:dnd2024',
    })
    expect(mocks.push).toHaveBeenLastCalledWith({
      name: 'play', query: { game: 'web|join-test|web_bot' },
    })
  })

  it('routes a same-rule legacy card into the professional review builder', async () => {
    mocks.cards = [{
      id: 'legacy-card', character_name: '旧卡迁移者', rule_id: 'test-rule',
      attributes: { str: 12 }, skills: [],
    }]
    const wrapper = shallowMount(CreateView, { global: { plugins: [createPinia()] } })
    await flushPromises()

    await wrapper.get('.create-actions .primary').trigger('click')
    await wrapper.findAll('.create-character-actions button')[1].trigger('click')
    wrapper.findComponent({ name: 'CharacterCardPicker' }).vm.$emit('pick', mocks.cards[0])
    await wrapper.vm.$nextTick()

    const host = wrapper.findComponent({ name: 'RulesetExperienceHost' })
    expect(host.exists()).toBe(true)
    expect(host.props('initial')).toMatchObject({ character_name: '旧卡迁移者' })
    expect(wrapper.findComponent({ name: 'CharacterWizard' }).exists()).toBe(false)
  })

  it('keeps the legacy wizard in CreateView when capability is legacy', async () => {
    mocks.professional = false
    const wrapper = shallowMount(CreateView, { global: { plugins: [createPinia()] } })
    await flushPromises()

    await wrapper.get('.create-actions .primary').trigger('click')
    await wrapper.get('.create-character-actions .primary').trigger('click')

    expect(wrapper.findComponent({ name: 'CharacterWizard' }).exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'RulesetExperienceHost' }).exists()).toBe(false)
  })

  it('uses the same embedded professional host on JoinView', async () => {
    const wrapper = shallowMount(JoinView, { global: { plugins: [createPinia()] } })
    await flushPromises()

    const host = wrapper.findComponent({ name: 'RulesetExperienceHost' })
    expect(host.exists()).toBe(true)
    expect(host.props('embedded')).toBe(true)
    expect(host.props('ruleId')).toBe('test-rule')
    expect(wrapper.find('.player-sheet-form').exists()).toBe(false)
  })

  it('keeps the legacy JoinView form when capability is legacy', async () => {
    mocks.professional = false
    const wrapper = shallowMount(JoinView, { global: { plugins: [createPinia()] } })
    await flushPromises()

    expect(wrapper.findComponent({ name: 'RulesetExperienceHost' }).exists()).toBe(false)
    expect(wrapper.find('.player-sheet-form').exists()).toBe(true)
  })
})

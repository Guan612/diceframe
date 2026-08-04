import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

// speechSynthesis 是浏览器 API，jsdom 下不存在，mock 它。
class MockSpeechSynthesisUtterance {
  text: string
  lang = ''
  rate = 1
  pitch = 1
  voice: unknown = null
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(text: string) { this.text = text }
}

const mocks = vi.hoisted(() => ({
  cancel: vi.fn(),
  speak: vi.fn(),
  getVoices: vi.fn(() => [{ lang: 'zh-CN', name: 'Mock 中文' }]),
  addEventListener: vi.fn(),
}))

vi.stubGlobal('speechSynthesis', {
  cancel: mocks.cancel,
  speak: mocks.speak,
  getVoices: mocks.getVoices,
  addEventListener: mocks.addEventListener,
})
vi.stubGlobal('SpeechSynthesisUtterance', MockSpeechSynthesisUtterance)

// jsdom 下 localStorage 可能因 opaque origin 抛 SecurityError，stub 一个内存实现。
const memStore = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (key: string) => memStore.get(key) ?? null,
  setItem: (key: string, value: string) => { memStore.set(key, String(value)) },
  removeItem: (key: string) => { memStore.delete(key) },
  clear: () => { memStore.clear() },
})

import { setTtsRate, speakingKey, ttsRate, ttsSpeak, ttsStop, ttsSupported, ttsToggle } from '../src/utils/tts'

describe('tts utils', () => {
  beforeEach(() => {
    mocks.cancel.mockReset()
    mocks.speak.mockReset()
    speakingKey.value = ''
    try { localStorage.removeItem('trpg_tts_rate') } catch { /* ignore */ }
  })

  afterEach(() => {
    ttsStop()
  })

  it('reports support when speechSynthesis exists', () => {
    expect(ttsSupported()).toBe(true)
  })

  it('uses the persisted rate preference when no explicit rate is passed', () => {
    setTtsRate(1.5)
    expect(ttsRate()).toBe(1.5)
    ttsSpeak('文本', 'gm:rate')
    const utterance = mocks.speak.mock.calls[0][0]
    expect(utterance.rate).toBe(1.5)
  })

  it('explicit rate overrides the persisted preference', () => {
    setTtsRate(1.5)
    ttsSpeak('文本', 'gm:rate2', { rate: 2 })
    const utterance = mocks.speak.mock.calls[0][0]
    expect(utterance.rate).toBe(2)
  })

  it('clamps the persisted rate into the 0.5–2.0 range', () => {
    setTtsRate(5)
    expect(ttsRate()).toBe(2)
    setTtsRate(0.1)
    expect(ttsRate()).toBe(0.5)
  })

  it('speaks and records the speaking key', () => {
    ttsSpeak('你好世界', 'gm:1', { lang: 'zh-CN' })
    expect(mocks.cancel).toHaveBeenCalled()
    expect(mocks.speak).toHaveBeenCalledOnce()
    expect(speakingKey.value).toBe('gm:1')
    const utterance = mocks.speak.mock.calls[0][0]
    expect(utterance.text).toBe('你好世界')
    expect(utterance.lang).toBe('zh-CN')
  })

  it('toggle speaks when idle, stops when already speaking', () => {
    ttsToggle('文本', 'act:u1')
    expect(mocks.speak).toHaveBeenCalledOnce()
    expect(speakingKey.value).toBe('act:u1')
    mocks.speak.mockClear()
    ttsToggle('文本', 'act:u1')
    expect(mocks.cancel).toHaveBeenCalled()
    expect(speakingKey.value).toBe('')
  })

  it('clear key when speech ends', () => {
    ttsSpeak('文本', 'gm:2')
    const utterance = mocks.speak.mock.calls[0][0]
    utterance.onend()
    expect(speakingKey.value).toBe('')
  })

  it('stop clears the speaking key', () => {
    ttsSpeak('文本', 'gm:3')
    ttsStop()
    expect(mocks.cancel).toHaveBeenCalled()
    expect(speakingKey.value).toBe('')
  })
})

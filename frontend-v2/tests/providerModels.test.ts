import { describe, expect, it, vi } from 'vitest'
import {
  catalogModelMainEligible,
  selectMainModelWithRollback,
  type CatalogSavedProvider,
} from '../src/utils/providerModels'

// 模型目录“设为主模型”的两个状态一致性契约：
// 1) 只认已持久化的 provider library（UI 草稿不算数）
// 2) 保存失败时把主模型字段回滚为点击前的值

describe('catalogModelMainEligible', () => {
  it('accepts persisted chat-capable models', () => {
    const saved = [{ id: 'provider-a', models: ['model-a', 'model-new'], model_capabilities: {} }]
    expect(catalogModelMainEligible(saved, 'provider-a', 'model-a')).toBe(true)
  })

  it('rejects models that only exist in the unsaved draft', () => {
    // 持久化：provider A models = [model-a]；草稿新加 model-new(chat) → 不可设为主模型
    const persisted = [{ id: 'provider-a', models: ['model-a'] }]
    expect(catalogModelMainEligible(persisted, 'provider-a', 'model-new')).toBe(false)
  })

  it('uses the saved capability, not the draft override', () => {
    // 持久化里 model-x 是 tts，草稿刚改成 chat 但未保存 → 不可设为主模型
    const persisted: CatalogSavedProvider[] = [
      { id: 'provider-b', models: ['model-x'], model_capabilities: { 'model-x': 'tts' } },
    ]
    expect(catalogModelMainEligible(persisted, 'provider-b', 'model-x')).toBe(false)
  })

  it('rejects providers that are not persisted yet', () => {
    expect(catalogModelMainEligible([], 'provider-c', 'model-c')).toBe(false)
  })
})

describe('selectMainModelWithRollback', () => {
  it('restores previous provider and model when saving fails', async () => {
    const config: Record<string, unknown> = { llm_provider_ref: 'provider-a', model: 'model-a' }
    const save = vi.fn(async () => false)

    const ok = await selectMainModelWithRollback(config, 'provider-b', 'model-b', save)

    expect(ok).toBe(false)
    expect(save).toHaveBeenCalledTimes(1)
    expect(config.llm_provider_ref).toBe('provider-a')
    expect(config.model).toBe('model-a')
  })

  it('keeps the new binding when saving succeeds', async () => {
    const config: Record<string, unknown> = { llm_provider_ref: 'provider-a', model: 'model-a' }

    const ok = await selectMainModelWithRollback(config, 'provider-b', 'model-b', async () => true)

    expect(ok).toBe(true)
    expect(config.llm_provider_ref).toBe('provider-b')
    expect(config.model).toBe('model-b')
  })
})

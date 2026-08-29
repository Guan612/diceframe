export type ModelCapability = 'chat' | 'image' | 'embedding' | 'tts' | 'asr'
export type ProviderTestMode = 'auto' | 'model' | 'embedding'
export type ProviderTestKind = Exclude<ProviderTestMode, 'auto'>

export function modelCapability(model: string, override?: string): ModelCapability {
  if (override && ['chat', 'image', 'embedding', 'tts', 'asr'].includes(override)) {
    return override as ModelCapability
  }
  const value = model.toLowerCase()
  if (/(image|dall-e|flux|stable[-_. ]?diffusion|(^|[-_.])sd3|kolors|qwen[-_. ]?image|ideogram|imagen)/.test(value)) {
    return 'image'
  }
  if (/(embed|embedding|bge|e5-|text2vec|rerank)/.test(value)) return 'embedding'
  if (/(whisper|sensevoice|paraformer|funasr|speech[-_. ]?to[-_. ]?text|transcri|(^|[-_.])asr)/.test(value)) return 'asr'
  if (/(tts|cosyvoice|fish[-_. ]?speech|gpt[-_. ]?sovits|chattts|voice)/.test(value)) return 'tts'
  return 'chat'
}

export function providerTestKind(
  model: string,
  mode: ProviderTestMode = 'auto',
  capabilityOverride?: string,
): ProviderTestKind | null {
  if (mode !== 'auto') return mode
  const value = model.trim().toLowerCase()
  if (!value || /rerank/.test(value)) return null
  const capability = modelCapability(value, capabilityOverride)
  if (capability === 'embedding') return 'embedding'
  if (capability === 'chat') return 'model'
  return null
}

export interface CatalogSavedProvider {
  id: string
  models?: string[]
  model_capabilities?: Record<string, ModelCapability>
}

/** 目录行“设为主模型”的资格判定：只认**已持久化**的 provider library——
 * provider 已保存、模型已在 saved models 里、保存后的能力是 chat。
 * UI 草稿（新建 provider / 未保存的新模型 / 刚改未保存的能力）不算数，
 * 否则 routing 会指向后端根本不存在的 provider/model 组合。 */
export function catalogModelMainEligible(
  savedProviders: CatalogSavedProvider[],
  providerId: string,
  modelName: string,
): boolean {
  const saved = savedProviders.find(provider => provider.id === providerId)
  if (!saved) return false
  if (!(saved.models || []).includes(modelName)) return false
  return modelCapability(modelName, saved.model_capabilities?.[modelName]) === 'chat'
}

/** 把主模型切到目标 provider/model 并持久化；保存失败时把这两个字段
 * 回滚为调用前的值（调用方负责提示，不做整页 config 重载）。 */
export async function selectMainModelWithRollback(
  config: Record<string, unknown>,
  providerId: string,
  modelName: string,
  save: () => Promise<boolean>,
): Promise<boolean> {
  const previousProviderRef = String(config.llm_provider_ref || '')
  const previousModel = String(config.model || '')
  config.llm_provider_ref = providerId
  config.model = modelName
  if (await save()) return true
  config.llm_provider_ref = previousProviderRef
  config.model = previousModel
  return false
}

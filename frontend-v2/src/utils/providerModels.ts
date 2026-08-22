export type ModelCapability = 'chat' | 'image' | 'embedding' | 'tts' | 'asr'
export type ProviderTestMode = 'auto' | 'model' | 'embedding'
export type ProviderTestKind = Exclude<ProviderTestMode, 'auto'>

export function modelCapability(model: string): ModelCapability {
  const value = model.toLowerCase()
  if (/(image|dall-e|flux|stable[-_. ]?diffusion|(^|[-_.])sd3|kolors|qwen[-_. ]?image|ideogram|imagen)/.test(value)) {
    return 'image'
  }
  if (/(embed|embedding|bge|e5-|text2vec|rerank)/.test(value)) return 'embedding'
  if (/(whisper|sensevoice|paraformer|funasr|speech[-_. ]?to[-_. ]?text|transcri|(^|[-_.])asr)/.test(value)) return 'asr'
  if (/(tts|cosyvoice|fish[-_. ]?speech|gpt[-_. ]?sovits|chattts|voice)/.test(value)) return 'tts'
  return 'chat'
}

export function providerTestKind(model: string, mode: ProviderTestMode = 'auto'): ProviderTestKind | null {
  if (mode !== 'auto') return mode
  const value = model.trim().toLowerCase()
  if (!value || /rerank/.test(value)) return null
  const capability = modelCapability(value)
  if (capability === 'embedding') return 'embedding'
  if (capability === 'chat') return 'model'
  return null
}

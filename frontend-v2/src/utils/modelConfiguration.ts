import type { AppConfig } from '@/api/types'

/**
 * The create screen must recognize both the legacy inline model fields and the
 * provider library introduced for shared model routing.
 */
export function isLlmConfigReady(config: Partial<AppConfig>): boolean {
  const providerRef = String(config.llm_provider_ref || '').trim()
  if (providerRef) {
    const provider = (config.ai_providers || []).find(item => item.id === providerRef)
    return Boolean(
      provider
      && String(provider.base_url || '').trim()
      && String(config.model || '').trim()
      && provider.api_key?.configured,
    )
  }
  return Boolean(
    String(config.base_url || '').trim()
    && String(config.model || '').trim()
    && config.api_key?.configured,
  )
}

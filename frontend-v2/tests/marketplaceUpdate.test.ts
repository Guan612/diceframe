import { describe, expect, it } from 'vitest'
import { isNewerPluginVersion, marketItemHasNewerVersion } from '../src/features/plugins/usePluginMarketplace'
import type { PluginMarketplaceItem } from '../src/api/types'

describe('marketItemHasNewerVersion', () => {
  const base: PluginMarketplaceItem = { id: 'demo', name: 'Demo' }

  it('returns true when latest.version is newer than installed', () => {
    expect(marketItemHasNewerVersion(
      { ...base, version: '1.0.0', latest: { version: '1.2.0', requires_approval: false } },
      '1.0.0',
    )).toBe(true)
  })

  it('returns false when latest.version equals installed', () => {
    expect(marketItemHasNewerVersion(
      { ...base, version: '1.0.0', latest: { version: '1.0.0', requires_approval: false } },
      '1.0.0',
    )).toBe(false)
  })

  it('falls back to item.version when latest is absent', () => {
    expect(marketItemHasNewerVersion({ ...base, version: '1.5.0' }, '1.0.0')).toBe(true)
    expect(marketItemHasNewerVersion({ ...base, version: '1.0.0' }, '1.0.0')).toBe(false)
  })

  it('returns false when the plugin is not installed', () => {
    expect(marketItemHasNewerVersion({ ...base, version: '1.0.0', latest: { version: '1.2.0' } }, undefined)).toBe(false)
  })

  it('treats requires_approval versions as newer when version is higher', () => {
    expect(marketItemHasNewerVersion(
      { ...base, version: '1.0.0', latest: { version: '2.0.0', requires_approval: true } },
      '1.0.0',
    )).toBe(true)
  })
})

describe('isNewerPluginVersion', () => {
  it('compares three-part versions', () => {
    expect(isNewerPluginVersion('1.2.0', '1.0.0')).toBe(true)
    expect(isNewerPluginVersion('1.0.0', '1.2.0')).toBe(false)
    expect(isNewerPluginVersion('1.0.0', '1.0.0')).toBe(false)
    expect(isNewerPluginVersion('v2.0.0', '1.9.9')).toBe(true)
  })
})

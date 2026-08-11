import { describe, expect, it } from 'vitest'
import { isNewerPluginVersion } from '@/features/plugins/usePluginMarketplace'

describe('plugin marketplace version comparison', () => {
  it('compares normalized numeric version segments', () => {
    expect(isNewerPluginVersion('v1.2.1', '1.2.0')).toBe(true)
    expect(isNewerPluginVersion('1.10.0', '1.9.9')).toBe(true)
    expect(isNewerPluginVersion('1.2', '1.2.0')).toBe(false)
    expect(isNewerPluginVersion('1.1.9', '1.2.0')).toBe(false)
  })

  it('does not offer updates for incomplete versions', () => {
    expect(isNewerPluginVersion('', '1.0.0')).toBe(false)
    expect(isNewerPluginVersion('1.0.0', undefined)).toBe(false)
    expect(isNewerPluginVersion('nightly', '1.0.0')).toBe(false)
  })

  it('orders prerelease identifiers and ignores build metadata', () => {
    expect(isNewerPluginVersion('1.9.12-beta.3', '1.9.12-beta.2')).toBe(true)
    expect(isNewerPluginVersion('1.9.12-rc.1', '1.9.12-beta.9')).toBe(true)
    expect(isNewerPluginVersion('1.9.12', '1.9.12-rc.1')).toBe(true)
    expect(isNewerPluginVersion('1.9.12-beta.1', '1.9.12')).toBe(false)
    expect(isNewerPluginVersion('1.9.12+build.2', '1.9.12+build.1')).toBe(false)
  })
})

import { describe, expect, it } from 'vitest'
import { shouldAutoDownloadUpdate } from '../src/composables/useUpdater'

describe('shouldAutoDownloadUpdate', () => {
  it('triggers when a source install has an available update and no active task', () => {
    expect(shouldAutoDownloadUpdate('source', 'idle', 'update', true)).toBe(true)
  })

  it('triggers when a portable install has an available update and no active task', () => {
    expect(shouldAutoDownloadUpdate('portable', 'idle', 'update', true)).toBe(true)
  })

  it('allows retry after a failed download', () => {
    expect(shouldAutoDownloadUpdate('source', 'failed', 'update', true)).toBe(true)
  })

  it('does not trigger when not entering via the update focus', () => {
    expect(shouldAutoDownloadUpdate('source', 'idle', '', true)).toBe(false)
  })

  it('does not trigger for unsupported modes', () => {
    expect(shouldAutoDownloadUpdate(null, 'idle', 'update', true)).toBe(false)
  })

  it('does not trigger while downloading, staged, or applied', () => {
    expect(shouldAutoDownloadUpdate('source', 'downloading', 'update', true)).toBe(false)
    expect(shouldAutoDownloadUpdate('source', 'staged', 'update', true)).toBe(false)
    expect(shouldAutoDownloadUpdate('source', 'done', 'update', true)).toBe(false)
    expect(shouldAutoDownloadUpdate('source', 'applying', 'update', true)).toBe(false)
  })

  it('does not trigger when no update is available', () => {
    expect(shouldAutoDownloadUpdate('source', 'idle', 'update', false)).toBe(false)
  })
})

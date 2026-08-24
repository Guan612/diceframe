import { beforeEach, describe, expect, it } from 'vitest'
import {
  accessTokenStorageKey,
  backendLoginUrl,
  buildApiUrl,
  currentBackendUrl,
  normalizeBackendUrl,
  setBackendUrl,
} from '../src/api/connection'

describe('frontend connection', () => {
  beforeEach(() => {
    localStorage.clear()
    window.location.hash = ''
  })

  it('normalizes backend addresses without changing reverse proxy paths', () => {
    expect(normalizeBackendUrl('https://example.com/diceframe/')).toBe('https://example.com/diceframe')
    expect(normalizeBackendUrl('example.com:9876')).toBe('http://example.com:9876')
    expect(normalizeBackendUrl('javascript:alert(1)')).toBe('')
  })

  it('builds a reconnect URL that preserves the current route', () => {
    window.history.replaceState({}, '', '/#/settings?section=connection')
    expect(backendLoginUrl()).toBe('/#/login?redirect=%2F%23%2Fsettings%3Fsection%3Dconnection')
  })

  it('keeps external backend state isolated behind the standalone build flag', () => {
    setBackendUrl('https://example.com/diceframe')
    expect(currentBackendUrl()).toBe('')
    expect(buildApiUrl('/config')).toBe('/api/config')
    expect(accessTokenStorageKey()).toBe('trpg_access_token')
  })
})

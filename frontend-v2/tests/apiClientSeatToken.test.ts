import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, retryOnRateLimit } from '@/api/client'
import { accessTokenStorageKey } from '@/api/connection'
import { readSeatToken, seatTokenKey, storeSeatToken } from '@/utils/seatToken'

const GAME = 'web|room|bot'

function okFetch() {
  const fetchMock = vi.fn().mockResolvedValue(new Response(
    JSON.stringify({ ok: true }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  ))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function sentUrl(fetchMock: ReturnType<typeof vi.fn>): URL {
  return new URL(String(fetchMock.mock.calls[0][0]), 'http://localhost')
}

function sentHeaders(fetchMock: ReturnType<typeof vi.fn>): Headers {
  return fetchMock.mock.calls[0][1].headers as Headers
}

describe('API client seat token', () => {
  beforeEach(() => {
    location.hash = `#/play?game=${encodeURIComponent(GAME)}&user=p1&share=1`
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
    location.hash = ''
  })

  it('identifies a share player by its seat token instead of the public uid', async () => {
    storeSeatToken(GAME, 'tok-p1')
    const fetchMock = okFetch()

    await api(`/games/${encodeURIComponent(GAME)}/private-log`)

    expect(sentHeaders(fetchMock).get('X-Seat-Token')).toBe('tok-p1')
    const url = sentUrl(fetchMock)
    expect(url.searchParams.has('user')).toBe(false)
    expect(url.searchParams.get('share')).toBe('1')
  })

  it('never sends a seat token to another game', async () => {
    storeSeatToken(GAME, 'tok-p1')
    const fetchMock = okFetch()

    await api('/games/web%7Cother%7Cbot/private-log')

    expect(sentHeaders(fetchMock).has('X-Seat-Token')).toBe(false)
  })

  it('keeps the owner path unchanged: no seat token, explicit user', async () => {
    localStorage.setItem(accessTokenStorageKey(), 'owner-pass')
    storeSeatToken(GAME, 'tok-p1')
    const fetchMock = okFetch()

    await api(`/games/${encodeURIComponent(GAME)}/private-log`)

    expect(sentHeaders(fetchMock).has('X-Seat-Token')).toBe(false)
    expect(sentHeaders(fetchMock).get('Authorization')).toBe('Bearer owner-pass')
    expect(sentUrl(fetchMock).searchParams.get('user')).toBe('p1')
  })

  it('forgets a revoked seat token and sends the player back to join', async () => {
    storeSeatToken(GAME, 'tok-old')
    localStorage.setItem('trpg_play_user_' + GAME, 'p1')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ ok: false, error_code: 'SEAT_TOKEN_INVALID', error: 'invalid' }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(api(`/games/${encodeURIComponent(GAME)}/private-log`)).rejects.toMatchObject({
      status: 401,
      code: 'SEAT_TOKEN_INVALID',
    })
    expect(readSeatToken(GAME)).toBe('')
    expect(localStorage.getItem(seatTokenKey(GAME))).toBeNull()
    expect(localStorage.getItem('trpg_play_user_' + GAME)).toBeNull()
    expect(location.hash).toContain('#/join?')
    expect(location.hash).toContain('notice=seat')
  })

  it('a missing token alone does not clear identity (claim flow handles it)', async () => {
    localStorage.setItem('trpg_play_user_' + GAME, 'p1')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ ok: false, error_code: 'SEAT_TOKEN_REQUIRED', error: 'required' }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(api(`/games/${encodeURIComponent(GAME)}/private-log`)).rejects.toMatchObject({ status: 401 })
    expect(localStorage.getItem('trpg_play_user_' + GAME)).toBe('p1')
    expect(location.hash).toContain('#/play?')
  })

  it('never attaches a seat token outside a player share page (GM page, no password)', async () => {
    location.hash = `#/play?game=${encodeURIComponent(GAME)}`
    storeSeatToken(GAME, 'tok-p1')
    const fetchMock = okFetch()

    await api(`/games/${encodeURIComponent(GAME)}/players/p2/seat-token`, { method: 'POST', body: '{}' })

    expect(sentHeaders(fetchMock).has('X-Seat-Token')).toBe(false)
  })

  it('never attaches a seat token to a delegated (P2P host) request', async () => {
    storeSeatToken(GAME, 'tok-p1')
    const fetchMock = okFetch()

    await api(`/games/${encodeURIComponent(GAME)}/action?user=player_9&share=1&delegate=1`, { method: 'POST', body: '{}' })

    expect(sentHeaders(fetchMock).has('X-Seat-Token')).toBe(false)
  })

  it('sends the confirm header on seat-token writes', async () => {
    const fetchMock = okFetch()

    await api(`/games/${encodeURIComponent(GAME)}/seat-token/claim`, { method: 'POST', body: '{}' })

    expect(sentHeaders(fetchMock).get('X-TRPG-Confirm')).toBe('true')
  })
})

describe('seat token is scoped to its backend (standalone frontend)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
    location.hash = ''
  })

  it('does not send a token issued by one server to another server named in a link', async () => {
    vi.stubGlobal('__DF_STANDALONE__', true)
    localStorage.setItem('trpg_backend_url', 'https://table.example.com')
    location.hash = `#/play?game=${encodeURIComponent(GAME)}&user=p1&share=1`
    storeSeatToken(GAME, 'tok-table')

    const fetchMock = okFetch()
    location.hash = `#/play?game=${encodeURIComponent(GAME)}&user=p1&share=1&server=${encodeURIComponent('https://evil.example.com')}`
    await api(`/games/${encodeURIComponent(GAME)}/private-log`)

    expect(String(fetchMock.mock.calls[0][0])).toContain('https://evil.example.com')
    expect(sentHeaders(fetchMock).has('X-Seat-Token')).toBe(false)
    expect(readSeatToken(GAME)).toBe('')
  })

  it('still sends the token to the server that issued it', async () => {
    vi.stubGlobal('__DF_STANDALONE__', true)
    location.hash = `#/play?game=${encodeURIComponent(GAME)}&user=p1&share=1&server=${encodeURIComponent('https://table.example.com')}`
    storeSeatToken(GAME, 'tok-table')
    const fetchMock = okFetch()

    await api(`/games/${encodeURIComponent(GAME)}/private-log`)

    expect(String(fetchMock.mock.calls[0][0])).toContain('https://table.example.com')
    expect(sentHeaders(fetchMock).get('X-Seat-Token')).toBe('tok-table')
  })
})

describe('retryOnRateLimit', () => {
  afterEach(() => { vi.useRealTimers() })

  it('retries once after the advertised wait on a short 429', async () => {
    vi.useFakeTimers()
    const request = vi.fn()
      .mockRejectedValueOnce(new ApiError('busy', 429, undefined, 2))
      .mockResolvedValueOnce({ ok: true })
    const pending = retryOnRateLimit(request)
    await vi.advanceTimersByTimeAsync(2000)
    await expect(pending).resolves.toEqual({ ok: true })
    expect(request).toHaveBeenCalledTimes(2)
  })

  it('does not retry other errors or long waits', async () => {
    const forbidden = vi.fn().mockRejectedValue(new ApiError('no', 403))
    await expect(retryOnRateLimit(forbidden)).rejects.toMatchObject({ status: 403 })
    expect(forbidden).toHaveBeenCalledTimes(1)
    const long = vi.fn().mockRejectedValue(new ApiError('busy', 429, undefined, 60))
    await expect(retryOnRateLimit(long)).rejects.toMatchObject({ status: 429 })
    expect(long).toHaveBeenCalledTimes(1)
  })
})

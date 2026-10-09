import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/client'
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
})

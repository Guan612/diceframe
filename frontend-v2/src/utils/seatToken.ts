/**
 * Per-seat share credential kept by a player's browser.
 *
 * A share-link player proves which seat it holds with that seat's token
 * (sent as the `X-Seat-Token` header), never with the public uid. The token
 * arrives once — in the response that creates a seat, from a GM takeover
 * link (`#/join?…&seat=<token>`), or from a one-time claim by a session
 * already bound to its seat — and is stored per game in this browser.
 */

import { currentBackendUrl } from '@/api/connection'

export const SEAT_TOKEN_HEADER = 'X-Seat-Token'

const STORAGE_PREFIX = 'trpg_seat_token_'

/**
 * Scoped by the backend the requests go to (like the owner access token), so a
 * crafted link pointing the frontend at another server can never pick up a
 * token issued by this one.
 */
export function seatTokenKey(gameKey: string): string {
  const backend = currentBackendUrl()
  const base = STORAGE_PREFIX + gameKey
  return backend ? `${base}@${encodeURIComponent(backend)}` : base
}

export function readSeatToken(gameKey: string): string {
  if (!gameKey) return ''
  try {
    return localStorage.getItem(seatTokenKey(gameKey)) || ''
  } catch {
    return ''
  }
}

export function storeSeatToken(gameKey: string, token: unknown): void {
  const value = typeof token === 'string' ? token.trim() : ''
  if (!gameKey || !value) return
  try {
    localStorage.setItem(seatTokenKey(gameKey), value)
  } catch {
    // Private mode / blocked storage: the token only lives for this page.
  }
}

export function clearSeatToken(gameKey: string): void {
  if (!gameKey) return
  try {
    localStorage.removeItem(seatTokenKey(gameKey))
  } catch {
    // Nothing stored to clear.
  }
}

/** Game key of an API path such as `/games/<key>/...`, decoded; '' otherwise. */
export function gameKeyOfApiPath(path: string): string {
  const match = /^\/games\/([^/?#]+)/u.exec(path)
  if (!match) return ''
  try {
    return decodeURIComponent(match[1])
  } catch {
    return ''
  }
}

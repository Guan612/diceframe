import type { RendezvousRoomResponse } from '@/api/types'

export const DEFAULT_STUN_URL = 'stun:stun.cloudflare.com:3478'

export interface PeerInvite {
  version: 1
  roomCode: string
  guestToken: string
  websocketUrl: string
  stunUrl: string
  expiresAt: string
}

function encodeBase64Url(value: string): string {
  const bytes = new TextEncoder().encode(value)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/u, '')
}

function decodeBase64Url(value: string): string {
  const normalized = value.replaceAll('-', '+').replaceAll('_', '/')
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
  const binary = atob(padded)
  const bytes = Uint8Array.from(binary, character => character.charCodeAt(0))
  return new TextDecoder().decode(bytes)
}

function validWebSocketUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return (url.protocol === 'wss:' || url.protocol === 'ws:')
      && !url.username && !url.password && !url.search && !url.hash
  } catch {
    return false
  }
}

function validStunUrl(value: string): boolean {
  return value === '' || /^stuns?:[^\s/?#]+(?::\d{1,5})?$/u.test(value)
}

export function encodePeerInvite(room: RendezvousRoomResponse, stunUrl: string): string {
  const invite: PeerInvite = {
    version: 1,
    roomCode: room.room_code,
    guestToken: room.guest_token,
    websocketUrl: room.websocket_url,
    stunUrl: stunUrl.trim(),
    expiresAt: room.expires_at,
  }
  return `DFP1-${encodeBase64Url(JSON.stringify(invite))}`
}

export function decodePeerInvite(value: string): PeerInvite {
  const compact = value.trim()
  if (!compact.startsWith('DFP1-')) throw new Error('invalid_invite')
  let candidate: unknown
  try {
    candidate = JSON.parse(decodeBase64Url(compact.slice(5)))
  } catch {
    throw new Error('invalid_invite')
  }
  if (!candidate || typeof candidate !== 'object') throw new Error('invalid_invite')
  const invite = candidate as Partial<PeerInvite>
  if (
    invite.version !== 1
    || typeof invite.roomCode !== 'string'
    || !/^[A-Z0-9]{8}$/u.test(invite.roomCode)
    || typeof invite.guestToken !== 'string'
    || invite.guestToken.length < 32
    || typeof invite.websocketUrl !== 'string'
    || !validWebSocketUrl(invite.websocketUrl)
    || typeof invite.stunUrl !== 'string'
    || !validStunUrl(invite.stunUrl)
    || typeof invite.expiresAt !== 'string'
    || !Number.isFinite(Date.parse(invite.expiresAt))
  ) {
    throw new Error('invalid_invite')
  }
  return invite as PeerInvite
}

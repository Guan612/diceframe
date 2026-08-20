import { describe, expect, it } from 'vitest'
import type { RendezvousRoomResponse } from '../src/api/types'
import { decodePeerInvite, encodePeerInvite } from '../src/features/peer/inviteCode'

const room: RendezvousRoomResponse = {
  ok: true,
  protocol_version: 1,
  room_code: 'ABCDEFGH',
  host_token: 'host-token-that-must-never-enter-the-invite',
  guest_token: 'guest-token-with-at-least-thirty-two-characters',
  expires_at: '2026-08-20T12:05:00+00:00',
  websocket_url: 'wss://api.diceframe.com/v1/rendezvous/rooms/ABCDEFGH/ws',
}

describe('peer invite code', () => {
  it('round-trips the guest rendezvous data without exposing the host token', () => {
    const code = encodePeerInvite(room, 'stun:stun.cloudflare.com:3478')
    const decoded = decodePeerInvite(code)

    expect(code.startsWith('DFP1-')).toBe(true)
    expect(code).not.toContain(room.host_token)
    expect(decoded.roomCode).toBe(room.room_code)
    expect(decoded.guestToken).toBe(room.guest_token)
    expect(decoded.websocketUrl).toBe(room.websocket_url)
  })

  it('rejects malformed codes instead of guessing defaults', () => {
    expect(() => decodePeerInvite('ABCDEFGH')).toThrow('invalid_invite')
    expect(() => decodePeerInvite('DFP1-not-base64-json')).toThrow('invalid_invite')
  })
})

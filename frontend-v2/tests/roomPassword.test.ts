import { describe, expect, it } from 'vitest'
import { ROOM_PASSWORD_MIN_LENGTH, isRoomPasswordTooShort } from '@/utils/roomPassword'

describe('room password length rule', () => {
  it('needs at least six characters for a new password', () => {
    expect(ROOM_PASSWORD_MIN_LENGTH).toBe(6)
    expect(isRoomPasswordTooShort('abcde')).toBe(true)
    expect(isRoomPasswordTooShort('abcdef')).toBe(false)
  })

  it('treats an empty value as "remove the password", not as too short', () => {
    expect(isRoomPasswordTooShort('')).toBe(false)
  })

  it('counts characters like the server (code points, not UTF-16 units)', () => {
    expect(isRoomPasswordTooShort('🎲🎲🎲')).toBe(true)
    expect(isRoomPasswordTooShort('🎲🎲🎲🎲🎲🎲')).toBe(false)
    expect(isRoomPasswordTooShort('龍龍龍龍龍龍')).toBe(false)
  })
})

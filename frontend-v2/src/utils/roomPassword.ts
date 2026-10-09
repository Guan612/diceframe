/**
 * Minimum length for a room password being set now. The server enforces the
 * same rule; passwords set before it was raised keep working.
 */
export const ROOM_PASSWORD_MIN_LENGTH = 6

/** Whether a non-empty new room password is too short ('' means "no password"). */
export function isRoomPasswordTooShort(password: string): boolean {
  // Count code points like the server does, not UTF-16 units.
  const length = [...String(password ?? '')].length
  return length > 0 && length < ROOM_PASSWORD_MIN_LENGTH
}

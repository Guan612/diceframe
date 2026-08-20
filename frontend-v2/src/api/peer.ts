import { api } from './client'
import type { RendezvousRoomResponse } from './types'

export function createRendezvousRoom(): Promise<RendezvousRoomResponse> {
  return api<RendezvousRoomResponse>('/hub/rendezvous/rooms', { method: 'POST' })
}

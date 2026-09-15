import { describe, expect, it } from 'vitest'
import { canRollRequest, createOperationId, isVisibleToActor } from '@/features/play/manual-rolls/useManualRolls'
import type { ManualRollRequest } from '@/features/play/manual-rolls/types'

const request: ManualRollRequest = {
  id: 'request-1', operation_id: 'operation-1', run_id: 'run-1', round_number: 2,
  created_by: 'gm', created_at: '2026-09-12T00:00:00Z', label: 'Perception', formula: 'd20',
  visibility: 'private', target_uids: ['player-1'], target_names: { 'player-1': 'Ari' },
  status: 'pending', results: {},
}

describe('manual roll helpers', () => {
  it('only offers a pending request to its target or GM', () => {
    expect(canRollRequest(request, 'player-1', false)).toBe(true)
    expect(canRollRequest(request, 'player-2', false)).toBe(false)
    expect(canRollRequest(request, 'gm', true)).toBe(true)
    expect(canRollRequest({ ...request, status: 'resolved' }, 'player-1', false)).toBe(false)
  })

  it('keeps private requests scoped to their targets and GM', () => {
    expect(isVisibleToActor(request, 'player-1', false)).toBe(true)
    expect(isVisibleToActor(request, 'player-2', false)).toBe(false)
    expect(isVisibleToActor(request, 'gm', true)).toBe(true)
    expect(isVisibleToActor({ ...request, visibility: 'party' }, 'player-2', false)).toBe(true)
  })

  it('creates a non-empty operation id for an idempotent create retry', () => {
    expect(createOperationId()).toMatch(/\S/)
  })
})

import { describe, expect, it } from 'vitest'
import type { PendingPayment } from '@/api/types'
import { isEconomyProposalActionable, nextEconomyProposal } from '@/features/play/economyPrompts'

const pending = (values: Partial<PendingPayment>): PendingPayment => ({
  id: 'proposal',
  status: 'pending',
  ...values,
})

describe('economy prompt authority', () => {
  it('routes a private charge only to its payer and a reward only to the GM', () => {
    const charge = pending({ id: 'charge', payer_uid: 'payer', approval_policy: 'payer' })
    const reward = pending({ id: 'reward', recipient_uid: 'player', approval_policy: 'gm' })

    expect(isEconomyProposalActionable(charge, 'payer', 'gm')).toBe(true)
    expect(isEconomyProposalActionable(charge, 'other', 'gm')).toBe(false)
    expect(isEconomyProposalActionable(reward, 'player', 'gm')).toBe(false)
    expect(isEconomyProposalActionable(reward, 'gm', 'gm')).toBe(true)
  })

  it('stops prompting a contributor after their approval while the party waits', () => {
    const split = pending({
      approval_policy: 'all_contributors',
      contributors: [{ uid: 'first', amount: 2 }, { uid: 'second', amount: 3 }],
      approvals: { first: true },
    })

    expect(isEconomyProposalActionable(split, 'first', 'first')).toBe(false)
    expect(isEconomyProposalActionable(split, 'second', 'first')).toBe(true)
  })

  it('keeps a closed proposal pending but skips it until the player reopens it', () => {
    const first = pending({ id: 'first', payer_uid: 'player' })
    const second = pending({ id: 'second', payer_uid: 'player' })

    expect(nextEconomyProposal([first, second], 'player', 'gm', new Set(['first']))).toBe(second)
    expect(nextEconomyProposal([first], 'player', 'gm', new Set(['first']))).toBeUndefined()
    expect(nextEconomyProposal([first], 'player', 'gm', new Set())).toBe(first)
  })
})

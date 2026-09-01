import type { PendingPayment } from '@/api/types'

export function isEconomyProposalActionable(
  proposal: PendingPayment,
  actorId: string,
  gmUid: string,
): boolean {
  if (proposal.status !== 'pending') return false
  if (proposal.approval_policy === 'all_contributors' && proposal.approvals?.[actorId]) {
    return false
  }
  return Boolean(
    proposal.payer_uid === actorId
    || proposal.uid === actorId
    || (proposal.approval_policy === 'gm' && gmUid === actorId)
    || proposal.contributors?.some(item => item.uid === actorId),
  )
}

export function nextEconomyProposal(
  proposals: PendingPayment[],
  actorId: string,
  gmUid: string,
  dismissedIds: ReadonlySet<string>,
): PendingPayment | undefined {
  return proposals.find((proposal) => {
    const id = String(proposal.id || proposal.payment_id || '')
    return id
      && !dismissedIds.has(id)
      && isEconomyProposalActionable(proposal, actorId, gmUid)
  })
}

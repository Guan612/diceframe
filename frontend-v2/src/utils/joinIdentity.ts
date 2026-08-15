import type { GameDetail } from '@/api/types'

/**
 * 判断本地缓存的玩家身份 uid 是否仍是该局成员。
 *
 * 玩家加入后前端会把 uid 存进 localStorage（`trpg_play_user_<gameKey>`），
 * JoinView 用它直接跳游玩界面。被 GM 踢出后该 uid 已从对局移除，
 * 若仍按缓存盲跳，玩家会被卡在「未加入本局」。此函数在跳转前校验成员资格，
 * 供 JoinView 决定"直接进游玩"还是"清缓存走重新加入"。
 */
export function isStoredPlayerMember(detail: GameDetail | Partial<GameDetail>, uid: string): boolean {
  const m = detail.multiplayer
  const members = [
    ...(m?.ready_players ?? []),
    ...(m?.waiting_players ?? []),
    ...(m?.away_players ?? []),
  ]
  return members.some(player => player.user_id === uid)
}

/**
 * 创建游戏时的逐卡控制方式。
 *
 * 控制语义由后端 Player Control Contract 定义（human / ai / unclaimed），这里只
 * 负责把它映射成「角色」步骤上的一个紧凑选择，并保证任何进入 characters[] 的角色
 * 都带着控制方式——手动创建、角色卡选择器、导入、专业建卡都走同一条补齐逻辑，不会
 * 出现「导入的角色没有控制方式」。
 *
 * 前端不新增 AI 状态字段，也不修改 control revision：选出来的值只是创建 payload
 * 里的 `control`，由服务端写成 `players[uid].control.mode`。
 */

export const CARD_CONTROL_MODES = ['human', 'ai'] as const

export type CardControlMode = (typeof CARD_CONTROL_MODES)[number]

/**
 * 第一张默认「玩家」、其余默认「AI 托管」：创建时不提供「等待认领」这个中间态，
 * 每张卡在创建阶段就必须落到一个明确的控制方，避免半成品进入 payload。
 */
export function defaultCardControl(index: number): CardControlMode {
  return index === 0 ? 'human' : 'ai'
}

/** 把一个（可能来自旧状态或用户输入的）值收敛为合法的控制方式。 */
export function normalizeCardControl(value: unknown, index: number): CardControlMode {
  const text = String(value ?? '')
  return (CARD_CONTROL_MODES as readonly string[]).includes(text)
    ? (text as CardControlMode)
    : defaultCardControl(index)
}

/**
 * 把控制方式数组补齐／裁剪到角色数量。
 *
 * 已有选择保持不变（导入或增删角色不该重置用户已做的选择），新出现的角色拿到默认值。
 */
export function syncCardControls(
  count: number,
  current: readonly unknown[],
): CardControlMode[] {
  return Array.from(
    { length: Math.max(0, count) },
    (_, index) => normalizeCardControl(current[index], index),
  )
}

/** 创建 payload 里每张角色应带的 control 值。 */
export function cardControlPayload(
  count: number,
  current: readonly unknown[],
): CardControlMode[] {
  return syncCardControls(count, current)
}

/**
 * 删除某一张角色时，同步删除它对应的控制方式。
 *
 * 角色与控制方式是按 index 平行保存的（`characters[i]` ↔ `cardControl[i]`）。只删
 * 角色不删控制方式，后面的角色就会**继承前一个角色的 control**：删掉 A(human) 之后
 * B 会拿到 human，而不是它原本的 ai。所以两者必须一起删。
 *
 * 越界 index 返回归一化后的原数组（不抛错、不误删）。归一化顺带把非法值收敛成合法
 * 模式，避免把坏值带进创建 payload。
 */
export function removeCardControl(
  current: readonly unknown[],
  index: number,
): CardControlMode[] {
  const next = syncCardControls(current.length, current)
  if (index < 0 || index >= next.length) return next
  next.splice(index, 1)
  return next
}

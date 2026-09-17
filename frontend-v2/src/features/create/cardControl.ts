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

export const CARD_CONTROL_MODES = ['human', 'ai', 'unclaimed'] as const

export type CardControlMode = (typeof CARD_CONTROL_MODES)[number]

/**
 * 第一张默认「真人」、其余默认「等待认领」：与既有产品默认一致，但以一个明确的
 * 值呈现，用户不需要再理解一层「跟随默认」。
 */
export function defaultCardControl(index: number): CardControlMode {
  return index === 0 ? 'human' : 'unclaimed'
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

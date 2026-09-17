import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  CARD_CONTROL_MODES,
  cardControlPayload,
  defaultCardControl,
  normalizeCardControl,
  syncCardControls,
} from '../src/features/create/cardControl'

const createView = readFileSync(
  join(process.cwd(), 'src/features/create/CreateView.vue'),
  'utf8',
)

describe('create-game per-card control', () => {
  it('uses the existing contract vocabulary only', () => {
    // 后端 Player Control Contract 的三个 mode，前端不得引入第四种。
    expect([...CARD_CONTROL_MODES]).toEqual(['human', 'ai', 'unclaimed'])
  })

  it('defaults the first character to human and the rest to unclaimed', () => {
    expect(defaultCardControl(0)).toBe('human')
    expect(defaultCardControl(1)).toBe('unclaimed')
    expect(syncCardControls(3, [])).toEqual(['human', 'unclaimed', 'unclaimed'])
  })

  it('keeps the user choices and fills newly added characters', () => {
    // 导入 / 选择器新增角色时，已做的选择不能被重置。
    const chosen = ['ai', 'human']
    expect(syncCardControls(4, chosen)).toEqual(['ai', 'human', 'unclaimed', 'unclaimed'])
    // 删掉角色时数组跟着收缩。
    expect(syncCardControls(1, chosen)).toEqual(['ai'])
  })

  it('converges junk values to a legal mode instead of sending them', () => {
    expect(normalizeCardControl('', 0)).toBe('human')
    expect(normalizeCardControl('script', 2)).toBe('unclaimed')
    expect(normalizeCardControl(undefined, 0)).toBe('human')
    expect(normalizeCardControl('ai', 1)).toBe('ai')
  })

  it('produces the payload control values for human / ai / unclaimed', () => {
    // 每张角色都带明确的 control，创建 payload 直接使用这些值。
    expect(cardControlPayload(3, ['human', 'ai', 'unclaimed'])).toEqual([
      'human', 'ai', 'unclaimed',
    ])
  })
})

describe('CreateView control placement contract', () => {
  it('offers a compact per-card control in the character step', () => {
    // 角色步骤：每张角色卡旁一个 select，而不是一组 radio。
    expect(createView).toMatch(
      /create-character-card[\s\S]*?<select v-model="cardControl\[i\]"/,
    )
    expect(createView).toContain('v-for="mode in CARD_CONTROL_MODES"')
  })

  it('keeps the confirm step a summary instead of a second config page', () => {
    const confirmSection = createView.slice(createView.indexOf('create-confirm-stage'))
    const summary = confirmSection.slice(0, confirmSection.indexOf('</section>'))
    // 确认页展示结果摘要……
    expect(summary).toContain('controlLabel(')
    // ……但不再铺任何 radio 配置控件。
    expect(summary).not.toContain('type="radio"')
  })

  it('does not expose the internal follow-default concept in the UI', () => {
    expect(createView).not.toContain('controlFollowDefault')
    expect(createView).not.toContain('unclaimedControlDefault')
  })
})

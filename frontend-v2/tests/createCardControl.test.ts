import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  CARD_CONTROL_MODES,
  cardControlPayload,
  defaultCardControl,
  normalizeCardControl,
  removeCardControl,
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

/**
 * 角色与控制方式按 index 平行保存，删除角色必须同步删除对应控制方式。
 * 只删角色会让后面的角色继承被删角色的 control（删 A(human) 后 B 变成 human）。
 */
describe('deleting a character keeps control aligned', () => {
  it('Case A — deleting the first character shifts the rest correctly', () => {
    // A human / B ai / C unclaimed → 删 A → B 仍是 ai、C 仍是 unclaimed
    expect(removeCardControl(['human', 'ai', 'unclaimed'], 0)).toEqual(['ai', 'unclaimed'])
  })

  it('Case B — deleting a middle character keeps its neighbours intact', () => {
    // 删 B → A 仍是 human、C 仍是 unclaimed
    expect(removeCardControl(['human', 'ai', 'unclaimed'], 1)).toEqual(['human', 'unclaimed'])
  })

  it('deleting the last character only drops the last control value', () => {
    expect(removeCardControl(['human', 'ai', 'unclaimed'], 2)).toEqual(['human', 'ai'])
  })

  it('an out-of-range index never removes anything', () => {
    expect(removeCardControl(['human', 'ai'], 5)).toEqual(['human', 'ai'])
    expect(removeCardControl(['human', 'ai'], -1)).toEqual(['human', 'ai'])
  })

  it('converges junk values while removing, so bad data cannot reach the payload', () => {
    expect(removeCardControl(['human', 'script', 'ai'], 0)).toEqual(['unclaimed', 'ai'])
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

  it('removes the matching control when a character is removed', () => {
    // 结构性锁定：removeCharacter 必须同时更新 cardControl，否则会再次错位。
    const body = createView.slice(createView.indexOf('function removeCharacter'))
    const fn = body.slice(0, body.indexOf('\n}'))
    expect(fn).toContain('characters.value.splice(idx, 1)')
    expect(fn).toContain('removeCardControl(cardControl.value, idx)')
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

import { expect, test } from './fixtures'
import { accessToken } from './support'

const token = accessToken

test('settings status summary stays structured and destructive confirmations are explicit', async ({ page }) => {
  await page.addInitScript(value => localStorage.setItem('trpg_access_token', value), token())

  await page.goto('/#/settings')
  await expect(page.locator('.system-status-grid')).toBeVisible()
  const statusCards = page.locator('.system-status-card')
  await expect(statusCards.first()).toBeVisible()
  const summaries = await statusCards.evaluateAll(elements => elements.map(element => ({
    label: element.querySelector('.system-status-head > span')?.textContent?.trim() ?? '',
    value: element.querySelector('.system-status-tag')?.textContent?.trim() ?? '',
    detail: element.querySelector('p')?.textContent?.trim() ?? '',
  })))
  expect(summaries.length).toBeGreaterThan(0)
  for (const summary of summaries) {
    expect(summary.label).not.toBe('')
    expect(summary.value).not.toBe('')
    expect(summary.detail).not.toBe('')
  }

  await page.goto('/')
  await page.getByRole('button', { name: '删除' }).first().click()
  await expect(page.getByText('删除存档').first()).toBeVisible()
  await expect(page.getByRole('button', { name: '删除存档' })).toBeVisible()
  await page.getByRole('button', { name: '取消', exact: true }).click()
})
test('rules page exposes structured editing for copied rules', async ({ page }) => {
  await page.addInitScript(value => localStorage.setItem('trpg_access_token', value), token())
  await page.goto('/#/rules')
  await page.getByRole('button', { name: '复制并编辑' }).first().click()
  await expect(page.getByRole('heading', { name: '复制并编辑规则' })).toBeVisible()
  await expect(page.getByLabel('规则 ID')).toBeVisible()
  await expect(page.getByLabel('规则名称')).toBeVisible()
  await expect(page.locator('.rule-editor-section').filter({ hasText: '属性' })).toBeVisible()
  await expect(page.getByText('高级 JSON')).toBeVisible()
  await page.getByRole('button', { name: '取消' }).click()
})

test('provider controls share one geometry and the add action stays at the rail bottom', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'desktop settings geometry contract')
  await page.goto('/#/settings?section=api')
  await expect(page.locator('.provider-test-section')).toBeVisible()

  const testGeometry = await page.locator('.provider-test-section').evaluate(element => {
    const controls = [
      element.querySelector<HTMLElement>('.provider-field .n-input'),
      element.querySelector<HTMLElement>('.provider-field .n-select'),
      ...Array.from(element.querySelectorAll<HTMLElement>('.provider-test-actions .n-button')),
    ].filter((control): control is HTMLElement => Boolean(control))
    const boxes = controls.map(control => control.getBoundingClientRect())
    return {
      topDelta: Math.max(...boxes.map(box => box.top)) - Math.min(...boxes.map(box => box.top)),
      bottomDelta: Math.max(...boxes.map(box => box.bottom)) - Math.min(...boxes.map(box => box.bottom)),
      heights: boxes.map(box => box.height),
      boxes: boxes.map((box, index) => ({
        kind: controls[index]?.className || controls[index]?.tagName || '',
        top: box.top,
        bottom: box.bottom,
        height: box.height,
      })),
    }
  })
  expect(testGeometry.topDelta, JSON.stringify(testGeometry.boxes)).toBeLessThanOrEqual(1)
  expect(testGeometry.bottomDelta, JSON.stringify(testGeometry.boxes)).toBeLessThanOrEqual(1)
  expect(new Set(testGeometry.heights.map(value => Math.round(value))).size).toBe(1)

  const selectAppearance = await page.locator('.provider-model-row').first().evaluate(element => {
    const selections = Array.from(element.querySelectorAll<HTMLElement>('.n-base-selection'))
    return selections.map(selection => {
      const style = getComputedStyle(selection)
      const box = selection.getBoundingClientRect()
      return {
        height: Math.round(box.height),
        radius: style.borderRadius,
        background: style.backgroundColor,
      }
    })
  })
  expect(selectAppearance).toHaveLength(2)
  expect(selectAppearance[0]).toEqual(selectAppearance[1])

  const railGeometry = await page.locator('.ai-provider-workspace').evaluate(workspace => {
    const rail = workspace.querySelector<HTMLElement>('.provider-library')!
    const button = rail.querySelector<HTMLElement>('.provider-library-footer button')!
    const workspaceBox = workspace.getBoundingClientRect()
    const railBox = rail.getBoundingClientRect()
    const buttonBox = button.getBoundingClientRect()
    const visibleRailBottom = Math.min(railBox.bottom, window.innerHeight)
    return {
      railBottomDelta: Math.abs(workspaceBox.bottom - railBox.bottom),
      buttonBottomGap: visibleRailBottom - buttonBox.bottom,
    }
  })
  expect(railGeometry.railBottomDelta).toBeLessThanOrEqual(1)
  expect(railGeometry.buttonBottomGap).toBeLessThanOrEqual(13)
})

test('model routing pane keeps provider and model assignment reactive after extraction', async ({ page }) => {
  await page.goto('/#/settings?section=models')
  const pane = page.locator('.model-routing-pane')
  await expect(pane).toBeVisible()
  await expect(pane.locator('.model-role-card-main')).toBeVisible()

  const mainProvider = pane.locator('.model-role-card-main > label select').nth(0)
  const mainModel = pane.locator('.model-role-card-main > label select').nth(1)
  const providerOptions = await mainProvider.locator('option').count()
  expect(providerOptions).toBeGreaterThan(1)
  await mainProvider.selectOption({ index: 1 })

  await expect(mainModel).toBeEnabled()
  await expect(mainModel).not.toHaveValue('')
  await expect(pane.locator('.model-role-card-embedding')).toBeVisible()
})

test('overview save artwork fills the complete card behind a readability gradient', async ({ page }) => {
  await page.goto('/#/overview')
  const card = page.locator('.game-card').first()
  await expect(card).toBeVisible()
  const artwork = await card.evaluate(element => {
    const art = element.querySelector<HTMLElement>('.game-card-art')!
    const cardBox = element.getBoundingClientRect()
    const artBox = art.getBoundingClientRect()
    const overlay = getComputedStyle(art, '::after')
    return {
      topGap: artBox.top - cardBox.top,
      rightGap: cardBox.right - artBox.right,
      bottomGap: cardBox.bottom - artBox.bottom,
      leftGap: artBox.left - cardBox.left,
      image: getComputedStyle(art).backgroundImage,
      overlay: overlay.backgroundImage,
    }
  })
  // Artwork is deliberately overscanned slightly for the hover zoom; the contract is
  // that it covers every card edge without leaving a gap.
  expect(Math.max(artwork.topGap, artwork.rightGap, artwork.bottomGap, artwork.leftGap)).toBeLessThanOrEqual(1)
  expect(artwork.image).toContain('url(')
  expect(artwork.overlay).toContain('linear-gradient')
})

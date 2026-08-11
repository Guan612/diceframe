import { expect, test } from './fixtures'
import { accessToken } from './support'

test('new shell and Vue login route render', async ({ page }) => {
  const token = accessToken()
  await page.addInitScript(value => {
    localStorage.setItem('trpg_access_token', value)
    localStorage.setItem('diceframe_locale', 'zh-CN')
  }, token)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '游戏总览' })).toBeVisible()
  await page.goto('/#/login')
  await expect(page.getByRole('heading', { name: 'DiceFrame', exact: true })).toBeVisible()
  await expect(page.locator('.login-announcement')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '📋 DiceFrame 使用指引', exact: true })).toHaveCount(0)

  const emblem = page.locator('.login-emblem-wrap')
  const mark = emblem.locator('.brand-mark')
  await expect(emblem.locator('.login-emblem-geometry')).toBeVisible()
  const [emblemBox, markBox] = await Promise.all([emblem.boundingBox(), mark.boundingBox()])
  expect(emblemBox).not.toBeNull()
  expect(markBox).not.toBeNull()
  expect(Math.abs((emblemBox!.x + emblemBox!.width / 2) - (markBox!.x + markBox!.width / 2))).toBeLessThanOrEqual(1)
  expect(Math.abs((emblemBox!.y + emblemBox!.height / 2) - (markBox!.y + markBox!.height / 2))).toBeLessThanOrEqual(1)
  const lowerRing = await page.locator('.login-page').evaluate(element => getComputedStyle(element, '::before').content)
  expect(lowerRing).toBe('none')
})

test('direct share route follows browser locale and exposes a language switch', async ({ browser }) => {
  const context = await browser.newContext({ locale: 'en-US' })
  const page = await context.newPage()
  await page.goto('/#/join?game=missing&share=1')

  const locale = page.locator('.join-actions select')
  await expect(locale).toHaveValue('en')
  await locale.selectOption('zh-CN')
  await expect(locale).toHaveValue('zh-CN')
  await context.close()
})

import { expect, test } from '@playwright/test'
import { prepareAuthenticatedContext } from './support'

test('two clients establish a direct data channel through Hub signaling', async ({ browser, request }) => {
  const context = await browser.newContext({ locale: 'zh-CN' })
  await prepareAuthenticatedContext(context, request)
  const host = await context.newPage()
  const guest = await context.newPage()

  await host.goto('/#/peer')
  await host.getByLabel('STUN 服务').fill('')
  await host.getByRole('button', { name: '创建临时直连房间' }).click()
  const invite = await host.locator('.peer-invite textarea').inputValue()
  expect(invite).toMatch(/^DFP1-/)

  await guest.goto('/#/peer')
  await guest.getByRole('button', { name: '我要加入' }).click()
  await guest.getByLabel('粘贴房主发来的链接码').fill(invite)
  await guest.getByRole('button', { name: '连接房主' }).click()

  await expect(host.getByText('P2P 直连成功')).toBeVisible({ timeout: 20_000 })
  await expect(guest.getByText('P2P 直连成功')).toBeVisible({ timeout: 20_000 })

  await guest.getByPlaceholder('输入不敏感的测试文本').fill('hello over data channel')
  await guest.getByRole('button', { name: '发送' }).click()
  await expect(host.locator('.peer-message-log .received')).toContainText('hello over data channel')

  await context.close()
})

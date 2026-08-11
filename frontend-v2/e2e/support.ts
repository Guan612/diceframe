import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { APIRequestContext, BrowserContext, Page } from '@playwright/test'

export const accessToken = () => {
  const dataDir = process.env.DICEFRAME_E2E_DATA_DIR
  if (!dataDir) throw new Error('DICEFRAME_E2E_DATA_DIR is required; run E2E through npm run test:e2e')
  return readFileSync(resolve(dataDir, 'access_token.txt'), 'utf8').trim()
}

async function announcementHash(request: APIRequestContext): Promise<string> {
  try {
    const response = await request.get('/api/announcements?lang=zh-CN')
    if (!response.ok()) return ''
    const payload = await response.json() as { hash?: unknown }
    return typeof payload.hash === 'string' ? payload.hash : ''
  } catch {
    return ''
  }
}

export async function prepareAuthenticatedPage(
  page: Page,
  request: APIRequestContext,
  options?: { light?: boolean },
) {
  const hash = await announcementHash(request)
  await page.addInitScript(({ token, hash, light }) => {
    localStorage.setItem('trpg_access_token', token)
    localStorage.setItem('diceframe_locale', 'zh-CN')
    if (hash) localStorage.setItem('diceframe_announcement_read_hash:zh', hash)
    if (light) {
      localStorage.setItem('diceframe_mode_v2', 'light')
      localStorage.setItem('diceframe_skin_v2', 'midnight')
      localStorage.removeItem('diceframe_plugin_theme_v2')
    }
  }, { token: accessToken(), hash, light: Boolean(options?.light) })
}

export async function prepareAuthenticatedContext(
  context: BrowserContext,
  request: APIRequestContext,
) {
  const hash = await announcementHash(request)
  await context.addInitScript(({ token, hash }) => {
    localStorage.setItem('trpg_access_token', token)
    localStorage.setItem('diceframe_locale', 'zh-CN')
    if (hash) localStorage.setItem('diceframe_announcement_read_hash:zh', hash)
  }, { token: accessToken(), hash })
}

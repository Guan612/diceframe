const URL_SCHEME_RE = /^[a-z][a-z0-9+.-]*:\/\//i
const fallbackOrigin = () => (typeof window === 'undefined' ? 'http://localhost' : window.location.origin)

export function normalizePublicBaseUrl(value?: string): string {
  const raw = String(value || '').trim()
  if (!raw) return fallbackOrigin()

  const candidate = URL_SCHEME_RE.test(raw) ? raw : `http://${raw}`
  try {
    const parsed = new URL(candidate)
    const path = parsed.pathname.replace(/\/+$/, '')
    return `${parsed.origin}${path}`
  } catch {
    return fallbackOrigin()
  }
}

export function buildJoinLink(gameKey: string, publicBaseUrl?: string, user?: string, backendUrl?: string): string {
  const base = normalizePublicBaseUrl(publicBaseUrl).replace(/\/+$/, '')
  const url = new URL(`${base}/`)
  const params = new URLSearchParams({ game: gameKey, share: '1' })
  if (user) params.set('user', user)
  const server = normalizePublicBaseUrl(backendUrl)
  if (backendUrl && server) params.set('server', server)
  url.hash = `/join?${params.toString()}`
  return url.toString()
}

/**
 * 移动端扫码登录的二维码载荷。
 *
 * 用 App 自己的 scheme 而不是 http 链接：这段内容只对 DiceFrame App 有意义，
 * 用 http 反而会让系统相机把 GM 引到浏览器里去。配对码是一次性短时效凭据，
 * 出现在二维码里是设计的一部分（见后端 src/webui/pairing.py）。
 */
export function buildPairingPayload(backendUrl: string, code: string): string {
  const params = new URLSearchParams({ s: normalizePublicBaseUrl(backendUrl), c: code })
  return `diceframe://pair?${params.toString()}`
}

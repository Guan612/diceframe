import { describe, expect, it } from 'vitest'
import { buildJoinLink } from '../src/utils/shareLink'

describe('shareLink', () => {
  it('uses configured public base url with a reverse proxy path', () => {
    expect(buildJoinLink('web|abc|bot', 'https://example.com/trpg/')).toBe(
      'https://example.com/trpg/#/join?game=web%7Cabc%7Cbot&share=1',
    )
  })

  it('accepts a host and port without an explicit scheme', () => {
    expect(buildJoinLink('game-1', 'nas.local:18000')).toBe(
      'http://nas.local:18000/#/join?game=game-1&share=1',
    )
  })

  it('carries the backend address for standalone frontend links', () => {
    expect(buildJoinLink('game-1', 'https://play.example.com', 'u1', 'https://api.example.com/')).toBe(
      'https://play.example.com/#/join?game=game-1&share=1&user=u1&server=https%3A%2F%2Fapi.example.com',
    )
  })
})

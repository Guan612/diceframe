import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

function source(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8')
}

const css = source('../src/styles/v2/worlds.css')

describe('world gallery card visual contract', () => {
  it('uses a continuous card overlay instead of a black information panel', () => {
    expect(css).toMatch(/\.world-card::after\s*\{[\s\S]*?linear-gradient/)
    expect(css).toMatch(/\.world-card-body\s*\{[\s\S]*?background:\s*transparent;/)
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)/)
  })
})

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
    expect(css).toMatch(/\.world-card-body h2\s*\{[\s\S]*?var\(--df-accent\)/)
    expect(css).toMatch(/:root\[data-mode="light"\] \.world-card-body h2\s*\{[\s\S]*?#e8c66f/)
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)/)
  })
})

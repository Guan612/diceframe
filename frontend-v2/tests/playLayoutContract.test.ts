import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

function source(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf-8')
}

const playViewSource = source('../src/features/play/PlayView.vue')
const actionComposerSource = source('../src/components/ActionComposer.vue')
const mainSource = source('../src/main.ts')
const layoutCss = source('../src/styles/v2/layout.css')
const lightCss = source('../src/styles/v2/light.css')
const rulesetWorkspaceCss = source('../src/styles/v2/ruleset-workspace.css')
const campaignSource = source('../src/features/rulesets/dnd2024/campaign/Dnd2024CampaignPanel.vue')
const combatSource = source('../src/features/rulesets/dnd2024/combat/Dnd2024CombatPanel.vue')

describe('shared host and player play layout', () => {
  it('anchors mobile play internals to PlayView instead of the owner app shell', () => {
    expect(playViewSource).toContain('class="play-page play-page-immersive"')
    expect(layoutCss).toContain('.play-page.play-page-immersive')
    expect(layoutCss).toContain('.play-page-immersive .play-hud')
    expect(layoutCss).toContain('.play-page-immersive .play-main')
    expect(lightCss).toContain('.play-page-immersive .play-main > .composer')

    const ownerOnlyInternalSelectors = [
      '.app-shell-play .game-sidebar',
      '.app-shell-play .play-control-rail',
      '.app-shell-play .play-drawer-backdrop',
      '.app-shell-play .play-hud',
      '.app-shell-play .play-main',
      '.app-shell-play .scene-strip',
      '.app-shell-play .scene-title',
      '.app-shell-play .scene-chips',
    ]
    for (const selector of ownerOnlyInternalSelectors) {
      expect(layoutCss).not.toContain(selector)
      expect(lightCss).not.toContain(selector)
    }
  })

  it('keeps the mobile action controls beside the textarea', () => {
    expect(actionComposerSource).toMatch(
      /@media \(max-width: 800px\)[\s\S]*?\.composer-row\.has-dictation\s*\{\s*grid-template-columns: minmax\(0, 1fr\) 40px 72px;/,
    )
    expect(actionComposerSource).not.toContain('grid-column: 1 / -1')
  })

  it('tracks the visible mobile viewport throughout browser toolbar transitions', () => {
    expect(mainSource).toContain("window.visualViewport?.addEventListener('resize', syncViewportHeight)")
    expect(mainSource).toContain("window.visualViewport?.addEventListener('scroll', syncViewportHeight)")
    expect(layoutCss).toMatch(/\.play-page\s*\{[\s\S]*?height: var\(--app-h, 100dvh\);/)
    expect(layoutCss).toContain('padding-bottom: calc(6px + env(safe-area-inset-bottom));')
  })

  it('isolates professional rulesets in an accessible, bounded, lazy workspace', () => {
    expect(playViewSource).toContain("defineAsyncComponent(\n  () => import('@/features/rulesets/dnd2024/combat/Dnd2024CombatPanel.vue')")
    expect(playViewSource).toContain("defineAsyncComponent(\n  () => import('@/features/rulesets/dnd2024/campaign/Dnd2024CampaignPanel.vue')")
    expect(playViewSource).toContain('role="tablist"')
    expect(playViewSource).toContain('role="tabpanel"')
    expect(playViewSource).toContain('@keydown="onRulesetTabKey"')
    expect(playViewSource).toContain("label: '5E 2024 游玩区'")
    expect(playViewSource).toContain("campaign: '1 从这里开始'")
    expect(playViewSource).toContain("combat: '2 遇敌时战斗'")
    expect(playViewSource).toContain("story: '3 回看故事（可选）'")
    expect(playViewSource).toContain('class="ruleset-workspace-guide"')
    expect(rulesetWorkspaceCss).toMatch(/\.ruleset-workspace\s*\{[\s\S]*?flex:\s*1 1 auto;[\s\S]*?overflow:\s*auto;/)
    expect(rulesetWorkspaceCss).toContain('.play-main.ruleset-mode')
  })

  it('keeps professional controls touch-sized and honors reduced motion and light mode', () => {
    for (const componentSource of [campaignSource, combatSource]) {
      expect(componentSource).toMatch(/button[^}]*\{[^}]*min-height:\s*44px;/)
      expect(componentSource).toContain('@media (prefers-reduced-motion: reduce)')
      expect(componentSource).toContain(':global(body.light ')
      expect(componentSource).not.toContain(':global(body.light) ')
      expect(componentSource).toContain(':focus-visible')
    }
  })
})

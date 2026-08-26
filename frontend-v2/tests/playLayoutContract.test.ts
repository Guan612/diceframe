import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

function source(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf-8').replace(/\r\n/g, '\n')
}

const playViewSource = source('../src/features/play/PlayView.vue')
const gameSidebarSource = source('../src/components/GameSidebar.vue')
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

  it('keeps one classic play surface and loads D&D enhancements in a bounded toolbox', () => {
    expect(playViewSource).toContain("defineAsyncComponent(\n  () => import('@/features/rulesets/dnd2024/combat/Dnd2024CombatPanel.vue')")
    expect(playViewSource).toContain("defineAsyncComponent(\n  () => import('@/features/rulesets/dnd2024/campaign/Dnd2024CampaignPanel.vue')")
    expect(playViewSource.match(/<GameTimeline/g)).toHaveLength(1)
    expect(playViewSource.match(/<ActionComposer/g)).toHaveLength(1)
    expect(playViewSource).toContain('dialog-class="dnd-toolbox-dialog"')
    expect(playViewSource).toContain('<template #after-perception>')
    expect(playViewSource).toContain("menu: 'DND5E工具'")
    expect(playViewSource).not.toContain('play-tools-menu')
    const dndToolsStart = playViewSource.indexOf('class="panel sidebar-disclosure dnd5e-sidebar-tools"')
    const dndTools = playViewSource.slice(dndToolsStart, playViewSource.indexOf('</details>', dndToolsStart))
    expect(dndTools).toContain('rulesetToolCopy.campaign')
    expect(dndTools).toContain('rulesetToolCopy.combat')
    expect(dndTools).not.toContain("t('characters')")
    expect(dndTools).not.toContain("t('mapTitle')")
    expect(dndTools).not.toContain("t('sceneGallery')")
    expect(dndTools).not.toContain("t('rule')")
    expect(gameSidebarSource.indexOf('<slot name="after-perception" />')).toBeGreaterThan(gameSidebarSource.indexOf("t('characterPerception')"))
    expect(gameSidebarSource.indexOf('<slot name="after-perception" />')).toBeLessThan(gameSidebarSource.indexOf("t('statusInfo')"))
    expect(playViewSource).toContain("@click=\"openRulesetTool('campaign')\"")
    expect(playViewSource).toContain("@click=\"openRulesetTool('combat')\"")
    expect(playViewSource).toContain("activeRulesetTool.value = 'combat'")
    expect(playViewSource).toContain("step?.requires === 'combat_ended'")
    expect(playViewSource).toContain("response.gameplay.encounter_request?.status === 'pending'")
    expect(playViewSource).not.toContain('Dnd2024PlayWorkspace')
    expect(playViewSource).not.toContain('Dnd2024PartyFeed')
    expect(playViewSource).not.toContain('unified_play_context')
    expect(actionComposerSource).not.toContain('professional-mode-switch')
    expect(rulesetWorkspaceCss).toContain('.dialog.dnd-toolbox-dialog')
    expect(rulesetWorkspaceCss).toContain('.dnd-toolbox-tabs')
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

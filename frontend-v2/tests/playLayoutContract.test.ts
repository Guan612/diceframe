import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

function source(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf-8').replace(/\r\n/g, '\n')
}

const playViewSource = source('../src/features/play/PlayView.vue')
const gameSidebarSource = source('../src/components/GameSidebar.vue')
const actionComposerSource = source('../src/components/ActionComposer.vue')
const multiplayerSource = source('../src/components/play/MultiplayerPanel.vue')
const mainSource = source('../src/main.ts')
const globalCss = source('../src/styles.css')
const layoutCss = source('../src/styles/v2/layout.css')
const lightCss = source('../src/styles/v2/light.css')
const rulesetWorkspaceCss = source('../src/styles/v2/ruleset-workspace.css')
const campaignSource = source('../src/features/rulesets/dnd2024/campaign/Dnd2024CampaignPanel.vue')
const combatSource = source('../src/features/rulesets/dnd2024/combat/Dnd2024CombatPanel.vue')
const overviewSource = source('../src/features/overview/OverviewView.vue')
const overviewCss = source('../src/styles/v2/overview.css')

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
    expect(playViewSource).toContain("menu: 'DND5E工具'")
    expect(playViewSource).not.toContain('play-tools-menu')
    expect(playViewSource).toContain('<template #tools>')
    expect(playViewSource).toContain('class="ruleset-context-tools"')
    expect(actionComposerSource).toContain('<slot name="tools" />')
    expect(playViewSource).not.toContain('dnd5e-sidebar-tools')
    expect(gameSidebarSource).toContain('<slot name="after-perception" />')
    expect(playViewSource).toContain("@click=\"openRulesetTool('campaign')\"")
    expect(playViewSource).toContain("@click=\"openRulesetTool('combat')\"")
    expect(playViewSource).toContain("activeRulesetTool.value = 'combat'")
    expect(playViewSource).toContain('<DirectorProposalCard')
    expect(playViewSource).not.toContain('<CombatLiveBar')
    expect(playViewSource).toContain('<CombatMessageComposer')
    expect(playViewSource).toContain('game.rulesetStateSignal.value')
    expect(playViewSource).toContain('response.gameplay.director?.proposal')
    expect(playViewSource).toContain("step?.requires === 'combat_ended'")
    expect(playViewSource).toContain("response.gameplay.encounter_request?.status === 'pending'")
    expect(playViewSource).not.toContain('Dnd2024PlayWorkspace')
    expect(playViewSource).not.toContain('Dnd2024PartyFeed')
    expect(playViewSource).not.toContain('unified_play_context')
    expect(actionComposerSource).not.toContain('professional-mode-switch')
    expect(rulesetWorkspaceCss).toContain('.dialog.dnd-toolbox-dialog')
    expect(rulesetWorkspaceCss).toContain('.dnd-toolbox-tabs')
    expect(rulesetWorkspaceCss).toMatch(/@media \(max-width: 800px\)[\s\S]*?\.ruleset-context-tools\s*\{[\s\S]*?position: fixed;/)
    expect(rulesetWorkspaceCss).toMatch(/@media \(max-width: 800px\)[\s\S]*?\.ruleset-context-tools \.combat-tool-trigger\s*\{\s*display: none;/)
    expect(rulesetWorkspaceCss).not.toMatch(/\.ruleset-context-tools \.campaign-tool-trigger\s*\{\s*display: none;/)
  })

  it('keeps player actions in two equal columns with away beside kick', () => {
    expect(multiplayerSource.indexOf("t('away')")).toBeLessThan(multiplayerSource.indexOf("t('kick')"))
    expect(globalCss).toMatch(/\.player-actions\{[^}]*display:grid;[^}]*grid-template-columns:repeat\(2,minmax\(0,1fr\)\);/)
    expect(globalCss).toMatch(/\.player-actions button\{[^}]*width:100%;[^}]*min-width:0;/)
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

  it('keeps overview save titles on one line while preserving the full title on hover', () => {
    expect(overviewSource).toContain(':title="g.world_name || g.game_key"')
    expect(overviewCss).toMatch(/\.game-card-body h2\s*\{[\s\S]*?text-overflow:\s*ellipsis;[\s\S]*?white-space:\s*nowrap;/)
    const titleRule = overviewCss.match(/\.game-card-body h2\s*\{([\s\S]*?)\n\}/)?.[1] || ''
    expect(titleRule).not.toContain('-webkit-line-clamp')
  })

  it('keeps combat grid rows and the initiative strip from collapsing inside the toolbox', () => {
    expect(combatSource).toMatch(/\.dnd-combat\s*\{[^}]*grid-auto-rows:\s*max-content;/)
    expect(combatSource).toMatch(/\.dnd-combat\s*\{[^}]*align-content:\s*start;/)
    expect(combatSource).toMatch(/\.initiative\s*\{[^}]*min-height:\s*34px;/)
    expect(combatSource).toMatch(/\.initiative\s*\{[^}]*overflow-y:\s*hidden;/)
    expect(combatSource).toContain("import CombatLiveBar from '@/components/play/CombatLiveBar.vue'")
    expect(combatSource).toContain('<CombatLiveBar')
  })
})

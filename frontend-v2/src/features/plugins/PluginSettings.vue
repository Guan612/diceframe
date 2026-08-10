<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { Component } from 'vue'
import {
  NAlert, NButton, NCheckbox, NCollapse, NCollapseItem, NIcon, NInput, NInputNumber,
  NModal, NPagination, NRate, NSelect, NSpin, NSwitch, NTabPane, NTabs, NTag,
} from 'naive-ui'
import DOMPurify from 'dompurify'
import {
  AddOutline, ChatbubblesOutline, ChevronDown, ChevronUp, CloudDownloadOutline,
  ColorPaletteOutline, ConstructOutline, CreateOutline, CubeOutline,
  ExtensionPuzzleOutline, MapOutline, RefreshOutline, Star, TrashOutline,
} from '@vicons/ionicons5'
import { useTheme, type SkinName } from '@/composables/useTheme'
import { useLocale } from '@/composables/useLocale'
import type { CharacterPortrait, PluginInfo, PluginToolDescriptor } from '@/api/types'
import NapcatGuide from '@/components/plugins/NapcatGuide.vue'
import PortraitImage from '@/components/PortraitImage.vue'
import { pluginApi } from '@/api/plugins'
import { usePluginContent } from './usePluginContent'
import { useInstalledPlugins } from './useInstalledPlugins'
import { usePluginMarketplace } from './usePluginMarketplace'
import { usePluginTools } from './usePluginTools'
import { usePluginExport } from './usePluginExport'
import { usePluginTypes } from './usePluginTypes'
import { usePluginUninstallCleanup } from './usePluginUninstallCleanup'
import TunnelCard from './TunnelCard.vue'
import PluginToolGroup from './PluginToolGroup.vue'
import MirrorsTab from './tabs/MirrorsTab.vue'
import ContentTab from './tabs/ContentTab.vue'
import ToolsTab from './tabs/ToolsTab.vue'
import ThemesTab from './tabs/ThemesTab.vue'
import InstalledTab from './tabs/InstalledTab.vue'
import MarketplaceTab from './tabs/MarketplaceTab.vue'
import HubDetailModal from './modals/HubDetailModal.vue'
import ExportPackModal from './modals/ExportPackModal.vue'

const { t } = useLocale()
const {
  skin, builtinSkins, applySkin,
  pluginThemes, pluginThemeId, loadPluginThemes, applyPluginTheme, clearPluginTheme,
} = useTheme()
const busy = ref('')
// 插件类型筛选（已装 + 商店共用同一筛选值）：筛选条由后端类型表驱动
const typeFilter = ref('')
const { pluginTypeFilters, pluginTypeLabel, loadTypes } = usePluginTypes()

// 插件类型 -> 图标映射（商店卡片标题左侧）
const pluginTypeIcons: Record<string, Component> = {
  'content-pack': CubeOutline,
  'theme': ColorPaletteOutline,
  'tool': ConstructOutline,
  'channel-adapter': ChatbubblesOutline,
  'map-pack': MapOutline,
}
function pluginTypeIcon(type?: string): Component {
  return (type && pluginTypeIcons[type]) || ExtensionPuzzleOutline
}
const sortOptions = [
  { label: t('pluginSortDefault'), value: '' },
  { label: t('pluginSortStars'), value: 'stars' },
  { label: t('pluginSortNameAsc'), value: 'name-asc' },
  { label: t('pluginSortNameDesc'), value: 'name-desc' },
]
const {
  tools, toolInputs, toolResults, toolsLoading,
  loadTools, setToolInput, invokeTool,
} = usePluginTools(busy)
const {
  loading: authorLoading,
  packId, packName, packVersion, packDescription,
  selectedWorldId, selectedRuleId, selectedCardIds,
  includePortraits, includeSceneImages, worldSceneImageFile, ruleSceneImageFile,
  worldOptions: authorWorldOptions, ruleOptions: authorRuleOptions, cardOptions: authorCardOptions,
  loadAuthorData, exportPack,
} = usePluginExport(busy)
function setExportSceneImage(kind: 'world' | 'rule', event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] || null
  if (kind === 'world') worldSceneImageFile.value = file
  else ruleSceneImageFile.value = file
}
const showExportModal = ref(false)
let authorLoaded = false
async function openExportModal() {
  showExportModal.value = true
  if (!authorLoaded) {
    authorLoaded = true
    await loadAuthorData()
  }
}
const {
  contentByPlugin, contentGroupCount, contentLoading, contentTargetWorldId, worldOptions,
  loadContentResources, loadWorlds, contentTitle, contentSubtitle, importContent, importAllContent,
} = usePluginContent(busy)

function contentPortrait(item: Record<string, unknown>): CharacterPortrait | undefined {
  const portrait = item.portrait
  return portrait && typeof portrait === 'object' && 'kind' in portrait
    ? portrait as CharacterPortrait
    : undefined
}

async function refreshPluginSurfaces() {
  await load()
  await Promise.all([loadMarketplace(), loadPluginThemes(), loadContentResources()])
}

const { onUninstalled } = usePluginUninstallCleanup()

const {
  mirrors, mirrorTests, marketplaceSource, marketKeyword,
  marketLoading, mirrorLoading, newMirror, sortMode, filteredMarketplace,
  hubPreferences, hubDetail, hubReadmeHtml, hubDetailOpen, hubDetailLoading, hubRating,
  page, totalPages, paginatedMarketplace, goToPage,
  canUpdateFromStore, loadMarketplace, loadHubPreferences, setHubTelemetry,
  loadMirrors, installMarketPlugin, openHubDetail, toggleHubLike, saveHubRating,
  updateInstalledPlugin, uninstallPlugin, addMirror, saveMirror,
  deleteMirror, testMirror, openUrl, marketItemHasNewerVersion,
} = usePluginMarketplace(busy, refreshPluginSurfaces, typeFilter, onUninstalled)
const safeHubReadmeHtml = computed(() => DOMPurify.sanitize(hubReadmeHtml.value))
const {
  plugins, filteredPlugins, expandedPluginNames, loading, installFile, overwriteInstall,
  load, ordered, value, textValue, selectValue, numberValue, set,
  listValue, secretPlaceholder, showGroup, parseList, save, restart,
  clearCardCache, toggleRunning, toggleEnabled, onPluginFile, installPlugin, rescanLocalPlugins,
} = useInstalledPlugins(
  busy,
  () => Promise.all([loadPluginThemes(), loadTools()]),
  refreshPluginSurfaces,
  typeFilter,
)
const themeOptions = computed(() => pluginThemes.value.map(theme => ({
  label: `${theme.name}${theme.plugin_name ? ` · ${theme.plugin_name}` : ''}`,
  value: theme.id,
})))
function permissionDescription(p: PluginInfo, permission: string): string {
  return p.permission_details?.find(item => item.id === permission)?.description || permission
}

// 工具页专用 UI registry：tool_ui 值 -> 渲染组件。未来进程插件声明新的 tool_ui
// 值并在此注册组件即可获得专用卡，无需改工具页分发逻辑。
const toolUiRegistry: Record<string, Component> = {
  'tunnel-card': TunnelCard,
}
interface PluginToolGroupState {
  plugin: PluginInfo
  tools: PluginToolDescriptor[]
  renderer: Component | null
}

// 工具页统一按插件分组。专用 UI 和通用 JSON 工具共享同一层插件模块外壳，
// 避免未来新增插件时把多个插件的状态和操作混在一起。
const toolGroups = computed<PluginToolGroupState[]>(() => {
  const toolsByPlugin = new Map<string, PluginToolDescriptor[]>()
  for (const tool of tools.value) {
    const group = toolsByPlugin.get(tool.plugin_id) || []
    group.push(tool)
    toolsByPlugin.set(tool.plugin_id, group)
  }
  return plugins.value.flatMap((plugin) => {
    const pluginTools = toolsByPlugin.get(plugin.id) || []
    const toolUi = plugin.tool_ui || pluginTools.find(tool => tool.tool_ui)?.tool_ui || ''
    if (!pluginTools.length && !toolUi) return []
    return [{
      plugin,
      tools: pluginTools,
      renderer: toolUiRegistry[toolUi] || null,
    }]
  })
})

function selectedThemeDescription(): string {
  const theme = pluginThemes.value.find(item => item.id === pluginThemeId.value)
  return theme?.description || ''
}
function selectPluginTheme(value: string | null) {
  applyPluginTheme(value)
}
function selectBuiltinSkin(value: SkinName) {
  clearPluginTheme()
  applySkin(value)
}
const skinNameKeys = {
  midnight: 'skinMidnight',
  royal: 'skinRoyal',
  jade: 'skinJade',
  crimson: 'skinCrimson',
} as const satisfies Record<SkinName, string>
const skinDescriptionKeys = {
  midnight: 'skinMidnightHelp',
  royal: 'skinRoyalHelp',
  jade: 'skinJadeHelp',
  crimson: 'skinCrimsonHelp',
} as const satisfies Record<SkinName, string>
const pluginDocs = ref<Record<string, { content: string; name: string }>>({})
const pluginDocsLoading = ref<Record<string, boolean>>({})

async function loadPluginDocs(pluginId: string) {
  if (pluginDocs.value[pluginId] !== undefined || pluginDocsLoading.value[pluginId]) return
  pluginDocsLoading.value[pluginId] = true
  try {
    const response = await pluginApi.docs(pluginId)
    if (response.ok && response.content) {
      pluginDocs.value[pluginId] = { content: response.content, name: response.name || '' }
    }
  } catch {
    // 忽略读取失败，不展示说明 tab 内容
  } finally {
    pluginDocsLoading.value[pluginId] = false
  }
}

function renderDocsMarkdown(markdown: string): string {
  // 轻量 markdown 转 HTML：标题、列表、加粗、代码、段落
  const escaped = markdown
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const withCode = escaped.replace(/`([^`]+)`/g, '<code>$1</code>')
  const withBold = withCode.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  const lines = withBold.split('\n')
  let html = ''
  let inList = false
  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('### ')) { if (inList) { html += '</ul>'; inList = false } html += `<h4>${trimmed.slice(4)}</h4>` }
    else if (trimmed.startsWith('## ')) { if (inList) { html += '</ul>'; inList = false } html += `<h3>${trimmed.slice(3)}</h3>` }
    else if (trimmed.startsWith('# ')) { if (inList) { html += '</ul>'; inList = false } html += `<h2>${trimmed.slice(2)}</h2>` }
    else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) { if (!inList) { html += '<ul>'; inList = true } html += `<li>${trimmed.slice(2)}</li>` }
    else if (trimmed === '') { if (inList) { html += '</ul>'; inList = false } }
    else { if (inList) { html += '</ul>'; inList = false } html += `<p>${trimmed}</p>` }
  }
  if (inList) html += '</ul>'
  return html
}

onMounted(async () => {
  await load()
  await Promise.all([
    loadMarketplace(), loadHubPreferences(), loadMirrors(), loadContentResources(), loadWorlds(), loadTypes(),
  ])
})
</script>

<template>
  <section class="plugin-workspace">
    <header class="view-title archive-hero">
      <div>
        <span class="section-kicker">{{ t('pluginsKicker') }}</span>
        <h1>{{ t('settingsSectionPlugins') }}</h1>
        <p class="muted">{{ t('pluginWorkspaceSubtitle') }}</p>
      </div>
    </header>
  <NTabs type="line" animated class="plugin-surface-tabs">
    <NTabPane name="installed" :tab="t('pluginsInstalledTab')">
      <InstalledTab
        :loading="loading"
        :plugins="plugins"
        :filtered-plugins="filteredPlugins"
        :expanded-plugin-names="expandedPluginNames"
        :type-filter="typeFilter"
        :plugin-type-filters="pluginTypeFilters"
        :busy="busy"
        :install-file="installFile"
        :overwrite-install="overwriteInstall"
        :plugin-docs="pluginDocs"
        :plugin-docs-loading="pluginDocsLoading"
        :can-update-from-store="canUpdateFromStore"
        :on-plugin-file="onPluginFile"
        :install-plugin="installPlugin"
        :rescan-local-plugins="rescanLocalPlugins"
        :toggle-running="toggleRunning"
        :toggle-enabled="toggleEnabled"
        :ordered="ordered"
        :value="value"
        :text-value="textValue"
        :select-value="selectValue"
        :number-value="numberValue"
        :set="set"
        :list-value="listValue"
        :secret-placeholder="secretPlaceholder"
        :show-group="showGroup"
        :parse-list="parseList"
        :save="save"
        :restart="restart"
        :clear-card-cache="clearCardCache"
        :update-installed-plugin="updateInstalledPlugin"
        :uninstall-plugin="uninstallPlugin"
        :permission-description="permissionDescription"
        :plugin-type-label="pluginTypeLabel"
        :load-plugin-docs="loadPluginDocs"
        :render-docs-markdown="renderDocsMarkdown"
        @update:type-filter="(v: string) => typeFilter = v"
        @update:expanded-plugin-names="(v: string[]) => expandedPluginNames = v"
        @update:overwrite-install="(v: boolean) => overwriteInstall = v"
      />
    </NTabPane>

    <NTabPane name="marketplace" :tab="t('pluginMarketplaceTab')">
      <MarketplaceTab
        :hub-preferences="hubPreferences"
        :market-keyword="marketKeyword"
        :sort-mode="sortMode"
        :market-loading="marketLoading"
        :marketplace-source="marketplaceSource"
        :filtered-marketplace="filteredMarketplace"
        :paginated-marketplace="paginatedMarketplace"
        :total-pages="totalPages"
        :page="page"
        :type-filter="typeFilter"
        :plugin-type-filters="pluginTypeFilters"
        :sort-options="sortOptions"
        :busy="busy"
        :plugin-type-icon="pluginTypeIcon"
        :plugin-type-label="pluginTypeLabel"
        :market-item-has-newer-version="marketItemHasNewerVersion"
        :set-hub-telemetry="setHubTelemetry"
        :load-marketplace="loadMarketplace"
        :install-market-plugin="installMarketPlugin"
        :open-url="openUrl"
        :open-hub-detail="openHubDetail"
        :go-to-page="goToPage"
        @update:market-keyword="(v: string) => marketKeyword = v"
        @update:sort-mode="(v: string) => sortMode = v"
        @update:type-filter="(v: string) => typeFilter = v"
      />
    </NTabPane>

    <NTabPane name="themes" :tab="t('themes')">
      <ThemesTab
        :builtin-skins="builtinSkins"
        :skin="skin"
        :plugin-theme-id="pluginThemeId"
        :plugin-themes="pluginThemes"
        :theme-options="themeOptions"
        :skin-name-keys="skinNameKeys"
        :skin-description-keys="skinDescriptionKeys"
        :load-plugin-themes="loadPluginThemes"
        :select-builtin-skin="selectBuiltinSkin"
        :select-plugin-theme="selectPluginTheme"
        :clear-plugin-theme="clearPluginTheme"
        :selected-theme-description="selectedThemeDescription"
      />
    </NTabPane>

    <NTabPane name="tools" :tab="t('pluginToolsTab')">
      <ToolsTab
        :plugins="plugins"
        :tools="tools"
        :tool-inputs="toolInputs"
        :tool-results="toolResults"
        :tools-loading="toolsLoading"
        :busy="busy"
        :load-tools="loadTools"
        :set-tool-input="setToolInput"
        :invoke-tool="invokeTool"
      />
    </NTabPane>

    <NTabPane name="content" :tab="t('contentPacks')">
      <ContentTab
        :content-by-plugin="contentByPlugin"
        :content-group-count="contentGroupCount"
        :content-loading="contentLoading"
        v-model:content-target-world-id="contentTargetWorldId"
        :world-options="worldOptions"
        :busy="busy"
        :load-content-resources="loadContentResources"
        :content-title="contentTitle"
        :content-subtitle="contentSubtitle"
        :import-content="importContent"
        :import-all-content="importAllContent"
        @open-export="openExportModal"
      />
    </NTabPane>

    <NTabPane name="mirrors" :tab="t('mirrorSources')">
      <MirrorsTab
        :mirrors="mirrors"
        :mirror-tests="mirrorTests"
        :mirror-loading="mirrorLoading"
        :new-mirror="newMirror"
        :busy="busy"
        :load-mirrors="loadMirrors"
        :add-mirror="addMirror"
        :save-mirror="saveMirror"
        :delete-mirror="deleteMirror"
        :test-mirror="testMirror"
      />
    </NTabPane>
  </NTabs>
  </section>

  <HubDetailModal
    v-model:show="hubDetailOpen"
    :hub-detail="hubDetail"
    :hub-detail-loading="hubDetailLoading"
    :hub-rating="hubRating"
    :busy="busy"
    :safe-hub-readme-html="safeHubReadmeHtml"
    :toggle-hub-like="toggleHubLike"
    :save-hub-rating="saveHubRating"
  />

  <ExportPackModal
    v-model:show="showExportModal"
    :author-loading="authorLoading"
    :pack-id="packId"
    :pack-name="packName"
    :pack-version="packVersion"
    :pack-description="packDescription"
    :selected-world-id="selectedWorldId"
    :selected-rule-id="selectedRuleId"
    :selected-card-ids="selectedCardIds"
    :include-portraits="includePortraits"
    :include-scene-images="includeSceneImages"
    :author-world-options="authorWorldOptions"
    :author-rule-options="authorRuleOptions"
    :author-card-options="authorCardOptions"
    :busy="busy"
    :set-pack-id="(v: string) => packId = v"
    :set-pack-name="(v: string) => packName = v"
    :set-pack-version="(v: string) => packVersion = v"
    :set-pack-description="(v: string) => packDescription = v"
    :set-selected-world-id="(v: string | null) => selectedWorldId = v || ''"
    :set-selected-rule-id="(v: string | null) => selectedRuleId = v || ''"
    :set-selected-card-ids="(v: (string | number)[] | null) => selectedCardIds = (v || []) as string[]"
    :set-include-portraits="(v: boolean) => includePortraits = v"
    :set-include-scene-images="(v: boolean) => includeSceneImages = v"
    :set-export-scene-image="setExportSceneImage"
    :export-pack="exportPack"
  />
</template>

<style scoped>
.plugin-head h3,
.market-card h3 {
  margin: 0;
}

.plugin-install,
.theme-plugin-panel,
.mirror-form,
.mirror-row,
.market-card {
  border: 1px solid var(--df-border-soft);
  border-radius: 8px;
  background: linear-gradient(180deg, var(--df-surface-1), var(--df-surface-2));
}

.plugin-install {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
  padding: 16px;
}

.theme-plugin-panel {
  display: grid;
  gap: 14px;
  padding: 16px;
}

.builtin-theme-panel {
  margin-bottom: 14px;
}

.builtin-theme-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.builtin-theme-card {
  display: grid;
  gap: 7px;
  min-width: 0;
  padding: 11px;
  text-align: left;
  background: var(--df-control-bg);
  border: 1px solid var(--df-border-soft);
  border-radius: var(--df-radius-md);
  color: var(--df-text);
}

.builtin-theme-card:hover,
.builtin-theme-card.active {
  border-color: var(--df-interactive);
  box-shadow: 0 0 0 2px var(--df-focus);
}

.builtin-theme-card strong {
  color: var(--df-accent-strong);
}

.builtin-theme-card small {
  color: var(--df-text-muted);
  line-height: 1.45;
}

.theme-swatches {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  height: 34px;
  overflow: hidden;
  border: 1px solid var(--df-border-soft);
  border-radius: var(--df-radius-sm);
}

.theme-swatches i {
  display: block;
}

.theme-plugin-panel h3 {
  margin: 0;
  color: var(--df-accent-strong);
}

.theme-plugin-panel p {
  margin: 4px 0 0;
}

.theme-plugin-controls {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) auto auto;
  gap: 10px;
  align-items: center;
}

.content-collapse {
  margin-top: 4px;
}

.content-collapse :deep(.n-collapse-item) {
  margin-bottom: 12px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--df-accent) 28%, var(--df-border-soft));
  border-radius: var(--df-radius-md);
  background: color-mix(in srgb, var(--df-surface-2) 84%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--df-text) 4%, transparent);
}

.content-collapse :deep(.n-collapse-item:last-child) {
  margin-bottom: 0;
}

.content-collapse :deep(.n-collapse-item__header) {
  padding: 10px 12px;
  border-bottom: 1px solid transparent;
  background: color-mix(in srgb, var(--df-surface-raised) 76%, transparent);
}

.content-collapse :deep(.n-collapse-item--active > .n-collapse-item__header) {
  border-bottom-color: var(--df-border-soft);
}

.content-collapse :deep(.n-collapse-item__header-main) {
  min-width: 0;
}

.content-collapse :deep(.n-collapse-item__header-extra) {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.content-count {
  white-space: nowrap;
  font-size: 13px;
}

.import-all-btn {
  flex-shrink: 0;
}

.content-plugin-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.content-plugin-head h3 {
  margin: 0;
  color: var(--df-accent-strong);
  font-size: 15px;
}

.content-plugin-body {
  display: grid;
  gap: 12px;
  padding: 12px;
}

.content-group {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--df-border-soft);
  border-radius: 8px;
  background: var(--df-surface-3);
}

.content-group h3 {
  margin: 0 0 10px;
  color: var(--df-accent-strong);
  font-size: 15px;
}

.content-group h4 {
  margin: 0 0 8px;
  color: var(--df-accent-strong);
  font-size: 14px;
}

.content-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.content-item {
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--df-border-soft);
  border-radius: 6px;
  background: color-mix(in srgb, var(--df-text) 3%, transparent);
  display: grid;
  gap: 10px;
  align-content: start;
}

.content-item:has(> .portrait-image) {
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
}

.content-item:has(> .portrait-image) > .n-button {
  grid-column: 1 / -1;
}

.content-item strong,
.content-item p {
  overflow-wrap: anywhere;
}

.content-item-main {
  min-width: 0;
}

.content-item p {
  margin: 4px 0 0;
  line-height: 1.45;
}

.plugin-tool-groups {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 410px), 1fr));
  gap: 16px;
  align-items: start;
}

.portrait-export-option {
  display: grid;
  gap: 5px;
}

:global(.export-pack-modal .n-card__content) {
  overflow: hidden;
  padding-top: 8px;
}

:global(.export-pack-modal .n-card-header__close),
:global(.export-pack-modal .n-base-close) {
  flex: 0 0 34px;
  display: grid;
  place-items: center;
  width: 34px;
  min-width: 34px;
  height: 34px;
  min-height: 34px;
  margin: 0;
  padding: 0;
  border: 1px solid var(--df-border-soft);
  border-radius: 50%;
  color: var(--df-text-secondary);
  background: color-mix(in srgb, var(--df-control-bg) 90%, transparent);
  box-shadow: none;
}

:global(.export-pack-modal .n-base-close:hover) {
  border-color: var(--df-interactive);
  color: var(--df-text);
  background: color-mix(in srgb, var(--df-interactive) 13%, var(--df-control-bg));
}

:global(.export-pack-modal .n-base-close .n-base-icon) {
  width: 18px;
  height: 18px;
  line-height: 18px;
}

.export-pack-help {
  margin: 0 0 12px;
  line-height: 1.5;
}

.export-pack-scroll {
  display: grid;
  max-height: calc(100dvh - 238px);
  overflow-y: auto;
  gap: 10px;
  padding-right: 4px;
}

.export-pack-section {
  padding: 11px 12px;
  border: 1px solid var(--df-border-soft);
  border-radius: var(--df-radius-md);
  background: color-mix(in srgb, var(--df-surface-2) 76%, transparent);
}

.export-pack-section h3 {
  margin: 0 0 9px;
  color: var(--df-accent-strong);
  font-size: 13px;
}

.export-pack-section .field {
  margin: 0;
}

.export-pack-section label {
  margin: 0;
}

.export-pack-meta-grid {
  display: grid;
  grid-template-columns: minmax(150px, 1fr) minmax(150px, 1fr) minmax(96px, .45fr);
  gap: 9px 12px;
}

.export-description-field {
  grid-column: 1 / -1;
}

.export-content-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 12px;
}

.export-content-column {
  display: grid;
  min-width: 0;
  gap: 8px;
}

.compact-file-field {
  display: grid;
  min-width: 0;
  gap: 4px;
  padding: 8px 9px;
  border: 1px dashed var(--df-border-soft);
  border-radius: var(--df-radius-sm);
  background: color-mix(in srgb, var(--df-control-bg) 72%, transparent);
  font-size: 12px;
}

.compact-file-field.disabled {
  opacity: .55;
}

.compact-file-field input {
  max-width: 100%;
  color: var(--df-text-secondary);
  font-size: 11px;
}

.compact-file-field small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.export-card-select {
  grid-column: 1 / -1;
}

.export-resource-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.export-resource-option {
  display: grid;
  align-content: center;
  gap: 4px;
  padding: 8px 9px;
  border-radius: var(--df-radius-sm);
  background: color-mix(in srgb, var(--df-control-bg) 68%, transparent);
}

.export-pack-footer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  padding-top: 11px;
  border-top: 1px solid var(--df-border-soft);
}

.export-pack-footer .hint,
.export-pack-footer .actions-row {
  margin: 0;
}

.export-pack-footer .hint {
  font-size: 11px;
  line-height: 1.4;
}

.content-world-select {
  width: min(360px, 100%);
}

.plugin-install h3 {
  margin: 0;
  color: var(--df-accent-strong);
}

.plugin-install p {
  margin: 4px 0 0;
}

.install-controls,
.plugin-extra,
.actions-row,
.toolbar-row,
.tag-row,
.market-actions,
.mirror-heading,
.mirror-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.plugin-extra {
  margin-right: 18px;
}

.install-controls {
  justify-content: flex-end;
}

.toolbar-row {
  margin-bottom: 14px;
}

.type-filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.create-pack-btn {
  margin-left: auto;
}

.market-sort-select {
  width: 150px;
}

.market-pagination {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

.source-line {
  margin: -4px 0 14px;
}

.plugin-head p {
  margin: 4px 0 0;
}

.plugin-tabs {
  margin-top: 4px;
}

.permission-panel {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid var(--df-border-soft);
  border-radius: 6px;
  background: var(--df-surface-3);
}

.plugin-docs {
  padding: 4px 0;
}

.plugin-docs-content {
  font-size: 14px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.plugin-docs-content h2 {
  font-size: 18px;
  margin: 0 0 10px;
  color: var(--df-accent-strong);
}

.plugin-docs-content h3 {
  font-size: 15px;
  margin: 16px 0 8px;
  color: var(--df-accent-strong);
}

.plugin-docs-content h4 {
  font-size: 14px;
  margin: 12px 0 6px;
  color: var(--df-accent-strong);
}

.plugin-docs-content p {
  margin: 6px 0;
}

.plugin-docs-content ul {
  margin: 6px 0;
  padding-left: 20px;
}

.plugin-docs-content li {
  margin: 4px 0;
}

.plugin-docs-content code {
  background: color-mix(in srgb, var(--df-text) 8%, transparent);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 13px;
}

.permission-panel h4 {
  margin: 0;
  color: var(--df-accent-strong);
  font-size: 14px;
}

.permission-panel p {
  margin: 0;
  line-height: 1.55;
}

.permission-list {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.plugin-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(260px, 1fr));
  gap: 14px 18px;
  align-items: start;
}

.field-group {
  grid-column: 1 / -1;
  margin: 10px 0 -2px;
  padding-top: 10px;
  border-top: 1px solid var(--df-border-soft);
  color: var(--df-accent-strong);
  font-size: 14px;
}

.field-group:first-child {
  margin-top: 0;
  padding-top: 0;
  border-top: none;
}

.field {
  min-width: 0;
}

.field-wide {
  grid-column: 1 / -1;
}

.input-label {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.switch-label {
  display: flex;
  gap: 10px;
  align-items: center;
  min-height: 34px;
}

.field-title {
  font-size: 13px;
  color: var(--df-text);
}

.field small {
  display: block;
  margin-top: 5px;
  line-height: 1.45;
}

.actions-row {
  margin-top: 16px;
}

.hint {
  margin-top: 8px;
}

.market-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
  align-items: stretch;
}

.market-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  min-width: 0;
}

.market-title {
  display: grid;
  grid-template-columns: 50px minmax(0, 1fr) auto;
  column-gap: 12px;
  align-items: start;
}

.market-title-text {
  min-width: 0;
}

.market-author {
  margin-top: 2px;
}

.market-title-icon {
  color: var(--df-accent-strong);
}

.market-title p,
.market-desc {
  margin: 5px 0 0;
}

.market-desc {
  min-height: 42px;
  max-height: 3.2em;
  overflow: hidden;
  color: var(--df-text);
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.market-permissions {
  min-height: 1.5em;
  margin: -4px 0 10px;
}

.market-warning {
  color: var(--df-danger-strong);
  margin: -4px 0 10px;
}

.tag-row {
  margin: 12px 0 6px 0;
}

.market-actions {
  margin-top: auto;
  flex-wrap: nowrap;
}

.market-actions :deep(button) {
  flex: 1 1 0;
  min-width: 0;
  white-space: nowrap;
}

.stars-tag :deep(.n-icon) {
  color: var(--df-accent-strong);
}

.mirror-form {
  display: grid;
  grid-template-columns: 1fr 1fr 96px auto auto;
  grid-template-areas:
    "id name priority switch btn"
    "raw raw clone clone .";
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
  padding: 14px;
  max-width: 100%;
  overflow: hidden;
}
.mirror-form .mirror-field-id { grid-area: id; }
.mirror-form .mirror-field-name { grid-area: name; }
.mirror-form .mirror-field-raw { grid-area: raw; }
.mirror-form .mirror-field-clone { grid-area: clone; }
.mirror-form .mirror-field-priority { grid-area: priority; }
.mirror-form .mirror-field-switch { grid-area: switch; }
.mirror-form .mirror-field-add { grid-area: btn; }

.mirror-list {
  display: grid;
  gap: 12px;
}

.mirror-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: flex-start;
  padding: 14px;
  max-width: 100%;
  overflow: hidden;
}

.mirror-main {
  min-width: 0;
}

.mirror-main p {
  margin: 6px 0 0;
  word-break: break-all;
}

.mirror-edit-grid {
  display: grid;
  grid-template-columns: minmax(120px, .8fr) minmax(160px, 1.2fr) minmax(160px, 1.2fr) minmax(90px, .5fr);
  gap: 8px;
  margin-top: 10px;
  min-width: 0;
}

.mirror-test {
  color: var(--df-accent-strong);
}

.mirror-actions {
  justify-content: flex-end;
  max-width: 100%;
}

.mirror-form :deep(.n-input),
.mirror-form :deep(.n-input-number),
.mirror-edit-grid :deep(.n-input),
.mirror-edit-grid :deep(.n-input-number) {
  min-width: 0;
  width: 100%;
}

@media (max-width: 1180px) {
  .mirror-form {
    grid-template-columns: 1fr 1fr auto auto;
    grid-template-areas:
      "id name priority btn"
      "raw raw clone clone";
  }

  .mirror-form .mirror-field-switch {
    display: none;
  }

  .mirror-edit-grid {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .mirror-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 980px) {
  .builtin-theme-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .mirror-form {
    grid-template-columns: 1fr;
    grid-template-areas:
      "id"
      "name"
      "raw"
      "clone"
      "priority"
      "btn";
  }

  .mirror-form .mirror-field-switch {
    display: none;
  }

  .mirror-edit-grid {
    grid-template-columns: 1fr;
  }

  .plugin-install {
    align-items: stretch;
    flex-direction: column;
  }

  .theme-plugin-controls {
    grid-template-columns: 1fr;
  }

  .install-controls,
  .mirror-actions {
    justify-content: flex-start;
  }
}

@media (max-width: 860px) {
  .plugin-form-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .builtin-theme-grid {
    grid-template-columns: 1fr;
  }

  .export-pack-scroll {
    max-height: calc(100dvh - 320px);
  }

  .export-content-grid,
  .export-resource-options,
  .export-pack-footer {
    grid-template-columns: 1fr;
  }

  .export-pack-meta-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .export-description-field,
  .export-card-select,
  .export-version-field {
    grid-column: auto;
  }

  .export-pack-footer .actions-row {
    justify-content: stretch;
  }

  .export-pack-footer .actions-row > * {
    flex: 1;
  }
}
.hub-choice-alert {
  margin-bottom: 14px;
}

.hub-choice-alert p {
  margin: 0 0 10px;
}

.hub-choice-actions,
.hub-interactions,
.hub-stats {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.hub-stats {
  margin: 14px 0;
}

.hub-stats span {
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--df-surface-2);
}

.hub-interactions {
  margin: 16px 0;
}

.hub-readme {
  max-height: 48vh;
  overflow: auto;
  padding-top: 12px;
  border-top: 1px solid var(--df-border-soft);
}

:global(.hub-detail-modal) {
  width: min(760px, calc(100vw - 28px));
}
</style>

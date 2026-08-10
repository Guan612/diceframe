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
      <NSpin :show="loading && !plugins.length">
        <section class="plugin-install">
          <div>
            <h3>{{ t('installPluginTitle') }}</h3>
            <p class="muted">{{ t('installPluginHelp') }}</p>
          </div>
          <div class="install-controls">
            <input type="file" accept=".dfplugin" :aria-label="t('pluginZipAria')" @change="onPluginFile">
            <NCheckbox v-model:checked="overwriteInstall">{{ t('overwriteSameIdPlugin') }}</NCheckbox>
            <NButton type="primary" :disabled="!installFile" :loading="busy === 'install'" @click="installPlugin">
              <template #icon><NIcon :component="CloudDownloadOutline" /></template>
              {{ t('install') }}
            </NButton>
            <NButton secondary :loading="busy === 'rescan'" @click="rescanLocalPlugins">
              <template #icon><NIcon :component="RefreshOutline" /></template>
              {{ t('rescanLocalPlugins') }}
            </NButton>
          </div>
        </section>

        <div class="type-filter-row">
          <NButton size="tiny" :type="typeFilter === '' ? 'primary' : 'default'" @click="typeFilter = ''">{{ t('pluginFilterAll') }}</NButton>
          <NButton v-for="opt in pluginTypeFilters" :key="opt.value" size="tiny" :type="typeFilter === opt.value ? 'primary' : 'default'" @click="typeFilter = opt.value">{{ t(opt.labelKey) }}</NButton>
        </div>

        <p v-if="!filteredPlugins.length" class="muted">{{ plugins.length ? t('pluginTypeFilterEmpty') : t('noPluginsAvailable') }}</p>

        <NCollapse v-model:expanded-names="expandedPluginNames">
          <NCollapseItem v-for="p in filteredPlugins" :key="p.id" :name="p.id" class="plugin-collapsible">
            <template #header>
              <div class="plugin-head">
                <h3>
                  {{ p.name }}
                  <NTag v-if="p.version" size="small" class="plugin-version">{{ t('installedVersion', { version: p.version }) }}</NTag>
                  <NTag v-if="canUpdateFromStore(p.id, p.version)" type="warning" size="small">{{ t('updateAvailable') }}</NTag>
                  <NTag v-if="p.needs_core_update" type="warning" size="small">{{ t('pluginNeedsCoreUpdate', { version: p.min_app_version || '' }) }}</NTag>
                </h3>
                <p class="muted">{{ p.description }}</p>
              </div>
            </template>
            <template #header-extra>
              <div class="plugin-extra" @click.stop>
                <NTag size="small">{{ pluginTypeLabel(p.plugin_type) }}</NTag>
                <NTag :type="p.running ? 'success' : 'default'" size="small">{{ p.status }}</NTag>
                <NSwitch v-if="p.has_entrypoint" :value="p.running" :disabled="busy === p.id" @update:value="toggleRunning(p, $event)" />
                <NSwitch
                  v-else-if="p.plugin_type === 'content-pack' || p.plugin_type === 'theme'"
                  :value="p.config?.enabled !== false"
                  :disabled="busy === p.id"
                  :aria-label="t('pluginEnabled')"
                  @update:value="toggleEnabled(p, $event)"
                />
              </div>
            </template>

            <NTabs type="line" animated class="plugin-tabs" @update:value="(name: string) => name === 'docs' && loadPluginDocs(p.id)">
              <NTabPane name="config" :tab="t('config')">
                <section v-if="p.permissions?.length" class="permission-panel">
                  <h4>{{ t('permissions') }}</h4>
                  <div class="permission-list">
                    <NTag v-for="permission in p.permissions" :key="permission" size="small">
                      {{ permission }}
                    </NTag>
                  </div>
                  <p class="muted">{{ p.permissions.map(permission => permissionDescription(p, permission)).join('；') }}</p>
                </section>
                <div class="plugin-form-grid">
                  <template v-for="(entry, i) in ordered(p)" :key="entry[0]">
                    <h4 v-if="showGroup(ordered(p), i)" class="field-group">{{ entry[1].ui?.group }}</h4>
                    <div class="field" :class="{ 'field-wide': entry[1].type === 'array' }">
                      <label v-if="entry[1].type === 'boolean'" class="switch-label">
                        <NSwitch :value="!!value(p, entry[0], entry[1])" :aria-label="entry[1].title || entry[0]" @update:value="set(p, entry[0], $event)" />
                        <span>{{ entry[1].title || entry[0] }}</span>
                      </label>
                      <label v-else class="input-label">
                        <span class="field-title">{{ entry[1].title || entry[0] }}</span>
                        <NSelect
                          v-if="entry[1].enum"
                          :value="selectValue(p, entry[0], entry[1])"
                          :options="(entry[1].enum || []).map(x => ({ label: x, value: x }))"
                          @update:value="set(p, entry[0], $event)"
                        />
                        <NInput
                          v-else-if="entry[1].type === 'array'"
                          type="textarea"
                          :rows="4"
                          :input-props="{ 'aria-label': entry[1].title || entry[0] }"
                          :value="listValue(p, entry[0], entry[1]).join('\n')"
                          :placeholder="t('arrayInputPlaceholder')"
                          @update:value="set(p, entry[0], parseList($event))"
                        />
                        <NInput
                          v-else-if="entry[1].ui?.sensitive"
                          type="password"
                          show-password-on="click"
                          :placeholder="secretPlaceholder(p, entry[0], entry[1])"
                          :value="textValue(p, entry[0], entry[1])"
                          @update:value="set(p, entry[0], $event)"
                        />
                        <NInputNumber
                          v-else-if="entry[1].type === 'number' || entry[1].type === 'integer'"
                          :value="numberValue(p, entry[0], entry[1])"
                          @update:value="set(p, entry[0], $event)"
                        />
                        <NInput
                          v-else
                          :value="textValue(p, entry[0], entry[1])"
                          @update:value="set(p, entry[0], $event)"
                        />
                      </label>
                      <small v-if="entry[1].description" class="muted">{{ entry[1].description }}</small>
                    </div>
                  </template>
                </div>
              </NTabPane>
              <NTabPane v-if="p.id === 'qq-napcat'" name="guide" :tab="t('guideDocs')">
                <NapcatGuide />
              </NTabPane>
              <NTabPane v-else-if="p.docs" name="docs" :tab="t('guideDocs')">
                <div class="plugin-docs">
                  <p v-if="pluginDocsLoading[p.id]" class="muted">{{ t('pluginLoading') }}</p>
                  <div v-else-if="pluginDocs[p.id]" class="plugin-docs-content" v-html="renderDocsMarkdown(pluginDocs[p.id].content)" />
                  <p v-else class="muted">{{ t('pluginNoDocs') }}</p>
                </div>
              </NTabPane>
            </NTabs>

            <div class="actions-row">
              <NButton type="primary" :loading="busy === p.id" @click="save(p)">{{ t('saveConfig') }}</NButton>
              <NButton v-if="p.has_entrypoint" :loading="busy === p.id" @click="restart(p)">
                <template #icon><NIcon :component="RefreshOutline" /></template>
                {{ t('restartPlugin') }}
              </NButton>
              <NButton v-if="canUpdateFromStore(p.id, p.version)" secondary :loading="busy === `${p.id}:update`" @click="updateInstalledPlugin(p)">
                <template #icon><NIcon :component="CloudDownloadOutline" /></template>
                {{ t('updateFromStore') }}
              </NButton>
              <NButton v-if="p.id === 'qq-napcat'" secondary :loading="busy === `${p.id}:card-cache`" @click="clearCardCache(p)">{{ t('clearCardCache') }}</NButton>
              <NButton tertiary type="error" :loading="busy === `${p.id}:uninstall`" @click="uninstallPlugin(p)">
                <template #icon><NIcon :component="TrashOutline" /></template>
                {{ t('uninstallPlugin') }}
              </NButton>
            </div>
            <p v-if="p.has_entrypoint" class="muted hint">{{ t('pluginRestartHint') }}</p>
            <p v-else class="muted hint">{{ t('declarativePluginHint') }}</p>
          </NCollapseItem>
        </NCollapse>
      </NSpin>
    </NTabPane>

    <NTabPane name="marketplace" :tab="t('pluginMarketplaceTab')">
      <NAlert
        v-if="hubPreferences?.available && !hubPreferences.choice_made"
        type="info"
        :title="t('hubTelemetryChoiceTitle')"
        class="hub-choice-alert"
      >
        <p>{{ t('hubTelemetryChoiceSummary') }}</p>
        <div class="hub-choice-actions">
          <NButton type="primary" :loading="busy === 'hub-telemetry'" @click="setHubTelemetry(true)">
            {{ t('hubTelemetryEnable') }}
          </NButton>
          <NButton :disabled="busy === 'hub-telemetry'" @click="setHubTelemetry(false)">
            {{ t('hubTelemetryKeepOff') }}
          </NButton>
        </div>
      </NAlert>
      <section class="toolbar-row">
        <NInput v-model:value="marketKeyword" :placeholder="t('pluginSearchPlaceholder')" clearable />
        <NSelect v-model:value="sortMode" class="market-sort-select" :options="sortOptions" :placeholder="t('pluginSort')" />
        <NButton :loading="marketLoading" @click="loadMarketplace">
          <template #icon><NIcon :component="RefreshOutline" /></template>
          {{ t('refresh') }}
        </NButton>
      </section>
      <div class="type-filter-row">
        <NButton size="tiny" :type="typeFilter === '' ? 'primary' : 'default'" @click="typeFilter = ''">{{ t('pluginFilterAll') }}</NButton>
        <NButton v-for="opt in pluginTypeFilters" :key="opt.value" size="tiny" :type="typeFilter === opt.value ? 'primary' : 'default'" @click="typeFilter = opt.value">{{ t(opt.labelKey) }}</NButton>
      </div>
      <p v-if="marketplaceSource?.mirror_name" class="muted source-line">
        {{ t('source') }}: {{ marketplaceSource.mirror_name }}, {{ marketplaceSource.elapsed_ms || 0 }} ms
      </p>
      <NSpin :show="marketLoading">
        <div class="market-grid">
          <article v-for="item in paginatedMarketplace" :key="item.id" class="market-card">
            <div class="market-title">
              <NIcon :component="pluginTypeIcon(item.plugin_type)" :size="26" class="market-title-icon" />
              <div class="market-title-text">
                <h3>{{ item.name }}</h3>
                <p class="muted">{{ item.id }} · {{ item.version || t('unknownVersion') }}</p>
                <p v-if="item.author" class="muted market-author">{{ t('author') }}: {{ item.author }}</p>
              </div>
              <NTag v-if="item.stars" size="small" class="stars-tag" :title="t('pluginStars', { count: item.stars })">
                <template #icon><NIcon :component="Star" /></template>
                {{ item.stars }}
              </NTag>
            </div>
            <p class="market-desc" :title="item.description">{{ item.description || t('noDescription') }}</p>
            <div class="tag-row">
              <NTag v-if="item.plugin_type" size="small">{{ pluginTypeLabel(item.plugin_type) }}</NTag>
              <NTag v-if="item.support?.level === 'partial'" type="warning" size="small">{{ t('pluginSupportPartial') }}</NTag>
              <NTag v-if="item.support?.level === 'reserved'" type="error" size="small">{{ t('pluginSupportReserved') }}</NTag>
              <NTag v-if="item.trust_level === 'official'" type="success" size="small">{{ t('pluginTrustOfficial') }}</NTag>
              <NTag v-else-if="item.trust_level === 'verified'" type="info" size="small">{{ t('pluginTrustVerified') }}</NTag>
              <NTag v-else size="small">{{ t('pluginTrustCommunity') }}</NTag>
              <NTag v-if="item.distribution === 'bundled'" type="success" size="small">{{ t('pluginBundled') }}</NTag>
              <NTag v-else-if="item.risk_level === 'declarative'" type="success" size="small">{{ t('pluginRiskDeclarative') }}</NTag>
              <NTag v-else-if="item.risk_level === 'unrestricted-process'" type="error" size="small">{{ t('pluginRiskProcess') }}</NTag>
              <NTag v-if="item.commit_sha" type="info" size="small">{{ t('pluginSourcePinned') }}</NTag>
              <NTag v-if="item.update_policy === 'approval-required'" type="error" size="small">{{ t('pluginUpdateApprovalRequired') }}</NTag>
              <NTag v-if="item.installed" type="success" size="small">{{ t('installedVersion', { version: item.installed_version || '' }) }}</NTag>
              <NTag v-if="item.installed && marketItemHasNewerVersion(item)" type="warning" size="small">{{ t('newVersionAvailable', { version: item.latest?.version || item.version || '' }) }}</NTag>
              <NTag v-for="tag in item.tags || []" :key="tag" size="small">{{ tag }}</NTag>
            </div>
            <p v-if="item.permissions?.length" class="muted market-permissions">
              {{ t('permissions') }}: {{ item.permissions.slice(0, 4).join(t('listSeparator')) }}{{ item.permissions.length > 4 ? t('andMore') : '' }}
            </p>
            <p v-if="item.support?.summary" class="muted market-permissions">{{ item.support.summary }}</p>
            <p v-if="item.verification_error" class="market-warning">{{ item.verification_error }}</p>
            <p v-else-if="item.needs_core_update" class="market-warning">{{ t('pluginNeedsCoreUpdate', { version: item.min_app_version || '' }) }}</p>
            <div class="market-actions">
              <NButton v-if="item.installed && !marketItemHasNewerVersion(item)" secondary disabled>{{ t('installed') }}</NButton>
              <NButton v-else type="primary" :disabled="item.installable === false" :loading="busy === `market:${item.id}`" @click="installMarketPlugin(item)">
                <template #icon><NIcon :component="CloudDownloadOutline" /></template>
                {{ item.installed ? t('update') : t('install') }}
              </NButton>
              <NButton secondary :disabled="!item.repository_url && !item.homepage" @click="openUrl(item.repository_url || item.homepage)">
                {{ t('openRepository') }}
              </NButton>
              <NButton v-if="marketplaceSource?.hub" secondary @click="openHubDetail(item)">
                {{ t('hubPluginDetails') }}
              </NButton>
            </div>
          </article>
        </div>
        <div v-if="totalPages > 1" class="market-pagination">
          <NPagination :page="page" :page-count="totalPages" @update:page="goToPage" />
        </div>
        <p v-if="!filteredMarketplace.length" class="muted">{{ t('marketplaceNoMatches') }}</p>
      </NSpin>
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

  <NModal v-model:show="hubDetailOpen" preset="card" class="hub-detail-modal" :title="hubDetail?.name || t('hubPluginDetails')">
    <NSpin :show="hubDetailLoading">
      <template v-if="hubDetail">
        <p class="muted">{{ hubDetail.id }} · {{ hubDetail.version || t('unknownVersion') }}</p>
        <p>{{ hubDetail.description || t('noDescription') }}</p>
        <div class="hub-stats">
          <span>{{ t('hubDownloads') }} <strong>{{ hubDetail.stats?.downloads_total || 0 }}</strong></span>
          <span>{{ t('hubLikes') }} <strong>{{ hubDetail.stats?.likes || 0 }}</strong></span>
          <span>{{ t('hubRating') }} <strong>{{ hubDetail.stats?.rating_average || 0 }}</strong></span>
        </div>
        <NAlert v-if="hubDetail.security?.install_allowed === false" type="error" :title="t('hubInstallBlocked')">
          {{ (hubDetail.security.blocking_reasons || []).join(t('listSeparator')) }}
        </NAlert>
        <div class="hub-interactions">
          <NButton :loading="busy === `hub-like:${hubDetail.id}`" @click="toggleHubLike">
            {{ hubDetail.liked ? t('hubUnlike') : t('hubLike') }}
          </NButton>
          <span>{{ t('hubYourRating') }}</span>
          <NRate :value="hubRating || 0" :disabled="busy === `hub-rating:${hubDetail.id}`" @update:value="saveHubRating" />
          <NButton v-if="hubRating" text @click="saveHubRating(null)">{{ t('hubClearRating') }}</NButton>
        </div>
        <section v-if="safeHubReadmeHtml" class="hub-readme safe-markdown" v-html="safeHubReadmeHtml" />
        <p v-else-if="!hubDetailLoading" class="muted">{{ t('hubReadmeUnavailable') }}</p>
      </template>
    </NSpin>
  </NModal>

  <NModal
    v-model:show="showExportModal"
    preset="card"
    class="export-pack-modal"
    :title="t('exportPackTitle')"
    :bordered="false"
    style="width: min(800px, calc(100vw - 24px)); max-height: calc(100dvh - 28px);"
  >
    <p class="muted export-pack-help">{{ t('exportPackHelp') }}</p>
    <NSpin :show="authorLoading">
      <div class="export-pack-scroll">
        <section class="export-pack-section">
          <h3>{{ t('exportPackBasicInfo') }}</h3>
          <div class="export-pack-meta-grid">
            <div class="field">
              <label class="input-label">
                <span class="field-title">{{ t('packId') }}</span>
                <NInput v-model:value="packId" placeholder="my-cool-pack" />
              </label>
            </div>
            <div class="field">
              <label class="input-label">
                <span class="field-title">{{ t('packName') }}</span>
                <NInput v-model:value="packName" />
              </label>
            </div>
            <div class="field export-version-field">
              <label class="input-label">
                <span class="field-title">{{ t('packVersion') }}</span>
                <NInput v-model:value="packVersion" />
              </label>
            </div>
            <div class="field export-description-field">
              <label class="input-label">
                <span class="field-title">{{ t('packDescription') }}</span>
                <NInput v-model:value="packDescription" type="textarea" :autosize="{ minRows: 1, maxRows: 2 }" />
              </label>
            </div>
          </div>
        </section>

        <section class="export-pack-section">
          <h3>{{ t('exportPackContentSelection') }}</h3>
          <div class="export-content-grid">
            <div class="export-content-column">
              <label class="input-label">
                <span class="field-title">{{ t('selectWorld') }}</span>
                <NSelect v-model:value="selectedWorldId" :options="authorWorldOptions" clearable />
              </label>
              <label class="compact-file-field" :class="{ disabled: !selectedWorldId || !includeSceneImages }">
                <span>{{ t('worldSceneImage') }}</span>
                <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="!selectedWorldId || !includeSceneImages" @change="setExportSceneImage('world', $event)">
                <small class="muted">{{ t('worldSceneImageHint') }}</small>
              </label>
            </div>
            <div class="export-content-column">
              <label class="input-label">
                <span class="field-title">{{ t('selectRule') }}</span>
                <NSelect v-model:value="selectedRuleId" :options="authorRuleOptions" clearable />
              </label>
              <label class="compact-file-field" :class="{ disabled: !selectedRuleId || !includeSceneImages }">
                <span>{{ t('ruleSceneImage') }}</span>
                <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="!selectedRuleId || !includeSceneImages" @change="setExportSceneImage('rule', $event)">
                <small class="muted">{{ t('ruleSceneImageHint') }}</small>
              </label>
            </div>
            <label class="input-label export-card-select">
              <span class="field-title">{{ t('selectCards') }}</span>
              <NSelect v-model:value="selectedCardIds" :options="authorCardOptions" multiple clearable />
            </label>
          </div>
        </section>

        <section class="export-pack-section export-resource-section">
          <h3>{{ t('exportPackPortableAssets') }}</h3>
          <div class="export-resource-options">
            <label class="export-resource-option" :title="t('includeContentPackPortraitsHint')">
              <NCheckbox v-model:checked="includePortraits">{{ t('includeContentPackPortraits') }}</NCheckbox>
            </label>
            <label class="export-resource-option" :title="t('includeContentPackSceneImagesHint')">
              <NCheckbox v-model:checked="includeSceneImages">{{ t('includeContentPackSceneImages') }}</NCheckbox>
            </label>
          </div>
        </section>
      </div>
      <footer class="export-pack-footer">
        <p class="muted hint">{{ t('exportPackFormatsHint') }}</p>
        <div class="actions-row">
          <NButton type="primary" :loading="busy === 'export-pack'" @click="exportPack(false)">
            <template #icon><NIcon :component="CloudDownloadOutline" /></template>
            {{ t('exportPack') }}
          </NButton>
          <NButton :loading="busy === 'export-pack'" :title="t('exportRepoSourceHint')" @click="exportPack(true)">
            <template #icon><NIcon :component="CreateOutline" /></template>
            {{ t('exportRepoSource') }}
          </NButton>
        </div>
      </footer>
    </NSpin>
  </NModal>
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

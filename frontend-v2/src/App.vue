<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  NConfigProvider, NMessageProvider, NDialogProvider, NLoadingBarProvider, NIcon,
  zhCN, enUS, deDE, dateZhCN, dateEnUS, dateDeDE,
} from 'naive-ui'
import { useTheme } from '@/composables/useTheme'
import { initializeBackgroundImages } from '@/composables/useBackgroundImages'
import { useLocale, type Locale } from '@/composables/useLocale'
import { useUpdateCheck } from '@/composables/useUpdateCheck'
import { useAnnouncements } from '@/composables/useAnnouncements'
import ThemeToggle from '@/components/ThemeToggle.vue'
import AnnouncementButton from '@/components/AnnouncementButton.vue'
import AnnouncementPanel from '@/components/AnnouncementPanel.vue'
import DevicePairingButton from '@/components/DevicePairingButton.vue'
import BrandLogo from '@/components/BrandLogo.vue'
import NaiveBridge from '@/components/common/NaiveBridge.vue'
import StartupPrivacyChoice from '@/components/common/StartupPrivacyChoice.vue'
import StartupUpdateCheck from '@/components/common/StartupUpdateCheck.vue'
import SectionWorkspaceShell from '@/components/navigation/SectionWorkspaceShell.vue'
import { readCurrentGame } from '@/stores/gameContext'
import { isPublicRoute } from '@/router'
import {
  appNavGroups,
  navGroupForRoute,
  navItem,
  primaryNavItemIds,
  type AppNavGroupId,
} from '@/navigation/appNavigation'

const route = useRoute()
const { naiveTheme, overrides, loadPluginThemes, suspendPluginTheme, restorePluginTheme } = useTheme()
const { locale, setLocale, t } = useLocale()
const { updateAvailable } = useUpdateCheck()
// naive-ui 无 ja locale；ja 界面回退英文组件语言，而非中文。de 有内置 locale，直接使用。
const naiveLocale = computed(() => {
  if (locale.value === 'zh-CN') return zhCN
  if (locale.value === 'de') return deDE
  return enUS
})
const naiveDateLocale = computed(() => {
  if (locale.value === 'zh-CN') return dateZhCN
  if (locale.value === 'de') return dateDeDE
  return dateEnUS
})

const primaryItems = primaryNavItemIds.map(navItem)
function menuTo(id: string) {
  if (id !== 'play') return { name: id }
  const game = String(route.query.game || readCurrentGame() || '')
  return game ? { name: 'play', query: { game } } : { name: 'overview' }
}

function groupTo(groupId: AppNavGroupId) {
  const group = appNavGroups.find(candidate => candidate.id === groupId)!
  return menuTo(group.defaultItemId)
}

const activeKey = computed(() => (route.name as string) ?? '')
const currentGameBadge = computed(() => String(route.query.game || readCurrentGame() || '').slice(0, 8))
const currentGameText = computed(() => currentGameBadge.value ? `${t('currentTable')} ${currentGameBadge.value}` : t('lobby'))
const publicRoute = computed(() => isPublicRoute(route))
const fullscreen = publicRoute
const workspaceGroup = computed(() => navGroupForRoute(activeKey.value))
function groupIsActive(groupId: AppNavGroupId) {
  return navGroupForRoute(activeKey.value) === groupId
}

function onLocaleChange(event: Event) {
  setLocale((event.target as HTMLSelectElement).value as Locale)
}

let pluginThemesLoaded = false
async function loadOwnerPluginThemes() {
  if (publicRoute.value || pluginThemesLoaded) return
  try {
    await loadPluginThemes()
    pluginThemesLoaded = true
  } catch {
    pluginThemesLoaded = false
  }
}

const { hasUnread, load, markRead } = useAnnouncements()
const announcementOpen = ref(false)
// 配对弹窗按需加载：不打开就不会把 QrCode/配对面板带进首屏包。
const DevicePairingModal = defineAsyncComponent(
  () => import('@/features/admin/settings/DevicePairingModal.vue'),
)
const pairingOpen = ref(false)
const startupPrivacySettled = ref(false)
const startupUpdateSettled = ref(false)

function tryOpenStartupAnnouncement() {
  if (publicRoute.value || !startupUpdateSettled.value || !hasUnread.value) return
  queueMicrotask(() => {
    if (!publicRoute.value && startupUpdateSettled.value && hasUnread.value) {
      announcementOpen.value = true
    }
  })
}

function onStartupUpdateSettled() {
  startupUpdateSettled.value = true
  tryOpenStartupAnnouncement()
}

function onStartupPrivacySettled() {
  startupPrivacySettled.value = true
}

onMounted(() => {
  void initializeBackgroundImages()
  if (publicRoute.value) suspendPluginTheme()
  void loadOwnerPluginThemes()
  void load(locale.value).then(() => {
    tryOpenStartupAnnouncement()
  })
})
watch(announcementOpen, (open) => { if (!open) markRead() })
watch(locale, (next) => {
  void load(next).then(() => {
    tryOpenStartupAnnouncement()
  })
})
watch(publicRoute, (isPublic) => {
  if (isPublic) {
    startupPrivacySettled.value = false
    startupUpdateSettled.value = false
    announcementOpen.value = false
    pairingOpen.value = false
    suspendPluginTheme()
    return
  }
  restorePluginTheme()
  void loadOwnerPluginThemes()
})
</script>

<template>
  <NConfigProvider
    :class="{ 'content-height-provider': route.name === 'join' }"
    :theme="naiveTheme"
    :theme-overrides="overrides"
    :locale="naiveLocale"
    :date-locale="naiveDateLocale"
  >
    <NLoadingBarProvider>
      <NMessageProvider>
        <NDialogProvider>
          <NaiveBridge>
            <StartupPrivacyChoice v-if="!publicRoute" @settled="onStartupPrivacySettled" />
            <StartupUpdateCheck
              v-if="!publicRoute && startupPrivacySettled"
              @settled="onStartupUpdateSettled"
            />
            <RouterView v-if="fullscreen" v-slot="{ Component }">
              <ThemeToggle class="theme-toggle-floating" />
              <KeepAlive :include="['PlayView']">
                <component :is="Component" />
              </KeepAlive>
            </RouterView>

            <div v-else class="app-shell" :class="{ 'app-shell-play': activeKey === 'play' }">
              <header class="app-header">
                <div class="app-header-inner">
                  <RouterLink :to="{ name: 'overview' }" class="app-brand" :aria-label="t('navOverview')">
                    <BrandLogo :size="32" :subtitle="t('appSubtitle')" />
                  </RouterLink>

                  <nav class="desktop-nav" :aria-label="t('appSubtitle')">
                    <RouterLink
                      v-for="item in primaryItems"
                      :key="item.id"
                      :to="menuTo(item.id)"
                      class="desktop-nav-link"
                      :class="{ active: activeKey === item.id }"
                    >
                      <NIcon :component="item.icon" />
                      <span>{{ t(item.labelKey) }}</span>
                    </RouterLink>
                    <RouterLink
                      v-for="group in appNavGroups"
                      :key="group.id"
                      :to="groupTo(group.id)"
                      class="desktop-nav-link"
                      :class="{ active: groupIsActive(group.id) }"
                    >
                      <NIcon :component="group.icon" />
                      <span>{{ t(group.labelKey) }}</span>
                      <i
                        v-if="group.id === 'management' && updateAvailable"
                        class="nav-update-dot"
                        :aria-label="t('updateAvailable')"
                      />
                    </RouterLink>
                  </nav>

                  <div class="app-header-actions">
                    <AnnouncementButton @open="announcementOpen = true" />
                    <AnnouncementPanel v-model:show="announcementOpen" />
                    <!-- owner-only：publicRoute（join / 公开访问 / play?user=）没有顶栏，
                         这里再显式挡一次，避免任何公共入口拿到配对能力。 -->
                    <DevicePairingButton v-if="!publicRoute" @open="pairingOpen = true" />
                    <ThemeToggle />
                    <label class="locale-select header-locale">
                      <span>{{ t('language') }}</span>
                      <select :value="locale" @change="onLocaleChange">
                        <option value="zh-CN">简体中文</option>
                        <option value="en">English</option>
                        <option value="ja">日本語</option>
                        <option value="de">Deutsch</option>
                      </select>
                    </label>
                    <div class="operator-chip" :title="currentGameText">
                      <span class="operator-copy">
                        <strong>{{ currentGameText }}</strong>
                        <small><i />{{ t('online') }}</small>
                      </span>
                    </div>
                  </div>
                </div>
              </header>

              <DevicePairingModal v-if="pairingOpen && !publicRoute" @close="pairingOpen = false" />

              <main class="app-workspace">
                <RouterView v-slot="{ Component }">
                  <SectionWorkspaceShell v-if="workspaceGroup" :group-id="workspaceGroup">
                    <component :is="Component" />
                  </SectionWorkspaceShell>
                  <KeepAlive v-else :include="['PlayView']">
                    <component :is="Component" />
                  </KeepAlive>
                </RouterView>
              </main>

              <nav class="mobile-bottom-nav" :aria-label="t('appSubtitle')">
                <RouterLink
                  v-for="item in primaryItems"
                  :key="item.id"
                  :to="menuTo(item.id)"
                  :class="{ active: activeKey === item.id }"
                >
                  <span class="mobile-nav-icon">
                    <NIcon :component="item.icon" />
                  </span>
                  <small>{{ t(item.labelKey) }}</small>
                </RouterLink>
                <RouterLink
                  v-for="group in appNavGroups"
                  :key="group.id"
                  :to="groupTo(group.id)"
                  :class="{ active: groupIsActive(group.id) }"
                >
                  <span class="mobile-nav-icon">
                    <NIcon :component="group.icon" />
                    <i
                      v-if="group.id === 'management' && updateAvailable"
                      class="nav-update-dot"
                      :aria-label="t('updateAvailable')"
                    />
                  </span>
                  <small>{{ t(group.labelKey) }}</small>
                </RouterLink>
              </nav>
            </div>
          </NaiveBridge>
        </NDialogProvider>
      </NMessageProvider>
    </NLoadingBarProvider>
  </NConfigProvider>
</template>

<style scoped>
/* 应用级导航：顶栏负责进入分区，分区内导航由共享工作区工具轨负责。 */
.app-header {
  position: sticky;
  z-index: 40;
  top: 0;
  min-width: 0;
  border-bottom: 1px solid var(--df-border-soft);
  background: color-mix(in srgb, var(--df-surface-1) 91%, transparent);
  box-shadow: 0 10px 32px rgba(0, 0, 0, .24);
  backdrop-filter: blur(18px) saturate(125%);
}

.app-header::after {
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 1px;
  content: "";
  pointer-events: none;
  background: linear-gradient(90deg, transparent, var(--df-accent), transparent);
  opacity: .46;
}

.app-header-inner {
  display: flex;
  align-items: center;
  gap: 18px;
  width: min(1680px, 100%);
  min-height: 68px;
  margin: 0 auto;
  padding: 0 24px;
}

.app-brand {
  flex: 0 0 auto;
  min-width: 174px;
  padding-right: 20px;
  border-right: 1px solid var(--df-border-soft);
  color: inherit;
  text-decoration: none;
}

.app-brand:hover { text-decoration: none; }
.app-brand :deep(.brand-text) strong { color: var(--df-accent-strong); letter-spacing: .045em; }
.app-brand :deep(.brand-text) small { color: var(--df-text-muted); }

.desktop-nav {
  display: flex;
  flex: 1 1 auto;
  align-self: stretch;
  min-width: 0;
  overflow: visible;
}

.desktop-nav-link {
  position: relative;
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-width: 84px;
  padding: 0 12px;
  color: var(--df-text-muted);
  font-size: 14px;
  text-decoration: none;
  transition: color .16s ease, background-color .16s ease;
}

.desktop-nav-link:visited { color: var(--df-text-muted); }

.desktop-nav-link::after {
  position: absolute;
  right: 14px;
  bottom: 0;
  left: 14px;
  height: 2px;
  content: "";
  background: linear-gradient(90deg, transparent, var(--df-interactive), transparent);
  opacity: 0;
  transform: scaleX(.4);
  transition: opacity .16s ease, transform .16s ease;
}

.desktop-nav-link:hover {
  color: var(--df-interactive-strong);
  text-decoration: none;
  background: linear-gradient(180deg, transparent, var(--df-hover));
}

.desktop-nav-link.active,
.desktop-nav-link.active:visited,
.desktop-nav-link.active:hover {
  border: 1px solid var(--df-border-soft);
  border-width: 0 1px;
  color: var(--df-accent-strong);
  text-decoration: none;
  background: linear-gradient(180deg, color-mix(in srgb, var(--df-accent) 13%, transparent), transparent);
}

.desktop-nav-link.active::after { opacity: 1; transform: scaleX(1); }
.desktop-nav-link :deep(.n-icon) { font-size: 17px; }

:deep(.nav-update-dot) {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--df-danger-strong);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--df-danger) 26%, transparent);
}

.app-header-actions { display: flex; flex: 0 0 auto; align-items: center; gap: 9px; }

.operator-chip { display: flex; align-items: center; min-width: 110px; }
.operator-copy { display: grid; min-width: 0; }
.operator-copy strong { max-width: 116px; overflow: hidden; color: var(--df-text-secondary); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.operator-copy small { display: inline-flex; align-items: center; gap: 5px; color: var(--df-success-strong); font-size: 10px; }
.operator-copy small i { width: 5px; height: 5px; border-radius: 50%; background: currentColor; box-shadow: 0 0 8px currentColor; }

.table-context {
  max-width: 152px;
  overflow: hidden;
  padding: 5px 9px;
  border: 1px solid var(--df-border-soft);
  border-radius: 999px;
  color: var(--df-text-muted);
  background: var(--df-control-bg);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-header .theme-toggle { border-color: var(--df-border-soft); background: var(--df-control-bg); box-shadow: none; }
.app-header .theme-toggle:hover { border-color: var(--df-interactive); }

.header-locale span {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}

.header-locale select { min-width: 62px; border-color: var(--df-border-soft); background: var(--df-control-bg); }

.mobile-bottom-nav { display: none; }

@media (max-width: 1260px) {
  .app-header-inner { gap: 10px; padding-inline: 14px; }
  .app-brand { min-width: 146px; padding-right: 12px; }
  .desktop-nav-link { min-width: 48px; padding-inline: 10px; }
  .desktop-nav-link span { display: none; }
  .table-context { max-width: 104px; }
  .operator-chip { display: none; }
}

@media (min-width: 981px) and (max-width: 1260px) {
  .desktop-nav-link { min-width: 60px; padding-inline: 7px; font-size: 11px; }
  .desktop-nav-link span { display: inline; }
  .app-header-inner { gap: 6px; padding-inline: 10px; }
  .header-locale select { min-width: 56px; }
}

@media (max-width: 800px) {
  .app-header-inner { min-height: 51px; padding: 0 10px; }
  .app-brand { flex: 1 1 auto; min-width: 0; padding-right: 0; border-right: 0; }
  .app-brand .brand-logo { gap: 7px; }
  .app-brand .brand-mark { width: 28px; height: 28px; }
  .app-brand :deep(.brand-text) small { display: none; }
  .desktop-nav, .table-context { display: none; }
  .app-header-actions { position: relative; }
  .header-locale select { width: 56px; min-width: 56px; padding-inline: 6px 18px; font-size: 11px; }

  .mobile-bottom-nav {
    position: fixed;
    z-index: 55;
    bottom: 0;
    left: 0;
    /* 100vw 含滚动条宽度：窄窗下经典滚动条占位时，底栏直接盖住那条空缺，
       不再给滚动条让位。真机的悬浮滚动条下 100vw 等于版式宽度，渲染不变。 */
    width: 100vw;
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    min-height: calc(64px + env(safe-area-inset-bottom));
    padding: 5px 7px env(safe-area-inset-bottom);
    border-top: 1px solid var(--df-border-soft);
    background: color-mix(in srgb, var(--df-surface-1) 94%, transparent);
    box-shadow: 0 -12px 34px rgba(0, 0, 0, .32);
    backdrop-filter: blur(18px) saturate(125%);
  }

  .app-shell-play .app-header,
  .app-shell-play .mobile-bottom-nav { display: none; }

  .mobile-bottom-nav::before { position: absolute; top: -1px; right: 12%; left: 12%; height: 1px; content: ""; background: linear-gradient(90deg, transparent, var(--df-accent), transparent); opacity: .55; }
  .mobile-bottom-nav > a { display: grid; grid-template-rows: 27px 17px; place-items: center; min-width: 0; border-radius: var(--df-radius-md); color: var(--df-text-muted); text-decoration: none; }
  .mobile-bottom-nav > a.active { color: var(--df-interactive-strong); background: linear-gradient(180deg, var(--df-hover), transparent); }
  .mobile-nav-icon { position: relative; display: grid; place-items: center; font-size: 21px; }
  .mobile-nav-icon :deep(.nav-update-dot) { position: absolute; top: 0; right: -4px; }
  .mobile-bottom-nav small { max-width: 100%; overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
}

@media (max-width: 420px) {
  .app-brand :deep(.brand-text) strong { font-size: 16px; }
  .app-header .theme-toggle { width: 34px; min-width: 34px; height: 34px; min-height: 34px; }
}
</style>

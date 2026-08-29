<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  NConfigProvider, NMessageProvider, NDialogProvider, NLoadingBarProvider, NIcon,
  zhCN, enUS, dateZhCN, dateEnUS,
} from 'naive-ui'
import {
  ChevronDownOutline, EllipsisHorizontalOutline,
} from '@vicons/ionicons5'
import { useTheme } from '@/composables/useTheme'
import { initializeBackgroundImages } from '@/composables/useBackgroundImages'
import { useLocale, type Locale } from '@/composables/useLocale'
import { useUpdateCheck } from '@/composables/useUpdateCheck'
import { useAnnouncements } from '@/composables/useAnnouncements'
import ThemeToggle from '@/components/ThemeToggle.vue'
import AnnouncementButton from '@/components/AnnouncementButton.vue'
import AnnouncementPanel from '@/components/AnnouncementPanel.vue'
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
  navGroupItems,
  navItem,
  primaryNavItemIds,
  type AppNavGroupId,
  type AppNavItem,
} from '@/navigation/appNavigation'

const route = useRoute()
const { naiveTheme, overrides, loadPluginThemes, suspendPluginTheme, restorePluginTheme } = useTheme()
const { locale, setLocale, t } = useLocale()
const { updateAvailable } = useUpdateCheck()
// naive-ui 无 ja locale；ja 界面回退英文组件语言，而非中文。
const naiveLocale = computed(() => locale.value === 'zh-CN' ? zhCN : enUS)
const naiveDateLocale = computed(() => locale.value === 'zh-CN' ? dateZhCN : dateEnUS)

const primaryItems = primaryNavItemIds.map(navItem)
const groupedItems = Object.fromEntries(
  appNavGroups.map(group => [group.id, navGroupItems(group)]),
) as Record<AppNavGroupId, AppNavItem[]>

function menuTo(id: string) {
  if (id !== 'play') return { name: id }
  const game = String(route.query.game || readCurrentGame() || '')
  return game ? { name: 'play', query: { game } } : { name: 'overview' }
}

const activeKey = computed(() => (route.name as string) ?? '')
const currentGameBadge = computed(() => String(route.query.game || readCurrentGame() || '').slice(0, 8))
const currentGameText = computed(() => currentGameBadge.value ? `${t('currentTable')} ${currentGameBadge.value}` : t('lobby'))
const publicRoute = computed(() => isPublicRoute(route))
const fullscreen = publicRoute
const workspaceGroup = computed(() => navGroupForRoute(activeKey.value))
const desktopNav = ref<HTMLElement | null>(null)
const openDesktopGroup = ref<AppNavGroupId | null>(null)
const openMobileGroup = ref<AppNavGroupId | null>(null)

function groupIsActive(groupId: AppNavGroupId) {
  return navGroupForRoute(activeKey.value) === groupId
}

function toggleDesktopGroup(groupId: AppNavGroupId) {
  openDesktopGroup.value = openDesktopGroup.value === groupId ? null : groupId
}

function toggleMobileGroup(groupId: AppNavGroupId) {
  openMobileGroup.value = openMobileGroup.value === groupId ? null : groupId
}

function closeNavigationMenus() {
  openDesktopGroup.value = null
  openMobileGroup.value = null
}

function onGlobalPointerDown(event: PointerEvent) {
  if (!openDesktopGroup.value || desktopNav.value?.contains(event.target as Node)) return
  openDesktopGroup.value = null
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
  window.addEventListener('pointerdown', onGlobalPointerDown)
  void initializeBackgroundImages()
  if (publicRoute.value) suspendPluginTheme()
  void loadOwnerPluginThemes()
  void load(locale.value).then(() => {
    tryOpenStartupAnnouncement()
  })
})
onBeforeUnmount(() => window.removeEventListener('pointerdown', onGlobalPointerDown))
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
    suspendPluginTheme()
    return
  }
  restorePluginTheme()
  void loadOwnerPluginThemes()
})
watch(() => route.fullPath, () => {
  closeNavigationMenus()
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

                  <nav
                    ref="desktopNav"
                    class="desktop-nav"
                    :aria-label="t('appSubtitle')"
                    @keydown.esc="closeNavigationMenus"
                  >
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
                    <div
                      v-for="group in appNavGroups"
                      :key="group.id"
                      class="desktop-nav-group"
                      :class="{ active: groupIsActive(group.id), open: openDesktopGroup === group.id }"
                    >
                      <button
                        type="button"
                        class="desktop-nav-link desktop-nav-trigger"
                        :class="{ active: groupIsActive(group.id) }"
                        :aria-expanded="openDesktopGroup === group.id"
                        aria-haspopup="menu"
                        @click="toggleDesktopGroup(group.id)"
                      >
                        <NIcon :component="group.icon" />
                        <span>{{ t(group.labelKey) }}</span>
                        <NIcon class="nav-chevron" :component="ChevronDownOutline" />
                        <i
                          v-if="group.id === 'management' && updateAvailable"
                          class="nav-update-dot"
                          :aria-label="t('updateAvailable')"
                        />
                      </button>
                      <div
                        v-if="openDesktopGroup === group.id"
                        class="desktop-nav-menu"
                        role="menu"
                        :aria-label="t(group.labelKey)"
                      >
                        <RouterLink
                          v-for="item in groupedItems[group.id]"
                          :key="item.id"
                          :to="menuTo(item.id)"
                          :class="{ active: activeKey === item.id }"
                          role="menuitem"
                        >
                          <NIcon :component="item.icon" />
                          <span>{{ t(item.labelKey) }}</span>
                          <i
                            v-if="item.id === 'settings' && updateAvailable"
                            class="nav-update-dot"
                            :aria-label="t('updateAvailable')"
                          />
                        </RouterLink>
                      </div>
                    </div>
                  </nav>

                  <div class="app-header-actions">
                    <AnnouncementButton @open="announcementOpen = true" />
                    <AnnouncementPanel v-model:show="announcementOpen" />
                    <ThemeToggle />
                    <label class="locale-select desktop-locale">
                      <span>{{ t('language') }}</span>
                      <select :value="locale" @change="onLocaleChange">
                        <option value="zh-CN">中文</option>
                        <option value="en">EN</option>
                        <option value="ja">日本語</option>
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

              <button
                v-if="openMobileGroup"
                type="button"
                class="mobile-nav-backdrop"
                :aria-label="t('close')"
                @click="closeNavigationMenus"
              />
              <section
                v-if="openMobileGroup"
                class="mobile-nav-panel"
                :aria-label="t(openMobileGroup === 'content' ? 'navContent' : 'navManagement')"
              >
                <header>
                  <strong>{{ t(openMobileGroup === 'content' ? 'navContent' : 'navManagement') }}</strong>
                  <button type="button" :aria-label="t('close')" @click="closeNavigationMenus">×</button>
                </header>
                <div class="mobile-nav-panel-grid">
                  <RouterLink
                    v-for="item in groupedItems[openMobileGroup]"
                    :key="item.id"
                    :to="menuTo(item.id)"
                    :class="{ active: activeKey === item.id }"
                  >
                    <NIcon :component="item.icon" />
                    <span>{{ t(item.labelKey) }}</span>
                    <i
                      v-if="item.id === 'settings' && updateAvailable"
                      class="nav-update-dot"
                      :aria-label="t('updateAvailable')"
                    />
                  </RouterLink>
                </div>
                <label v-if="openMobileGroup === 'management'" class="locale-select mobile-nav-locale">
                  <span>{{ t('language') }}</span>
                  <select :value="locale" @change="onLocaleChange">
                    <option value="zh-CN">中文</option>
                    <option value="en">EN</option>
                    <option value="ja">日本語</option>
                  </select>
                </label>
              </section>

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
                <button
                  type="button"
                  class="mobile-nav-action"
                  :class="{ active: groupIsActive('content') || openMobileGroup === 'content' }"
                  :aria-expanded="openMobileGroup === 'content'"
                  @click="toggleMobileGroup('content')"
                >
                  <span class="mobile-nav-icon"><NIcon :component="appNavGroups[0].icon" /></span>
                  <small>{{ t('navContent') }}</small>
                </button>
                <button
                  type="button"
                  class="mobile-nav-action"
                  :class="{ active: groupIsActive('management') || openMobileGroup === 'management' }"
                  :aria-expanded="openMobileGroup === 'management'"
                  @click="toggleMobileGroup('management')"
                >
                  <span class="mobile-nav-icon">
                    <NIcon :component="EllipsisHorizontalOutline" />
                    <i
                      v-if="updateAvailable"
                      class="nav-update-dot"
                      :aria-label="t('updateAvailable')"
                    />
                  </span>
                  <small>{{ t('navMore') }}</small>
                </button>
              </nav>
            </div>
          </NaiveBridge>
        </NDialogProvider>
      </NMessageProvider>
    </NLoadingBarProvider>
  </NConfigProvider>
</template>

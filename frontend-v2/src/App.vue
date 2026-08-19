<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  NConfigProvider, NMessageProvider, NDialogProvider, NLoadingBarProvider, NIcon,
  zhCN, enUS, dateZhCN, dateEnUS,
} from 'naive-ui'
import {
  HomeOutline, GameControllerOutline, PersonOutline, BookOutline,
  CloudOutline, DocumentTextOutline, OptionsOutline, SettingsOutline, MenuOutline,
  ExtensionPuzzleOutline,
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
import { readCurrentGame } from '@/stores/gameContext'
import { isPublicRoute } from '@/router'

const route = useRoute()
const { naiveTheme, overrides, loadPluginThemes, suspendPluginTheme, restorePluginTheme } = useTheme()
const { locale, setLocale, t } = useLocale()
const { updateAvailable } = useUpdateCheck()
// naive-ui 无 ja locale；ja 界面回退英文组件语言，而非中文。
const naiveLocale = computed(() => locale.value === 'zh-CN' ? zhCN : enUS)
const naiveDateLocale = computed(() => locale.value === 'zh-CN' ? dateZhCN : dateEnUS)

const items = [
  { id: 'overview', labelKey: 'navOverview', icon: HomeOutline },
  { id: 'play', labelKey: 'navPlay', icon: GameControllerOutline },
  { id: 'characters', labelKey: 'navCharacters', icon: PersonOutline },
  { id: 'lorebook', labelKey: 'navLorebook', icon: BookOutline },
  { id: 'memory', labelKey: 'navMemory', icon: CloudOutline },
  { id: 'logs', labelKey: 'navLogs', icon: DocumentTextOutline },
  { id: 'rules', labelKey: 'navRules', icon: OptionsOutline },
  { id: 'plugins', labelKey: 'navPlugins', icon: ExtensionPuzzleOutline },
  { id: 'settings', labelKey: 'navSettings', icon: SettingsOutline },
] as const

const mobileItems = items.filter(item => (
  ['overview', 'play', 'characters', 'lorebook', 'settings'] as string[]
).includes(item.id))
const utilityItems = items.filter(item => ['memory', 'logs', 'rules', 'plugins'].includes(item.id))

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
const mobileMore = ref<HTMLDetailsElement | null>(null)

function onLocaleChange(event: Event) {
  setLocale((event.target as HTMLSelectElement).value as Locale)
}

function onDesktopNavWheel(event: WheelEvent) {
  const element = event.currentTarget as HTMLElement
  if (element.scrollWidth <= element.clientWidth) return
  element.scrollLeft += event.deltaY || event.deltaX
  event.preventDefault()
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
    suspendPluginTheme()
    return
  }
  restorePluginTheme()
  void loadOwnerPluginThemes()
})
watch(() => route.fullPath, () => {
  if (mobileMore.value) mobileMore.value.open = false
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

                  <nav class="desktop-nav" :aria-label="t('appSubtitle')" @wheel="onDesktopNavWheel">
                    <RouterLink
                      v-for="item in items"
                      :key="item.id"
                      :to="menuTo(item.id)"
                      class="desktop-nav-link"
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
                    <details ref="mobileMore" class="mobile-more">
                      <summary :aria-label="t('navSettings')">
                        <NIcon :component="MenuOutline" />
                      </summary>
                      <div class="mobile-more-menu">
                        <RouterLink v-for="item in utilityItems" :key="item.id" :to="menuTo(item.id)">
                          <NIcon :component="item.icon" />
                          <span>{{ t(item.labelKey) }}</span>
                        </RouterLink>
                        <label class="locale-select">
                          <span>{{ t('language') }}</span>
                          <select :value="locale" @change="onLocaleChange">
                            <option value="zh-CN">中文</option>
                            <option value="en">EN</option>
                            <option value="ja">日本語</option>
                          </select>
                        </label>
                      </div>
                    </details>
                    <div class="operator-chip" :title="currentGameText">
                      <span class="operator-copy">
                        <strong>{{ currentGameText }}</strong>
                        <small><i />{{ t('online') }}</small>
                      </span>
                    </div>
                  </div>
                </div>
              </header>

              <main class="app-workspace">
                <RouterView v-slot="{ Component }">
                  <KeepAlive :include="['PlayView']">
                    <component :is="Component" />
                  </KeepAlive>
                </RouterView>
              </main>

              <nav class="mobile-bottom-nav" :aria-label="t('appSubtitle')">
                <RouterLink
                  v-for="item in mobileItems"
                  :key="item.id"
                  :to="menuTo(item.id)"
                  :class="{ active: activeKey === item.id }"
                >
                  <span class="mobile-nav-icon">
                    <NIcon :component="item.icon" />
                    <i
                      v-if="item.id === 'settings' && updateAvailable"
                      class="nav-update-dot"
                      :aria-label="t('updateAvailable')"
                    />
                  </span>
                  <small>{{ t(item.labelKey) }}</small>
                </RouterLink>
              </nav>
            </div>
          </NaiveBridge>
        </NDialogProvider>
      </NMessageProvider>
    </NLoadingBarProvider>
  </NConfigProvider>
</template>

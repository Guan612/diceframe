<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { NIcon } from 'naive-ui'
import type { MessageKey } from '@/i18n'
import { appNavGroups, navGroupItems, type AppNavItemId } from '@/navigation/appNavigation'
import { useLocale } from '@/composables/useLocale'
import { readCurrentGame } from '@/stores/gameContext'

const route = useRoute()
const { t } = useLocale()
const contentGroup = appNavGroups.find(group => group.id === 'content')!
const contentItems = navGroupItems(contentGroup)
const currentGame = computed(() => String(route.query.game || readCurrentGame() || ''))
const playTarget = computed(() => currentGame.value
  ? { name: 'play', query: { game: currentGame.value } }
  : { name: 'overview' })

const hintKeys: Partial<Record<AppNavItemId, MessageKey>> = {
  lorebook: 'contentWorkspaceLorebookHint',
  worlds: 'contentWorkspaceWorldsHint',
  adventures: 'contentWorkspaceAdventuresHint',
  rules: 'contentWorkspaceRulesHint',
}
</script>

<template>
  <div class="content-workspace">
    <aside class="content-workspace-rail">
      <header class="content-workspace-heading">
        <span>{{ t('contentWorkspaceKicker') }}</span>
        <strong>{{ t('contentWorkspaceTitle') }}</strong>
        <small>{{ t('contentWorkspaceHint') }}</small>
      </header>

      <nav class="content-workspace-nav" :aria-label="t('contentWorkspaceTitle')">
        <RouterLink
          v-for="item in contentItems"
          :key="item.id"
          :to="{ name: item.id }"
          :class="{ active: route.name === item.id }"
        >
          <NIcon :component="item.icon" />
          <span>
            <strong>{{ t(item.labelKey) }}</strong>
            <small>{{ t(hintKeys[item.id] || 'contentWorkspaceHint') }}</small>
          </span>
        </RouterLink>
      </nav>

      <section class="content-workspace-flow" :aria-label="t('contentWorkspaceRelation')">
        <span>{{ t('contentWorkspaceRelation') }}</span>
        <div>
          <b>{{ t('navLorebook') }}</b>
          <i>+</i>
          <b>{{ t('navRules') }}</b>
          <i>→</i>
          <b>{{ t('navWorlds') }}</b>
          <i>→</i>
          <b>{{ t('navAdventures') }}</b>
        </div>
        <small>{{ t('contentWorkspaceRelationHint') }}</small>
      </section>

      <footer class="content-workspace-session">
        <span>{{ currentGame ? `${t('currentTable')} ${currentGame.slice(0, 8)}` : t('lobby') }}</span>
        <RouterLink :to="playTarget">{{ t('contentWorkspaceEnterPlay') }}</RouterLink>
      </footer>
    </aside>

    <section class="content-workspace-main">
      <slot />
    </section>
  </div>
</template>

<script setup lang="ts">
import { NButton, NSelect } from 'naive-ui'
import { useLocale } from '@/composables/useLocale'
import type { BuiltinSkin, SkinName } from '@/composables/useTheme'
import type { PluginTheme } from '@/api/types'

const props = defineProps<{
  builtinSkins: readonly BuiltinSkin[]
  skin: SkinName
  pluginThemeId: string
  pluginThemes: PluginTheme[]
  themeOptions: { label: string; value: string }[]
  skinNameKeys: Record<SkinName, string>
  skinDescriptionKeys: Record<SkinName, string>
  loadPluginThemes: () => Promise<void> | void
  selectBuiltinSkin: (id: SkinName) => void
  selectPluginTheme: (value: string | null) => void
  clearPluginTheme: () => void
  selectedThemeDescription: () => string
}>()

const { t } = useLocale()
</script>

<template>
  <section class="theme-plugin-panel builtin-theme-panel">
    <div>
      <h3>{{ t('builtinThemes') }}</h3>
      <p class="muted">{{ t('builtinThemesHelp') }}</p>
    </div>
    <div class="builtin-theme-grid">
      <button
        v-for="item in builtinSkins"
        :key="item.id"
        type="button"
        class="builtin-theme-card"
        :class="{ active: skin === item.id && !pluginThemeId }"
        :aria-pressed="skin === item.id && !pluginThemeId"
        @click="selectBuiltinSkin(item.id)"
      >
        <span class="theme-swatches" aria-hidden="true">
          <i v-for="color in item.swatches" :key="color" :style="{ backgroundColor: color }" />
        </span>
        <strong>{{ t(skinNameKeys[item.id] as never) }}</strong>
        <small>{{ t(skinDescriptionKeys[item.id] as never) }}</small>
      </button>
    </div>
  </section>
  <section class="theme-plugin-panel">
    <div>
      <h3>{{ t('pluginThemes') }}</h3>
      <p class="muted">{{ t('pluginThemesHelp') }}</p>
    </div>
    <div class="theme-plugin-controls">
      <NSelect
        :value="pluginThemeId || null"
        :options="themeOptions"
        :placeholder="t('selectEnabledThemePlugin')"
        clearable
        @update:value="selectPluginTheme"
      />
      <NButton :disabled="!pluginThemeId" @click="clearPluginTheme">{{ t('clear') }}</NButton>
      <NButton @click="loadPluginThemes">{{ t('refresh') }}</NButton>
    </div>
    <p v-if="selectedThemeDescription()" class="muted">{{ selectedThemeDescription() }}</p>
    <p v-if="!pluginThemes.length" class="muted">{{ t('noEnabledThemePlugins') }}</p>
  </section>
</template>

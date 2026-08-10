<script setup lang="ts">
import { NCollapse, NCollapseItem, NButton, NIcon, NSelect, NSpin } from 'naive-ui'
import { CreateOutline, RefreshOutline } from '@vicons/ionicons5'
import { useLocale } from '@/composables/useLocale'
import type { CharacterPortrait, PluginContentResource } from '@/api/types'
import PortraitImage from '@/components/PortraitImage.vue'

interface ContentPluginGroup { key: string; labelKey: string; items: PluginContentResource[] }
interface ContentPluginEntry { plugin_id: string; plugin_name: string; groups: ContentPluginGroup[] }

const props = defineProps<{
  contentByPlugin: ContentPluginEntry[]
  contentGroupCount: number
  contentLoading: boolean
  contentTargetWorldId: string
  worldOptions: { label: string; value: string }[]
  busy: string
  loadContentResources: () => Promise<void> | void
  contentTitle: (item: PluginContentResource) => string
  contentSubtitle: (item: PluginContentResource) => string
  importContent: (kind: string, item: PluginContentResource) => Promise<void> | void
  importAllContent: (pluginId: string) => Promise<void> | void
}>()
const emit = defineEmits<{ 'update:contentTargetWorldId': [value: string]; 'open-export': [] }>()

const { t } = useLocale()

function contentPortrait(item: PluginContentResource): CharacterPortrait | undefined {
  const portrait = item.portrait
  return portrait && typeof portrait === 'object' && 'kind' in portrait
    ? portrait as CharacterPortrait
    : undefined
}
</script>

<template>
  <section class="toolbar-row content-pack-toolbar">
    <NSelect
      :value="contentTargetWorldId"
      :options="worldOptions"
      :placeholder="t('selectLorebook')"
      class="content-world-select"
      @update:value="(v) => emit('update:contentTargetWorldId', String(v || ''))"
    />
    <span class="muted">{{ t('contentTotalCount', { count: contentGroupCount }) }}</span>
    <NButton :loading="contentLoading" @click="loadContentResources">
      <template #icon><NIcon :component="RefreshOutline" /></template>
      {{ t('refresh') }}
    </NButton>
    <NButton type="primary" @click="emit('open-export')" class="create-pack-btn">
      <template #icon><NIcon :component="CreateOutline" /></template>
      {{ t('createContentPack') }}
    </NButton>
  </section>
  <p class="muted content-auto-import-hint">{{ t('contentAutoImportHint') }}</p>
  <NSpin :show="contentLoading">
    <p v-if="!contentByPlugin.length" class="muted">{{ t('noPluginsAvailable') }}</p>
    <NCollapse v-else class="content-collapse">
      <NCollapseItem v-for="plugin in contentByPlugin" :key="plugin.plugin_id" :name="plugin.plugin_id">
        <template #header>
          <div class="content-plugin-head">
            <h3>{{ plugin.plugin_name }}</h3>
            <span class="muted">{{ plugin.plugin_id }}</span>
          </div>
        </template>
        <template #header-extra>
          <span class="content-count muted">{{ plugin.groups.reduce((sum, g) => sum + g.items.length, 0) }} {{ t('contentItems') }}</span>
          <NButton
            size="small"
            secondary
            class="import-all-btn"
            :loading="busy === `import-all:${plugin.plugin_id}`"
            @click.stop="importAllContent(plugin.plugin_id)"
          >
            {{ t('importAllContent') }}
          </NButton>
        </template>
        <div class="content-plugin-body">
          <section v-for="group in plugin.groups" :key="group.key" class="content-group">
            <h4>{{ t(group.labelKey as never) }} <span class="muted">{{ group.items.length }}</span></h4>
            <div v-if="group.items.length" class="content-list">
              <article
                v-for="item in group.items"
                :key="`${group.key}:${item.plugin_id}:${item.id || item.name || item.character_name}`"
                class="content-item"
              >
                <PortraitImage
                  v-if="contentPortrait(item)"
                  :portrait="contentPortrait(item)"
                  :rule-id="String(item.rule_id || '')"
                  :seed="String(item.id || item.name || item.character_name || '')"
                  :name="contentTitle(item)"
                  :size="54"
                />
                <div class="content-item-main">
                  <strong>{{ contentTitle(item) }}</strong>
                  <p class="muted">{{ contentSubtitle(item) || t('noDescription') }}</p>
                </div>
                <NButton
                  size="small"
                  secondary
                  :disabled="group.key !== 'character_template' && !contentTargetWorldId"
                  :loading="busy === `${group.key}:${item.plugin_id}:${item.id || item.name || item.character_name}`"
                  @click="importContent(group.key, item)"
                >
                  {{ group.key === 'character_template' ? t('importCharacterCard') : t('importLorebook') }}
                </NButton>
              </article>
            </div>
            <p v-else class="muted">{{ t('none') }}</p>
          </section>
        </div>
      </NCollapseItem>
    </NCollapse>
  </NSpin>
</template>

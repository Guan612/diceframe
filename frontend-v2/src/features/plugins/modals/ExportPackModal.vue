<script setup lang="ts">
import { NButton, NCheckbox, NIcon, NInput, NModal, NSelect, NSpin, type SelectOption } from 'naive-ui'
import { CloudDownloadOutline, CreateOutline } from '@vicons/ionicons5'
import { useLocale } from '@/composables/useLocale'

defineProps<{
  show: boolean
  authorLoading: boolean
  packId: string
  packName: string
  packVersion: string
  packDescription: string
  selectedWorldId: string
  selectedRuleId: string
  selectedCardIds: string[]
  includePortraits: boolean
  includeSceneImages: boolean
  authorWorldOptions: SelectOption[]
  authorRuleOptions: SelectOption[]
  authorCardOptions: SelectOption[]
  busy: string
  setPackId: (v: string) => void
  setPackName: (v: string) => void
  setPackVersion: (v: string) => void
  setPackDescription: (v: string) => void
  setSelectedWorldId: (v: string | null) => void
  setSelectedRuleId: (v: string | null) => void
  setSelectedCardIds: (v: (string | number)[] | null) => void
  setIncludePortraits: (v: boolean) => void
  setIncludeSceneImages: (v: boolean) => void
  setExportSceneImage: (kind: 'world' | 'rule', event: Event) => void
  exportPack: (repoSource: boolean) => Promise<void> | void
}>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()

const { t } = useLocale()
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    class="export-pack-modal"
    :title="t('exportPackTitle')"
    :bordered="false"
    style="width: min(800px, calc(100vw - 24px)); max-height: calc(100dvh - 28px);"
    @update:show="(v: boolean) => emit('update:show', v)"
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
                <NInput :value="packId" placeholder="my-cool-pack" @update:value="setPackId" />
              </label>
            </div>
            <div class="field">
              <label class="input-label">
                <span class="field-title">{{ t('packName') }}</span>
                <NInput :value="packName" @update:value="setPackName" />
              </label>
            </div>
            <div class="field export-version-field">
              <label class="input-label">
                <span class="field-title">{{ t('packVersion') }}</span>
                <NInput :value="packVersion" @update:value="setPackVersion" />
              </label>
            </div>
            <div class="field export-description-field">
              <label class="input-label">
                <span class="field-title">{{ t('packDescription') }}</span>
                <NInput :value="packDescription" type="textarea" :autosize="{ minRows: 1, maxRows: 2 }" @update:value="setPackDescription" />
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
                <NSelect :value="selectedWorldId" :options="authorWorldOptions" clearable @update:value="setSelectedWorldId" />
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
                <NSelect :value="selectedRuleId" :options="authorRuleOptions" clearable @update:value="setSelectedRuleId" />
              </label>
              <label class="compact-file-field" :class="{ disabled: !selectedRuleId || !includeSceneImages }">
                <span>{{ t('ruleSceneImage') }}</span>
                <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="!selectedRuleId || !includeSceneImages" @change="setExportSceneImage('rule', $event)">
                <small class="muted">{{ t('ruleSceneImageHint') }}</small>
              </label>
            </div>
            <label class="input-label export-card-select">
              <span class="field-title">{{ t('selectCards') }}</span>
              <NSelect :value="selectedCardIds" :options="authorCardOptions" multiple clearable @update:value="setSelectedCardIds" />
            </label>
          </div>
        </section>

        <section class="export-pack-section export-resource-section">
          <h3>{{ t('exportPackPortableAssets') }}</h3>
          <div class="export-resource-options">
            <label class="export-resource-option" :title="t('includeContentPackPortraitsHint')">
              <NCheckbox :checked="includePortraits" @update:checked="setIncludePortraits">{{ t('includeContentPackPortraits') }}</NCheckbox>
            </label>
            <label class="export-resource-option" :title="t('includeContentPackSceneImagesHint')">
              <NCheckbox :checked="includeSceneImages" @update:checked="setIncludeSceneImages">{{ t('includeContentPackSceneImages') }}</NCheckbox>
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

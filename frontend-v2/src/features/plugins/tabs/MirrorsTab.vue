<script setup lang="ts">
import { NButton, NIcon, NInput, NInputNumber, NSpin, NSwitch, NTag } from 'naive-ui'
import {
  AddOutline, ChevronDown, ChevronUp, CreateOutline, RefreshOutline, TrashOutline,
} from '@vicons/ionicons5'
import { useLocale } from '@/composables/useLocale'
import type { PluginMirror } from '@/api/types'

const { t } = useLocale()

defineProps<{
  mirrors: PluginMirror[]
  mirrorTests: Record<string, string>
  mirrorLoading: boolean
  newMirror: PluginMirror
  busy: string
  loadMirrors: () => Promise<void> | void
  addMirror: () => Promise<void> | void
  saveMirror: (mirror: PluginMirror, patch: Partial<PluginMirror>) => Promise<void> | void
  deleteMirror: (mirror: PluginMirror) => Promise<void> | void
  testMirror: (mirror?: PluginMirror) => Promise<void> | void
}>()
</script>

<template>
  <section class="toolbar-row">
    <NButton :loading="mirrorLoading" @click="loadMirrors">
      <template #icon><NIcon :component="RefreshOutline" /></template>
      {{ t('refresh') }}
    </NButton>
    <NButton :loading="busy === 'mirror-test:all'" @click="testMirror()">
      {{ t('testAll') }}
    </NButton>
  </section>

  <div class="mirror-form">
    <NInput v-model:value="newMirror.id" class="mirror-field-id" :placeholder="t('mirrorIdPlaceholder')" />
    <NInput v-model:value="newMirror.name" class="mirror-field-name" :placeholder="t('name')" />
    <NInput v-model:value="newMirror.raw_prefix" class="mirror-url-input mirror-field-raw" :placeholder="t('rawPrefix')" />
    <NInput v-model:value="newMirror.clone_prefix" class="mirror-url-input mirror-field-clone" :placeholder="t('clonePrefix')" />
    <NInputNumber v-model:value="newMirror.priority" :min="1" class="mirror-field-priority" :placeholder="t('priority')" />
    <NSwitch v-model:value="newMirror.enabled" class="mirror-field-switch" />
    <NButton type="primary" class="mirror-field-add" :loading="busy === 'mirror:add'" @click="addMirror">
      <template #icon><NIcon :component="AddOutline" /></template>
      {{ t('add') }}
    </NButton>
  </div>

  <NSpin :show="mirrorLoading">
    <div class="mirror-list">
      <article v-for="mirror in mirrors" :key="mirror.id" class="mirror-row">
        <div class="mirror-main">
          <div class="mirror-heading">
            <NSwitch :value="mirror.enabled" @update:value="saveMirror(mirror, { enabled: $event })" />
            <strong>{{ mirror.name }}</strong>
            <NTag size="small">{{ mirror.id }}</NTag>
            <NTag size="small">{{ t('priority') }} {{ mirror.priority }}</NTag>
          </div>
          <p class="muted">Raw：{{ mirror.raw_prefix }}</p>
          <div class="mirror-edit-grid">
            <NInput v-model:value="mirror.name" :placeholder="t('name')" />
            <NInput v-model:value="mirror.raw_prefix" class="mirror-url-input" :placeholder="t('rawPrefix')" />
            <NInput v-model:value="mirror.clone_prefix" class="mirror-url-input" :placeholder="t('downloadPrefix')" />
            <NInputNumber v-model:value="mirror.priority" :min="1" />
          </div>
          <p v-if="mirrorTests[mirror.id]" class="mirror-test">{{ mirrorTests[mirror.id] }}</p>
        </div>
        <div class="mirror-actions">
          <NButton size="small" :loading="busy === `mirror-test:${mirror.id}`" @click="testMirror(mirror)">{{ t('test') }}</NButton>
          <NButton size="small" @click="saveMirror(mirror, { priority: Math.max(1, mirror.priority - 1) })">
            <template #icon><NIcon :component="ChevronUp" /></template>
          </NButton>
          <NButton size="small" @click="saveMirror(mirror, { priority: mirror.priority + 1 })">
            <template #icon><NIcon :component="ChevronDown" /></template>
          </NButton>
          <NButton size="small" @click="saveMirror(mirror, mirror)">
            <template #icon><NIcon :component="CreateOutline" /></template>
            {{ t('saveAction') }}
          </NButton>
          <NButton size="small" type="error" tertiary @click="deleteMirror(mirror)">
            <template #icon><NIcon :component="TrashOutline" /></template>
          </NButton>
        </div>
      </article>
    </div>
  </NSpin>
</template>

<script setup lang="ts">
import { NAlert, NButton, NModal, NRate, NSpin } from 'naive-ui'
import { useLocale } from '@/composables/useLocale'
import type { PluginMarketplaceItem } from '@/api/types'

const props = defineProps<{
  show: boolean
  hubDetail: PluginMarketplaceItem | null
  hubDetailLoading: boolean
  hubRating: number | null
  busy: string
  safeHubReadmeHtml: string
  toggleHubLike: () => Promise<void> | void
  saveHubRating: (stars: number | null) => Promise<void> | void
}>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()

const { t } = useLocale()
</script>

<template>
  <NModal :show="show" preset="card" class="hub-detail-modal" :title="hubDetail?.name || t('hubPluginDetails')" @update:show="(v: boolean) => emit('update:show', v)">
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
</template>

<script setup lang="ts">
/**
 * 邀请二维码：把已经算好的加入链接同时以二维码和文本两种形态给出。
 *
 * 链接由调用方（PlayView）用 buildJoinLink 算好后传进来——公网地址、独立前端
 * origin、后端地址这几个来源的取舍是对局页的职责，本组件只负责出示。
 */
import QrCode from '@/components/common/QrCode.vue'
import { useLocale } from '@/composables/useLocale'
import { useToast } from '@/composables/useToast'
import { copyToClipboard } from '@/utils/clipboard'

const props = defineProps<{ link: string; title: string; hint?: string }>()
const emit = defineEmits<{ close: [] }>()

const { t } = useLocale()
const toast = useToast()

async function copy() {
  await copyToClipboard(props.link)
  toast.success(t('inviteCopied'))
}
</script>

<template>
  <div class="modal" @click.self="emit('close')">
    <section class="dialog invite-dialog">
      <header><h2>{{ title }}</h2><button @click="emit('close')">×</button></header>
      <p v-if="hint">{{ hint }}</p>
      <div class="invite-qr">
        <QrCode :value="link" :size="216" level="M" />
      </div>
      <p class="invite-scan-hint">{{ t('inviteScanHint') }}</p>
      <!-- 扫码之外仍要留可复制的原文：微信/QQ 里发链接比拍屏幕现实得多 -->
      <code class="invite-link">{{ link }}</code>
      <div class="actions">
        <button @click="emit('close')">{{ t('close') }}</button>
        <button class="primary" @click="copy">{{ t('inviteCopyLink') }}</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.invite-dialog{max-width:420px}
.invite-qr{display:flex;justify-content:center;padding:12px 0}
.invite-scan-hint{margin:0 0 10px;text-align:center;color:var(--df-text-muted);font-size:13px}
.invite-link{display:block;padding:8px 10px;border-radius:6px;background:color-mix(in srgb,var(--df-accent) 10%,transparent);font-family:var(--df-font-mono);font-size:12px;word-break:break-all;line-height:1.6}
</style>

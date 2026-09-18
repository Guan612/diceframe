<script setup lang="ts">
/**
 * 邀请二维码：把已经算好的加入链接同时以二维码和文本两种形态给出。
 *
 * 链接由调用方（PlayView）用 buildJoinLink 算好后传进来——公网地址、独立前端
 * origin、后端地址这几个来源的取舍是对局页的职责，本组件只负责出示。
 *
 * 这里同时给出「好友需要能访问该地址」的说明：复制成功不等于对方打得开，而地址
 * 该用局域网还是公网取决于玩家自己的网络环境。说明是静态的辅助信息，不做任何
 * 网络探测，也不阻止复制；要改地址就去设置里的分享地址。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import QrCode from '@/components/common/QrCode.vue'
import { useLocale } from '@/composables/useLocale'
import { useToast } from '@/composables/useToast'
import { copyToClipboard } from '@/utils/clipboard'

const props = defineProps<{ link: string; title: string; hint?: string }>()
const emit = defineEmits<{ close: [] }>()

const { t } = useLocale()
const toast = useToast()
const router = useRouter()

/** 链接 host 明确只指向本机时，其它设备必然打不开——这是唯一可靠的静态判断。 */
const localOnly = computed(() => {
  try {
    const host = new URL(props.link).hostname.toLowerCase()
    return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]'
  } catch {
    return false
  }
})

async function copy() {
  await copyToClipboard(props.link)
  toast.success(t('inviteCopied'))
}

function openShareSettings() {
  emit('close')
  router.push({ name: 'settings' })
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
      <p class="invite-address-hint">
        <span aria-hidden="true">ⓘ</span>
        {{ t('inviteAddressHint') }}
        <button type="button" class="invite-address-settings" @click="openShareSettings">{{ t('inviteAddressSettingsLink') }}</button>
      </p>
      <p v-if="localOnly" class="invite-address-local">{{ t('inviteLocalOnlyWarning') }}</p>
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
.invite-address-hint{margin:10px 0 0;color:var(--df-text-muted);font-size:12px;line-height:1.6}
.invite-address-settings{margin-left:4px;padding:0;border:0;background:none;color:var(--df-accent);font-size:12px;text-decoration:underline;cursor:pointer}
.invite-address-local{margin:6px 0 0;color:var(--df-danger,var(--df-text-muted));font-size:12px;line-height:1.6}
</style>

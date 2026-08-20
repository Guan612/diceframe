<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { NIcon } from 'naive-ui'
import { ArrowBackOutline, CopyOutline, LinkOutline, SendOutline } from '@vicons/ionicons5'
import { createRendezvousRoom } from '@/api/peer'
import { errorMessage } from '@/api/client'
import { PeerConnectionSession, type PeerConnectionState } from '@/composables/usePeerConnection'
import { useLocale } from '@/composables/useLocale'
import { useToast } from '@/composables/useToast'
import { copyToClipboard } from '@/utils/clipboard'
import { DEFAULT_STUN_URL, decodePeerInvite, encodePeerInvite } from './inviteCode'

type Mode = 'host' | 'guest'
type DiagnosticMessage = { direction: 'sent' | 'received'; text: string }

const { t } = useLocale()
const toast = useToast()
const mode = ref<Mode>('host')
const state = ref<PeerConnectionState>('idle')
const stateDetail = ref('')
const busy = ref(false)
const stunUrl = ref(DEFAULT_STUN_URL)
const roomCode = ref('')
const inviteCode = ref('')
const inviteInput = ref('')
const outbound = ref('')
const messages = ref<DiagnosticMessage[]>([])
let session: PeerConnectionSession | null = null

const connected = computed(() => state.value === 'connected')
const stateLabel = computed(() => t(`peerState_${state.value}`))

function updateState(next: PeerConnectionState, detail = '') {
  state.value = next
  stateDetail.value = detail
}

function stopSession() {
  session?.close()
  session = null
}

function selectMode(next: Mode) {
  stopSession()
  mode.value = next
  state.value = 'idle'
  stateDetail.value = ''
  roomCode.value = ''
  inviteCode.value = ''
  messages.value = []
}

function startSession(options: {
  role: Mode
  roomCode: string
  token: string
  websocketUrl: string
  stunUrl: string
}) {
  stopSession()
  session = new PeerConnectionSession({
    ...options,
    onState: updateState,
    onMessage(message) {
      messages.value.push({ direction: 'received', text: message })
    },
  })
  session.connect()
}

async function createRoom() {
  busy.value = true
  stateDetail.value = ''
  try {
    const room = await createRendezvousRoom()
    roomCode.value = room.room_code
    inviteCode.value = encodePeerInvite(room, stunUrl.value)
    startSession({
      role: 'host',
      roomCode: room.room_code,
      token: room.host_token,
      websocketUrl: room.websocket_url,
      stunUrl: stunUrl.value.trim(),
    })
  } catch (error) {
    updateState('error', errorMessage(error))
  } finally {
    busy.value = false
  }
}

function joinRoom() {
  try {
    const invite = decodePeerInvite(inviteInput.value)
    if (Date.parse(invite.expiresAt) <= Date.now()) throw new Error(t('peerInviteExpired'))
    roomCode.value = invite.roomCode
    stunUrl.value = invite.stunUrl
    startSession({
      role: 'guest',
      roomCode: invite.roomCode,
      token: invite.guestToken,
      websocketUrl: invite.websocketUrl,
      stunUrl: invite.stunUrl,
    })
  } catch (error) {
    updateState('error', error instanceof Error && error.message !== 'invalid_invite'
      ? error.message
      : t('peerInviteInvalid'))
  }
}

async function copyInvite() {
  await copyToClipboard(inviteCode.value)
  toast.success(t('peerInviteCopied'))
}

function sendDiagnostic() {
  const text = outbound.value.trim()
  if (!text || !session) return
  try {
    session.send(text)
    messages.value.push({ direction: 'sent', text })
    outbound.value = ''
  } catch {
    toast.error(t('peerSendUnavailable'))
  }
}

onBeforeUnmount(stopSession)
</script>

<template>
  <section class="peer-page">
    <header class="peer-header">
      <RouterLink :to="{ name: 'overview' }" class="peer-back">
        <NIcon :component="ArrowBackOutline" />{{ t('peerBack') }}
      </RouterLink>
      <span class="section-kicker">{{ t('peerKicker') }}</span>
      <h1>{{ t('peerTitle') }}</h1>
      <p>{{ t('peerSubtitle') }}</p>
    </header>

    <main class="peer-layout">
      <section class="peer-card peer-setup">
        <div class="peer-mode-tabs">
          <button :class="{ active: mode === 'host' }" @click="selectMode('host')">{{ t('peerHostMode') }}</button>
          <button :class="{ active: mode === 'guest' }" @click="selectMode('guest')">{{ t('peerGuestMode') }}</button>
        </div>

        <label v-if="mode === 'host'" class="peer-field">
          <span>{{ t('peerStunServer') }}</span>
          <input v-model.trim="stunUrl" :disabled="state !== 'idle' && state !== 'closed' && state !== 'error'">
          <small>{{ t('peerStunHint') }}</small>
        </label>

        <template v-if="mode === 'host'">
          <button class="success peer-primary" :disabled="busy || state === 'signaling' || state === 'waiting' || state === 'connecting'" @click="createRoom">
            <NIcon :component="LinkOutline" />{{ t('peerCreateRoom') }}
          </button>
          <div v-if="inviteCode" class="peer-invite">
            <div><span>{{ t('peerRoomCode') }}</span><code>{{ roomCode }}</code></div>
            <label class="peer-field">
              <span>{{ t('peerInviteCode') }}</span>
              <textarea :value="inviteCode" readonly rows="4" />
            </label>
            <button @click="copyInvite"><NIcon :component="CopyOutline" />{{ t('peerCopyInvite') }}</button>
            <small>{{ t('peerInviteSecurityHint') }}</small>
          </div>
        </template>

        <template v-else>
          <label class="peer-field">
            <span>{{ t('peerPasteInvite') }}</span>
            <textarea v-model.trim="inviteInput" rows="6" :placeholder="t('peerInvitePlaceholder')" />
          </label>
          <button class="success peer-primary" :disabled="!inviteInput || state === 'signaling' || state === 'connecting'" @click="joinRoom">
            <NIcon :component="LinkOutline" />{{ t('peerJoinRoom') }}
          </button>
        </template>
      </section>

      <section class="peer-card peer-status">
        <header>
          <div>
            <span>{{ t('peerConnectionStatus') }}</span>
            <strong :class="`peer-state-${state}`"><i />{{ stateLabel }}</strong>
          </div>
          <code v-if="roomCode">{{ roomCode }}</code>
        </header>
        <p v-if="stateDetail" class="error-banner">{{ stateDetail }}</p>
        <p class="peer-privacy-warning">{{ t('peerPrivacyWarning') }}</p>
        <p class="peer-boundary">{{ t('peerBoundary') }}</p>

        <div class="peer-diagnostics">
          <h2>{{ t('peerDiagnosticTitle') }}</h2>
          <p>{{ t('peerDiagnosticHint') }}</p>
          <div class="peer-message-log">
            <p v-if="!messages.length" class="muted">{{ t('peerNoMessages') }}</p>
            <div v-for="(message, index) in messages" :key="index" :class="message.direction">
              <small>{{ t(message.direction === 'sent' ? 'peerSent' : 'peerReceived') }}</small>
              <span>{{ message.text }}</span>
            </div>
          </div>
          <form class="peer-message-form" @submit.prevent="sendDiagnostic">
            <input v-model="outbound" maxlength="4096" :disabled="!connected" :placeholder="t('peerMessagePlaceholder')">
            <button class="success" :disabled="!connected || !outbound.trim()">
              <NIcon :component="SendOutline" />{{ t('send') }}
            </button>
          </form>
        </div>
      </section>
    </main>
  </section>
</template>

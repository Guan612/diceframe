export type PeerRole = 'host' | 'guest'
export type PeerConnectionState = 'idle' | 'signaling' | 'waiting' | 'connecting' | 'connected' | 'closed' | 'error'

interface PeerConnectionOptions {
  role: PeerRole
  roomCode: string
  token: string
  websocketUrl: string
  stunUrl: string
  onState: (state: PeerConnectionState, detail?: string) => void
  onMessage: (message: string) => void
}

interface SignalingMessage {
  type?: string
  description?: RTCSessionDescriptionInit
  candidate?: RTCIceCandidateInit
  code?: string
}

export class PeerConnectionSession {
  private socket: WebSocket | null = null
  private peer: RTCPeerConnection | null = null
  private channel: RTCDataChannel | null = null
  private pendingCandidates: RTCIceCandidateInit[] = []
  private closed = false

  constructor(private readonly options: PeerConnectionOptions) {}

  connect(): void {
    if (this.socket || this.peer) throw new Error('session_already_started')
    this.closed = false
    this.options.onState('signaling')
    this.peer = new RTCPeerConnection({
      iceServers: this.options.stunUrl ? [{ urls: this.options.stunUrl }] : [],
    })
    this.peer.onicecandidate = event => {
      if (event.candidate) {
        this.sendSignal({ type: 'ice', candidate: event.candidate.toJSON() })
      } else {
        this.sendSignal({ type: 'ice-complete' })
      }
    }
    this.peer.onconnectionstatechange = () => {
      const state = this.peer?.connectionState
      if (state === 'failed') this.fail('peer_connection_failed')
      if (state === 'disconnected' && !this.closed) this.options.onState('connecting', 'peer_disconnected')
      if (state === 'closed' && !this.closed) this.options.onState('closed')
    }

    if (this.options.role === 'host') {
      this.bindChannel(this.peer.createDataChannel('diceframe-control', { ordered: true }))
    } else {
      this.peer.ondatachannel = event => this.bindChannel(event.channel)
    }

    this.socket = new WebSocket(this.options.websocketUrl)
    this.socket.onopen = () => {
      this.sendSignal({
        type: 'authenticate',
        role: this.options.role,
        token: this.options.token,
      })
    }
    this.socket.onmessage = event => {
      if (typeof event.data !== 'string') return
      void this.handleSignal(event.data).catch(error => this.fail(String(error)))
    }
    this.socket.onerror = () => this.fail('signaling_socket_failed')
    this.socket.onclose = () => {
      this.socket = null
      if (!this.closed && this.channel?.readyState !== 'open') this.fail('signaling_socket_closed')
    }
  }

  send(message: string): void {
    const text = message.trim()
    if (!text || text.length > 4096 || this.channel?.readyState !== 'open') {
      throw new Error('data_channel_not_ready')
    }
    if (this.channel.bufferedAmount > 256 * 1024) throw new Error('data_channel_busy')
    this.channel.send(text)
  }

  close(): void {
    this.closed = true
    this.channel?.close()
    this.peer?.close()
    this.socket?.close(1000)
    this.channel = null
    this.peer = null
    this.socket = null
    this.pendingCandidates = []
    this.options.onState('closed')
  }

  private async handleSignal(raw: string): Promise<void> {
    const message = JSON.parse(raw) as SignalingMessage
    if (message.type === 'authenticated' || message.type === 'peer-waiting') {
      this.options.onState('waiting')
      return
    }
    if (message.type === 'peer-ready') {
      this.options.onState('connecting')
      if (this.options.role === 'host') await this.createOffer()
      return
    }
    if (message.type === 'offer' && this.options.role === 'guest' && message.description) {
      await this.peer?.setRemoteDescription(message.description)
      await this.flushCandidates()
      const answer = await this.peer?.createAnswer()
      if (!answer || !this.peer) throw new Error('answer_creation_failed')
      await this.peer.setLocalDescription(answer)
      this.sendSignal({ type: 'answer', description: this.peer.localDescription })
      return
    }
    if (message.type === 'answer' && this.options.role === 'host' && message.description) {
      await this.peer?.setRemoteDescription(message.description)
      await this.flushCandidates()
      return
    }
    if (message.type === 'ice' && message.candidate) {
      if (this.peer?.remoteDescription) await this.peer.addIceCandidate(message.candidate)
      else this.pendingCandidates.push(message.candidate)
      return
    }
    if (message.type === 'peer-left') {
      if (this.channel?.readyState !== 'open') this.options.onState('waiting')
      return
    }
    if (message.type === 'complete') {
      this.socket?.close(1000)
      return
    }
    if (message.type === 'error') throw new Error(message.code || 'signaling_error')
  }

  private async createOffer(): Promise<void> {
    if (!this.peer) throw new Error('peer_connection_missing')
    const offer = await this.peer.createOffer()
    await this.peer.setLocalDescription(offer)
    this.sendSignal({ type: 'offer', description: this.peer.localDescription })
  }

  private async flushCandidates(): Promise<void> {
    if (!this.peer) return
    for (const candidate of this.pendingCandidates) await this.peer.addIceCandidate(candidate)
    this.pendingCandidates = []
  }

  private bindChannel(channel: RTCDataChannel): void {
    this.channel = channel
    channel.onopen = () => {
      this.options.onState('connected')
      this.sendSignal({ type: 'complete' })
    }
    channel.onmessage = event => {
      if (typeof event.data === 'string' && event.data.length <= 4096) this.options.onMessage(event.data)
    }
    channel.onerror = () => this.fail('data_channel_failed')
    channel.onclose = () => {
      if (!this.closed) this.options.onState('closed')
    }
  }

  private sendSignal(payload: Record<string, unknown>): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(payload))
  }

  private fail(detail: string): void {
    if (this.closed) return
    this.closed = true
    this.channel?.close()
    this.peer?.close()
    this.socket?.close()
    this.channel = null
    this.peer = null
    this.socket = null
    this.pendingCandidates = []
    this.options.onState('error', detail)
  }
}

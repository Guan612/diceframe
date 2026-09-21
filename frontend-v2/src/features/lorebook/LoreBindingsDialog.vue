<script setup lang="ts">
import { computed, ref, watch } from 'vue'

export interface LoreBinding {
  id: string
  book_id: string
  scope_kind: string
  scope_id: string
  role?: string
  order?: number
}

export interface LoreBindingTargetCharacter { uid:string; name:string }

const props = defineProps<{
  open: boolean
  bookName?: string
  bindings?: LoreBinding[]
  worldId?: string
  worldName?: string
  gameKey?: string
  characters?: LoreBindingTargetCharacter[]
  busy?: boolean
}>()
const emit = defineEmits<{
  close:[]
  add:[binding: { scope_kind:string; scope_id:string }]
  remove:[bindingId: string]
}>()

type ScopeChoice = 'world' | 'game' | 'character' | 'global'
const scope = ref<ScopeChoice>('world')
const characterUid = ref('')

const canBindGame = computed(() => !!props.gameKey)
const canBindCharacter = computed(() => (props.characters || []).length > 0)
const addDisabled = computed(() => props.busy || (scope.value === 'character' && !characterUid.value))

watch(() => props.open, isOpen => {
  if (!isOpen) return
  scope.value = 'world'
  characterUid.value = ''
})

function scopeTargetLabel(binding: LoreBinding): string {
  if (binding.scope_kind === 'global') return 'global'
  if (binding.scope_kind === 'character') {
    const match = (props.characters || []).find(item => item.uid === binding.scope_id)
    return match ? match.name : binding.scope_id
  }
  if (binding.scope_kind === 'world' && binding.scope_id === props.worldId) {
    return props.worldName || binding.scope_id
  }
  return binding.scope_id || '—'
}

function add() {
  if (scope.value === 'global') return emit('add', { scope_kind: 'global', scope_id: '' })
  if (scope.value === 'game') return emit('add', { scope_kind: 'game', scope_id: String(props.gameKey || '') })
  if (scope.value === 'character') return emit('add', { scope_kind: 'character', scope_id: characterUid.value })
  return emit('add', { scope_kind: 'world', scope_id: String(props.worldId || '') })
}
</script>

<template>
  <div v-if="open" class="lore-bindings-dialog" role="dialog" aria-modal="true" aria-label="Manage bindings">
    <div class="lore-bindings-dialog__panel">
      <h2>绑定<template v-if="bookName">：{{ bookName }}</template></h2>

      <table class="lore-bindings-dialog__table">
        <thead>
          <tr><th>scope</th><th>目标</th><th>role</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="binding in bindings || []" :key="binding.id" class="lore-binding-row">
            <td>{{ binding.scope_kind }}</td>
            <td>{{ scopeTargetLabel(binding) }}</td>
            <td>{{ binding.role || '—' }}</td>
            <td>
              <button
                class="danger"
                :disabled="busy"
                :aria-label="`解除绑定 ${binding.scope_kind}`"
                @click="emit('remove', binding.id)"
              >解除</button>
            </td>
          </tr>
          <tr v-if="!(bindings || []).length">
            <td colspan="4" class="muted">这本世界书当前没有绑定（不会被任何运行时作用域加载）。</td>
          </tr>
        </tbody>
      </table>

      <fieldset class="lore-bindings-dialog__add">
        <legend>新增绑定</legend>
        <label><input v-model="scope" type="radio" value="world"> 当前 world</label>
        <label><input v-model="scope" type="radio" value="game" :disabled="!canBindGame"> 当前 game</label>
        <label><input v-model="scope" type="radio" value="character" :disabled="!canBindCharacter"> 某 character</label>
        <select
          v-if="scope === 'character'"
          v-model="characterUid"
          aria-label="选择绑定的角色"
        >
          <option value="">请选择角色…</option>
          <option v-for="item in characters || []" :key="item.uid" :value="item.uid">{{ item.name }}</option>
        </select>
        <label><input v-model="scope" type="radio" value="global"> global</label>
        <button :disabled="addDisabled" @click="add()">新增</button>
      </fieldset>

      <div class="lore-bindings-dialog__buttons">
        <button @click="emit('close')">关闭</button>
      </div>
    </div>
  </div>
</template>

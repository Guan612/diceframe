<script setup lang="ts">
import { computed, ref } from 'vue'

export interface LorebookCard { id:string; name:string; scope?:string; primary?:boolean; enabled?:boolean }

const props = defineProps<{ books: LorebookCard[]; activeId?: string; busy?: boolean }>()
const emit = defineEmits<{
  select:[id:string]
  create:[]
  rename:[book: LorebookCard]
  remove:[book: LorebookCard]
  'toggle-enabled':[book: LorebookCard]
  bindings:[book: LorebookCard]
  import:[]
  export:[]
}>()

// 「全部」之外的每个 scope 都对应 binding 的 canonical scope_kind，UI 不发明新 scope。
const SCOPES = ['all', 'world', 'game', 'character', 'global'] as const
type Scope = typeof SCOPES[number]
const SCOPE_LABELS: Record<Scope, string> = {
  all: '全部', world: '当前世界', game: '当前游戏', character: '角色', global: '全局',
}

const search = ref('')
const scope = ref<Scope>('all')

const visibleBooks = computed(() => {
  const needle = search.value.trim().toLowerCase()
  return props.books.filter(book => {
    if (scope.value !== 'all' && String(book.scope || '') !== scope.value) return false
    if (!needle) return true
    return book.name.toLowerCase().includes(needle) || book.id.toLowerCase().includes(needle)
  })
})

function scopeLabel(book: LorebookCard): string {
  const value = String(book.scope || '')
  return value ? (SCOPE_LABELS[value as Scope] || value) : '未绑定'
}
</script>

<template>
  <aside class="lorebook-sidebar" aria-label="Lorebooks">
    <div class="lorebook-sidebar__title">Books</div>

    <div class="lorebook-sidebar__filters">
      <input
        v-model="search"
        class="lorebook-sidebar__search"
        type="search"
        placeholder="搜索世界书"
        aria-label="搜索世界书"
      >
      <select v-model="scope" class="lorebook-sidebar__scope" aria-label="按范围筛选">
        <option v-for="value in SCOPES" :key="value" :value="value">{{ SCOPE_LABELS[value] }}</option>
      </select>
    </div>

    <div class="lorebook-sidebar__actions">
      <button class="lorebook-sidebar__new" :disabled="busy" @click="emit('create')">新建世界书</button>
      <button :disabled="busy" @click="emit('import')">导入</button>
      <button :disabled="busy" @click="emit('export')">导出</button>
    </div>

    <ul class="lorebook-sidebar__list">
      <li v-for="book in visibleBooks" :key="book.id" class="lorebook-sidebar__row">
        <button
          class="lorebook-sidebar__item"
          :class="{ active: book.id === activeId, disabled: book.enabled === false }"
          @click="emit('select', book.id)"
        >
          <span class="lorebook-sidebar__name">{{ book.name }}</span>
          <small v-if="book.primary" class="lorebook-sidebar__badge">Primary</small>
          <small class="lorebook-sidebar__scope-badge">{{ scopeLabel(book) }}</small>
          <small class="lorebook-sidebar__state">{{ book.enabled === false ? '已停用' : '启用中' }}</small>
        </button>
        <div class="lorebook-sidebar__row-actions">
          <button :disabled="busy" :aria-label="`重命名 ${book.name}`" @click="emit('rename', book)">重命名</button>
          <button :disabled="busy" :aria-label="`绑定 ${book.name}`" @click="emit('bindings', book)">绑定</button>
          <button
            :disabled="busy"
            :aria-label="`${book.enabled === false ? '启用' : '停用'} ${book.name}`"
            @click="emit('toggle-enabled', book)"
          >{{ book.enabled === false ? '启用' : '停用' }}</button>
          <!-- primary world book 不可删除：删掉它世界就没有主世界书了 -->
          <button
            v-if="!book.primary"
            class="danger"
            :disabled="busy"
            :aria-label="`删除 ${book.name}`"
            @click="emit('remove', book)"
          >删除</button>
        </div>
      </li>
    </ul>

    <p v-if="!books.length" class="muted">No lorebooks in this scope.</p>
    <p v-else-if="!visibleBooks.length" class="muted">没有匹配的世界书。</p>
  </aside>
</template>

<script setup lang="ts">
export interface LorebookCard { id:string; name:string; scope?:string; primary?:boolean; enabled?:boolean }
defineProps<{ books: LorebookCard[]; activeId?: string }>()
const emit = defineEmits<{ select:[id:string] }>()
</script>

<template>
  <aside class="lorebook-sidebar" aria-label="Lorebooks">
    <div class="lorebook-sidebar__title">Books</div>
    <button v-for="book in books" :key="book.id" class="lorebook-sidebar__item" :class="{ active: book.id === activeId }" @click="emit('select', book.id)">
      <span>{{ book.name }}</span><small v-if="book.primary">Primary</small>
    </button>
    <p v-if="!books.length" class="muted">No lorebooks in this scope.</p>
  </aside>
</template>

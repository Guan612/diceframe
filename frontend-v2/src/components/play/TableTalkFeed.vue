<script setup lang="ts">
import { computed, ref } from 'vue'
import type { TableTalkExchange } from '@/api/types'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{ exchanges: TableTalkExchange[] }>()
const { t } = useLocale()
const expanded = ref(false)
const visible = computed(() => (
  expanded.value ? props.exchanges : props.exchanges.slice(-2)
))
</script>

<template>
  <section v-if="exchanges.length" class="table-talk-feed" aria-live="polite">
    <header>
      <strong>{{ t('tableTalkTitle') }}</strong>
      <button
        v-if="exchanges.length > 2"
        type="button"
        class="text-button"
        @click="expanded = !expanded"
      >{{ expanded ? t('tableTalkCollapse') : t('tableTalkExpand', { count: exchanges.length }) }}</button>
    </header>
    <article v-for="exchange in visible" :key="exchange.id" class="table-talk-exchange">
      <p class="table-talk-question">
        <strong>{{ exchange.actor_name }}</strong>
        <span>{{ exchange.question }}</span>
      </p>
      <p class="table-talk-answer"><strong>{{ t('tableTalkGm') }}</strong><span>{{ exchange.answer }}</span></p>
    </article>
  </section>
</template>

<style scoped>
.table-talk-feed {
  display: grid;
  gap: 9px;
  margin: 12px 0;
  padding: 12px;
  border: 1px solid color-mix(in srgb, var(--df-interactive) 22%, var(--df-border-soft));
  border-radius: var(--df-radius-lg);
  background: color-mix(in srgb, var(--df-interactive) 5%, var(--df-surface-1));
}

.table-talk-feed > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--df-text-secondary);
  font-size: 12px;
}

.text-button {
  padding: 2px 0;
  border: 0;
  color: var(--df-interactive-strong);
  background: transparent;
  font-size: 12px;
}

.table-talk-exchange {
  display: grid;
  gap: 5px;
  padding: 9px 11px;
  border-radius: var(--df-radius-md);
  background: var(--df-surface-raised);
  box-shadow: var(--df-shadow-sm);
}

.table-talk-exchange p {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 8px;
  margin: 0;
  line-height: 1.55;
  white-space: pre-wrap;
}

.table-talk-question { color: var(--df-text-secondary); }
.table-talk-answer { color: var(--df-text); }
.table-talk-answer strong { color: var(--df-interactive-strong); }
</style>

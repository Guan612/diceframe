<script setup lang="ts">
import { useLocale } from '@/composables/useLocale'

// testid 落在 .dialog 上：根节点是 Teleport，属性透传不生效，必须显式接。
defineProps<{ title: string; dialogClass?: string; testid?: string }>()
const emit=defineEmits<{close:[]}>()
const { t } = useLocale()
</script>
<template>
  <Teleport to="body">
    <div class="modal" data-testid="modal">
      <section class="dialog" :class="dialogClass" :data-testid="testid">
        <header><h2>{{title}}</h2><button class="modal-x" data-testid="modal-close" @click="emit('close')" :title="t('close')">✕</button></header>
        <slot/>
        <div v-if="$slots.actions" class="actions"><slot name="actions"/></div>
      </section>
    </div>
  </Teleport>
</template>

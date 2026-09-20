<script setup lang="ts">
defineProps<{ open:boolean; preview?: { format:string; counts:{ entries:number; mapped:number; warnings:number; unsupported:number }; warnings:string[] } }>()
const emit = defineEmits<{ close:[]; confirm:[] }>()
</script>

<template>
  <div v-if="open" class="lore-import-dialog" role="dialog" aria-modal="true">
    <div class="lore-import-dialog__panel">
      <h2>Import lorebook</h2>
      <p v-if="preview">Detected: <strong>{{ preview.format }}</strong> · {{ preview.counts.entries }} entries · {{ preview.counts.mapped }} mapped</p>
      <ul v-if="preview?.warnings?.length"><li v-for="warning in preview.warnings" :key="warning">{{ warning }}</li></ul>
      <p v-if="preview?.counts.unsupported" class="warning">{{ preview.counts.unsupported }} unsupported fields are preserved and will not execute.</p>
      <button @click="emit('close')">Cancel</button><button :disabled="!preview" @click="emit('confirm')">Import</button>
    </div>
  </div>
</template>

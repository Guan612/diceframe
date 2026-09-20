<script setup lang="ts">
export interface LoreEntryAdvancedModel { secondary_keys:string[]; selective_logic:string; use_regex:boolean; case_sensitive:boolean; match_whole_words:boolean; scan_depth:number; priority:number; prompt_slot:string; probability:number; groups:string[]; group_weight:number; non_recursable:boolean; prevent_further_recursion:boolean; delay_until_recursion:boolean; recursion_level:number }
const props = defineProps<{ modelValue: LoreEntryAdvancedModel }>()
const emit = defineEmits<{ 'update:modelValue':[value:LoreEntryAdvancedModel] }>()
function update<K extends keyof LoreEntryAdvancedModel>(key:K, value:LoreEntryAdvancedModel[K]) { emit('update:modelValue', { ...props.modelValue, [key]: value }) }
</script>

<template>
  <details class="lore-entry-advanced">
    <summary>Advanced matching and activation</summary>
    <label>Selective logic <select :value="modelValue.selective_logic" @change="update('selective_logic', ($event.target as HTMLSelectElement).value)"><option>any</option><option>all</option><option>not_any</option><option>not_all</option></select></label>
    <label><input type="checkbox" :checked="modelValue.use_regex" @change="update('use_regex', ($event.target as HTMLInputElement).checked)"> Regex</label>
    <label><input type="checkbox" :checked="modelValue.case_sensitive" @change="update('case_sensitive', ($event.target as HTMLInputElement).checked)"> Case-sensitive</label>
    <label>Priority <input type="number" :value="modelValue.priority" @input="update('priority', Number(($event.target as HTMLInputElement).value))"></label>
    <label>Probability <input type="number" min="0" max="100" :value="modelValue.probability" @input="update('probability', Number(($event.target as HTMLInputElement).value))"></label>
  </details>
</template>

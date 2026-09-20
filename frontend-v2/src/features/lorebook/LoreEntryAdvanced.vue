<script setup lang="ts">
export interface LoreEntryAdvancedModel {
  secondary_keys: string[]
  selective_logic: string
  use_regex: boolean
  case_sensitive: boolean
  match_whole_words: boolean
  vector_activation?: string
  scan_depth: number
  priority: number
  probability: number
  prompt_slot: string
  groups: string[]
  group_weight: number
  group_scoring?: string
  sticky?: number
  cooldown?: number
  delay?: number
  non_recursable: boolean
  prevent_further_recursion: boolean
  delay_until_recursion: boolean
  recursion_level: number
}
const props = defineProps<{ modelValue: LoreEntryAdvancedModel }>()
const emit = defineEmits<{ 'update:modelValue':[value:LoreEntryAdvancedModel] }>()
function update<K extends keyof LoreEntryAdvancedModel>(key:K, value:LoreEntryAdvancedModel[K]) { emit('update:modelValue', { ...props.modelValue, [key]: value }) }
function updateList(key: 'secondary_keys' | 'groups', value: string) { update(key, value.split(',').map(item => item.trim()).filter(Boolean)) }
function updateNumber<K extends 'scan_depth' | 'priority' | 'probability' | 'group_weight' | 'sticky' | 'cooldown' | 'delay' | 'recursion_level'>(key: K, event: Event) { update(key, Number((event.target as HTMLInputElement).value) as LoreEntryAdvancedModel[K]) }
</script>

<template>
  <details class="lore-entry-advanced">
    <summary>Advanced matching and activation</summary>
    <label data-field="secondary_keys">Secondary keys (comma-separated) <input type="text" :value="(modelValue.secondary_keys || []).join(', ')" @input="updateList('secondary_keys', ($event.target as HTMLInputElement).value)"></label>
    <label data-field="selective_logic">Selective logic <select :value="modelValue.selective_logic" @change="update('selective_logic', ($event.target as HTMLSelectElement).value)"><option>any</option><option>all</option><option>not_any</option><option>not_all</option></select></label>
    <label><input type="checkbox" :checked="modelValue.use_regex" @change="update('use_regex', ($event.target as HTMLInputElement).checked)"> Regex</label>
    <label><input type="checkbox" :checked="modelValue.case_sensitive" @change="update('case_sensitive', ($event.target as HTMLInputElement).checked)"> Case-sensitive</label>
    <label data-field="match_whole_words"><input type="checkbox" :checked="modelValue.match_whole_words" @change="update('match_whole_words', ($event.target as HTMLInputElement).checked)"> Match whole words</label>
    <label data-field="vector_activation">Vector activation <select :value="modelValue.vector_activation || 'off'" @change="update('vector_activation', ($event.target as HTMLSelectElement).value)"><option value="off">off</option><option value="hybrid">hybrid</option><option value="vector_only">vector only</option></select></label>
    <label data-field="scan_depth">Scan depth <input type="number" :value="modelValue.scan_depth" @input="updateNumber('scan_depth', $event)"></label>
    <label data-field="priority">Priority <input type="number" :value="modelValue.priority" @input="updateNumber('priority', $event)"></label>
    <label data-field="probability">Probability <input type="number" min="0" max="100" :value="modelValue.probability" @input="updateNumber('probability', $event)"></label>
    <label data-field="groups">Groups (comma-separated) <input type="text" :value="(modelValue.groups || []).join(', ')" @input="updateList('groups', ($event.target as HTMLInputElement).value)"></label>
    <label data-field="group_weight">Group weight <input type="number" :value="modelValue.group_weight" @input="updateNumber('group_weight', $event)"></label>
    <label data-field="group_scoring">Group scoring <input type="text" :value="modelValue.group_scoring || ''" @input="update('group_scoring', ($event.target as HTMLInputElement).value)"></label>
    <label data-field="sticky">Sticky <input type="number" :value="modelValue.sticky ?? 0" @input="updateNumber('sticky', $event)"></label>
    <label data-field="cooldown">Cooldown <input type="number" :value="modelValue.cooldown ?? 0" @input="updateNumber('cooldown', $event)"></label>
    <label data-field="delay">Delay <input type="number" :value="modelValue.delay ?? 0" @input="updateNumber('delay', $event)"></label>
    <label data-field="non_recursable"><input type="checkbox" :checked="modelValue.non_recursable" @change="update('non_recursable', ($event.target as HTMLInputElement).checked)"> Non-recursable</label>
    <label data-field="prevent_further_recursion"><input type="checkbox" :checked="modelValue.prevent_further_recursion" @change="update('prevent_further_recursion', ($event.target as HTMLInputElement).checked)"> Prevent further recursion</label>
    <label data-field="delay_until_recursion"><input type="checkbox" :checked="modelValue.delay_until_recursion" @change="update('delay_until_recursion', ($event.target as HTMLInputElement).checked)"> Delay until recursion</label>
    <label data-field="recursion_level">Recursion level <input type="number" :value="modelValue.recursion_level" @input="updateNumber('recursion_level', $event)"></label>
    <label data-field="prompt_slot">Prompt slot <input type="text" :value="modelValue.prompt_slot" @input="update('prompt_slot', ($event.target as HTMLInputElement).value)"></label>
  </details>
</template>

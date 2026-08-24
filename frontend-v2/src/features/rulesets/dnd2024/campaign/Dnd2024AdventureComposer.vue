<script setup lang="ts">
import { computed, ref } from 'vue'
import { submitRulesetAdventureAction } from '../api'

const props = withDefaults(defineProps<{
  gameKey: string
  language?: string
  disabled?: boolean
}>(), { language: 'zh-CN', disabled: false })
const emit = defineEmits<{ refresh: []; navigate: [target: 'combat'] }>()

type Mode = 'act' | 'say' | 'ask'
const mode = ref<Mode>('act')
const declaration = ref('')
const busy = ref(false)
const error = ref('')
const narration = ref('')
const zh = computed(() => !props.language.toLowerCase().startsWith('en'))
const showSettingsLink = computed(() => /设置|配置|Settings|configur/i.test(error.value))
const text = (cn: string, en: string) => zh.value ? cn : en
const examples = computed<Record<Mode, string[]>>(() => zh.value ? {
  act: ['我仔细观察门边有没有脚印。', '我慢慢靠近灯塔，先听里面的声音。', '我把火把举高，保护同伴走在前面。'],
  say: ['我向守灯人问好，并说明我们愿意帮忙。', '我低声提醒同伴先别碰可疑的东西。'],
  ask: ['我现在最需要注意什么？', '周围有什么看起来不寻常？'],
} : {
  act: ['I check the doorway for tracks.', 'I approach the tower slowly and listen first.', 'I raise my torch and take the lead.'],
  say: ['I greet the keeper and offer our help.', 'I quietly warn my companions not to touch anything yet.'],
  ask: ['What should I pay attention to right now?', 'What looks unusual nearby?'],
})

function operationId(): string {
  return globalThis.crypto?.randomUUID?.()
    || `adventure-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

async function submit(): Promise<void> {
  const value = declaration.value.trim()
  if (!value || busy.value || props.disabled) return
  busy.value = true
  error.value = ''
  try {
    const response = await submitRulesetAdventureAction(props.gameKey, {
      mode: mode.value,
      text: value,
      operation_id: operationId(),
    })
    narration.value = response.narration
    declaration.value = ''
    emit('refresh')
  } catch (cause: unknown) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally { busy.value = false }
}

function useExample(value: string): void {
  declaration.value = value
}

function onKeydown(event: KeyboardEvent): void {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault()
    void submit()
  }
}
</script>

<template>
  <section class="adventure-composer" aria-labelledby="adventure-composer-title">
    <header>
      <div>
        <span>{{ text('不用懂术语 · 直接说人话', 'No rules jargon required') }}</span>
        <h3 id="adventure-composer-title">{{ text('你现在想做什么？', 'What do you want to do?') }}</h3>
        <p>{{ text('写角色想尝试的行动、说的话，或者直接问“我现在能做什么”。系统会描述反馈；若需要检定或进入战斗，会明确告诉你下一步点哪里。', 'Describe an action, speak in character, or simply ask what you can do. The game narrates the response and tells you when a check or combat action is needed.') }}</p>
      </div>
    </header>

    <div class="mode-switch" role="group" :aria-label="text('输入类型', 'Declaration type')">
      <button :class="{ active: mode === 'act' }" @click="mode = 'act'">{{ text('我想行动', 'I act') }}</button>
      <button :class="{ active: mode === 'say' }" @click="mode = 'say'">{{ text('我想说话', 'I speak') }}</button>
      <button :class="{ active: mode === 'ask' }" @click="mode = 'ask'">{{ text('我想提问', 'I ask') }}</button>
    </div>

    <div class="example-row">
      <button v-for="example in examples[mode]" :key="example" type="button" @click="useExample(example)">{{ example }}</button>
    </div>

    <label>
      <span>{{ text('用自己的话描述；不必写骰子、属性名或指令', 'Use your own words; do not enter dice, ability names, or commands') }}</span>
      <textarea
        v-model="declaration"
        rows="4"
        maxlength="1200"
        :placeholder="text('例如：我先问问守灯人昨晚看见了什么。', 'Example: I ask the keeper what he saw last night.')"
        :disabled="busy || disabled"
        @keydown="onKeydown"
      ></textarea>
    </label>
    <div class="composer-actions">
      <small>{{ text('Ctrl / ⌘ + Enter 发送', 'Ctrl / ⌘ + Enter to send') }}</small>
      <button class="adventure-submit" :disabled="busy || disabled || !declaration.trim()" @click="submit">{{ busy ? text('正在生成故事回应…', 'Creating the story response…') : text('发送行动，继续冒险', 'Send action and continue') }}</button>
    </div>
    <div v-if="error" class="composer-error" role="alert">
      <p>{{ error }}</p>
      <a v-if="showSettingsLink" href="#/settings">{{ text('打开设置页检查模型', 'Open Settings to check the model') }}</a>
    </div>
    <article v-if="narration" class="narration-result" aria-live="polite">
      <b>{{ text('GM 的回应', 'GM response') }}</b>
      <p>{{ narration }}</p>
      <small>{{ text('这段已写入“剧情回顾”。重要规则变化仍只由专用按钮执行。', 'This is saved in Story Recap. Mechanical changes still use dedicated actions only.') }}</small>
    </article>
  </section>
</template>

<style scoped>
.adventure-composer { display: grid; gap: 12px; padding: 16px; border: 1px solid #527f78; border-radius: 14px; background: linear-gradient(135deg, rgb(25 52 50 / 88%), rgb(15 26 33 / 94%)); }
.adventure-composer header span { color: #8dd6c8; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }.adventure-composer h3 { margin: 3px 0; font-size: 21px; }.adventure-composer header p { margin: 0; color: #b9ccca; line-height: 1.55; }
.mode-switch { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; }.mode-switch button.active { border-color: #72d1bf; background: #276c63; color: #fff; }
.example-row { display: flex; gap: 7px; overflow-x: auto; padding-bottom: 3px; }.example-row button { flex: 0 0 auto; min-height: 38px; padding: 6px 10px; border-style: dashed; color: #c8dbd7; }
.adventure-composer label { display: grid; gap: 6px; }.adventure-composer label span { color: #c9d8d5; font-size: 12px; }.adventure-composer textarea { width: 100%; box-sizing: border-box; padding: 12px; border: 1px solid #56746f; border-radius: 10px; background: #091613; color: #f0f7f5; resize: vertical; }
.composer-actions { display: flex; justify-content: space-between; align-items: center; gap: 10px; }.composer-actions small { color: #9fb5b1; }.adventure-submit { min-width: 150px; border-color: #54ae9d; background: #2d8074; color: #fff; }
.composer-error { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 12px; margin: 0; padding: 10px; border-radius: 8px; background: rgb(142 39 39 / 28%); color: #ffd0d0; }.composer-error p { margin: 0; }.composer-error a { color: #fff; font-weight: 700; }.narration-result { display: grid; gap: 7px; padding: 13px; border-left: 4px solid #d4aa5b; border-radius: 8px; background: rgb(13 22 28 / 78%); }.narration-result p { margin: 0; white-space: pre-wrap; line-height: 1.65; }.narration-result small { color: #a9bbb8; }
:global(body.light .adventure-composer) { border-color: #72a098; background: linear-gradient(135deg, #eef8f5, #fff); color: #17312d; }:global(body.light .adventure-composer header p), :global(body.light .adventure-composer .composer-actions small), :global(body.light .adventure-composer label span) { color: #3e5e58; }:global(body.light .adventure-composer textarea) { border-color: #7b9d96; background: #fff; color: #172f2b; }:global(body.light .narration-result) { background: #fff9ec; }
@media (max-width: 640px) { .mode-switch { grid-template-columns: 1fr; }.composer-actions { align-items: stretch; flex-direction: column; }.adventure-submit { width: 100%; } }
</style>

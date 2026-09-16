<script setup lang="ts">
/**
 * 二维码渲染：把一段文本画成 SVG。
 *
 * 用 SVG 而不是 canvas / img：手机对着屏幕扫，缩放到任意尺寸都要保持边缘锐利，
 * 并且深浅主题下前景色要跟着主题令牌走。
 *
 * 取景区必须是纯白底 + 足够的 quiet zone（四周留白 4 个模块是规范要求），
 * 否则暗色主题下对比度不足，多数手机扫不出来——所以这里的白底是刻意硬编码的，
 * 不跟随主题。
 */
import { computed } from 'vue'
import qrcode from 'qrcode-generator'

const props = withDefaults(defineProps<{
  value: string
  /** 渲染像素尺寸（正方形边长） */
  size?: number
  /** 容错级别；带 logo 或反光屏幕建议用 'M' 以上 */
  level?: 'L' | 'M' | 'Q' | 'H'
}>(), { size: 200, level: 'M' })

const QUIET_ZONE = 4

const model = computed(() => {
  if (!props.value) return null
  // 默认的 stringToBytes 走 SJIS，非 ASCII 会编坏；统一按 UTF-8 编码。
  qrcode.stringToBytes = qrcode.stringToBytesFuncs['UTF-8']
  const qr = qrcode(0, props.level)
  qr.addData(props.value)
  qr.make()
  const count = qr.getModuleCount()
  const parts: string[] = []
  for (let row = 0; row < count; row++) {
    for (let col = 0; col < count; col++) {
      // 逐块 rect 合并成单条 path：模块数多时比几百个 <rect> 节点便宜得多。
      if (qr.isDark(row, col)) parts.push(`M${col + QUIET_ZONE} ${row + QUIET_ZONE}h1v1h-1z`)
    }
  }
  return { extent: count + QUIET_ZONE * 2, path: parts.join('') }
})
</script>

<template>
  <svg
    v-if="model"
    class="qr-code"
    :width="size"
    :height="size"
    :viewBox="`0 0 ${model.extent} ${model.extent}`"
    role="img"
    shape-rendering="crispEdges"
  >
    <rect :width="model.extent" :height="model.extent" fill="#ffffff" />
    <path :d="model.path" fill="#000000" />
  </svg>
</template>

<style scoped>
.qr-code{display:block;border-radius:8px}
</style>

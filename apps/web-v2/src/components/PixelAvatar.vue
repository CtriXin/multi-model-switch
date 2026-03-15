<script setup lang="ts">
/**
 * PixelAvatar — 像素风头像组件
 * 接收 grid（字符矩阵）和 palette（字符→颜色映射），渲染为圆形 SVG
 */
const props = defineProps<{
  grid: string[]
  palette: Record<string, string>
  size?: number
}>()

const cellSize = 4
const gridHeight = props.grid.length
const gridWidth = Math.max(...props.grid.map((r) => r.length))
const svgWidth = gridWidth * cellSize
const svgHeight = gridHeight * cellSize
</script>

<template>
  <div
    class="rounded-full overflow-hidden bg-surface-3 shrink-0 flex items-center justify-center"
    :style="{ width: (size ?? 36) + 'px', height: (size ?? 36) + 'px' }"
  >
    <svg
      :viewBox="`0 0 ${svgWidth} ${svgHeight}`"
      :width="(size ?? 36) - 4"
      :height="(size ?? 36) - 4"
      xmlns="http://www.w3.org/2000/svg"
      style="image-rendering: pixelated"
    >
      <template v-for="(row, y) in grid" :key="y">
        <rect
          v-for="(char, x) in row.split('')"
          :key="`${y}-${x}`"
          v-show="char !== '.' && palette[char]"
          :x="x * cellSize"
          :y="y * cellSize"
          :width="cellSize"
          :height="cellSize"
          :fill="palette[char] || 'transparent'"
        />
      </template>
    </svg>
  </div>
</template>

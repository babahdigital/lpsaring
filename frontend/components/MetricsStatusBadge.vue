<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  severity: 'ok' | 'warn' | 'danger'
  label?: string
}
const props = defineProps<Props>()

const colorClass = computed(() => ({
  ok: 'bg-green-100 text-green-700 border border-green-300',
  warn: 'bg-amber-100 text-amber-700 border border-amber-300',
  danger: 'bg-red-100 text-red-700 border border-red-300',
})[props.severity])

const title = computed(() => ({
  ok: 'Semua normal',
  warn: 'Rasio kegagalan meningkat',
  danger: 'Rasio kegagalan tinggi',
})[props.severity])

const label = computed(() => props.label || title.value)
</script>

<template>
  <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium gap-1" :class="[colorClass]" :title="title">
    <slot name="icon">
      <span v-if="severity === 'ok'">✅</span>
      <span v-else-if="severity === 'warn'">⚠️</span>
      <span v-else>🛑</span>
    </slot>
    <slot>{{ label }}</slot>
  </span>
</template>

<style scoped>
span { transition: background-color .2s, color .2s; }
</style>

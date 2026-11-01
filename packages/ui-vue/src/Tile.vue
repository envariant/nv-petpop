<script setup lang="ts">
import { cx } from './mode';
defineProps<{ label: string; selected?: boolean; highlight?: boolean; testId?: string; dashed?: boolean }>();
defineEmits<{ click: [] }>();
</script>

<template>
  <button
    :aria-pressed="selected"
    :aria-label="label"
    :data-testid="testId"
    :class="cx(
      'press hit flex min-h-[6rem] flex-col items-center justify-center gap-1 rounded-tile border-4 bg-card p-2 shadow-soft transition-colors',
      selected ? 'border-accent' : dashed ? 'border-dashed border-line' : 'border-transparent',
      highlight && 'ring-highlight',
    )"
    @click="$emit('click')"
  >
    <slot />
    <span class="font-display text-base font-medium leading-tight md:text-lg">{{ label }}</span>
  </button>
</template>

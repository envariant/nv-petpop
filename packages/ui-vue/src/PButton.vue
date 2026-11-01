<script setup lang="ts">
import { cx } from './mode';
withDefaults(defineProps<{ variant?: 'primary' | 'ghost' | 'soft'; disabled?: boolean; testId?: string }>(), { variant: 'primary' });
defineEmits<{ click: [] }>();
</script>

<template>
  <button
    :disabled="disabled"
    :data-testid="testId"
    :class="cx(
      'press hit whitespace-nowrap rounded-tile px-4 py-2.5 font-display text-lg font-semibold transition-colors disabled:opacity-40 md:px-6 md:py-3 md:text-2xl',
      variant === 'primary' && 'bg-accent text-white shadow-soft',
      variant === 'soft' && 'bg-card text-ink shadow-soft',
      variant === 'ghost' && 'bg-transparent text-muted',
    )"
    @click="$emit('click')"
  >
    <slot />
  </button>
</template>

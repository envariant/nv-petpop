<script setup lang="ts">
import { cx } from './mode';
defineProps<{ selected?: boolean; testId?: string }>();
defineEmits<{ click: [] }>();
</script>

<template>
  <button
    :aria-pressed="selected"
    :data-testid="testId"
    :class="cx('press hit shrink-0 rounded-full border-4 px-4 py-1.5 font-display text-base md:text-lg', selected ? 'border-accent bg-accent text-white' : 'border-line bg-card text-ink')"
    @click="$emit('click')"
  >
    <slot />
  </button>
</template>

<script setup lang="ts">
import { cx } from './mode';
withDefaults(defineProps<{ hex: string; label: string; selected?: boolean; highlight?: boolean; testId?: string; size?: string }>(), { size: '3rem' });
defineEmits<{ click: [] }>();
</script>

<template>
  <button
    :aria-label="label"
    :aria-pressed="selected"
    :data-testid="testId"
    :class="cx('press hit shrink-0 rounded-full border-4 shadow-soft', selected ? 'border-accent' : 'border-card', highlight && 'ring-highlight')"
    :style="{ width: size, height: size, background: hex }"
    @click="$emit('click')"
  />
</template>

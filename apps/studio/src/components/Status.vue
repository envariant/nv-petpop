<script setup lang="ts">
import { cx } from '@petpop/ui-vue';
defineProps<{ status: string }>();
const STYLE: Record<string, string> = {
  draft: 'bg-line text-ink', accepted: 'bg-accent text-white', rejected: 'bg-accent2 text-white', published: 'bg-ink text-white', superseded: 'bg-line text-muted',
};
</script>

<template>
  <span :class="cx('shrink-0 rounded-full px-3 py-0.5 font-display text-sm md:text-base', STYLE[status] ?? 'bg-line')">{{ status }}</span>
</template>

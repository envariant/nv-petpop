<script setup lang="ts">
defineProps<{ value: string; placeholder: string; testId?: string }>();
</script>

<template>
  <div :data-testid="testId" class="rounded-tile border-4 border-line bg-card px-4 py-3 text-xl md:text-2xl">
    <span v-if="value">{{ value }}</span><span v-else class="text-muted">{{ placeholder }}</span>
    <span class="ml-1 inline-block h-[1em] w-0.5 animate-pulse bg-accent align-middle" />
  </div>
</template>

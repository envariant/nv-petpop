<script setup lang="ts">
defineProps<{ testId: string }>();
</script>

<template>
  <div :data-testid="testId" class="absolute inset-0 z-40 flex items-center justify-center bg-ink/60 p-4 md:p-10">
    <div class="max-h-full w-full max-w-2xl overflow-y-auto rounded-tile bg-paper p-6 shadow-soft md:p-10"><slot /></div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ testId: string }>();
</script>

<template>
  <div :data-testid="testId" class="absolute inset-0 z-40 flex items-center justify-center bg-ink/60 p-4 md:p-12"><slot /></div>
</template>

<script setup lang="ts">
defineProps<{ sub?: string }>();
</script>

<template>
  <header class="mb-4 md:mb-6">
    <h1 class="font-display text-3xl font-semibold leading-tight md:text-4xl"><slot /></h1>
    <p v-if="sub" class="mt-1 text-base text-muted md:text-lg">{{ sub }}</p>
  </header>
</template>

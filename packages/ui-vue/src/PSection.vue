<script setup lang="ts">
defineProps<{ title: string; testId?: string }>();
</script>

<template>
  <section class="mb-6" :data-testid="testId">
    <h3 class="mb-2 font-display text-lg font-semibold md:text-xl">{{ title }}</h3>
    <slot />
  </section>
</template>

<script setup lang="ts">
defineProps<{ error?: string | null; notice?: string | null; prefix?: string }>();
</script>

<template>
  <p v-if="error || notice" :class="['mb-4 text-base font-semibold md:text-lg', error ? 'text-accent2' : 'text-accent']"
    :data-testid="`${prefix ?? 'curate'}-${error ? 'error' : 'notice'}`">{{ error ?? notice }}</p>
</template>

<script setup lang="ts">
// A scrolling page with the Studio's reading width (desktop first; narrower screens get the full width).
defineProps<{ testId?: string; wide?: boolean }>();
</script>

<template>
  <div class="no-scrollbar h-full overflow-y-auto" :data-testid="testId">
    <div :class="['mx-auto px-4 pb-10 pt-6 md:px-8 md:pt-8', wide ? 'max-w-[90rem]' : 'max-w-5xl']"><slot /></div>
  </div>
</template>

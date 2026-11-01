<script setup lang="ts">
import { mode, theme } from './mode';
defineProps<{ species?: string | null; themeName?: string }>();
</script>

<template>
  <div class="kiosk pp-frame" :data-theme="themeName ?? theme()" :data-species="species ?? 'dog'" :data-mode="mode">
    <slot />
  </div>
</template>

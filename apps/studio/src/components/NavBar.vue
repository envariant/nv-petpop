<script setup lang="ts">
import { PButton } from '@petpop/ui-vue';
withDefaults(defineProps<{ back?: () => void; next?: () => void; nextLabel?: string; nextDisabled?: boolean }>(), { nextLabel: 'Next' });
</script>

<template>
  <nav class="flex shrink-0 items-center justify-between gap-4 border-t-2 border-line bg-paper px-4 py-3 md:px-8 md:py-4">
    <PButton v-if="back" variant="soft" test-id="nav-back" @click="back()">‹ Back</PButton>
    <span v-else />
    <slot />
    <PButton v-if="next" :disabled="nextDisabled" test-id="nav-next" @click="next()">{{ nextLabel }} ›</PButton>
  </nav>
</template>

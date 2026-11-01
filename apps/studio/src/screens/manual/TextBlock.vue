<script setup lang="ts">
import { PSection } from '@petpop/ui-vue';
import CopyButton from './CopyButton.vue';
defineProps<{ title: string; text: string; testId: string }>();
</script>

<template>
  <PSection :title="title">
    <div class="flex items-start gap-3">
      <p class="flex-1 select-all rounded-tile bg-card p-4 text-base leading-snug shadow-soft md:text-lg" :data-testid="testId">{{ text }}</p>
      <CopyButton :text="text" :test-id="`${testId}-copy`" />
    </div>
  </PSection>
</template>

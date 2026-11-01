<script setup lang="ts">
import { label } from '@petpop/core';
import { PRow, Swatch } from '@petpop/ui-vue';
withDefaults(defineProps<{ value: string; options: { name: string; hex: string }[]; testId: string; size?: string }>(), { size: '2.75rem' });
defineEmits<{ pick: [string] }>();
</script>

<template>
  <PRow>
    <Swatch v-for="o in options" :key="o.name" :hex="o.hex" :label="label(o.name)" :size="size" :selected="o.hex.toUpperCase() === value.toUpperCase()"
      :test-id="`${testId}-${o.name}`" @click="$emit('pick', o.hex.toUpperCase())" />
  </PRow>
</template>

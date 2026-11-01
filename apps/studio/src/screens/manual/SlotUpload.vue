<script setup lang="ts">
import { computed, ref } from 'vue';
import type { ManualTask } from '@petpop/core';
import { PButton } from '@petpop/ui-vue';
import { useManual } from '../../stores/manual';
const props = defineProps<{ t: ManualTask; slot: string }>();
const m = useManual();
const file = ref<File | null>(null);
const done = computed(() => (props.t.filled ?? []).includes(props.slot));
</script>

<template>
  <div class="mb-2 flex flex-wrap items-center gap-3 rounded-tile bg-card p-3 text-base shadow-soft md:text-lg" :data-testid="`manual-slot-${slot}`">
    <b class="w-20 capitalize">{{ slot }}</b>
    <span v-if="done" class="flex-1 text-accent" :data-testid="`manual-slot-${slot}-done`">received ✓</span>
    <template v-else>
      <input type="file" :accept="t.expects.accept.join(',')" class="min-w-0 flex-1" :data-testid="`manual-file-${slot}`"
        @change="file = ($event.target as HTMLInputElement).files?.[0] ?? null" />
      <PButton :disabled="!file || m.busy" :test-id="`manual-submit-${slot}`" @click="file && m.submit(file, slot)">Send</PButton>
    </template>
  </div>
</template>

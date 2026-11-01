<script setup lang="ts">
import { computed } from 'vue';
import { label, nearestPalette } from '@petpop/core';
import { Chip, PRow, Swatch } from '@petpop/ui-vue';
import { useSession } from '../../stores/session';
import { ACC, ACC_COLOURS, ACC_ICON, useHighlight } from './vocab';
const s = useSession();
const hl = useHighlight();
const list = computed(() => s.spec?.accessories ?? []);
const has = (t: string) => list.value.some((a) => a.type === t);
function toggle(t: (typeof ACC)[number]) {
  s.tap('accessories', has(t) ? list.value.filter((a) => a.type !== t)
    : [...list.value, { type: t, colour_hex: ACC_COLOURS[0], colour_name: nearestPalette(ACC_COLOURS[0]), ...(t === 'collar' ? { tag: true } : {}) }]);
}
const recolour = (t: string, hex: string) => s.tap('accessories', list.value.map((a) => (a.type === t ? { ...a, colour_hex: hex, colour_name: nearestPalette(hex) } : a)));
</script>

<template>
  <div class="flex flex-col gap-3">
    <PRow>
      <Chip v-for="t in ACC" :key="t" :test-id="`chip-acc-${t}`" :selected="has(t)" :highlight="has(t) && hl('accessories')" @click="toggle(t)">{{ ACC_ICON[t] }} {{ label(t) }}</Chip>
    </PRow>
    <div v-for="a in list" :key="a.type" class="flex flex-wrap items-center gap-2">
      <span class="w-24 font-display text-lg">{{ label(a.type) }}</span>
      <Swatch v-for="hex in ACC_COLOURS" :key="hex" size="2.25rem" :hex="hex" :label="`${a.type} ${hex}`" :selected="a.colour_hex === hex" @click="recolour(a.type, hex)" />
    </div>
  </div>
</template>

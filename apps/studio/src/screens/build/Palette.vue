<script setup lang="ts">
import { computed, ref } from 'vue';
import { PALETTE, PALETTE_ORDER, label, nearestPalette } from '@petpop/core';
import { Chip, Swatch, cx } from '@petpop/ui-vue';
import { useSession } from '../../stores/session';
import { useHighlight, useValue } from './vocab';
import ColourWheel from './ColourWheel.vue';
const props = defineProps<{ path: 'colour.base' | 'colour.secondary'; optional?: boolean }>();
const s = useSession();
const hl = useHighlight();
const value = useValue();
const wheel = ref(false);
const current = computed(() => value(props.path) as { name: string; hex: string } | undefined);
const isCustom = computed(() => !!current.value && !PALETTE_ORDER.some((n) => PALETTE[n].hex.toUpperCase() === current.value!.hex.toUpperCase()));
</script>

<template>
  <div>
    <div class="flex flex-wrap gap-2">
      <button v-if="optional" :data-testid="`swatch-${path}-none`" :aria-pressed="!current"
        :class="cx('hit h-12 w-12 rounded-full border-4 border-dashed font-display text-xs', !current ? 'border-accent' : 'border-line')" @click="s.tap(path, undefined)">None</button>
      <Swatch v-for="n in PALETTE_ORDER" :key="n" :hex="PALETTE[n].hex" :label="label(n)" :test-id="`swatch-${path}-${n}`"
        :selected="current?.hex.toUpperCase() === PALETTE[n].hex.toUpperCase()" :highlight="current?.name === n && hl(path)" @click="s.tap(path, { name: n, hex: PALETTE[n].hex })" />
      <button :data-testid="`swatch-${path}-custom`" aria-label="Custom colour" :aria-pressed="isCustom"
        :class="cx('hit h-12 w-12 rounded-full border-4 shadow-soft', isCustom ? 'border-accent' : 'border-card')"
        :style="{ background: isCustom ? current!.hex : 'conic-gradient(red, yellow, lime, cyan, blue, magenta, red)' }" @click="wheel = !wheel" />
    </div>
    <div v-if="wheel" class="mt-4 flex items-center gap-6">
      <ColourWheel @pick="(hex) => s.tap(path, { name: nearestPalette(hex), hex })" />
      <Chip @click="wheel = false">Done</Chip>
    </div>
  </div>
</template>

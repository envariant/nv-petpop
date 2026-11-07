<script setup lang="ts">
import { computed } from 'vue';
import { Chip, PRow } from '@petpop/ui-vue';
import { MAX_STAMPS, SPOT_MM, useDesign } from '../../stores/design';
import Swatches from './Swatches.vue';
import { FUR } from './palettes';
const d = useDesign();
const count = computed(() => d.active?.stamps?.length ?? 0); // a figure of parts too (decision 139)
const SIZES = { s: 'Small spot', m: 'Spot', l: 'Patch' } as const;
</script>

<template>
  <PRow>
    <Chip v-for="(name, s) in SIZES" :key="s" :selected="d.tool === 'spot' && d.spot === s" :test-id="`tool-spot-${s}`"
      @click="(d.tool = 'spot'), (d.spot = s), (d.turning = false)">{{ name }} · {{ SPOT_MM[s] }} mm</Chip>
    <Chip :selected="d.tool === 'brush'" test-id="tool-brush" @click="(d.tool = 'brush'), (d.turning = false)">Brush</Chip>
  </PRow>
  <div class="mt-3"><Swatches :value="d.paintColour" :options="FUR" test-id="paint" @pick="(hex) => (d.paintColour = hex)" /></div>
  <div class="mt-3 flex flex-wrap items-center gap-2">
    <Chip :selected="d.symmetry" test-id="symmetry" @click="d.symmetry = !d.symmetry">Mirror both sides</Chip>
    <Chip :selected="d.turning" test-id="turn" @click="d.turning = !d.turning">⟳ Turn figure</Chip>
    <Chip test-id="undo" @click="d.undo()">↶ Undo</Chip>
    <span class="text-base text-muted md:text-lg" data-testid="stamp-count">{{ count }}/{{ MAX_STAMPS }} dabs</span>
  </div>
  <p class="mt-2 text-base text-muted md:text-lg">Tap the figure to add a spot, or drag with the brush.</p>
</template>

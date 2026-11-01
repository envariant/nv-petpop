<script setup lang="ts">
import { computed } from 'vue';
import { PSection, Tile } from '@petpop/ui-vue';
import { MAX_LAYERS, useDesign } from '../../stores/design';
import Swatches from './Swatches.vue';
import { FUR } from './palettes';
const d = useDesign();
const c = computed(() => d.composition!);
const patterns = computed(() => d.manifest().pattern_layers);
const on = computed(() => new Set(c.value.layers.map((l) => l.pattern_id)));
const pattern = (id: string) => patterns.value.find((p) => p.id === id)!;
</script>

<template>
  <PSection title="Coat colour" test-id="base-colour">
    <Swatches :value="c.base_colour" :options="FUR" test-id="base" @pick="d.setBase" />
  </PSection>
  <PSection :title="`Markings (${c.layers.length}/${MAX_LAYERS})`">
    <div class="grid grid-cols-[repeat(auto-fill,minmax(5.5rem,1fr))] gap-2" data-testid="pattern-tiles">
      <Tile v-for="p in patterns" :key="p.id" :label="p.name" :selected="on.has(p.id)" :test-id="`pattern-${p.id}`" @click="d.toggleLayer(p.id)">
        <img :src="d.lib!.url(p.thumbnail)" alt="" class="h-14 w-14 object-contain" draggable="false" />
      </Tile>
    </div>
  </PSection>
  <div v-for="l in c.layers" :key="l.pattern_id" class="mb-4 rounded-tile bg-card p-3 shadow-soft" :data-testid="`layer-${l.pattern_id}`">
    <div class="mb-2 flex items-center gap-3">
      <span class="w-24 font-display text-lg md:w-28 md:text-xl">{{ pattern(l.pattern_id).name }}</span>
      <input type="range" :min="pattern(l.pattern_id).coverage.min" :max="pattern(l.pattern_id).coverage.max" step="0.01" :value="l.coverage"
        class="h-10 flex-1 accent-[rgb(var(--pp-accent))]" :aria-label="`${pattern(l.pattern_id).name} coverage`" :data-testid="`coverage-${l.pattern_id}`"
        @input="d.setCoverage(l.pattern_id, Number(($event.target as HTMLInputElement).value))" />
    </div>
    <Swatches :value="l.colour" :options="FUR" :test-id="`layer-colour-${l.pattern_id}`" size="2.25rem" @pick="(hex) => d.setLayerColour(l.pattern_id, hex)" />
  </div>
</template>

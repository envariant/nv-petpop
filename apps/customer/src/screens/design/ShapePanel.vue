<script setup lang="ts">
import { computed } from 'vue';
import { label } from '@petpop/core';
import { REGIONS, sharedWith, type Region } from '@petpop/scene';
import { Chip, PRow, Tile } from '@petpop/ui-vue';
import { useDesign, type ShapeRegion } from '../../stores/design';
const d = useDesign();
const REGION_LABEL: Record<ShapeRegion, string> = { family: 'Body', ears: 'Ears', tail: 'Tail', muzzle: 'Muzzle', head: 'Head', legs: 'Legs' };
const c = computed(() => d.composition!);
// Part variants belong to one mesh (decision 118): only this figurine's mesh offers them.
const own = computed(() => d.manifest().region_deltas.filter((p) => p.mesh_id === c.value.mesh_id));
const regions = computed<ShapeRegion[]>(() => ['family', ...REGIONS.filter((r) => own.value.some((p) => p.region === r))]);
const shared = computed(() => sharedWith(d.manifest(), c.value.mesh_id, c.value.breed_id).map((b) => label(b)));
const items = computed(() =>
  d.region === 'family'
    ? d.manifest().families.map((f) => ({ id: f.id, name: f.name, thumb: f.thumbnail, selected: c.value.family_id === f.id, pick: () => void d.setFamily(f.id) }))
    : own.value.filter((p) => p.region === d.region)
      .map((p) => ({ id: p.id, name: p.name, thumb: p.thumbnail, selected: c.value.parts[d.region as Region] === p.id, pick: () => d.setPart(d.region as Region, p.id) })),
);
</script>

<template>
  <PRow>
    <Chip v-for="r in regions" :key="r" :selected="d.region === r" :test-id="`region-${r}`" @click="d.region = r">{{ REGION_LABEL[r] }}</Chip>
  </PRow>
  <p v-if="d.region === 'family' && shared.length > 0" class="mt-2 text-sm opacity-70 md:text-base" data-testid="shared-mesh">
    Same figure shape as {{ shared.slice(0, 3).join(', ') }}{{ shared.length > 3 ? ` and ${shared.length - 3} more` : '' }}
  </p>
  <div class="mt-3 grid grid-cols-[repeat(auto-fill,minmax(6.5rem,1fr))] gap-2" data-testid="part-tiles">
    <Tile v-for="it in items" :key="it.id" :label="it.name" :selected="it.selected" :test-id="`part-${it.id}`" @click="it.pick()">
      <img :src="d.lib!.url(it.thumb)" alt="" class="h-20 w-20 object-contain" draggable="false" />
    </Tile>
  </div>
</template>

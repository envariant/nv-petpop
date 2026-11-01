<script setup lang="ts">
import { assetUrl, label } from '@petpop/core';
import { Tile } from '@petpop/ui-vue';
import { useSession } from '../../stores/session';
import { TILE_LABEL, useHighlight, useValue } from './vocab';
defineProps<{ path: string; values: string[] }>();
const s = useSession();
const hl = useHighlight();
const value = useValue();
</script>

<template>
  <div class="grid grid-cols-[repeat(auto-fill,minmax(7rem,1fr))] gap-3">
    <Tile v-for="v in values" :key="v" :label="label(TILE_LABEL[v] ?? v)" :selected="value(path) === v" :highlight="value(path) === v && hl(path)"
      :test-id="`tile-${path}-${v}`" @click="s.tap(path, v)">
      <img :src="assetUrl(`assets/tiles/${s.spec!.species}/${path}__${v}.png`)" alt="" class="h-20 w-20 object-contain" draggable="false" />
    </Tile>
  </div>
</template>

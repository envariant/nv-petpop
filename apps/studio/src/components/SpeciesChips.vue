<script setup lang="ts">
import { Chip, PRow } from '@petpop/ui-vue';
import { useCurate } from '../stores/curate';
const c = useCurate();
</script>

<template>
  <PRow>
    <Chip v-for="sp in (['dog', 'cat'] as const)" :key="sp" :selected="c.species === sp" :test-id="`curate-species-${sp}`" @click="c.setSpecies(sp)">
      {{ sp === 'dog' ? 'Dogs' : 'Cats' }}
    </Chip>
  </PRow>
</template>

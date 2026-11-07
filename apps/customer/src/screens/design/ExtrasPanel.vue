<script setup lang="ts">
import { computed } from 'vue';
import { PSection, Tile } from '@petpop/ui-vue';
import { useDesign } from '../../stores/design';
import Swatches from './Swatches.vue';
import { EYES, NOSES, SHELL_COLOURS } from './palettes';
const d = useDesign();
// either figure: a whole-figure composition or a figure of parts (decision 139)
const c = computed(() => ({ shells: d.active?.shells ?? [], eye_colour: d.active?.eye_colour ?? '#3B2412', nose_colour: d.active?.nose_colour ?? '#1E1B1A' }));
</script>

<template>
  <PSection title="Accessories">
    <div class="grid grid-cols-[repeat(auto-fill,minmax(5.5rem,1fr))] gap-2">
      <Tile v-for="s in d.manifest().shell_parts" :key="s.id" :label="s.name" :selected="c.shells.some((x) => x.part_id === s.id)" :test-id="`shell-${s.id}`" @click="d.toggleShell(s.id)">
        <img :src="d.fileUrl(s.thumbnail)" alt="" class="h-14 w-14 object-contain" draggable="false" />
      </Tile>
    </div>
    <div v-for="s in c.shells" :key="s.part_id" class="mt-3">
      <Swatches :value="s.colour" :options="SHELL_COLOURS" :test-id="`shell-colour-${s.part_id}`" size="2.25rem" @pick="(hex) => d.setShellColour(s.part_id, hex)" />
    </div>
  </PSection>
  <PSection title="Eyes" test-id="eyes"><Swatches :value="c.eye_colour" :options="EYES" test-id="eye" @pick="d.setEyes" /></PSection>
  <PSection title="Nose" test-id="nose"><Swatches :value="c.nose_colour" :options="NOSES" test-id="nose" @pick="d.setNose" /></PSection>
</template>

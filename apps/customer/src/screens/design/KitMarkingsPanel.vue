<script setup lang="ts">
// Markings for a figure of part kits (decision 136): the coat (colour A), the markings' colour (B) and a third (C) for
// tricolour patterns, which markings are on (those the breed's parts have masks for), and the eyes and nose when
// the head has masks for them. Painted on screen as in print.
import { computed } from 'vue';
import { label } from '@petpop/core';
import { EYE, NOSE, markingsOf } from '@petpop/scene';
import { Chip, PRow, PSection } from '@petpop/ui-vue';
import { useDesign } from '../../stores/design';
import Swatches from './Swatches.vue';
import { EYES, FUR, NOSES } from './palettes';
const d = useDesign();
const c = computed(() => d.kitComposition!);
const masks = computed(() => (d.kitManifest().masks ?? []).filter((m) => d.kit!.parts.some((p) => p.uv_layout === m.uv_layout)).map((m) => m.name));
const markings = computed(() => [...new Set([...markingsOf(d.kitManifest(), d.kit!), ...c.value.texture.markings])]);
const nameOf = (hex: string) => FUR.find((f) => f.hex.toUpperCase() === hex.toUpperCase())?.name ?? null;
</script>

<template>
  <PSection title="Coat" test-id="kit-coat">
    <Swatches :value="c.texture.base.hex" :options="FUR" test-id="kit-coat" @pick="(hex) => d.setKitColour('base', hex, nameOf(hex) ?? undefined)" />
  </PSection>
  <PSection v-if="markings.length" title="Markings" test-id="kit-markings">
    <PRow>
      <Chip v-for="m in markings" :key="m" :selected="c.texture.markings.includes(m)" :test-id="`kit-marking-${m}`" @click="d.toggleMarking(m)">{{ label(m) }}</Chip>
    </PRow>
  </PSection>
  <PSection v-if="markings.length || c.texture.pattern" title="Markings colour" test-id="kit-secondary">
    <Swatches :value="(c.texture.secondary ?? c.texture.base).hex" :options="FUR" test-id="kit-secondary" @pick="(hex) => d.setKitColour('secondary', hex, nameOf(hex) ?? undefined)" />
  </PSection>
  <PSection v-if="c.texture.tertiary" title="Third colour" test-id="kit-tertiary">
    <Swatches :value="c.texture.tertiary.hex" :options="FUR" test-id="kit-tertiary" @pick="(hex) => d.setKitColour('tertiary', hex, nameOf(hex) ?? undefined)" />
  </PSection>
  <PSection v-if="masks.includes(EYE)" title="Eyes" test-id="kit-eyes">
    <Swatches :value="c.eye_colour ?? ''" :options="EYES" test-id="kit-eyes" @pick="d.setEyes" />
  </PSection>
  <PSection v-if="masks.includes(NOSE)" title="Nose" test-id="kit-nose">
    <Swatches :value="c.nose_colour ?? ''" :options="NOSES" test-id="kit-nose" @pick="d.setNose" />
  </PSection>
</template>

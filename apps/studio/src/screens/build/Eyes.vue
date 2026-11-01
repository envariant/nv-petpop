<script setup lang="ts">
import { computed } from 'vue';
import { EYE_PALETTE, label } from '@petpop/core';
import { Chip, Swatch } from '@petpop/ui-vue';
import { useSession } from '../../stores/session';
import { useHighlight } from './vocab';
const s = useSession();
const hl = useHighlight();
const eyes = computed(() => s.spec!.eyes);
const names = Object.keys(EYE_PALETTE);
const set = (patch: Record<string, unknown>) => s.tap('eyes', { ...eyes.value, ...patch });
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center gap-2">
      <Swatch v-for="n in names" :key="n" :hex="EYE_PALETTE[n].hex" :label="`${label(n)} eyes`" :test-id="`swatch-eyes-${n}`" :selected="eyes.colour === n"
        :highlight="eyes.colour === n && hl('eyes')" @click="set({ colour: n, hex: EYE_PALETTE[n].hex })" />
      <Chip test-id="toggle-heterochromia" :selected="eyes.heterochromia"
        @click="set({ heterochromia: !eyes.heterochromia, second_colour: eyes.second_colour ?? 'blue', second_hex: eyes.second_hex ?? EYE_PALETTE.blue.hex })">Odd eyes</Chip>
    </div>
    <div v-if="eyes.heterochromia" class="mt-3 flex flex-wrap items-center gap-2">
      <span class="text-base text-muted">Second eye</span>
      <Swatch v-for="n in names" :key="n" size="2.5rem" :hex="EYE_PALETTE[n].hex" :label="`Second eye ${label(n)}`" :selected="eyes.second_colour === n"
        @click="set({ second_colour: n, second_hex: EYE_PALETTE[n].hex })" />
    </div>
  </div>
</template>

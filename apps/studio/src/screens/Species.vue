<script setup lang="ts">
// One-off figurine, step 1: species.
import { PTitle } from '@petpop/ui-vue';
import { useSession } from '../stores/session';
const s = useSession();
const TILES = [
  { sp: 'dog' as const, emoji: '🐶', label: 'Dog', colour: '#FF8A3D' },
  { sp: 'cat' as const, emoji: '🐱', label: 'Cat', colour: '#7A5CFF' },
];
</script>

<template>
  <div class="mx-auto flex h-full max-w-5xl flex-col px-4 pb-6 pt-6 md:px-8 md:pt-8">
    <PTitle sub="Pick the species for this figurine.">Dog or cat?</PTitle>
    <div class="flex min-h-0 flex-1 flex-col gap-4 sm:flex-row md:gap-6">
      <button v-for="t in TILES" :key="t.sp" :data-testid="`species-${t.sp}`" class="press hit flex flex-1 flex-col items-center justify-center rounded-tile shadow-soft"
        :style="{ background: t.colour }" @click="s.chooseSpecies(t.sp)">
        <span class="text-[clamp(4rem,14vw,10rem)] leading-none" aria-hidden="true">{{ t.emoji }}</span>
        <span class="mt-4 font-display text-4xl font-semibold text-white md:text-5xl">{{ t.label }}</span>
      </button>
    </div>
  </div>
</template>

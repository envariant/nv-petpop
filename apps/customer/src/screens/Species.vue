<script setup lang="ts">
import { PTitle } from '@petpop/ui-vue';
import type { Species } from '@petpop/core';
import { useSession } from '../stores/session';
const s = useSession();
const tiles: { sp: Species; emoji: string; label: string; colour: string }[] = [
  { sp: 'dog', emoji: '🐶', label: 'Dog', colour: '#FF8A3D' },
  { sp: 'cat', emoji: '🐱', label: 'Cat', colour: '#7A5CFF' },
];
</script>

<template>
  <div class="flex h-full flex-col px-4 pb-6 pt-2 md:px-8">
    <PTitle sub="Pick one to start.">Dog or cat?</PTitle>
    <div class="flex min-h-0 flex-1 flex-col gap-4 landscape:flex-row md:gap-8">
      <button v-for="t in tiles" :key="t.sp" :data-testid="`species-${t.sp}`" class="press hit flex flex-1 flex-col items-center justify-center rounded-tile shadow-soft"
        :style="{ background: t.colour }" @click="s.chooseSpecies(t.sp)">
        <span class="text-[min(28vw,28vh)] leading-none" aria-hidden="true">{{ t.emoji }}</span>
        <span class="mt-4 font-display text-4xl font-semibold text-white md:text-5xl">{{ t.label }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
// The start: an attract loop of finished figurines on a kiosk, a welcome on phones and desktops.
import { onBeforeUnmount, onMounted, ref, computed } from 'vue';
import fixtureIndex from '@fixtures/pets/index.json';
import showcase from '../showcase.json';
import { assetUrl } from '@petpop/core';
import { GlbView, isKiosk } from '@petpop/ui-vue';
import { useSession } from '../stores/session';
const s = useSession();
const SHOWCASE = showcase.pets.map((id) => fixtureIndex.pets.find((p) => p.id === id)!);
const i = ref(0);
let t = 0;
onMounted(() => (t = window.setInterval(() => (i.value = (i.value + 1) % SHOWCASE.length), 6000)));
onBeforeUnmount(() => clearInterval(t));
const pet = computed(() => SHOWCASE[i.value]);
</script>

<template>
  <!-- Portrait: title, figure, caption, button in a column. Landscape: the words on the left, the figure on the right. -->
  <button data-testid="attract" class="flex h-full w-full flex-col items-center gap-4 px-6 py-8 text-center landscape:md:flex-row landscape:md:px-16 landscape:md:text-left" @click="s.start()">
    <div class="contents landscape:md:flex landscape:md:flex-1 landscape:md:flex-col landscape:md:items-start landscape:md:justify-center landscape:md:gap-6">
      <div class="order-1">
        <div class="font-display text-6xl font-semibold tracking-tight md:text-7xl">Pet<span class="text-accent">Pop</span></div>
        <p class="mt-3 text-xl text-muted md:text-2xl">Your pet, as a tiny collectible figure</p>
      </div>
      <p class="order-3 text-lg text-muted md:text-xl" data-testid="attract-caption" aria-live="polite">{{ pet.pet_name }} the {{ pet.breed.replace(/_/g, ' ') }}</p>
      <div class="pulse order-4 rounded-full bg-accent px-10 py-4 font-display text-3xl font-semibold text-white shadow-soft">
        {{ isKiosk ? 'Tap to make yours' : 'Make yours' }}
      </div>
    </div>
    <div class="relative order-2 min-h-0 w-full flex-1 landscape:md:h-full">
      <Transition name="fade" mode="out-in">
        <GlbView :key="pet.id" :url="assetUrl(`fixtures/${pet.id}/figure.glb`)" :fallback-image="assetUrl(`fixtures/${pet.id}/thumbnail.png`)" spin />
      </Transition>
    </div>
  </button>
</template>

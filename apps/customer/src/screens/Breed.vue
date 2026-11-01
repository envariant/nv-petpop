<script setup lang="ts">
// Breed search and grid: the on-screen keyboard on a kiosk, the system keyboard otherwise.
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { KioskApi } from '@petpop/core';
import type { Breed } from '@petpop/core';
import { Keyboard, PTitle, TextDisplay, Tile, isKiosk } from '@petpop/ui-vue';
import { useSession } from '../stores/session';
const s = useSession();
const q = ref('');
const items = ref<Breed[]>([]);
const typing = ref(false);
let t = 0;
let seq = 0;
watch([() => s.species, q], () => {
  clearTimeout(t);
  const mine = ++seq;
  t = window.setTimeout(() => {
    KioskApi.breeds(s.species ?? 'dog', q.value).then((r) => mine === seq && (items.value = r.items)).catch(() => undefined);
  }, 120);
}, { immediate: true });
onBeforeUnmount(() => clearTimeout(t));
const silhouette = computed(() => (s.species === 'cat' ? '🐈' : '🐕'));
</script>

<template>
  <div class="flex h-full flex-col px-4 pb-4 pt-2 md:px-8">
    <PTitle sub="Search or tap. Not sure? Pick Mixed.">Which breed?</PTitle>
    <button v-if="isKiosk" class="mb-3 text-left" data-testid="breed-search" @click="typing = true">
      <TextDisplay :value="q" placeholder="🔍  Search breeds" />
    </button>
    <input v-else v-model="q" data-testid="breed-search-input" type="search" placeholder="🔍  Search breeds" autocomplete="off"
      class="mb-3 rounded-tile border-4 border-line bg-card px-4 py-3 text-lg text-ink outline-none focus:border-accent md:text-xl" />
    <div class="no-scrollbar grid min-h-0 flex-1 auto-rows-[7.5rem] grid-cols-[repeat(auto-fill,minmax(8.5rem,1fr))] content-start gap-3 overflow-y-auto pb-4" data-testid="breed-grid">
      <Tile v-for="b in items" :key="b.id" :label="b.label" :test-id="`breed-${b.id}`" :dashed="b.id === 'mixed'" @click="s.chooseBreed(b)">
        <span class="text-4xl" aria-hidden="true">{{ b.id === 'mixed' ? '❓' : silhouette }}</span>
      </Tile>
      <p v-if="items.length === 0" class="col-span-full text-lg text-muted">No breed matches “{{ q }}”. Try Mixed / not sure.</p>
    </div>
    <Keyboard v-if="isKiosk && typing" v-model="q" :max-length="30" compact :capitalize="false" @done="typing = false" />
  </div>
</template>

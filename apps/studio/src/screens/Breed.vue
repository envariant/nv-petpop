<script setup lang="ts">
// One-off figurine, step 2: breed, searched with the system keyboard.
import { onBeforeUnmount, ref, watch } from 'vue';
import { StudioApi } from '@petpop/core';
import type { Breed } from '@petpop/core';
import { PTitle, Tile } from '@petpop/ui-vue';
import { useSession } from '../stores/session';
const s = useSession();
const q = ref('');
const items = ref<Breed[]>([]);
let timer = 0;
let seq = 0;
watch([() => s.species, q], () => {
  clearTimeout(timer);
  const mine = ++seq;
  timer = window.setTimeout(() => {
    StudioApi.breeds(s.species ?? 'dog', q.value).then((r) => mine === seq && (items.value = r.items)).catch(() => undefined);
  }, 120);
}, { immediate: true });
onBeforeUnmount(() => clearTimeout(timer));
</script>

<template>
  <div class="mx-auto flex h-full max-w-6xl flex-col px-4 pt-6 md:px-8 md:pt-8">
    <PTitle sub="Search or pick. Not sure? Pick Mixed.">Which breed?</PTitle>
    <input v-model="q" placeholder="🔍  Search breeds" maxlength="30" data-testid="breed-search" autocomplete="off"
      class="mb-4 w-full rounded-tile border-4 border-line bg-card px-4 py-3 text-lg outline-none focus:border-accent md:text-xl" />
    <div class="no-scrollbar grid min-h-0 flex-1 auto-rows-[8.5rem] grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-3 overflow-y-auto pb-6" data-testid="breed-grid">
      <Tile v-for="b in items" :key="b.id" :label="b.label" :test-id="`breed-${b.id}`" :dashed="b.id === 'mixed'" @click="s.chooseBreed(b)">
        <span class="text-5xl" aria-hidden="true">{{ b.id === 'mixed' ? '❓' : s.species === 'cat' ? '🐈' : '🐕' }}</span>
      </Tile>
      <p v-if="items.length === 0" class="col-span-full text-lg text-muted">No breed matches “{{ q }}”. Try Mixed / not sure.</p>
    </div>
  </div>
</template>

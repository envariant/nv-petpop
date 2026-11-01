<script setup lang="ts">
// Curation: the library. Families (each on its mesh), parts, accessories and pattern layers, with the editor beside
// the grid on a wide screen and above it on a narrow one.
import { watch } from 'vue';
import type { ItemKind } from '@petpop/core';
import { Chip, PRow, PTitle, cx } from '@petpop/ui-vue';
import { useCurate } from '../stores/curate';
import Notice from '../components/Notice.vue';
import Page from '../components/Page.vue';
import SpeciesChips from '../components/SpeciesChips.vue';
import Editor from './library/Editor.vue';
const c = useCurate();
const KINDS: { kind: ItemKind; title: string }[] = [
  { kind: 'family', title: 'Families' },
  { kind: 'region', title: 'Parts' },
  { kind: 'shell', title: 'Accessories' },
  { kind: 'pattern', title: 'Patterns' },
];
watch(() => c.species, () => void c.loadItems(), { immediate: true });
</script>

<template>
  <Page test-id="library" wide>
    <PTitle sub="Edit names, tags, colours and coverage. Editing a published item starts its next version; publish it to ship it in the next release.">Library</PTitle>
    <Notice :error="c.error" :notice="c.notice" />
    <div class="mb-4 flex flex-wrap items-center gap-4">
      <SpeciesChips />
      <PRow><Chip v-for="k in KINDS" :key="k.kind" :selected="c.kind === k.kind" :test-id="`kind-${k.kind}`" @click="c.loadItems(k.kind)">{{ k.title }}</Chip></PRow>
    </div>
    <div class="flex flex-col gap-6 lg:flex-row-reverse lg:items-start">
      <div v-if="c.selected" class="lg:sticky lg:top-0 lg:w-[30rem] lg:shrink-0"><Editor :item="c.selected" /></div>
      <div class="grid flex-1 grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-3" data-testid="library-items">
        <button v-for="it in c.items" :key="it.id" :data-testid="`item-${it.id}`"
          :class="cx('hit flex flex-col items-center gap-1 rounded-tile border-4 bg-card p-2 shadow-soft', c.selected?.id === it.id ? 'border-accent' : 'border-transparent')"
          @click="c.selected = it">
          <img v-if="it.thumbnail_url" :src="it.thumbnail_url" alt="" class="h-20 w-20 object-contain" />
          <span class="w-full truncate text-center font-display text-base">{{ it.name }}</span>
          <span class="text-sm text-muted">v{{ it.version }} · {{ it.status }}</span>
        </button>
      </div>
    </div>
  </Page>
</template>

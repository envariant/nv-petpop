<script setup lang="ts">
import { computed } from 'vue';
import { label } from '@petpop/core';
import type { LibraryCandidate } from '@petpop/core';
import { Chip } from '@petpop/ui-vue';
import { useCurate } from '../../stores/curate';
import Status from '../../components/Status.vue';
import QcLine from './QcLine.vue';
const props = defineProps<{ c: LibraryCandidate }>();
const cur = useCurate();
const hero = computed(() => props.c.tags.includes('hero'));
const toggleHero = () =>
  void cur.decide([{ item_id: props.c.id, action: props.c.status === 'rejected' ? 'reject' : 'accept', tags: hero.value ? props.c.tags.filter((t) => t !== 'hero') : [...props.c.tags, 'hero'] }]);
const publish = () => void cur.publish({ species: cur.batch?.species ?? 'dog', kind: props.c.kind, id: props.c.id }).then(() => cur.refreshBatch());
</script>

<template>
  <div class="flex flex-wrap items-center gap-3 border-t-2 border-line py-2" :data-testid="`cand-${c.id}`">
    <img v-if="c.thumbnail_url" :src="c.thumbnail_url" alt="" class="h-14 w-14 object-contain" />
    <div class="flex min-w-[12rem] flex-1 flex-col">
      <span class="truncate font-display text-lg">{{ c.kind === 'family' ? 'Family on its own mesh' : label(c.region ?? '') }}</span>
      <QcLine :c="c" />
    </div>
    <Status :status="c.status" />
    <template v-if="c.status !== 'published'">
      <Chip :selected="c.status === 'accepted'" :test-id="`accept-${c.id}`" @click="cur.decide([{ item_id: c.id, action: 'accept' }])">✓</Chip>
      <Chip :selected="c.status === 'rejected'" :test-id="`reject-${c.id}`" @click="cur.decide([{ item_id: c.id, action: 'reject' }])">✕</Chip>
      <Chip :selected="hero" :test-id="`hero-${c.id}`" @click="toggleHero">★</Chip>
    </template>
    <Chip v-if="c.status === 'accepted'" :test-id="`publish-${c.id}`" @click="publish">Publish</Chip>
  </div>
</template>

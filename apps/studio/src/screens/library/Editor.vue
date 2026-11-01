<script setup lang="ts">
// The item editor: name, tags, breeds on a family (sharing its mesh), colours and coverage; save starts the next
// version, publish ships it in the next release.
import { ref, watch } from 'vue';
import { label } from '@petpop/core';
import type { LibraryItem } from '@petpop/core';
import { PButton, PRow, Swatch } from '@petpop/ui-vue';
import { useCurate } from '../../stores/curate';
import Status from '../../components/Status.vue';
const props = defineProps<{ item: LibraryItem }>();
const c = useCurate();
const COLOURS = ['#F4EFE6', '#1E1B1A', '#C8763A', '#8A5A3B', '#E8D8B8', '#6E6A68', '#DD3333', '#3366CC', '#F2C230', '#E04A8A'];
const name = ref('');
const tags = ref('');
const colour = ref('');
const cov = ref({ min: 0, max: 1, default: 0.5 });
const breeds = ref('');
watch(() => props.item, (it) => {
  name.value = it.name;
  tags.value = it.tags.join(', ');
  colour.value = it.default_colour ?? '';
  cov.value = { ...(it.coverage ?? { min: 0, max: 1, default: 0.5 }) };
  breeds.value = (it.breeds ?? []).join(', ');
}, { immediate: true });
const list = (t: string) => t.split(',').map((x) => x.trim()).filter(Boolean);
const save = () => c.edit({
  name: name.value, tags: list(tags.value),
  ...(props.item.kind === 'shell' || props.item.kind === 'pattern' ? { default_colour: colour.value } : {}),
  ...(props.item.kind === 'pattern' ? { coverage: { ...cov.value } } : {}),
  ...(props.item.kind === 'family' ? { breeds: list(breeds.value) } : {}),
});
const field = 'w-full rounded-tile border-4 border-line bg-paper px-4 py-2 text-base outline-none focus:border-accent md:text-lg';
</script>

<template>
  <div class="rounded-tile bg-card p-5 shadow-soft" data-testid="item-editor">
    <div class="mb-4 flex items-center gap-4">
      <img v-if="item.thumbnail_url" :src="item.thumbnail_url" alt="" class="h-20 w-20 object-contain" />
      <div class="flex min-w-0 flex-col">
        <span class="truncate font-display text-xl">{{ item.id }}</span>
        <span class="text-base text-muted">version {{ item.version }} of {{ item.versions.join(', ') }} · published {{ item.published_version ?? 'none' }}</span>
      </div>
      <span class="ml-auto"><Status :status="item.status" /></span>
    </div>
    <div class="flex flex-col gap-3">
      <input v-model="name" :class="field" data-testid="edit-name" aria-label="Name" />
      <input v-model="tags" :class="field" data-testid="edit-tags" aria-label="Tags" placeholder="tags, comma separated" />
      <input v-if="item.kind === 'family'" v-model="breeds" :class="field" data-testid="edit-breeds" aria-label="Breeds" placeholder="breed ids" />
      <p v-if="item.mesh_id" class="text-sm text-muted md:text-base" data-testid="item-mesh">
        Mesh {{ item.mesh_id }}{{ item.shared_with && item.shared_with.length ? ` · shared with ${item.shared_with.map((b) => label(b)).join(', ')}` : ' · not shared' }}
      </p>
      <PRow v-if="item.kind === 'shell' || item.kind === 'pattern'">
        <Swatch v-for="h in COLOURS" :key="h" :hex="h" :label="h" size="2.5rem" :selected="colour.toUpperCase() === h" :test-id="`edit-colour-${h.slice(1)}`" @click="colour = h" />
      </PRow>
      <template v-if="item.kind === 'pattern'">
        <label v-for="k in (['min', 'default', 'max'] as const)" :key="k" class="flex items-center gap-3 text-base">
          <span class="w-20">{{ k }}</span>
          <input v-model.number="cov[k]" type="range" min="0" max="1" step="0.01" class="flex-1" :data-testid="`cov-${k}`" />
          <span class="w-12">{{ cov[k].toFixed(2) }}</span>
        </label>
      </template>
      <p v-if="item.qc" class="break-all text-sm text-muted">QC: {{ JSON.stringify(item.qc) }}</p>
    </div>
    <div class="mt-4 flex flex-wrap gap-3">
      <PButton variant="soft" :disabled="c.busy" test-id="edit-save" @click="save">Save</PButton>
      <PButton :disabled="c.busy || item.status === 'published' || item.status === 'rejected'" test-id="edit-publish" @click="c.publish(item)">Publish v{{ item.version }}</PButton>
      <PButton variant="ghost" :disabled="c.busy || item.published_version === null" test-id="edit-unpublish" @click="c.unpublish(item)">Unpublish</PButton>
    </div>
  </div>
</template>

<script setup lang="ts">
// Curation (BRIEF Section 16, M8): the batch spec builder (breeds x variants x seeds) and the batches so far.
// One-off figurines (bespoke jobs) keep the Build, Brief and Name flow.
import { computed, ref, watch } from 'vue';
import { StudioApi } from '@petpop/core';
import type { Breed } from '@petpop/core';
import { Chip, PButton, PRow, PSection, PTitle } from '@petpop/ui-vue';
import { usePoll } from '../composables';
import { MAX_FIGURINES, VARIANTS, useCurate } from '../stores/curate';
import { useSession } from '../stores/session';
import Notice from '../components/Notice.vue';
import Page from '../components/Page.vue';
import ProfilePicker from '../components/ProfilePicker.vue';
import SpeciesChips from '../components/SpeciesChips.vue';
import Status from '../components/Status.vue';
const c = useCurate();
const s = useSession();
const breeds = ref<Breed[]>([]);
watch(() => c.species, (sp) => void StudioApi.breeds(sp).then((r) => (breeds.value = r.items)).catch(() => (breeds.value = [])), { immediate: true });
usePoll(() => c.loadBatches(), 3000);
const total = computed(() => c.breeds.length * c.variants.length * c.seeds);
function open(id: string) {
  void c.openBatch(id);
  s.go('review');
}
</script>

<template>
  <Page test-id="generate" wide>
    <div class="grid gap-8 xl:grid-cols-[minmax(0,1fr)_28rem]">
      <div>
        <PTitle sub="Breeds x variants x seeds, each a full pipeline run; every figurine becomes a family on its own mesh, checked.">New batch</PTitle>
        <Notice :error="c.error" :notice="c.notice" />
        <PSection title="Species"><SpeciesChips /></PSection>
        <PSection :title="`Breeds (${c.breeds.length})`" test-id="batch-breeds">
          <PRow><Chip v-for="b in breeds" :key="b.id" :selected="c.breeds.includes(b.id)" :test-id="`batch-breed-${b.id}`" @click="c.toggleBreed(b.id)">{{ b.label }}</Chip></PRow>
        </PSection>
        <PSection title="Variants" test-id="batch-variants">
          <PRow><Chip v-for="v in VARIANTS" :key="v.label" :selected="c.variants.includes(v.label)" :test-id="`batch-variant-${v.label}`" @click="c.toggleVariant(v.label)">{{ v.title }}</Chip></PRow>
        </PSection>
        <PSection title="Seeds per variant">
          <div class="flex items-center gap-4">
            <PButton variant="soft" test-id="seeds-minus" @click="c.seeds = Math.max(1, c.seeds - 1)">−</PButton>
            <span class="w-12 text-center font-display text-3xl" data-testid="seeds">{{ c.seeds }}</span>
            <PButton variant="soft" test-id="seeds-plus" @click="c.seeds = Math.min(10, c.seeds + 1)">+</PButton>
          </div>
        </PSection>
        <ProfilePicker />
        <div class="flex flex-wrap items-center gap-4">
          <PButton class="flex-1" :disabled="!total || total > MAX_FIGURINES || c.busy" test-id="start-batch" @click="c.startBatch()">
            {{ total > MAX_FIGURINES ? `${total} figurines: at most ${MAX_FIGURINES}` : `Generate ${total} figurine${total === 1 ? '' : 's'}` }}
          </PButton>
          <PButton variant="ghost" test-id="one-off" @click="s.clearFigure('species')">One-off figurine ›</PButton>
        </div>
      </div>
      <PSection title="Batches" test-id="batch-list">
        <p v-if="c.batches.length === 0" class="text-base text-muted">No batches yet.</p>
        <button v-for="b in c.batches" :key="b.batch_id" :data-testid="`batch-${b.batch_id}`"
          class="hit mb-2 flex w-full items-center justify-between gap-3 rounded-tile bg-card p-4 text-left text-base shadow-soft" @click="open(b.batch_id)">
          <span>
            <b>{{ b.species }}</b> · {{ b.summary.finished }}/{{ b.summary.figurines }} done · {{ b.summary.passed_qc }}/{{ b.summary.candidates }} pass QC ·
            {{ b.summary.meshes_published }} meshes published · by {{ b.created_by }}<span v-if="b.genai_profile" :data-testid="`batch-profile-${b.batch_id}`">
              · on {{ b.genai_profile }}{{ b.pipeline ? `, ${b.pipeline.replace('_', ' ')}` : '' }}</span>
          </span>
          <Status :status="b.status" />
        </button>
      </PSection>
    </div>
  </Page>
</template>

<script setup lang="ts">
// Curation: the review grid. Each figurine is one candidate, a family on its own mesh, with its turntable and mesh
// QC; accept, reject, star heroes and publish.
import { computed, onMounted } from 'vue';
import { PButton, PTitle } from '@petpop/ui-vue';
import { usePoll } from '../composables';
import { useCurate } from '../stores/curate';
import { useSession } from '../stores/session';
import Notice from '../components/Notice.vue';
import Page from '../components/Page.vue';
import FigurineCard from './review/FigurineCard.vue';
const c = useCurate();
const s = useSession();
onMounted(async () => {
  if (c.batch) return;
  await c.loadBatches();
  if (c.batches[0]) await c.openBatch(c.batches[0].batch_id);
});
usePoll(() => c.refreshBatch(), 2000);
const all = computed(() => (c.batch ? c.batch.figurines.flatMap((f) => f.candidates) : []));
const passing = computed(() => all.value.filter((x) => !x.auto_rejected && x.status === 'draft'));
const accepted = computed(() => all.value.filter((x) => x.status === 'accepted'));
async function publishAll() {
  const sp = c.batch!.species;
  for (const x of accepted.value) await c.publish({ species: sp, kind: x.kind, id: x.id });
  await c.refreshBatch();
}
const summary = computed(() => {
  const m = c.batch!.summary;
  return `${m.finished}/${m.figurines} figurines done · ${m.passed_qc}/${m.candidates} pass QC · ${m.accepted} accepted · ${m.published} published · ${m.meshes_published} meshes`;
});
</script>

<template>
  <div v-if="!c.batch" class="flex h-full flex-col items-center justify-center gap-6 px-4 text-center" data-testid="review">
    <PTitle sub="Start a batch in Generate.">Nothing to review</PTitle>
    <PButton @click="s.go('generate')">New batch</PButton>
  </div>
  <Page v-else test-id="review" wide>
    <PTitle :sub="summary">Review {{ c.batch.species }} batch</PTitle>
    <Notice :error="c.error" :notice="c.notice" />
    <div class="mb-4 flex flex-wrap gap-3">
      <PButton variant="soft" :disabled="!passing.length || c.busy" test-id="accept-passing" @click="c.decide(passing.map((x) => ({ item_id: x.id, action: 'accept' as const })))">
        Accept {{ passing.length }} that passed QC
      </PButton>
      <PButton :disabled="!accepted.length || c.busy" test-id="publish-accepted" @click="publishAll">Publish {{ accepted.length }} accepted</PButton>
    </div>
    <p class="mb-4 text-sm text-muted md:text-base">Fix in Blender: download a figurine's GLB from the queue, edit it, and re-run it as a one-off; it comes back here as a mesh of its own for review.</p>
    <div class="grid gap-4 2xl:grid-cols-2">
      <FigurineCard v-for="f in c.batch.figurines" :key="f.job_id" :f="f" />
    </div>
  </Page>
</template>

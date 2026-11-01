<script setup lang="ts">
// Manual mode inbox (decision 111): each card is a request the pipeline would have sent the GenAI API, shown so the
// operator can run it in the vendor's own app (Tripo Studio). The list sits beside the task on a wide screen.
import { computed, watch } from 'vue';
import { Chip, PRow, PSection, PTitle, cx } from '@petpop/ui-vue';
import { usePoll } from '../composables';
import { useManual, type ManualFilter } from '../stores/manual';
import Notice from '../components/Notice.vue';
import Page from '../components/Page.vue';
import Detail from './manual/Detail.vue';
const m = useManual();
usePoll(() => m.load(), 5000);
watch(() => m.filter, () => void m.load());
const selected = computed(() => m.tasks.find((t) => t.task_id === m.selectedId) ?? null);
const FILTERS: ManualFilter[] = ['pending', 'submitted', 'all'];
</script>

<template>
  <Page test-id="manual" wide>
    <PTitle sub="Requests the pipeline would send the GenAI API. Run each in the vendor's app, then upload the output here.">Manual tasks ({{ m.pending }} waiting)</PTitle>
    <Notice :error="m.error" :notice="m.notice" prefix="manual" />
    <PRow><Chip v-for="f in FILTERS" :key="f" :selected="m.filter === f" :test-id="`manual-filter-${f}`" @click="m.filter = f">{{ f }}</Chip></PRow>
    <div class="mt-4 flex flex-col gap-6 lg:flex-row lg:items-start">
      <PSection title="Tasks" test-id="manual-list" class="lg:w-[26rem] lg:shrink-0">
        <p v-if="m.tasks.length === 0" class="text-base text-muted">Nothing waiting. Jobs on a manual profile stop here for you.</p>
        <button v-for="t in m.tasks" :key="t.task_id" :data-testid="`manual-task-${t.task_id}`"
          :class="cx('hit mb-2 flex w-full items-center justify-between gap-3 rounded-tile p-4 text-left text-base shadow-soft', t.task_id === m.selectedId ? 'bg-accent text-white' : 'bg-card')"
          @click="m.select(t.task_id)">
          <span><b>{{ t.title }}</b> · {{ t.pet_name ?? t.breed_label ?? t.species }} · job {{ t.job_id }}</span>
          <span :class="cx('shrink-0 rounded-full px-3 py-0.5 font-display text-sm', t.status === 'pending' ? 'bg-accent2 text-white' : 'bg-line text-ink')">{{ t.status }}</span>
        </button>
      </PSection>
      <div class="min-w-0 flex-1"><Detail v-if="selected" :t="selected" /></div>
    </div>
  </Page>
</template>

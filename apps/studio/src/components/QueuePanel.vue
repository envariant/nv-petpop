<script setup lang="ts">
// The studio queue: what is running, what waits, the last 20 jobs with retry and reprint.
import { onMounted, ref } from 'vue';
import { StudioApi } from '@petpop/core';
import type { StaffQueue } from '@petpop/core';
import { PButton } from '@petpop/ui-vue';
import Backdrop from './Backdrop.vue';
defineEmits<{ close: [] }>();
const q = ref<StaffQueue | null>(null);
const err = ref<string | null>(null);
async function load() {
  try {
    q.value = await StudioApi.queue();
    err.value = null;
  } catch {
    err.value = 'Could not load the queue';
  }
}
onMounted(load);
const retry = (id: string) => void StudioApi.retry(id).then(load);
const reprint = (id: string) => void StudioApi.fulfil(id).then(load);
</script>

<template>
  <Backdrop test-id="staff-panel">
    <div class="max-h-full w-full max-w-5xl overflow-y-auto rounded-tile bg-paper p-6 shadow-soft md:p-10">
      <div class="mb-6 flex items-center justify-between gap-4">
        <h2 class="font-display text-3xl font-semibold">Studio queue</h2>
        <PButton variant="soft" test-id="staff-close" @click="$emit('close')">Close</PButton>
      </div>
      <p v-if="!q" class="text-lg text-muted">{{ err ?? 'Loading…' }}</p>
      <div v-else class="text-base md:text-lg" data-testid="staff-queue">
        <p class="mb-4">
          Mode <b>{{ q.mode }}</b> · GPU <b>{{ q.gpu.name }}</b> · {{ q.gpu.temp_c ?? '–' }} °C · running {{ q.running ? q.running.pet_name : 'nothing' }} · {{ q.queued.length }} queued
        </p>
        <div class="overflow-x-auto">
          <table class="w-full min-w-[40rem] text-left">
            <thead class="text-muted">
              <tr><th /><th>Pet</th><th>By</th><th>Status</th><th>Fallback</th><th>Time</th><th /></tr>
            </thead>
            <tbody>
              <tr v-for="j in q.recent" :key="j.job_id" class="border-t border-line">
                <td><img v-if="j.thumbnail_url" :src="j.thumbnail_url" alt="" class="h-12 w-12 object-contain" /></td>
                <td>{{ j.pet_name }}</td>
                <td>{{ j.kind === 'bespoke' ? `${j.requested_by} (bespoke)` : j.requested_by }}</td>
                <td>{{ j.status }}</td>
                <td>{{ j.fallback }}</td>
                <td>{{ j.total_ms ? `${Math.round(j.total_ms / 1000)} s` : '–' }}</td>
                <td class="flex gap-2 py-2">
                  <button class="hit rounded-full bg-card px-3 py-1 shadow-soft" @click="retry(j.job_id)">Retry</button>
                  <button v-if="j.status === 'done' || j.status === 'fulfilled'" class="hit rounded-full bg-card px-3 py-1 shadow-soft" @click="reprint(j.job_id)">Reprint</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </Backdrop>
</template>

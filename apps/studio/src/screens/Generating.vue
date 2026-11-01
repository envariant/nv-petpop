<script setup lang="ts">
// One-off figurine, step 6: live progress with the real intermediate previews, then the result.
import { computed, onBeforeUnmount, watch } from 'vue';
import { subscribeJob } from '@petpop/core';
import { GlbView, PButton, PTitle, cx } from '@petpop/ui-vue';
import { useSession } from '../stores/session';
const s = useSession();
const STAGES = [
  { id: 'A', label: 'Reading the description' },
  { id: 'B', label: 'Concept sketch' },
  { id: 'C', label: 'Four views' },
  { id: 'D', label: 'Sculpting' },
  { id: 'E', label: 'Fitting the figure' },
  { id: 'F', label: 'Painting and print prep' },
];
const ORDER = ['queued', 'A', 'control', 'B', 'C', 'D', 'E', 'F', 'done'];
let unsubscribe: (() => void) | null = null;
let timer = 0;
watch(() => s.jobId, (id) => {
  unsubscribe?.();
  unsubscribe = id ? subscribeJob(id, s.onEvent, s.onJob) : null;
}, { immediate: true });
const last = computed(() => s.events[s.events.length - 1]);
const status = computed(() => s.job?.status ?? last.value?.status ?? 'queued');
const stage = computed(() => last.value?.stage ?? s.job?.stage ?? 'queued');
const pct = computed(() => Math.max(last.value?.pct ?? 0, s.job?.pct ?? 0));
const done = computed(() => status.value === 'done' || status.value === 'fulfilled');
const failed = computed(() => status.value === 'failed');
watch(() => done.value && !!s.job, (ready) => {
  if (ready) timer = window.setTimeout(() => s.go('result'), 1200);
}, { immediate: true });
onBeforeUnmount(() => {
  unsubscribe?.();
  clearTimeout(timer);
});
const p = computed(() => s.previews);
const views = computed(() => ['view_front', 'view_left', 'view_back', 'view_right'].filter((k) => p.value[k]));
const name = computed(() => (s.spec as { pet_name?: string } | null)?.pet_name ?? 'your pet');
const stateOf = (id: string) => (ORDER.indexOf(stage.value) > ORDER.indexOf(id) || done.value ? 'done' : stage.value === id && !done.value ? 'current' : 'todo');
</script>

<template>
  <div class="mx-auto flex h-full max-w-6xl flex-col px-4 pb-6 pt-6 md:px-8 md:pt-8" data-testid="generating" :data-status="status">
    <PTitle :sub="failed ? undefined : 'This takes two to four minutes. Watch it come together.'">
      {{ failed ? 'That one got stuck' : done ? `${name} is ready!` : `Making ${name}…` }}
    </PTitle>
    <div v-if="status === 'waiting'" class="mb-4 flex flex-wrap items-center justify-between gap-4 rounded-tile bg-card p-5 text-lg shadow-soft" data-testid="waiting-operator">
      <span>This figurine is waiting for you: run its request in Tripo Studio and upload the output.</span>
      <button class="hit font-display text-accent underline" data-testid="open-manual" @click="s.go('manual')">Manual tasks ›</button>
    </div>
    <div v-if="status === 'queued'" class="mb-4 rounded-tile bg-card p-5 text-xl shadow-soft" data-testid="queue-position">
      You're <b>#{{ last?.queue_position ?? s.job?.queue_position ?? 1 }}</b> in the queue. Another figurine is being made first.
    </div>
    <div class="mb-3 h-4 shrink-0 overflow-hidden rounded-full bg-line" role="progressbar" :aria-valuenow="pct" aria-valuemin="0" aria-valuemax="100">
      <div class="h-full bg-accent transition-[width] duration-500" :style="{ width: `${pct}%` }" />
    </div>
    <p class="mb-4 text-lg" data-testid="progress-message" aria-live="polite">{{ last?.message ?? 'Starting…' }}</p>
    <div class="flex min-h-0 flex-1 flex-col gap-4 lg:flex-row">
      <div class="relative min-h-[16rem] flex-1 overflow-hidden rounded-tile bg-card shadow-soft" data-testid="preview-stage">
        <Transition name="fade" mode="out-in">
          <div v-if="p.glb && done" key="final" class="absolute inset-0"><GlbView :url="p.glb" :fallback-image="p.thumbnail" /></div>
          <div v-else-if="p.shape" key="shape" class="absolute inset-0" data-testid="preview-shape">
            <GlbView :url="p.shape" />
            <span class="absolute bottom-4 left-4 rounded-full bg-ink/80 px-3 py-0.5 text-sm text-paper">Raw shape</span>
          </div>
          <div v-else-if="views.length" key="views" class="absolute inset-0 grid grid-cols-2 gap-3 p-4" data-testid="preview-views">
            <img v-for="k in views" :key="k" :src="p[k]" :alt="k.replace('_', ' ')" class="h-full w-full rounded-2xl bg-paper object-contain" />
          </div>
          <img v-else-if="p.concept" key="concept" :src="p.concept" alt="concept" class="absolute inset-0 h-full w-full object-contain p-4" data-testid="preview-concept" />
          <div v-else key="wait" class="pulse absolute inset-0 flex items-center justify-center text-8xl">{{ s.species === 'cat' ? '🐱' : '🐶' }}</div>
        </Transition>
      </div>
      <ol class="grid shrink-0 grid-cols-2 gap-2 text-base sm:grid-cols-3 lg:w-72 lg:grid-cols-1">
        <li v-for="st in STAGES" :key="st.id" :data-testid="`stage-${st.id}`" :data-state="stateOf(st.id)"
          :class="cx('rounded-2xl px-3 py-2', stateOf(st.id) === 'done' ? 'bg-accent/15 text-ink' : stateOf(st.id) === 'current' ? 'bg-accent text-white' : 'bg-card text-muted')">
          {{ stateOf(st.id) === 'done' ? '✓ ' : '' }}{{ st.label }}
        </li>
      </ol>
    </div>
    <div v-if="failed" class="mt-4 flex flex-wrap items-center gap-4" data-testid="generate-failed">
      <p class="flex-1 text-lg text-muted">{{ s.job?.error ?? 'Something went wrong.' }} Retry it from the queue.</p>
      <PButton variant="soft" @click="s.go('build')">Back to Build</PButton>
    </div>
  </div>
</template>

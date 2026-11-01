<script setup lang="ts">
import { label } from '@petpop/core';
import type { BatchFigurine } from '@petpop/core';
import CandidateRow from './CandidateRow.vue';
defineProps<{ f: BatchFigurine }>();
</script>

<template>
  <div class="rounded-tile bg-card p-4 shadow-soft" :data-testid="`fig-${f.job_id}`">
    <div class="flex flex-col gap-4 sm:flex-row">
      <div class="h-44 w-full shrink-0 overflow-hidden rounded-tile bg-paper sm:w-44">
        <video v-if="f.turntable_url" :src="f.turntable_url" :poster="f.thumbnail_url ?? undefined" autoplay loop muted playsinline class="h-full w-full object-contain" />
        <img v-else-if="f.thumbnail_url" :src="f.thumbnail_url" alt="" class="h-full w-full object-contain" />
        <div v-else class="flex h-full items-center justify-center text-lg text-muted">{{ f.stage }}…</div>
      </div>
      <div class="flex min-w-0 flex-1 flex-col">
        <span class="font-display text-xl">{{ label(f.breed_id) }} · {{ f.variant }} · seed {{ f.seed }}</span>
        <span class="text-base text-muted">{{ f.status }}<template v-if="f.error"> · {{ f.error }}</template></span>
        <CandidateRow v-for="c in f.candidates" :key="c.id" :c="c" />
      </div>
    </div>
  </div>
</template>

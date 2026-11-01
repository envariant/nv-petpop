<script setup lang="ts">
import { computed } from 'vue';
import type { LibraryCandidate } from '@petpop/core';
const props = defineProps<{ c: LibraryCandidate }>();
type Qc = { symmetry_mm?: number; boundary_strain?: number; self_intersections?: number; reasons?: string[]; segmentation_valid?: boolean; print_watertight?: boolean; figure_tris?: number | null };
const q = computed(() => props.c.qc as Qc);
// A curated figurine is a mesh of its own (decision 119): its QC is the segmentation and the print checks.
const text = computed(() =>
  q.value.segmentation_valid !== undefined
    ? `parts ${q.value.segmentation_valid ? 'labelled' : 'not labelled'} · ${q.value.print_watertight ? 'watertight' : 'leaky'} · ${q.value.figure_tris ?? '?'} tris`
    : `sym ${q.value.symmetry_mm?.toFixed(2)} mm · strain ${q.value.boundary_strain?.toFixed(2)} · x ${q.value.self_intersections}`,
);
</script>

<template>
  <span :class="['text-sm md:text-base', c.auto_rejected ? 'text-accent2' : 'text-muted']" :title="(q.reasons ?? []).join('; ')">
    {{ text }}<template v-if="c.auto_rejected"> · {{ (q.reasons ?? [])[0] ?? 'rejected' }}</template>
  </span>
</template>

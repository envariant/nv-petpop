<script setup lang="ts">
// A GLB figure on a FigureStage (the attract loop, the result and order screens), with an image fallback when WebGL
// or the model is unavailable.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { FigureStage, loadGlb, setClay, webglAvailable } from '@petpop/scene';
import type { Object3D } from 'three';
const props = withDefaults(defineProps<{ url: string; spin?: boolean; interactive?: boolean; clay?: boolean; fallbackImage?: string; testId?: string }>(),
  { spin: true });
const el = ref<HTMLDivElement | null>(null);
const failed = ref(!webglAvailable());
let stage: FigureStage | null = null;
let model: Object3D | null = null;
let seq = 0;
async function load(url: string) {
  const mine = ++seq;
  try {
    const obj = await loadGlb(url);
    if (mine !== seq || !stage) return;
    model = obj;
    setClay(obj, props.clay);
    stage.setObject(obj);
  } catch {
    failed.value = true;
  }
}
onMounted(() => {
  if (failed.value || !el.value) return;
  try {
    stage = new FigureStage(el.value, { spin: props.spin, interactive: props.interactive });
  } catch {
    failed.value = true;
    return;
  }
  void load(props.url);
});
watch(() => props.url, (u) => void load(u));
watch(() => props.clay, (c) => model && setClay(model, c));
watch(() => props.spin, (s) => stage && (stage.spin = s));
onBeforeUnmount(() => {
  seq++;
  stage?.dispose();
  stage = null;
});
</script>

<template>
  <div class="h-full w-full" :data-testid="testId">
    <img v-if="failed && fallbackImage" :src="fallbackImage" alt="figurine" class="h-full w-full object-contain" />
    <div v-else-if="failed" class="flex h-full items-center justify-center text-lg text-muted">3D preview unavailable</div>
    <div v-else ref="el" class="h-full w-full" />
  </div>
</template>

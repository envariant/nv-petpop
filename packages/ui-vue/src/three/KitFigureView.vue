<script setup lang="ts">
// A figure of part kits on a FigureStage (decision 136): the parts placed and painted from the composition, refit
// when they move; orbit when interactive. data-ready and data-shape let tests see it built and re-placed.
import { markRaw, onBeforeUnmount, onMounted, ref, toRaw, watch } from 'vue';
import { FigureStage, KitFigure, webglAvailable, type Kit, type KitComposition, type KitManifest } from '@petpop/scene';
const props = withDefaults(defineProps<{ manifest: KitManifest; kit: Kit; composition: KitComposition; url: (path: string) => string;
  spin?: boolean; interactive?: boolean; testId?: string }>(), { interactive: true, testId: 'design-preview' });
const el = ref<HTMLDivElement | null>(null);
const failed = ref(!webglAvailable());
const ready = ref(false);
const shape = ref('');
let stage: FigureStage | null = null;
let figure: KitFigure | null = null;
const plain = (c: KitComposition): KitComposition => JSON.parse(JSON.stringify(c));
const shapeOf = (c: KitComposition) => JSON.stringify([c.variants, c.preset_id, c.pose_id]);

async function build() {
  if (!stage) return;
  figure?.dispose();
  const mine = markRaw(new KitFigure(toRaw(props.manifest), toRaw(props.kit), props.url));
  figure = mine;
  await mine.update(plain(props.composition));
  if (figure !== mine || !stage) return;
  stage.setObject(mine.root);
  ready.value = true;
  shape.value = shapeOf(props.composition);
}
async function apply(c: KitComposition) {
  const f = figure;
  if (!f || !stage || !ready.value) return;
  if (await f.update(plain(c))) stage.fit();
  shape.value = shapeOf(c);
}
onMounted(() => {
  if (failed.value || !el.value) return;
  try {
    stage = new FigureStage(el.value, { spin: props.spin, interactive: props.interactive });
  } catch {
    failed.value = true;
    return;
  }
  void build();
});
watch(() => [props.kit, props.manifest], () => {
  ready.value = false;
  void build();
});
watch(() => props.composition, (c) => void apply(c), { deep: true });
watch(() => props.spin, (s) => stage && (stage.spin = s));
onBeforeUnmount(() => {
  figure?.dispose();
  figure = null;
  stage?.dispose();
  stage = null;
});
</script>

<template>
  <div :data-testid="testId" :data-ready="ready ? 'true' : 'false'" :data-shape="shape" class="h-full w-full" :style="{ touchAction: interactive ? 'none' : 'auto' }">
    <div v-if="failed" class="flex h-full items-center justify-center text-lg text-muted">3D preview unavailable</div>
    <div v-else ref="el" class="h-full w-full" />
  </div>
</template>

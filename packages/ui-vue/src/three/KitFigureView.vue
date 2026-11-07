<script setup lang="ts">
// A figure of part kits on a FigureStage (decisions 136, 139): the parts placed and painted from the composition,
// extras on its sockets, refit when they move; orbit when interactive, tap or drag to paint when `paint` is on.
// data-ready, data-shape and data-extras let tests see it built, re-placed and dressed.
import { markRaw, onBeforeUnmount, onMounted, ref, toRaw, watch } from 'vue';
import { FigureStage, KitFigure, webglAvailable, type Kit, type KitComposition, type KitHit, type KitManifest } from '@petpop/scene';
const props = withDefaults(defineProps<{ manifest: KitManifest; kit: Kit; composition: KitComposition; url: (path: string) => string;
  spin?: boolean; interactive?: boolean; paint?: boolean; testId?: string;
  onBake?: (bake: (size: number) => Promise<Record<string, { key: string; rgba: Uint8Array }>>) => void }>(), { interactive: true, testId: 'design-preview' });
const emit = defineEmits<{ paint: [KitHit & { dragging: boolean }] }>();
const el = ref<HTMLDivElement | null>(null);
const failed = ref(!webglAvailable());
const ready = ref(false);
const shape = ref('');
const extras = ref('');
let stage: FigureStage | null = null;
let painting = false;
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
  extras.value = mine.extraIds().join(',');
  props.onBake?.((size) => mine.bakeTiles(plain(props.composition), size));
}
async function apply(c: KitComposition) {
  const f = figure;
  if (!f || !stage || !ready.value) return;
  if (await f.update(plain(c))) stage.fit();
  shape.value = shapeOf(c);
  extras.value = f.extraIds().join(',');
}
function controls() {
  stage?.setInteractive(props.interactive && !props.paint);
}
function hit(e: PointerEvent, dragging: boolean) {
  if (!props.paint || !stage || !figure) return;
  const h = figure.pick(stage.rayFrom(e));
  if (h) emit('paint', { ...h, dragging });
}
function down(e: PointerEvent) {
  painting = true;
  hit(e, false);
}
function move(e: PointerEvent) {
  if (painting) hit(e, true);
}
function up() {
  painting = false;
}
onMounted(() => {
  if (failed.value || !el.value) return;
  try {
    stage = new FigureStage(el.value, { spin: props.spin, interactive: props.interactive && !props.paint });
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
watch(() => props.paint, controls);
onBeforeUnmount(() => {
  figure?.dispose();
  figure = null;
  stage?.dispose();
  stage = null;
});
</script>

<template>
  <div :data-testid="testId" :data-ready="ready ? 'true' : 'false'" :data-shape="shape" :data-extras="extras" class="h-full w-full"
    :style="{ touchAction: interactive ? 'none' : 'auto' }" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @pointerleave="up">
    <div v-if="failed" class="flex h-full items-center justify-center text-lg text-muted">3D preview unavailable</div>
    <div v-else ref="el" class="h-full w-full" />
  </div>
</template>

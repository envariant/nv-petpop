<script setup lang="ts">
// A library composition on a FigureStage (the Design screen): geometry, shells and colours from the composition,
// tap or drag to paint when `paint` is on (orbit otherwise), and the atlas bake for gate 7 (print = screen).
import { markRaw, onBeforeUnmount, onMounted, ref, toRaw, watch } from 'vue';
import { ComposedFigure, FigureStage, webglAvailable, type Composition, type LoadedLibrary, type PaintHit } from '@petpop/scene';
const props = withDefaults(defineProps<{ lib: LoadedLibrary; composition: Composition; paint?: boolean; spin?: boolean; interactive?: boolean; testId?: string;
  onBake?: (bake: () => Uint8Array) => void }>(), { interactive: true, testId: 'design-preview' });
const emit = defineEmits<{ paint: [PaintHit] }>();
const el = ref<HTMLDivElement | null>(null);
const failed = ref(!webglAvailable());
let stage: FigureStage | null = null;
let figure: ComposedFigure | null = null;
let painting = false;
/** A plain copy of the (reactive, JSON) composition for three.js. */
const plain = (c: Composition): Composition => JSON.parse(JSON.stringify(c));

async function build(lib: LoadedLibrary) {
  if (!stage) return;
  figure = markRaw(new ComposedFigure(toRaw(lib)));
  const mine = figure;
  await mine.update(plain(props.composition));
  if (figure !== mine || !stage) return;
  stage.setObject(mine.root);
  props.onBake?.(() => mine.bake(stage!.renderer));
}
async function apply(c: Composition) {
  const f = figure;
  if (!f || !stage) return;
  if (await f.update(plain(c))) stage.fit();
}
function controls() {
  stage?.setInteractive(props.interactive && !props.paint);
}
function down(e: PointerEvent) {
  painting = true;
  hit(e, false);
}
function up() {
  painting = false;
}
function move(e: PointerEvent) {
  if (painting) hit(e, true);
}
function hit(e: PointerEvent, dragging: boolean) {
  if (!props.paint || !stage || !figure) return;
  const p = figure.pick(stage.rayFrom(e));
  if (p) emit('paint', { p, dragging });
}
onMounted(() => {
  if (failed.value || !el.value) return;
  try {
    stage = new FigureStage(el.value, { spin: props.spin, interactive: props.interactive && !props.paint });
  } catch {
    failed.value = true;
    return;
  }
  void build(props.lib);
});
watch(() => props.lib, (lib) => void build(lib));
watch(() => props.composition, (c) => void apply(c), { deep: true });
watch(() => [props.paint, props.interactive], controls);
watch(() => props.spin, (s) => stage && (stage.spin = s));
onBeforeUnmount(() => {
  figure = null;
  stage?.dispose();
  stage = null;
});
</script>

<template>
  <div :data-testid="testId" class="h-full w-full" :style="{ touchAction: paint || interactive ? 'none' : 'auto' }"
    @pointerdown="down" @pointermove="move" @pointerup="up" @pointerleave="up">
    <div v-if="failed" class="flex h-full items-center justify-center text-lg text-muted">3D preview unavailable</div>
    <div v-else ref="el" class="h-full w-full" />
  </div>
</template>

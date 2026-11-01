<script setup lang="ts">
// The Studio's live Build preview: the species base mesh with the spec's morph weights and its painted albedo
// (masks and palette, packages/scene albedo.ts), re-applied on every tap.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import * as THREE from 'three';
import { assetUrl, type PetSpec } from '@petpop/core';
import { FigureStage, loadGlb, loadMasks, morphWeights, paintAlbedo, webglAvailable, type Masks } from '@petpop/scene';
const props = withDefaults(defineProps<{ spec: PetSpec; spin?: boolean; testId?: string }>(), { spin: true, testId: 'live-preview' });
const el = ref<HTMLDivElement | null>(null);
const failed = ref(!webglAvailable());
let stage: FigureStage | null = null;
let model: THREE.Object3D | null = null;
let masks: Masks | null = null;
let species = '';
const canvas = document.createElement('canvas');
canvas.width = canvas.height = 256;
const texture = new THREE.CanvasTexture(canvas);
texture.flipY = false;
texture.colorSpace = THREE.SRGBColorSpace;
const material = new THREE.MeshStandardMaterial({ map: texture, roughness: 0.55, metalness: 0 });

function apply() {
  const spec = JSON.parse(JSON.stringify(props.spec)) as PetSpec;
  if (model) {
    const w = morphWeights(spec);
    model.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh || !mesh.morphTargetDictionary || !mesh.morphTargetInfluences) return;
      for (const [name, idx] of Object.entries(mesh.morphTargetDictionary)) mesh.morphTargetInfluences[idx] = w[name] ?? 0;
    });
  }
  if (masks) {
    const g = canvas.getContext('2d')!;
    const img = g.createImageData(masks.size, masks.size);
    paintAlbedo(spec, masks, img);
    g.putImageData(img, 0, 0);
    texture.needsUpdate = true;
  }
}

async function load(sp: string) {
  species = sp;
  try {
    const [obj, m] = await Promise.all([loadGlb(assetUrl(`assets/base/${sp}/base.glb`)), loadMasks(sp).catch(() => null)]);
    if (sp !== species || !stage) return;
    obj.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.isMesh) mesh.material = material;
    });
    model = obj;
    masks = m;
    apply();
    stage.setObject(obj);
  } catch {
    failed.value = true;
  }
}

onMounted(() => {
  if (failed.value || !el.value) return;
  try {
    stage = new FigureStage(el.value, { spin: props.spin, spinSpeed: 0.25 });
  } catch {
    failed.value = true;
    return;
  }
  void load(props.spec.species);
});
watch(() => props.spec.species, (sp) => sp !== species && void load(sp));
watch(() => props.spec, apply, { deep: true });
onBeforeUnmount(() => {
  species = '';
  stage?.dispose();
  stage = null;
  texture.dispose();
  material.dispose();
});
</script>

<template>
  <div class="h-full w-full" :data-testid="testId">
    <div v-if="failed" class="flex h-full items-center justify-center text-lg text-muted">3D preview unavailable</div>
    <div v-else ref="el" class="h-full w-full" />
  </div>
</template>

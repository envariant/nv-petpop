<script setup lang="ts">
// The rigging workbench's viewport (decision 127). Assembled: the torso, every part on its slot in the previewed pose,
// and a marker (a dot and the axis arrow) on each torso attachment. Part: the selected part alone, as authored, with
// its pivot. Drag a marker with the gizmo (move, or rotate to turn the axis); the edit is shown live and saved when
// the drag ends. Click a marker or a part to select it. Decision 130: the assembled figure shows each part stretched to
// this breed; a socket dragged on the stretched torso is saved in the torso's own (shared, unstretched) coordinates.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import * as THREE from 'three';
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js';
import { FigureStage, SLOTS, SLOT_KIND, loadGlb, placement, stretchJoint, unstretch, webglAvailable, type Slot } from '@petpop/scene';
import type { Part } from '@petpop/core';
import { useParts } from '../stores/parts';

const ps = useParts();
const el = ref<HTMLDivElement | null>(null);
const failed = ref(!webglAvailable());
let stage: FigureStage | null = null;
let tc: TransformControls | null = null;
const root = new THREE.Group();
const meshes = new Map<string, THREE.BufferGeometry>(); // part_id -> geometry
const markers = new Map<string, THREE.Group>(); // "slot:<slot>" | "part:<id>" -> marker
const clay = new THREE.MeshStandardMaterial({ color: '#d8cfc6', roughness: 0.8 });
const picked = new THREE.MeshStandardMaterial({ color: '#ffb27a', roughness: 0.6 });
const Y = new THREE.Vector3(0, 1, 0);
let fitted = false;
let dragging = false;

async function geometry(p: Part): Promise<THREE.BufferGeometry | null> {
  if (meshes.has(p.part_id)) return meshes.get(p.part_id)!;
  try {
    const obj = await loadGlb(p.mesh_url);
    let g: THREE.BufferGeometry | null = null;
    obj.traverse((o) => {
      const m = o as THREE.Mesh;
      if (!g && m.isMesh) g = (m.geometry as THREE.BufferGeometry).clone().applyMatrix4(m.matrixWorld);
    });
    if (g) {
      (g as THREE.BufferGeometry).computeVertexNormals();
      meshes.set(p.part_id, g);
    }
    return g;
  } catch {
    return null;
  }
}

function marker(key: string, colour: string): THREE.Group {
  const g = new THREE.Group();
  g.name = key;
  const dot = new THREE.Mesh(new THREE.SphereGeometry(1.6, 16, 12), new THREE.MeshBasicMaterial({ color: colour, depthTest: false }));
  dot.renderOrder = 10;
  dot.userData.pick = key;
  const arrow = new THREE.ArrowHelper(Y, new THREE.Vector3(), 12, colour, 3, 2);
  arrow.traverse((o) => {
    const m = (o as THREE.Mesh).material as THREE.Material | undefined;
    if (m) m.depthTest = false;
    o.renderOrder = 10;
  });
  g.add(dot, arrow);
  return g;
}

function place(g: THREE.Group, point: number[], axis: number[]) {
  g.position.set(point[0], point[1], point[2]);
  g.quaternion.setFromUnitVectors(Y, new THREE.Vector3(axis[0], axis[1], axis[2]).normalize());
}

const selectedKey = () => (ps.target.type === 'slot' ? `slot:${ps.target.slot}` : `part:${ps.target.partId}`);

async function rebuild() {
  if (!stage || !ps.kit) return;
  root.clear();
  markers.clear();
  const torso = ps.torso;
  if (ps.view === 'part' && ps.selectedPart) {
    const p = ps.selectedPart;
    const g = await geometry(p);
    if (g) root.add(new THREE.Mesh(g, picked));
    if (p.joint) {
      const m = marker(`part:${p.part_id}`, '#e0457b');
      place(m, p.joint.pivot, p.joint.axis);
      markers.set(m.name, m);
      root.add(m);
    }
  } else if (torso) {
    const tg = await geometry(torso);
    if (tg) {
      const tm = new THREE.Mesh(tg, clay);
      tm.scale.set(torso.stretch?.[0] ?? 1, torso.stretch?.[1] ?? 1, torso.stretch?.[2] ?? 1);
      root.add(tm);
    }
    for (const slot of SLOTS as Slot[]) {
      const att = torso.attachments?.[slot];
      const part = ps.partOf(SLOT_KIND[slot]);
      if (att && part?.joint) {
        const g = await geometry(part);
        if (g) {
          const mesh = new THREE.Mesh(g, ps.target.type === 'slot' && ps.target.slot === slot ? picked : clay);
          mesh.matrixAutoUpdate = false;
          mesh.matrix.copy(placement(part.joint, att, slot, ps.pose, part.stretch, torso.stretch));
          mesh.userData.pick = `slot:${slot}`;
          root.add(mesh);
        }
      }
      if (att) {
        const m = marker(`slot:${slot}`, slot.endsWith('right') ? '#7a5cff' : '#ff8a3d');
        const shown = stretchJoint(att, 'position', torso.stretch);
        place(m, shown.position, shown.axis);
        markers.set(m.name, m);
        root.add(m);
      }
    }
  }
  if (!fitted || ps.view === 'part') {
    stage.setObject(root);
    fitted = ps.view !== 'part';
  }
  attachGizmo();
}

function attachGizmo() {
  if (!tc) return;
  const m = markers.get(selectedKey());
  if (m) tc.attach(m);
  else tc.detach();
  tc.setMode(ps.gizmo);
}

function readMarker(m: THREE.Group) {
  const axis = Y.clone().applyQuaternion(m.quaternion).normalize();
  return { point: [m.position.x, m.position.y, m.position.z].map((x) => Math.round(x * 1000) / 1000), axis: [axis.x, axis.y, axis.z].map((x) => Math.round(x * 1e5) / 1e5) };
}

function onDrag() {
  const m = tc?.object as THREE.Group | undefined;
  if (!m) return;
  const { point, axis } = readMarker(m);
  if (m.name.startsWith('slot:')) {
    const slot = m.name.slice(5) as Slot;
    const old = ps.torso?.attachments?.[slot];
    const own = unstretch(point, axis, ps.torso?.stretch);
    ps.setAttachment(slot, { position: own.point, axis: own.axis, twist: old?.twist ?? 0 });
  } else {
    const id = m.name.slice(5);
    const old = ps.kit?.parts.find((p) => p.part_id === id)?.joint;
    ps.setJoint(id, { pivot: point, axis, twist: old?.twist ?? 0 });
  }
}

function pick(e: PointerEvent) {
  if (!stage || dragging) return;
  const hits = stage.rayFrom(e).intersectObjects(root.children, true);
  const key = hits.map((h) => h.object.userData.pick ?? h.object.parent?.userData?.pick).find(Boolean) as string | undefined;
  if (key?.startsWith('slot:')) ps.select({ type: 'slot', slot: key.slice(5) as Slot });
}

onMounted(() => {
  if (failed.value || !el.value) return;
  try {
    stage = new FigureStage(el.value, { interactive: true, spin: false });
  } catch {
    failed.value = true;
    return;
  }
  tc = new TransformControls(stage.camera, stage.renderer.domElement);
  tc.setSize(0.8);
  tc.addEventListener('dragging-changed', (ev) => {
    dragging = Boolean((ev as unknown as { value: boolean }).value);
    if (stage?.controls) stage.controls.enabled = !dragging;
    if (!dragging) void save();
  });
  tc.addEventListener('objectChange', onDrag);
  stage.scene.add(tc.getHelper());
  stage.renderer.domElement.addEventListener('pointerup', pick);
  void rebuild();
});

async function save() {
  const m = tc?.object as THREE.Group | undefined;
  if (!m) return;
  if (m.name.startsWith('slot:')) await ps.saveTorso();
  else await ps.saveJoint(m.name.slice(5));
}

// Rebuild on anything the figure depends on; while dragging, only move what the drag moves.
watch(() => [ps.kit, ps.view, ps.target, ps.preview, ps.poseId], () => !dragging && void rebuild(), { deep: true });
watch(() => [ps.torso?.attachments, ps.kit?.parts.map((p) => p.joint)], () => dragging && void rebuild(), { deep: true });
watch(() => ps.gizmo, () => tc?.setMode(ps.gizmo));
onBeforeUnmount(() => {
  stage?.renderer.domElement.removeEventListener('pointerup', pick);
  tc?.dispose();
  stage?.dispose();
  stage = null;
  meshes.forEach((g) => g.dispose());
});
</script>

<template>
  <div class="relative h-full w-full" data-testid="rig-view">
    <div v-if="failed" class="flex h-full items-center justify-center text-lg text-muted">3D view unavailable</div>
    <div v-else ref="el" class="h-full w-full" />
  </div>
</template>

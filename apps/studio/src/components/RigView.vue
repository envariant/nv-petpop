<script setup lang="ts">
// The rigging workbench's viewport (decision 127). Assembled: the torso, every part on its slot in the previewed pose,
// and a marker (a dot and the axis arrow) on each torso attachment. Part: the selected part alone, as authored, with
// its pivot. Drag a marker with the gizmo (move, or rotate to turn the axis); the edit is shown live and saved when
// the drag ends. Click a marker or a part to select it. Decision 130: the assembled figure shows each part stretched to
// this breed; a socket dragged on the stretched torso is saved in the torso's own (shared, unstretched) coordinates.
// Decision 131: the torso shows the previewed preset (its stretch and socket offsets); where sockets are this breed's
// offsets (a shared torso, or a preset other than the default) a drag sets the offset instead.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import * as THREE from 'three';
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js';
import { FigureStage, SLOTS, SLOT_KIND, frame, loadGlb, offsetBetween, offsetSocket, placement, stretchJoint, twistFor, unstretch, webglAvailable, type Slot } from '@petpop/scene';
import type { Part } from '@petpop/core';
import { useParts } from '../stores/parts';

const ps = useParts();
const el = ref<HTMLDivElement | null>(null);
const failed = ref(!webglAvailable());
let stage: FigureStage | null = null;
let tc: TransformControls | null = null;
const root = new THREE.Group();
// a part as its GLB has it: every mesh, with its own materials (textures); shared by every instance on screen
type Model = { geometry: THREE.BufferGeometry; material: THREE.Material | THREE.Material[] }[];
const models = new Map<string, Promise<Model | null>>(); // part_id + sha -> model
const tints = new WeakMap<THREE.Material, THREE.Material>();
const markers = new Map<string, THREE.Group>(); // "slot:<slot>" | "part:<id>" -> marker
const clay = new THREE.MeshStandardMaterial({ color: '#d8cfc6', roughness: 0.8 });
const picked = new THREE.MeshStandardMaterial({ color: '#ffb27a', roughness: 0.6 });
const Y = new THREE.Vector3(0, 1, 0);
let fitted = false;
let dragging = false;

function model(p: Part): Promise<Model | null> {
  const key = `${p.part_id}:${p.sha256}`;
  if (!models.has(key)) {
    models.set(key, loadGlb(p.mesh_url).then((obj) => {
      obj.updateMatrixWorld(true);
      const out: Model = [];
      obj.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh) return;
        const g = (m.geometry as THREE.BufferGeometry).clone().applyMatrix4(m.matrixWorld);
        if (!g.getAttribute('normal')) g.computeVertexNormals();
        out.push({ geometry: g, material: m.material });
      });
      return out.length ? out : null;
    }).catch(() => null));
  }
  return models.get(key)!;
}

/** The selected part keeps its texture, lit with a warm glow. */
function tint(m: THREE.Material): THREE.Material {
  let t = tints.get(m);
  if (!t) {
    t = m.clone();
    if ((t as THREE.MeshStandardMaterial).isMeshStandardMaterial) {
      (t as THREE.MeshStandardMaterial).emissive = new THREE.Color('#ff7a2a');
      (t as THREE.MeshStandardMaterial).emissiveIntensity = 0.35;
    } else t = picked;
    tints.set(m, t);
  }
  return t;
}

/** One instance of a part on screen: its own materials, or clay, the selected one glowing. */
function instance(md: Model, selected: boolean, pick?: string): THREE.Group {
  const g = new THREE.Group();
  for (const { geometry, material } of md) {
    const own = Array.isArray(material) ? material : [material];
    const mats = ps.clay ? own.map(() => (selected ? picked : clay)) : own.map((x) => (selected ? tint(x) : x));
    const mesh = new THREE.Mesh(geometry, Array.isArray(material) ? mats : mats[0]);
    if (pick) mesh.userData.pick = pick;
    g.add(mesh);
  }
  if (pick) g.userData.pick = pick;
  return g;
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
    const md = await model(p);
    if (md) root.add(instance(md, false));
    if (p.joint) {
      const m = marker(`part:${p.part_id}`, '#e0457b');
      place(m, p.joint.pivot, p.joint.axis);
      markers.set(m.name, m);
      root.add(m);
    }
  } else if (torso) {
    const tmd = await model(torso);
    if (tmd) {
      const tm = instance(tmd, false);
      const ts = ps.torsoStretch;
      tm.scale.set(ts?.[0] ?? 1, ts?.[1] ?? 1, ts?.[2] ?? 1);
      root.add(tm);
    }
    for (const slot of SLOTS as Slot[]) {
      const att = torso.attachments?.[slot];
      const part = ps.partOf(SLOT_KIND[slot]);
      if (att && part?.joint) {
        const md = await model(part);
        if (md) {
          const inst = instance(md, ps.target.type === 'slot' && ps.target.slot === slot, `slot:${slot}`);
          inst.matrixAutoUpdate = false;
          inst.matrix.copy(placement(part.joint, att, slot, ps.pose, part.stretch, ps.torsoStretch, ps.preset?.sockets?.[slot]));
          root.add(inst);
        }
      }
      if (att) {
        const m = marker(`slot:${slot}`, slot.endsWith('right') ? '#7a5cff' : '#ff8a3d');
        const shown = offsetSocket(stretchJoint(att, 'position', ps.torsoStretch), ps.preset?.sockets?.[slot]);
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

const r3 = (x: number) => Math.round(x * 1000) / 1000;
const frameOf = (axis: number[], twist: number) => frame(axis, twist);

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
    if (old && ps.offsetMode) {
      // this breed's offset: the socket as stretched, to where it was dragged; the axis turned the shortest way, so
      // the twist follows it
      const base = stretchJoint(old, 'position', ps.torsoStretch);
      const now = offsetSocket(base, ps.preset?.sockets?.[slot]);
      const turn = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(...(now.axis as [number, number, number])).normalize(),
        new THREE.Vector3(...(axis as [number, number, number])).normalize());
      const f = new THREE.Vector3(), ref = new THREE.Vector3(), c = new THREE.Vector3();
      const fr = new THREE.Matrix4();
      fr.copy(frameOf(now.axis, now.twist ?? 0));
      fr.extractBasis(f, ref, c);
      ref.applyQuaternion(turn);
      const moved = { position: point, axis, twist: twistFor(axis, [ref.x, ref.y, ref.z]) };
      const off = offsetBetween(base, moved);
      ps.setOffset(slot, { translate: off.translate.map(r3), rotate: off.rotate.map(r3) });
      return;
    }
    const own = unstretch(point, axis, ps.torsoStretch);
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
  if (m.name.startsWith('slot:') && ps.offsetMode) await ps.saveOffsets();
  else if (m.name.startsWith('slot:')) await ps.saveTorso();
  else await ps.saveJoint(m.name.slice(5));
}

// Rebuild on anything the figure depends on; while dragging, only move what the drag moves.
watch(() => [ps.kit, ps.view, ps.target, ps.preview, ps.poseId, ps.presetId, ps.clay], () => !dragging && void rebuild(), { deep: true });
watch(() => [ps.torso?.attachments, ps.kit?.parts.map((p) => p.joint), ps.preset?.sockets], () => dragging && void rebuild(), { deep: true });
watch(() => ps.gizmo, () => tc?.setMode(ps.gizmo));
onBeforeUnmount(() => {
  stage?.renderer.domElement.removeEventListener('pointerup', pick);
  // TransformControls.dispose() in three r169 calls this.traverse, which the controls (no longer an Object3D) do not
  // have: it threw, and the screen never left the workbench. Detach, disconnect and free the gizmo's helper instead.
  if (tc) {
    tc.detach();
    tc.disconnect();
    const helper = tc.getHelper();
    stage?.scene.remove(helper);
    helper.traverse((o) => {
      const m = o as THREE.Mesh;
      m.geometry?.dispose();
      (Array.isArray(m.material) ? m.material : m.material ? [m.material] : []).forEach((x) => x.dispose());
    });
    tc = null;
  }
  stage?.dispose();
  stage = null;
  models.forEach((p) => void p.then((md) => md?.forEach(({ geometry }) => geometry.dispose())));
});
</script>

<template>
  <div class="relative h-full w-full" data-testid="rig-view">
    <div v-if="failed" class="flex h-full items-center justify-center text-lg text-muted">3D view unavailable</div>
    <div v-else ref="el" class="h-full w-full" />
  </div>
</template>

// Painting a figure of part kits (decisions 135, 139): the twin of petpop_library/kit_figure.py's sample_mask,
// paint_layers, paint_tile, stamp_tile, mirror_stamp and _landmarks. The same float64 sums in the same order, the
// same 8-bit rounding and the atlas rasteriser for stamps, so a part's tile on screen is its tile in the print, byte
// for byte (gate 7 compares them).
import type * as THREE from 'three';
import { buildTexelMap, type BaseData } from './atlas';
import { maskLayers, type KitTexture } from './kit';
import { StampLayer, type Stamp } from './stamps';

/** A mask image: one byte per pixel (its red channel), w x h, row 0 at the top. */
export interface MaskImage { data: Uint8Array; w: number; h: number }

export type KitSlot = 'torso' | 'head' | 'front_left' | 'front_right' | 'hind_left' | 'hind_right' | 'tail';
/** A spot or brush dab on one part, in that part's own frame (mm, before it is stretched and placed). */
export interface KitStamp extends Stamp { slot: KitSlot }

const q8 = (x: number) => Math.min(255, Math.max(0, Math.floor(x + 0.5)));
const rgb = (hex: string): [number, number, number] => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number];

/** size x size values in [0, 1]: the mask sampled bilinearly at each texel centre, edges clamped (sample_mask). */
export function sampleMask(m: MaskImage, size: number): Float64Array {
  const axis = (n: number) => {
    const i0 = new Int32Array(size), i1 = new Int32Array(size), f = new Float64Array(size);
    for (let k = 0; k < size; k++) {
      const s = Math.min(Math.max(((k + 0.5) / size) * n - 0.5, 0), n - 1);
      i0[k] = Math.floor(s);
      i1[k] = Math.min(i0[k] + 1, n - 1);
      f[k] = s - i0[k];
    }
    return { i0, i1, f };
  };
  const X = axis(m.w), Y = axis(m.h);
  const out = new Float64Array(size * size);
  for (let y = 0; y < size; y++) {
    const r0 = Y.i0[y] * m.w, r1 = Y.i1[y] * m.w, fy = Y.f[y];
    for (let x = 0; x < size; x++) {
      const x0 = X.i0[x], x1 = X.i1[x], fx = X.f[x];
      const top = m.data[r0 + x0] * (1 - fx) + m.data[r0 + x1] * fx;
      const bot = m.data[r1 + x0] * (1 - fx) + m.data[r1 + x1] * fx;
      out[y * size + x] = (top * (1 - fy) + bot * fy) / 255;
    }
  }
  return out;
}

/** size x size x 3 float64: colour A, then each mask layer over it (paint_layers). */
export function paintLayers(size: number, t: KitTexture, masks: Map<string, MaskImage>, eye?: string, nose?: string): Float64Array {
  const n = size * size;
  const img = new Float64Array(n * 3);
  const a = rgb(t.base.hex);
  for (let i = 0; i < n; i++) img.set(a, i * 3);
  for (const [name, colour] of maskLayers(t, eye, nose)) {
    const m = masks.get(name);
    if (!m) continue;
    const w = sampleMask(m, size);
    for (let i = 0; i < n; i++) {
      for (let k = 0; k < 3; k++) img[i * 3 + k] = img[i * 3 + k] * (1 - w[i]) + colour[k] * w[i];
    }
  }
  return img;
}

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));

/** A part's mesh as the atlas rasteriser reads one: its vertices, faces and clamped corner UVs (part_mesh), v as the
 *  export reads it (1 - glTF's v: texel row 0 is glTF's v = 0, the tile's top row). Every mesh of the part, in order;
 *  a part without UVs has them all at (0.5, 0.5). */
export function partBase(geometries: THREE.BufferGeometry[]): BaseData {
  let n = 0, t = 0;
  for (const g of geometries) {
    n += g.getAttribute('position').count;
    t += (g.index ? g.index.count : g.getAttribute('position').count) / 3;
  }
  const co = new Float32Array(n * 3);
  const tri = new Uint32Array(t * 3);
  const uv = new Float32Array(t * 6);
  let vo = 0, to = 0;
  for (const g of geometries) {
    const pos = g.getAttribute('position');
    const tex = g.getAttribute('uv');
    for (let i = 0; i < pos.count; i++) co.set([pos.getX(i), pos.getY(i), pos.getZ(i)], (vo + i) * 3);
    const count = g.index ? g.index.count : pos.count;
    for (let k = 0; k < count; k++) {
      const v = g.index ? g.index.getX(k) : k;
      tri[to * 3 + k] = vo + v;
      uv[to * 6 + k * 2] = tex ? clamp01(tex.getX(v)) : 0.5;
      uv[to * 6 + k * 2 + 1] = tex ? clamp01(Math.fround(1 - tex.getY(v))) : 0.5; // trimesh's v (it flips glTF's, in float32)
    }
    vo += pos.count;
    to += count / 3;
  }
  return { n, t, co, tri, uv, shell: new Uint8Array(n) };
}

/** size x size RGBA: a slot's stamps on its part's texels, grown 2 texels into the UV padding (stamp_tile). */
export function stampTile(part: BaseData, size: number, stamps: Stamp[]): Uint8Array {
  const layer = new StampLayer(part, buildTexelMap(part, size));
  for (const s of stamps) layer.add(s);
  return layer.toRGBA(undefined, true);
}

/** One part's albedo, size x size RGBA, image rows top down (paint_tile): the layers, then its slot's stamps. */
export function paintKitTile(size: number, t: KitTexture, masks: Map<string, MaskImage>, eye?: string, nose?: string,
  part?: BaseData | null, stamps?: Stamp[]): Uint8Array<ArrayBuffer> {
  const img = paintLayers(size, t, masks, eye, nose);
  const n = size * size;
  if (stamps?.length && part) {
    const layer = stampTile(part, size, stamps);
    for (let i = 0; i < n; i++) {
      const sa = layer[i * 4 + 3] / 255;
      if (!sa) continue;
      for (let k = 0; k < 3; k++) img[i * 3 + k] = img[i * 3 + k] * (1 - sa) + layer[i * 4 + k] * sa;
    }
  }
  const out = new Uint8Array(new ArrayBuffer(n * 4));
  for (let i = 0; i < n; i++) {
    for (let k = 0; k < 3; k++) out[i * 4 + k] = q8(img[i * 3 + k]);
    out[i * 4 + 3] = 255;
  }
  return out;
}

const OTHER: Partial<Record<KitSlot, KitSlot>> = { front_left: 'front_right', front_right: 'front_left', hind_left: 'hind_right', hind_right: 'hind_left' };

/** A stamp's mirror image across the pet's centre line (mirror_stamp): a leg's on the other leg at the same place
 *  (the right legs are the left ones mirrored), a centre part's at -x. */
export function mirrorStamp(s: KitStamp): KitStamp {
  const other = OTHER[s.slot];
  return other ? { ...s, slot: other } : { ...s, p: [-s.p[0], s.p[1], s.p[2]] };
}

export const LANDMARK_SLOTS: KitSlot[] = ['torso', 'head', 'front_left', 'front_right', 'hind_left', 'hind_right', 'tail'];

/** The segmentation schema's landmarks, near enough, on a placed figure of parts (kit_figure._landmarks): co is the
 *  glTF frame (+Y up, +Z front, +X the pet's left), slotOf the LANDMARK_SLOTS index of each vertex. */
export function kitLandmarks(co: Float64Array, slotOf: Uint8Array): Record<string, number> {
  const n = slotOf.length;
  const pick = (slot: KitSlot, score: (x: number, y: number, z: number) => number, side = 0): number => {
    const s = LANDMARK_SLOTS.indexOf(slot);
    let idx: number[] = [];
    for (let v = 0; v < n; v++) if (slotOf[v] === s) idx.push(v);
    if (side) {
      const sided = idx.filter((v) => co[v * 3] * side > 0);
      if (sided.length) idx = sided;
    }
    if (!idx.length) idx = Array.from({ length: n }, (_, v) => v);
    let best = idx[0], bestScore = -Infinity;
    for (const v of idx) {
      const sc = score(co[v * 3], co[v * 3 + 1], co[v * 3 + 2]);
      if (sc > bestScore) { bestScore = sc; best = v; }
    }
    return best;
  };
  const head = (f: (x: number, y: number, z: number) => number, side = 0) => pick('head', f, side);
  let base = 0, baseScore = Infinity;
  for (let v = 0; v < n; v++) {
    const sc = co[v * 3 + 1] + 0.05 * Math.abs(co[v * 3]) + 0.05 * Math.abs(co[v * 3 + 2]);
    if (sc < baseScore) { baseScore = sc; base = v; }
  }
  return {
    nose_tip: head((_x, _y, z) => z), chin: head((_x, y, z) => -y + 0.5 * z),
    eye_L: head((_x, y, z) => z + 0.6 * y, 1), eye_R: head((_x, y, z) => z + 0.6 * y, -1),
    ear_tip_L: head((_x, y) => y, 1), ear_tip_R: head((_x, y) => y, -1),
    ear_base_L: head((_x, y, z) => y - 0.5 * z, 1), ear_base_R: head((_x, y, z) => y - 0.5 * z, -1),
    back_of_head: head((_x, _y, z) => -z), neck_front: head((_x, y, z) => -y - 0.2 * z),
    tail_tip: pick('tail', (_x, y, z) => -z + 0.3 * y),
    paw_FL: pick('front_left', (_x, y) => -y), paw_FR: pick('front_right', (_x, y) => -y),
    base_centre: base,
  };
}

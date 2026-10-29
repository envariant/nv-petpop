// Library mode in the viewer (BRIEF Section 16): a release's base mesh, region and family deltas, shell parts and
// pattern masks, composed exactly as the export composes them (petpop_library.deltas / paint / accessories).
import * as THREE from 'three';
import type { BaseData } from './atlas';

export type Region = 'ears' | 'tail' | 'muzzle' | 'head' | 'legs';
export const REGIONS: Region[] = ['ears', 'tail', 'muzzle', 'head', 'legs'];

export interface FamilyItem { id: string; name: string; delta: string; default_parts: Record<string, string>; breeds: string[]; tags: string[]; version: number; thumbnail: string }
export interface DeltaItem { id: string; name: string; region: Region; delta: string; tags: string[]; version: number; thumbnail: string }
export interface ShellItem { id: string; name: string; socket: 'neck' | 'head' | 'face'; kind: string; mesh: string; default_colour: string; tags?: string[]; version: number; thumbnail: string }
export interface PatternItem { id: string; name: string; channel: number; default_colour: string; coverage: { min: number; max: number; default: number }; tags?: string[]; version: number; thumbnail: string }
export interface ReleaseManifest {
  release_version: string;
  species: 'dog' | 'cat';
  number: number;
  base_mesh_version: string;
  base_topology: string;
  atlas: { size: number; mask_files: string[]; channels: Record<string, number> };
  mesh: string;
  families: FamilyItem[];
  region_deltas: DeltaItem[];
  shell_parts: ShellItem[];
  pattern_layers: PatternItem[];
}
export interface MeshInfo { base_mesh_version: string; topology: string; vertices: number; triangles: number; bin: string; landmarks: Record<string, number> }

/** Composition (data/schema/composition.schema.json): the order record and the export's only input. */
export interface Composition {
  composition_version: '1.0';
  species: 'dog' | 'cat';
  release_version: string;
  base_mesh_version: string;
  pet_name?: string;
  breed_id?: string;
  family_id: string;
  parts: Partial<Record<Region, string>>;
  shells: { part_id: string; colour: string }[];
  base_colour: string;
  layers: { pattern_id: string; coverage: number; colour: string }[];
  stamps: { p: [number, number, number]; r: number; colour: string }[];
  eye_colour: string;
  nose_colour: string;
}

/** IEEE 754 half -> float (deltas are little-endian float16, like numpy '<f2'). */
export function decodeF16(buf: ArrayBuffer): Float32Array {
  const h = new Uint16Array(buf);
  const out = new Float32Array(h.length);
  for (let i = 0; i < h.length; i++) {
    const x = h[i];
    const s = x & 0x8000 ? -1 : 1;
    const e = (x >> 10) & 0x1f;
    const f = x & 0x3ff;
    out[i] = e === 0 ? s * 2 ** -14 * (f / 1024) : e === 31 ? (f ? NaN : s * Infinity) : s * 2 ** (e - 15) * (1 + f / 1024);
  }
  return out;
}

/** base + family + region deltas (float64, the export's order). */
export function composeCoords(base: BaseData, deltas: (Float32Array | null | undefined)[]): Float64Array {
  const co = new Float64Array(base.n * 3);
  for (let i = 0; i < co.length; i++) co[i] = base.co[i];
  for (const d of deltas) if (d) for (let i = 0; i < co.length; i++) co[i] += d[i];
  return co;
}

/** Indexed geometry split at UV seams (one vertex per (vertex, uv) pair); triangle order = base triangle order. */
export interface SplitGeometry { geometry: THREE.BufferGeometry; vertexOf: Uint32Array }

export function buildGeometry(base: BaseData): SplitGeometry {
  const key = new Map<string, number>();
  const vertexOf: number[] = [];
  const uvs: number[] = [];
  const index = new Uint32Array(base.t * 3);
  for (let t = 0; t < base.t; t++) {
    for (let c = 0; c < 3; c++) {
      const v = base.tri[t * 3 + c];
      const u = base.uv[t * 6 + c * 2], w = base.uv[t * 6 + c * 2 + 1];
      const k = `${v}:${u}:${w}`;
      let id = key.get(k);
      if (id === undefined) {
        id = vertexOf.length;
        key.set(k, id);
        vertexOf.push(v);
        uvs.push(u, w);
      }
      index[t * 3 + c] = id;
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(vertexOf.length * 3), 3));
  geometry.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(vertexOf.length * 3), 3));
  geometry.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(uvs), 2));
  geometry.setIndex(new THREE.BufferAttribute(index, 1));
  return { geometry, vertexOf: Uint32Array.from(vertexOf) };
}

/** Write composed positions into the split geometry, with smooth normals shared across seams. */
export function updateGeometry(base: BaseData, split: SplitGeometry, co: Float64Array): void {
  const normals = new Float64Array(base.n * 3);
  for (let t = 0; t < base.t; t++) {
    const a = base.tri[t * 3], b = base.tri[t * 3 + 1], c = base.tri[t * 3 + 2];
    const ux = co[b * 3] - co[a * 3], uy = co[b * 3 + 1] - co[a * 3 + 1], uz = co[b * 3 + 2] - co[a * 3 + 2];
    const vx = co[c * 3] - co[a * 3], vy = co[c * 3 + 1] - co[a * 3 + 1], vz = co[c * 3 + 2] - co[a * 3 + 2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    for (const v of [a, b, c]) {
      normals[v * 3] += nx;
      normals[v * 3 + 1] += ny;
      normals[v * 3 + 2] += nz;
    }
  }
  const pos = split.geometry.getAttribute('position') as THREE.BufferAttribute;
  const nor = split.geometry.getAttribute('normal') as THREE.BufferAttribute;
  for (let i = 0; i < split.vertexOf.length; i++) {
    const v = split.vertexOf[i];
    pos.setXYZ(i, co[v * 3], co[v * 3 + 1], co[v * 3 + 2]);
    const l = Math.hypot(normals[v * 3], normals[v * 3 + 1], normals[v * 3 + 2]) || 1;
    nor.setXYZ(i, normals[v * 3] / l, normals[v * 3 + 1] / l, normals[v * 3 + 2] / l);
  }
  pos.needsUpdate = true;
  nor.needsUpdate = true;
  split.geometry.computeBoundingBox();
  split.geometry.computeBoundingSphere();
}

/** Socket frames from the composed mesh (petpop_library/accessories.py: accessory_anchors). */
export function socketFrames(co: Float64Array, landmarks: Record<string, number>, shell: Uint8Array): Record<string, { loc: [number, number, number]; scale: number }> {
  const p = (name: string): [number, number, number] => {
    const v = landmarks[name];
    return [co[v * 3], co[v * 3 + 1], co[v * 3 + 2]];
  };
  const neck = p('neck_front');
  const band: [number, number][] = [];
  let headTop = -Infinity;
  for (let v = 0; v < shell.length; v++) {
    if (shell[v] !== 0) continue;
    const z = co[v * 3 + 2];
    headTop = Math.max(headTop, z);
    if (Math.abs(z - neck[2]) < 2) band.push([co[v * 3], co[v * 3 + 1]]);
  }
  const centreY = band.length ? band.reduce((s, b) => s + b[1], 0) / band.length : neck[1] + 8;
  const radii = band.map(([x, y]) => Math.hypot(x, y - centreY)).sort((a, b) => a - b);
  const radius = radii.length ? percentile(radii, 60) : 10;
  const bl = p('ear_base_L'), br = p('ear_base_R'), el = p('eye_L'), er = p('eye_R');
  const earMidY = (bl[1] + br[1]) / 2;
  const eyesY = (el[1] + er[1]) / 2, eyesZ = (el[2] + er[2]) / 2;
  const eyeSpan = Math.abs(el[0] - er[0]);
  return {
    collar: { loc: [0, centreY, neck[2]], scale: radius * 0.97 },
    bandana: { loc: [0, neck[1] + 1.5, neck[2] - 1], scale: radius },
    bow: { loc: [0, earMidY - 2, headTop - 1.5], scale: 8 },
    hat: { loc: [0, earMidY, headTop - 3], scale: eyeSpan * 0.9 },
    glasses: { loc: [0, eyesY - 2.5, eyesZ], scale: eyeSpan / 2 },
  };
}

function percentile(sorted: number[], q: number): number {
  // numpy's default (linear interpolation between closest ranks)
  const pos = ((sorted.length - 1) * q) / 100;
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

/** Map a hit on the composed mesh (triangle, point) back to base-mesh space, where stamps live. */
export function hitToBase(base: BaseData, co: Float64Array, tri: number, point: THREE.Vector3): [number, number, number] {
  const ids = [base.tri[tri * 3], base.tri[tri * 3 + 1], base.tri[tri * 3 + 2]];
  const P = ids.map((v) => new THREE.Vector3(co[v * 3], co[v * 3 + 1], co[v * 3 + 2]));
  const bary = new THREE.Vector3();
  THREE.Triangle.getBarycoord(point, P[0], P[1], P[2], bary);
  const out: [number, number, number] = [0, 0, 0];
  const w = [bary.x, bary.y, bary.z];
  for (let k = 0; k < 3; k++) for (let c = 0; c < 3; c++) out[c] += w[k] * base.co[ids[k] * 3 + c];
  return [round3(out[0]), round3(out[1]), round3(out[2])];
}

const round3 = (x: number) => Math.round(x * 1000) / 1000;

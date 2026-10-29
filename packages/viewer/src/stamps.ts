// Seam-correct stamps in the UV atlas: a port of stamp_layer() in packages/library/python/petpop_library/paint.py.
// A stamp (p, r, colour) paints every texel whose 3D base-mesh position is within r of p (soft over FEATHER_MM),
// triangle by triangle, so a stamp that crosses a UV seam lands on both islands. Same float64 maths and the same
// 8-bit quantisation as the export, so the kiosk screen and the print agree texel for texel.
import { texelsOf, type BaseData, type TexelMap } from './atlas';

export const FEATHER_MM = 0.5;

export interface Stamp {
  p: [number, number, number];
  r: number;
  colour: string;
}

export function hexRgb(h: string): [number, number, number] {
  const s = h.replace('#', '');
  return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
}

const q8 = (x: number) => Math.min(255, Math.max(0, Math.floor(x + 0.5)));

export interface TriangleSpheres {
  centres: Float64Array;
  radii: Float64Array;
}

export function triangleSpheres(base: BaseData): TriangleSpheres {
  const centres = new Float64Array(base.t * 3);
  const radii = new Float64Array(base.t);
  for (let t = 0; t < base.t; t++) {
    const v = [base.tri[t * 3], base.tri[t * 3 + 1], base.tri[t * 3 + 2]];
    for (let k = 0; k < 3; k++) centres[t * 3 + k] = (base.co[v[0] * 3 + k] + base.co[v[1] * 3 + k] + base.co[v[2] * 3 + k]) / 3;
    let r = 0;
    for (const vi of v) {
      const dx = base.co[vi * 3] - centres[t * 3], dy = base.co[vi * 3 + 1] - centres[t * 3 + 1], dz = base.co[vi * 3 + 2] - centres[t * 3 + 2];
      r = Math.max(r, Math.sqrt(dx * dx + dy * dy + dz * dz));
    }
    radii[t] = r;
  }
  return { centres, radii };
}

/** Accumulating stamp layer: float64 straight colour + coverage, quantised on read (like the export). */
export class StampLayer {
  readonly rgb: Float64Array;
  readonly alpha: Float64Array;
  constructor(
    readonly base: BaseData,
    readonly tm: TexelMap,
    readonly spheres: TriangleSpheres = triangleSpheres(base),
  ) {
    this.rgb = new Float64Array(tm.size * tm.size * 3);
    this.alpha = new Float64Array(tm.size * tm.size);
  }

  clear(): void {
    this.rgb.fill(0);
    this.alpha.fill(0);
  }

  /** Paint one stamp; returns the texel indices it touched (for incremental texture updates). */
  add(s: Stamp): number[] {
    const { base, tm, spheres } = this;
    const [px, py, pz] = s.p;
    const r = s.r;
    const col = hexRgb(s.colour);
    const touched: number[] = [];
    for (let t = 0; t < base.t; t++) {
      const dx = spheres.centres[t * 3] - px, dy = spheres.centres[t * 3 + 1] - py, dz = spheres.centres[t * 3 + 2] - pz;
      if (Math.sqrt(dx * dx + dy * dy + dz * dz) > r + FEATHER_MM + spheres.radii[t]) continue;
      const tex = texelsOf(tm, t);
      if (!tex.length) continue;
      const v0 = base.tri[t * 3], v1 = base.tri[t * 3 + 1], v2 = base.tri[t * 3 + 2];
      for (let k = 0; k < tex.length; k++) {
        const i = tex[k];
        const w0 = tm.bary[i * 3], w1 = tm.bary[i * 3 + 1], w2 = tm.bary[i * 3 + 2];
        const x = w0 * base.co[v0 * 3] + w1 * base.co[v1 * 3] + w2 * base.co[v2 * 3];
        const y = w0 * base.co[v0 * 3 + 1] + w1 * base.co[v1 * 3 + 1] + w2 * base.co[v2 * 3 + 1];
        const z = w0 * base.co[v0 * 3 + 2] + w1 * base.co[v1 * 3 + 2] + w2 * base.co[v2 * 3 + 2];
        const ex = x - px, ey = y - py, ez = z - pz;
        const d = Math.sqrt(ex * ex + ey * ey + ez * ez);
        const a = Math.min(1, Math.max(0, (r - d) / FEATHER_MM + 0.5));
        if (!(a > 0)) continue;
        const a0 = this.alpha[i];
        const na = a + a0 * (1 - a);
        for (let c = 0; c < 3; c++) this.rgb[i * 3 + c] = (col[c] * a + this.rgb[i * 3 + c] * (a0 * (1 - a))) / na;
        this.alpha[i] = na;
        touched.push(i);
      }
    }
    return touched;
  }

  /** RGBA8 as the export sees it. `padded` also copies edge texels into the UV padding (as the export's albedo
   *  does), so the GPU's bilinear sampling never blends in an empty texel at a seam. */
  toRGBA(out: Uint8Array = new Uint8Array(this.tm.size * this.tm.size * 4), padded = false): Uint8Array {
    const n = this.tm.size * this.tm.size;
    for (let i = 0; i < n; i++) {
      out[i * 4] = q8(this.rgb[i * 3]);
      out[i * 4 + 1] = q8(this.rgb[i * 3 + 1]);
      out[i * 4 + 2] = q8(this.rgb[i * 3 + 2]);
      out[i * 4 + 3] = q8(this.alpha[i] * 255);
    }
    if (padded) {
      const pad = (this.padding ??= paddingPairs(this.tm, 2));
      for (let k = 0; k < pad.length; k += 2) out.copyWithin(pad[k] * 4, pad[k + 1] * 4, pad[k + 1] * 4 + 4);
    }
    return out;
  }

  private padding?: Int32Array;
}

/** (padding texel, source texel) pairs: covered texels grown `px` texels outwards, 4-connected, in order, like
 *  petpop_library.atlas.dilate_into_padding. Applying them in order resolves chains. */
export function paddingPairs(tm: TexelMap, px: number): Int32Array {
  const S = tm.size;
  const have = new Uint8Array(S * S);
  for (let i = 0; i < have.length; i++) have[i] = tm.tri[i] >= 0 ? 1 : 0;
  const pairs: number[] = [];
  for (let step = 0; step < px; step++) {
    const add: number[] = [];
    for (let y = 0; y < S; y++) {
      for (let x = 0; x < S; x++) {
        const i = y * S + x;
        if (have[i]) continue;
        const src = x > 0 && have[i - 1] ? i - 1 : x < S - 1 && have[i + 1] ? i + 1 : y > 0 && have[i - S] ? i - S : y < S - 1 && have[i + S] ? i + S : -1;
        if (src >= 0) add.push(i, src);
      }
    }
    for (let k = 0; k < add.length; k += 2) have[add[k]] = 1;
    pairs.push(...add);
  }
  return Int32Array.from(pairs);
}

export function stampLayer(base: BaseData, tm: TexelMap, stamps: Stamp[]): Uint8Array {
  const layer = new StampLayer(base, tm);
  for (const s of stamps) layer.add(s);
  return layer.toRGBA();
}

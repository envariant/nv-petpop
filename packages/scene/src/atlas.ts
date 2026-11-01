// The species UV atlas as a texel map: which triangle owns each texel, and its barycentrics. A line-for-line port
// of packages/library/python/petpop_library/atlas.py (same texel-centre convention, triangle order and formula,
// all in float64), so stamps painted on the kiosk land on exactly the texels the export paints.
// Convention: texel (x, y), row 0 at the top, has its centre at u = (x + 0.5) / S, v = 1 - (y + 0.5) / S.

export const EPS = -1e-9;

export interface BaseData {
  n: number;
  t: number;
  co: Float32Array; // n * 3, mm, Z up
  tri: Uint32Array; // t * 3
  uv: Float32Array; // t * 6 corner UVs
  shell: Uint8Array; // n
}

export interface TexelMap {
  size: number;
  tri: Int32Array; // S * S, -1 where no triangle covers the texel centre
  bary: Float64Array; // S * S * 3
  order: Int32Array; // covered texel indices sorted by triangle
  starts: Int32Array; // t + 1 offsets into order
}

/** Parse a mesh binary, PPB1 (see petpop_library/basebin.py). */
export function parseBaseBin(buf: ArrayBuffer): BaseData {
  const magic = new TextDecoder().decode(new Uint8Array(buf, 0, 4));
  if (magic !== 'PPB1') throw new Error('not a PPB1 mesh binary');
  const dv = new DataView(buf);
  const n = dv.getUint32(4, true);
  const t = dv.getUint32(8, true);
  let off = 12;
  const co = new Float32Array(buf.slice(off, off + n * 12));
  off += n * 12;
  const tri = new Uint32Array(buf.slice(off, off + t * 12));
  off += t * 12;
  const uv = new Float32Array(buf.slice(off, off + t * 24));
  off += t * 24;
  const shell = new Uint8Array(buf.slice(off, off + n));
  return { n, t, co, tri, uv, shell };
}

export function buildTexelMap(base: BaseData, size: number): TexelMap {
  const tri = new Int32Array(size * size).fill(-1);
  const bary = new Float64Array(size * size * 3);
  for (let t = 0; t < base.t; t++) {
    const x0 = base.uv[t * 6] * size - 0.5, y0 = (1 - base.uv[t * 6 + 1]) * size - 0.5;
    const x1 = base.uv[t * 6 + 2] * size - 0.5, y1 = (1 - base.uv[t * 6 + 3]) * size - 0.5;
    const x2 = base.uv[t * 6 + 4] * size - 0.5, y2 = (1 - base.uv[t * 6 + 5]) * size - 0.5;
    const den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2);
    if (den === 0) continue;
    const minx = Math.max(Math.ceil(Math.min(x0, x1, x2)), 0);
    const maxx = Math.min(Math.floor(Math.max(x0, x1, x2)), size - 1);
    const miny = Math.max(Math.ceil(Math.min(y0, y1, y2)), 0);
    const maxy = Math.min(Math.floor(Math.max(y0, y1, y2)), size - 1);
    for (let ys = miny; ys <= maxy; ys++) {
      for (let xs = minx; xs <= maxx; xs++) {
        const a = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / den;
        const b = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / den;
        const g = 1 - a - b;
        if (a >= EPS && b >= EPS && g >= EPS) {
          const i = ys * size + xs;
          tri[i] = t;
          bary[i * 3] = a;
          bary[i * 3 + 1] = b;
          bary[i * 3 + 2] = g;
        }
      }
    }
  }
  const counts = new Int32Array(base.t);
  for (let i = 0; i < tri.length; i++) if (tri[i] >= 0) counts[tri[i]]++;
  const starts = new Int32Array(base.t + 1);
  for (let t = 0; t < base.t; t++) starts[t + 1] = starts[t] + counts[t];
  const fill = starts.slice(0, base.t);
  const order = new Int32Array(starts[base.t]);
  for (let i = 0; i < tri.length; i++) if (tri[i] >= 0) order[fill[tri[i]]++] = i; // stable: texel index order per triangle
  return { size, tri, bary, order, starts };
}

/** Texel indices owned by triangle t. */
export function texelsOf(tm: TexelMap, t: number): Int32Array {
  return tm.order.subarray(tm.starts[t], tm.starts[t + 1]);
}

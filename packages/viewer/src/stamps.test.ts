// The kiosk's stamp rasteriser must produce the same bytes as the export's (fixtures/library/golden.json, written
// by scripts/make_library_golden.py from the Python rasteriser), or the print would not match the screen.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { buildTexelMap, parseBaseBin } from './atlas';
import { stampLayer, type Stamp } from './stamps';

const root = new URL('../../../', import.meta.url);

/** Minimal ustar reader: name -> bytes. */
function untar(buf: Buffer): Map<string, Buffer> {
  const out = new Map<string, Buffer>();
  let off = 0;
  while (off + 512 <= buf.length) {
    const name = buf.subarray(off, off + 100).toString('utf8').replace(/\0.*$/s, '');
    if (!name) break;
    const size = parseInt(buf.subarray(off + 124, off + 136).toString('utf8').replace(/\0.*$/s, '').trim(), 8);
    out.set(name, buf.subarray(off + 512, off + 512 + size));
    off += 512 + Math.ceil(size / 512) * 512;
  }
  return out;
}

describe('stamps', () => {
  const golden = JSON.parse(readFileSync(new URL('fixtures/library/golden.json', root), 'utf8'));
  const files = untar(readFileSync(new URL(`fixtures/library/${golden.release}`, root)));
  const bin = files.get('base.bin')!;
  const base = parseBaseBin(bin.buffer.slice(bin.byteOffset, bin.byteOffset + bin.byteLength) as ArrayBuffer);

  for (const c of golden.cases as { species: string; size: number; stamps: Stamp[]; rgba_sha256: string; painted_texels: number }[]) {
    it(`paint the same texels as the export (${c.species}, ${c.stamps.length} stamps)`, () => {
      const tm = buildTexelMap(base, c.size);
      const rgba = stampLayer(base, tm, c.stamps);
      let painted = 0;
      for (let i = 3; i < rgba.length; i += 4) if (rgba[i] > 0) painted++;
      expect(painted).toBe(c.painted_texels);
      expect(createHash('sha256').update(rgba).digest('hex')).toBe(c.rgba_sha256);
    });
  }
});

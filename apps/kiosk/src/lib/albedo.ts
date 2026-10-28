// Preview albedo painted in UV space from the base-mesh region masks, following the same rules as
// backend/core/colouring.py (patterns use 2D UV noise here instead of 3D position noise). ~10 ms at 256 px.
import type { PetSpec } from '../api/types';
import { hexToRgb } from './spec';

export const NOSE_HEX: Record<string, string> = { black: '#1E1B1A', brown: '#5C3A21', pink: '#E8A0A0', liver: '#7A3E2A', grey: '#6E6E6E' };
const WHITE: Rgb = [244, 239, 230];
const BLACK: Rgb = [30, 27, 26];
type Rgb = [number, number, number];

export interface Masks { size: number; a: Uint8ClampedArray; b: Uint8ClampedArray }

export async function loadMasks(species: string, size = 256): Promise<Masks> {
  const read = async (name: string) => {
    const img = new Image();
    img.src = `/assets/base/${species}/${name}`;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = c.height = size;
    const g = c.getContext('2d', { willReadFrequently: true })!;
    g.drawImage(img, 0, 0, size, size);
    return g.getImageData(0, 0, size, size).data;
  };
  const [a, b] = await Promise.all([read('mask_a.png'), read('mask_b.png')]);
  return { size, a, b };
}

function noise(x: number, y: number, scale: number, seed: number): number {
  let s = 0;
  let r = seed * 9301 + 49297;
  for (let i = 0; i < 4; i++) {
    r = (r * 9301 + 49297) % 233280;
    const a = (r / 233280) * Math.PI * 2;
    r = (r * 9301 + 49297) % 233280;
    const ph = (r / 233280) * 6.283;
    s += Math.sin((x * Math.cos(a) + y * Math.sin(a)) * scale + ph);
  }
  return (s / 4) * 0.5 + 0.5;
}

const mix = (c: Rgb, d: Rgb, w: number): Rgb => [c[0] + (d[0] - c[0]) * w, c[1] + (d[1] - c[1]) * w, c[2] + (d[2] - c[2]) * w];

export function paintAlbedo(spec: PetSpec, m: Masks, target: ImageData): void {
  const col = spec.colour;
  const base = hexToRgb(col.base.hex) as Rgb;
  const hasSec = !!col.secondary;
  const sec = (hasSec ? hexToRgb(col.secondary!.hex) : WHITE) as Rgb;
  const dark: Rgb = [base[0] * 0.45, base[1] * 0.45, base[2] * 0.45];
  const eye = hexToRgb(spec.eyes.hex) as Rgb;
  const nose = hexToRgb(NOSE_HEX[spec.nose.colour] ?? '#1E1B1A') as Rgb;
  const marks = new Set(col.markings ?? []);
  const p = col.pattern;
  const seed = spec.seed % 1000;
  const n = m.size;
  const out = target.data;
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const i = (y * n + x) * 4;
      const chest = m.a[i] / 255, socks = m.a[i + 1] / 255, blaze = m.a[i + 2] / 255, points = m.a[i + 3] / 255;
      const saddle = m.b[i] / 255, face = m.b[i + 1] / 255, eyeNose = m.b[i + 3] / 255;
      const u = x / n, v = y / n;
      const whiteParts = Math.min(1, chest + socks + blaze);
      let c: Rgb = base;
      if (p === 'bicolour') c = mix(c, sec, Math.min(1, chest + socks));
      else if (p === 'tricolour') { c = mix(c, (base[0] + base[1] + base[2]) / 765 > 0.25 ? BLACK : [184, 138, 90], saddle); c = mix(c, sec, whiteParts); }
      else if (p === 'saddle_with_white_chest') { c = mix(c, dark, saddle); c = mix(c, sec, whiteParts); }
      else if (p === 'tuxedo') c = mix(c, sec, whiteParts);
      else if (p === 'colourpoint') c = mix(c, hasSec ? sec : dark, points);
      else if (p === 'sable') c = mix(c, dark, saddle * 0.8);
      else if (p === 'brindle') c = mix(c, dark, Math.sin(v * 90 + 3 * noise(u, v, 12, seed)) > 0.55 ? 0.85 : 0);
      else if (p === 'tabby') c = mix(c, hasSec ? sec : dark, Math.sin(u * 70 + 2 * noise(u, v, 9, seed)) > 0.35 ? 0.9 : 0);
      else if (p === 'spotted') c = mix(c, hasSec ? sec : BLACK, noise(u, v, 60, seed) > 0.78 ? 1 : 0);
      else if (p === 'merle') { c = mix(c, (base[0] + base[1] + base[2]) / 765 > 0.3 ? BLACK : dark, noise(u, v, 30, seed) > 0.62 ? 1 : 0); c = mix(c, sec, whiteParts * 0.9); }
      else if (p === 'calico') { const a = noise(u, v, 20, seed), b = noise(u, v, 20, seed + 1); c = mix(c, sec, a > 0.6 ? 1 : 0); c = mix(c, BLACK, b > 0.65 && a <= 0.6 ? 1 : 0); c = mix(c, WHITE, chest); }
      if (marks.has('white_blaze')) c = mix(c, WHITE, blaze);
      if (marks.has('white_socks')) c = mix(c, WHITE, socks);
      if (marks.has('white_chest')) c = mix(c, WHITE, chest);
      if (marks.has('dark_mask')) c = mix(c, BLACK, face * 0.85);
      if (marks.has('points') && p !== 'colourpoint') c = mix(c, hasSec ? sec : dark, points * 0.85);
      if (eyeNose > 0.75) c = eye;
      else if (eyeNose > 0.3) c = nose;
      out[i] = c[0]; out[i + 1] = c[1]; out[i + 2] = c[2]; out[i + 3] = 255;
    }
  }
}

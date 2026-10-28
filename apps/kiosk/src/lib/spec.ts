// PetSpec helpers mirrored from backend/core/spec.py: preset -> taps -> parser patch.
import type { Breed, PetSpec, Species } from '../api/types';
import vocab from '@data/schema/vocab.json';

export type Flat = Record<string, unknown>;

export function flatten(obj: Record<string, unknown>, prefix = ''): Flat {
  const out: Flat = {};
  for (const [k, v] of Object.entries(obj)) {
    const p = prefix ? `${prefix}.${k}` : k;
    if (k === 'overrides' && v && typeof v === 'object') {
      for (const [ok, ov] of Object.entries(v as Flat)) out[`overrides.${ok}`] = ov;
    } else if (v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length) {
      Object.assign(out, flatten(v as Record<string, unknown>, p));
    } else {
      out[p] = v;
    }
  }
  return out;
}

export function setPath(obj: Record<string, unknown>, path: string, value: unknown): void {
  if (path.startsWith('overrides.')) {
    const o = (obj.overrides ??= {}) as Flat;
    o[path.slice('overrides.'.length)] = value;
    return;
  }
  const parts = path.split('.');
  let node = obj as Record<string, unknown>;
  for (const p of parts.slice(0, -1)) node = (node[p] ??= {}) as Record<string, unknown>;
  node[parts[parts.length - 1]] = value;
}

export function getPath(obj: unknown, path: string): unknown {
  if (path.startsWith('overrides.')) return ((obj as Flat)?.overrides as Flat | undefined)?.[path.slice(10)];
  return path.split('.').reduce<unknown>((n, p) => (n && typeof n === 'object' ? (n as Flat)[p] : undefined), obj);
}

export function isTapped(path: string, tapped: Set<string> | string[]): boolean {
  const t = tapped instanceof Set ? tapped : new Set(tapped);
  const parts = path.split('.');
  for (let i = 1; i <= parts.length; i++) if (t.has(parts.slice(0, i).join('.'))) return true;
  return false;
}

export function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

export function specFromBreed(species: Species, breed: Breed, seed: number, petName?: string): PetSpec {
  const preset = clone(breed.preset) as Record<string, unknown>;
  const spec = {
    spec_version: '1.0',
    species,
    breed: { id: breed.id, label: breed.label, confidence: 1 },
    ...preset,
    accessories: [],
    personality: [],
    free_text: '',
    overrides: {},
    seed,
  } as unknown as PetSpec;
  if (petName) (spec as Flat).pet_name = petName;
  return spec;
}

export function applyPatch(spec: PetSpec, patch: Record<string, unknown>, tapped: string[] = []): { spec: PetSpec; changed: string[] } {
  const out = clone(spec) as unknown as Record<string, unknown>;
  const before = flatten(spec as unknown as Record<string, unknown>);
  const changed: string[] = [];
  for (const [path, value] of Object.entries(flatten(patch))) {
    if (isTapped(path, tapped)) continue;
    setPath(out, path, value);
    if (JSON.stringify(before[path]) !== JSON.stringify(value)) changed.push(path);
  }
  return { spec: out as unknown as PetSpec, changed };
}

export function randomSeed(): number {
  return Math.floor(Math.random() * 2147483646);
}

type Palette = Record<string, { hex: string; prompt: string; synonyms: string[] }>;
export const PALETTE = vocab.palette as Palette;
export const EYE_PALETTE = vocab.eye_palette as Palette;
export const PALETTE_ORDER = ['black', 'white', 'cream', 'gold', 'red', 'tan', 'fawn', 'chocolate', 'grey', 'blue_grey', 'ginger', 'silver'];

export function hexToRgb(hex: string): [number, number, number] {
  let h = hex.replace('#', '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

export function nearestPalette(hex: string): string {
  const [r, g, b] = hexToRgb(hex);
  let best = 'grey';
  let bd = Infinity;
  for (const [name, e] of Object.entries(PALETTE)) {
    const [pr, pg, pb] = hexToRgb(e.hex);
    const d = (r - pr) ** 2 * 0.3 + (g - pg) ** 2 * 0.59 + (b - pb) ** 2 * 0.11;
    if (d < bd) [best, bd] = [name, d];
  }
  return best;
}

export function label(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

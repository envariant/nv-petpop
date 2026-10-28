// PetSpec -> shape-key weights, mirrored from backend/core/vocab.py morph_weights().
import vocab from '@data/schema/vocab.json';
import type { PetSpec } from '../api/types';
import { getPath } from './spec';

type Entry = { prompt: string; morph: Record<string, number>; synonyms: string[] };
const slots = vocab.slots as unknown as Record<string, Record<string, Entry>>;
const MORPH_SLOTS = [
  'body.size', 'body.build', 'body.leg_length', 'head.muzzle_length', 'head.muzzle_width', 'head.brachycephalic',
  'ears.shape', 'ears.size', 'ears.tip', 'ears.tufted', 'tail.type', 'tail.length', 'tail.curl', 'coat.length', 'coat.texture',
];

export function morphWeights(spec: PetSpec): Record<string, number> {
  const species = spec.species;
  const targets = (vocab.morph_targets as Record<string, string[]>)[species];
  const subs = (vocab.species_substitutes as Record<string, Record<string, Record<string, number>>>)[species] ?? {};
  const raw: Record<string, number> = {};
  for (const slot of MORPH_SLOTS) {
    const v = getPath(spec, slot);
    if (v === undefined || v === null) continue;
    const key = typeof v === 'boolean' ? String(v) : String(v);
    for (const [name, w] of Object.entries(slots[slot]?.[key]?.morph ?? {})) raw[name] = (raw[name] ?? 0) + w;
  }
  const fl = getPath(spec, 'coat.fluffiness');
  if (typeof fl === 'number') raw.fluff = (raw.fluff ?? 0) + 0.5 * fl;
  const out: Record<string, number> = Object.fromEntries(targets.map((t) => [t, 0]));
  for (const [name, w] of Object.entries(raw)) {
    if (name in out) out[name] += w;
    else if (subs[name]) for (const [s, k] of Object.entries(subs[name])) if (s in out) out[s] += w * k;
  }
  for (const k of Object.keys(out)) out[k] = Math.max(-1, Math.min(1, out[k]));
  return out;
}

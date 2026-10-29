// Small in-browser stand-in for the rule-based parser (backend/core/parser.py) used by MSW only.
import vocab from '@data/schema/vocab.json';
import type { ParseResponse, PetSpec } from '@petpop/core';
import { applyPatch, setPath } from '@petpop/core';

type Entry = { prompt: string; morph: Record<string, number>; synonyms: string[] };
const slots = vocab.slots as unknown as Record<string, Record<string, Entry>>;

export function mockParse(text: string, current: PetSpec, tapped: string[]): ParseResponse {
  const t0 = performance.now();
  let s = ` ${text.toLowerCase().replace(/[^a-z0-9' ]+/g, ' ')} `;
  const flat: Record<string, unknown> = {};
  const cands: [string, string, string][] = [];
  for (const [slot, values] of Object.entries(slots)) {
    if (['species', 'accessories.type', 'accessories.tag', 'body.pose'].includes(slot)) continue;
    for (const [value, e] of Object.entries(values)) for (const syn of e.synonyms) cands.push([syn, slot, value]);
  }
  cands.sort((a, b) => b[0].length - a[0].length);
  const markings: string[] = [];
  for (const [syn, slot, value] of cands) {
    const needle = ` ${syn.replace(/-/g, ' ')} `;
    if (!s.includes(needle)) continue;
    s = s.replace(needle, ' ');
    const typed = value === 'true' ? true : value === 'false' ? false : value;
    if (slot === 'colour.markings') markings.push(value);
    else flat[slot] = typed;
  }
  if (markings.length) flat['colour.markings'] = markings;
  for (const [name, e] of Object.entries(vocab.palette)) {
    if (e.synonyms.some((syn) => s.includes(` ${syn} `)) && !flat['colour.base']) flat['colour.base'] = { name, hex: e.hex };
  }
  const personality = Object.keys(vocab.personality_words).filter((w) => s.includes(` ${w} `)).slice(0, 4);
  if (personality.length) flat.personality = personality;
  const patch: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(flat)) if (!tapped.some((t) => k === t || k.startsWith(`${t}.`))) setPath(patch, k, v);
  const { changed } = applyPatch(current, patch, tapped);
  return {
    patch,
    changed_fields: changed,
    personality,
    free_text_unmapped: '',
    parser: 'rules',
    llm_available: false,
    flavour_only: text.trim().length > 0 && changed.length === 0,
    blocked: false,
    ms: Math.round(performance.now() - t0),
  };
}

// A breed's starting composition (BRIEF Section 2, shipped journey): the breed picks a family and a default parts
// set from the library, and its preset colours and markings become the first pattern layers. Pure functions.
import type { Breed } from '@petpop/core';
import { NOSE_HEX, REGIONS, type Composition, type DeltaItem, type ReleaseManifest } from '@petpop/viewer';

const REGION_SLOTS: Record<string, string[]> = {
  ears: ['ears.shape', 'ears.size'],
  tail: ['tail.type', 'tail.length'],
  muzzle: ['head.brachycephalic', 'head.muzzle_length'],
  legs: ['body.leg_length'],
  head: [],
};

/** Preset markings and patterns -> pattern layers (id, colour source). */
const MARKING_LAYERS: Record<string, string> = {
  white_blaze: 'pattern_blaze', white_socks: 'pattern_socks', white_chest: 'pattern_chest', dark_mask: 'pattern_mask', points: 'pattern_points',
};
const PATTERN_LAYERS: Record<string, string[]> = {
  saddle_with_white_chest: ['pattern_saddle', 'pattern_chest'], tricolour: ['pattern_saddle', 'pattern_chest'], bicolour: ['pattern_tuxedo'],
  tuxedo: ['pattern_tuxedo'], colourpoint: ['pattern_points'], sable: ['pattern_saddle'], brindle: ['pattern_brindle'], tabby: ['pattern_tabby'],
  merle: ['pattern_merle'], spotted: ['pattern_merle'], calico: ['pattern_merle', 'pattern_chest'],
};
const WHITE = '#F4EFE6';

function get(obj: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((o, k) => (o && typeof o === 'object' ? (o as Record<string, unknown>)[k] : undefined), obj);
}

export function familyFor(manifest: ReleaseManifest, breedId: string): string {
  const exact = manifest.families.find((f) => f.breeds.includes(breedId));
  return (exact ?? manifest.families.find((f) => f.id === 'family_standard') ?? manifest.families[0]).id;
}

/** The part in a region whose tags best match the breed preset, else the family default. */
export function partFor(manifest: ReleaseManifest, region: string, preset: unknown, fallback?: string): string | undefined {
  const parts = manifest.region_deltas.filter((d: DeltaItem) => d.region === region);
  for (const slot of REGION_SLOTS[region] ?? []) {
    const v = get(preset, slot);
    if (v === undefined || v === null) continue;
    const tag = `${slot}:${String(v).toLowerCase()}`;
    const hit = parts.find((p) => p.tags.includes(tag));
    if (hit) return hit.id;
  }
  return fallback && parts.some((p) => p.id === fallback) ? fallback : parts[0]?.id;
}

export function startingComposition(manifest: ReleaseManifest, breed: Breed, petName = ''): Composition {
  const preset = breed.preset as Record<string, unknown>;
  const familyId = familyFor(manifest, breed.id);
  const family = manifest.families.find((f) => f.id === familyId)!;
  const parts: Composition['parts'] = {};
  for (const region of REGIONS) {
    const id = partFor(manifest, region, preset, family.default_parts[region]);
    if (id) parts[region] = id;
  }
  const base = (get(preset, 'colour.base.hex') as string) ?? '#C8763A';
  const secondary = (get(preset, 'colour.secondary.hex') as string) ?? WHITE;
  const pattern = get(preset, 'colour.pattern') as string | undefined;
  const markings = (get(preset, 'colour.markings') as string[] | undefined) ?? [];
  const have = new Set(manifest.pattern_layers.map((p) => p.id));
  const layers: Composition['layers'] = [];
  const add = (id: string, colour?: string) => {
    if (!have.has(id) || layers.some((l) => l.pattern_id === id)) return;
    const p = manifest.pattern_layers.find((x) => x.id === id)!;
    layers.push({ pattern_id: id, coverage: p.coverage.default, colour: colour ?? p.default_colour });
  };
  for (const id of PATTERN_LAYERS[pattern ?? ''] ?? []) {
    const dark = id === 'pattern_saddle' || id === 'pattern_brindle' || id === 'pattern_tabby' || id === 'pattern_merle';
    add(id, dark ? undefined : secondary);
  }
  for (const m of markings) if (MARKING_LAYERS[m]) add(MARKING_LAYERS[m], m === 'dark_mask' ? undefined : m === 'points' ? undefined : WHITE);
  const nose = NOSE_HEX[(get(preset, 'nose.colour') as string) ?? 'black'] ?? NOSE_HEX.black;
  return {
    composition_version: '1.0',
    species: manifest.species,
    release_version: manifest.release_version,
    base_mesh_version: manifest.base_mesh_version,
    pet_name: petName,
    breed_id: breed.id,
    family_id: familyId,
    parts,
    shells: [],
    base_colour: base.toUpperCase(),
    layers: layers.slice(0, 10),
    stamps: [],
    eye_colour: ((get(preset, 'eyes.hex') as string) ?? '#3B2412').toUpperCase(),
    nose_colour: nose.toUpperCase(),
  };
}

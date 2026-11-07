// Figures of part kits in the customer app (decisions 133 to 135): the kits a release carries, the composition 3.0
// a customer builds from one, where each part goes, and which masks paint it. The twin of
// petpop_library/composition.py (check_kit, sample_kit) and petpop_library/kit_figure.py (variants_for, mask_layers);
// the painting itself is kitPaint.ts.
import * as THREE from 'three';
import { SLOTS, SLOT_KIND, placement, type AttachmentData, type JointData, type Kind, type PoseData, type Slot, type SocketOffset, type Vec3 } from './parts';

export interface KitColour { name?: string | null; hex: string }
export interface KitTexture { base: KitColour; secondary?: KitColour | null; tertiary?: KitColour | null; pattern?: string | null; markings: string[] }
export interface KitPreset { preset_id: string; label: string; stretch: Vec3; sockets?: Partial<Record<Slot, SocketOffset>> }
export interface KitPart {
  part_id: string; kind: Kind; variant: string; label: string; mesh: { file: string; sha256: string; tris: number }; uv_layout?: string;
  shared?: boolean; stretch?: Vec3; joint?: JointData; attachments?: Record<Slot, AttachmentData>; presets?: KitPreset[];
}
export interface KitPose extends PoseData { pose_id: string; label: string; variants?: Partial<Record<Kind, string>> }
/** A kit as a release 3.0 carries it (data/schema/part_kit.schema.json, kit-3, plus its breed's label). */
export interface Kit {
  kit_version: string; species: 'dog' | 'cat'; breed_id: string; label: string; version: number; parts: KitPart[];
  defaults: Record<Kind, string>; allowed?: Partial<Record<Kind, string[]>>; poses: KitPose[]; default_pose: string; texture?: KitTexture | null;
}
export interface KitMask { uv_layout: string; name: string; file: string }
export interface KitShellItem { id: string; name: string; socket: string; kind: string; mesh: string; default_colour: string; thumbnail: string }
export interface KitManifest { release_version: string; species: 'dog' | 'cat'; kits?: Kit[]; masks?: KitMask[]; shell_parts?: KitShellItem[] }
/** A spot or brush dab on one part, in that part's own frame (mm, before it is stretched and placed), decision 139. */
export interface KitCompositionStamp { slot: Slot | 'torso'; p: [number, number, number]; r: number; colour: string }
/** Composition 3.0 (data/schema/composition3.schema.json). */
export interface KitComposition {
  composition_version: '3.0'; species: 'dog' | 'cat'; release_version: string; breed_id: string; kit_version: number;
  variants: Record<Kind, string>; preset_id: string; pose_id: string; texture: KitTexture; pet_name?: string; eye_colour?: string; nose_colour?: string;
  shells?: { part_id: string; colour: string }[]; stamps?: KitCompositionStamp[];
}

export const kitFor = (m: KitManifest, breedId: string): Kit | null => m.kits?.find((k) => k.breed_id === breedId) ?? null;
export const EYE = 'eye';
export const NOSE = 'nose';

/** The composition a customer starts from: the kit's defaults, the standard shape, the default pose, the breed's texture. */
export function startingKitComposition(m: KitManifest, kit: Kit): KitComposition {
  const t = kit.texture ?? { base: { name: null, hex: '#C8763A' }, markings: [] };
  return {
    composition_version: '3.0', species: kit.species, release_version: m.release_version, breed_id: kit.breed_id, kit_version: kit.version,
    variants: { ...kit.defaults }, preset_id: 'default', pose_id: kit.default_pose,
    texture: { base: { ...t.base }, secondary: t.secondary ? { ...t.secondary } : null, tertiary: t.tertiary ? { ...t.tertiary } : null,
      pattern: t.pattern ?? null, markings: [...(t.markings ?? [])] },
    eye_colour: '#3B2412', nose_colour: '#1E1B1A', shells: [], stamps: [],
  };
}

/** The variants a customer may pick per kind on this breed (the defaults included). */
export function offered(kit: Kit, kind: Kind): string[] {
  return kit.allowed?.[kind] ?? kit.parts.filter((p) => p.kind === kind).map((p) => p.variant);
}
export const partOf = (kit: Kit, kind: Kind, variant: string): KitPart | undefined => kit.parts.find((p) => p.kind === kind && p.variant === variant);
export const presetsOf = (kit: Kit, torsoVariant: string): KitPreset[] => partOf(kit, 'torso', torsoVariant)?.presets ?? [];

/** Variants the pose swaps in win (a sitting pose folds the hind legs), decision 134. */
export function effectiveVariants(kit: Kit, c: KitComposition): Record<Kind, string> {
  const pose = kit.poses.find((p) => p.pose_id === c.pose_id);
  return { ...c.variants, ...(pose?.variants ?? {}) } as Record<Kind, string>;
}

export interface PlacedPart { slot: Slot | 'torso'; part: KitPart; matrix: THREE.Matrix4 }

/** Where every part goes (petpop_library.parts.compose_plan): the torso stretched by its shape, every other part on
 *  its slot, stretched, the right legs mirrored, posed. */
export function kitPlan(kit: Kit, c: KitComposition): PlacedPart[] {
  const v = effectiveVariants(kit, c);
  const pose = kit.poses.find((p) => p.pose_id === c.pose_id) ?? kit.poses[0];
  const torso = partOf(kit, 'torso', v.torso)!;
  const preset = torso.presets?.find((p) => p.preset_id === c.preset_id) ?? torso.presets?.[0];
  const ts = preset?.stretch ?? torso.stretch ?? [1, 1, 1];
  const out: PlacedPart[] = [{ slot: 'torso', part: torso, matrix: new THREE.Matrix4().makeScale(ts[0], ts[1], ts[2]) }];
  for (const slot of SLOTS) {
    const part = partOf(kit, SLOT_KIND[slot], v[SLOT_KIND[slot]]);
    const att = torso.attachments?.[slot];
    if (!part?.joint || !att) continue;
    out.push({ slot, part, matrix: placement(part.joint, att, slot, pose, part.stretch, ts, preset?.sockets?.[slot]) });
  }
  return out;
}

/** The marking and pattern masks a kit's parts have, by name (the `_c` and eye/nose masks aside): what a customer can
 *  switch on. */
export function markingsOf(m: KitManifest, kit: Kit): string[] {
  const layouts = new Set(kit.parts.map((p) => p.uv_layout).filter(Boolean));
  const names = (m.masks ?? []).filter((x) => layouts.has(x.uv_layout)).map((x) => x.name);
  return [...new Set(names.filter((n) => !n.endsWith('_c') && n !== EYE && n !== NOSE))].sort();
}

const rgb = (hex: string): [number, number, number] => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number];

/** (mask name, colour) painted over colour A, in order (kit_figure.mask_layers). */
export function maskLayers(t: KitTexture, eye?: string, nose?: string): [string, [number, number, number]][] {
  const b = t.secondary ?? t.base;
  const c = t.tertiary ?? b;
  const out: [string, [number, number, number]][] = [];
  for (const name of [t.pattern, ...(t.markings ?? [])]) {
    if (name) out.push([name, rgb(b.hex)], [`${name}_c`, rgb(c.hex)]);
  }
  if (eye) out.push([EYE, rgb(eye)]);
  if (nose) out.push([NOSE, rgb(nose)]);
  return out;
}

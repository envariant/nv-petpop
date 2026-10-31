// Library-mode design state (BRIEF Section 16): the loaded release, the composition the customer is building, the
// paint tools and the undo history, and the order once it is placed. Everything here is local to the kiosk: no
// GenAI host, no generation, only the library release and the kiosk's own API.
import { create } from 'zustand';
import { ApiFailure, KioskApi } from '@petpop/core';
import type { Breed, CompositionBody, CompositionStatus, Species } from '@petpop/core';
import { loadLibrary, syncStamps, uploadStamps, type Composition, type LoadedLibrary, type PaintHit, type Region, type ReleaseManifest } from '@petpop/viewer';
import { partFor, startingComposition } from '../lib/compose';

export type Tab = 'shape' | 'patterns' | 'paint' | 'extras';
export type ShapeRegion = 'family' | Region;
export type Tool = 'spot' | 'brush';
export const SPOT_MM: Record<'s' | 'm' | 'l', number> = { s: 3, m: 5, l: 8 };
export const BRUSH_MM = 1.5;
export const MAX_STAMPS = 400;
export const MAX_LAYERS = 10;

export interface DesignState {
  lib: LoadedLibrary | null;
  loading: boolean;
  libError: string | null;
  composition: Composition | null;
  strokes: number[]; // stamps per undo step
  tab: Tab;
  region: ShapeRegion;
  tool: Tool;
  spot: 's' | 'm' | 'l';
  paintColour: string;
  symmetry: boolean;
  turning: boolean; // in the Paint tab, drag turns the figure instead of painting
  order: CompositionStatus | null;
  orderError: string | null;
  // actions
  load: (species: Species) => Promise<void>;
  begin: (breed: Breed) => Promise<void>;
  set: (p: Partial<DesignState>) => void;
  setFamily: (id: string) => Promise<void>;
  setPart: (region: Region, id: string) => void;
  setBase: (hex: string) => void;
  toggleLayer: (patternId: string) => void;
  setCoverage: (patternId: string, coverage: number) => void;
  setLayerColour: (patternId: string, hex: string) => void;
  toggleShell: (partId: string) => void;
  setShellColour: (partId: string, hex: string) => void;
  setEyes: (hex: string) => void;
  setNose: (hex: string) => void;
  setName: (name: string) => void;
  paint: (hit: PaintHit) => void;
  undo: () => void;
  placeOrder: (sessionId: string | null) => Promise<void>;
  refreshOrder: () => Promise<void>;
  reset: () => void;
}

const initial = {
  lib: null,
  loading: false,
  libError: null,
  composition: null,
  strokes: [],
  tab: 'shape' as Tab,
  region: 'family' as ShapeRegion,
  tool: 'spot' as Tool,
  spot: 'm' as const,
  paintColour: '#1E1B1A',
  symmetry: true,
  turning: false,
  order: null,
  orderError: null,
};

let libSpecies: Species | null = null;
let release: { manifest: ReleaseManifest; url: (path: string) => string } | null = null;
let lastDab: [number, number, number] | null = null;
const libs = new Map<string, Promise<LoadedLibrary>>(); // one per mesh of the active release

let breedPreset: unknown = null;

function meshLibrary(meshId: string): Promise<LoadedLibrary> {
  if (!release) return Promise.reject(new Error('no release loaded'));
  if (!libs.has(meshId)) libs.set(meshId, loadLibrary(release.manifest, release.url, meshId));
  return libs.get(meshId)!;
}

export const useDesign = create<DesignState>((set, get) => {
  const edit = (f: (c: Composition) => Composition) => {
    const c = get().composition;
    if (c) set({ composition: f(c) });
  };
  return {
    ...initial,
    load: async (species) => {
      if (libSpecies === species && get().lib) return;
      set({ loading: true, libError: null });
      try {
        const rel = await KioskApi.libraryRelease(species);
        release = { manifest: rel.manifest as unknown as ReleaseManifest, url: (path) => `${rel.files_url}${path}` };
        libs.clear();
        const lib = await meshLibrary(release.manifest.families[0]?.mesh_id ?? release.manifest.meshes[0].id);
        libSpecies = species;
        set({ lib, loading: false });
      } catch {
        set({ loading: false, libError: 'The parts library is not available right now.' });
      }
    },
    begin: async (breed) => {
      await get().load(breed.species);
      if (!get().lib || !release) return;
      const composition = startingComposition(release.manifest, breed);
      const lib = await meshLibrary(composition.mesh_id);
      syncStamps(lib, []);
      breedPreset = breed.preset;
      set({ lib, composition, strokes: [], tab: 'shape', region: 'family', order: null, orderError: null });
    },
    set: (p) => set(p),
    setFamily: async (id) => {
      const c = get().composition;
      const fam = release?.manifest.families.find((f) => f.id === id);
      if (!c || !fam || !release) return;
      if (fam.mesh_id === c.mesh_id) {
        edit((x) => ({ ...x, family_id: id }));
        return;
      }
      // Another mesh (decision 118): its own part variants, and stamps start afresh because they live on the mesh.
      const lib = await meshLibrary(fam.mesh_id);
      syncStamps(lib, []);
      const parts: Composition['parts'] = {};
      for (const region of Object.keys(fam.default_parts) as Region[]) {
        const pid = partFor(release.manifest, region, breedPreset, fam.default_parts[region], fam.mesh_id);
        if (pid) parts[region] = pid;
      }
      set({ lib, composition: { ...c, family_id: id, mesh_id: fam.mesh_id, parts, stamps: [] }, strokes: [] });
    },
    setPart: (region, id) => edit((c) => ({ ...c, parts: { ...c.parts, [region]: id } })),
    setBase: (hex) => edit((c) => ({ ...c, base_colour: hex })),
    toggleLayer: (pid) =>
      edit((c) => {
        if (c.layers.some((l) => l.pattern_id === pid)) return { ...c, layers: c.layers.filter((l) => l.pattern_id !== pid) };
        if (c.layers.length >= MAX_LAYERS) return c;
        const p = get().lib!.manifest.pattern_layers.find((x) => x.id === pid)!;
        return { ...c, layers: [...c.layers, { pattern_id: pid, coverage: p.coverage.default, colour: p.default_colour }] };
      }),
    setCoverage: (pid, coverage) => edit((c) => ({ ...c, layers: c.layers.map((l) => (l.pattern_id === pid ? { ...l, coverage } : l)) })),
    setLayerColour: (pid, hex) => edit((c) => ({ ...c, layers: c.layers.map((l) => (l.pattern_id === pid ? { ...l, colour: hex } : l)) })),
    toggleShell: (partId) =>
      edit((c) => {
        if (c.shells.some((s) => s.part_id === partId)) return { ...c, shells: c.shells.filter((s) => s.part_id !== partId) };
        const item = get().lib!.manifest.shell_parts.find((s) => s.id === partId)!;
        const sameSocket = new Set(get().lib!.manifest.shell_parts.filter((s) => s.socket === item.socket).map((s) => s.id));
        return { ...c, shells: [...c.shells.filter((s) => !sameSocket.has(s.part_id)), { part_id: partId, colour: item.default_colour }] };
      }),
    setShellColour: (partId, hex) => edit((c) => ({ ...c, shells: c.shells.map((s) => (s.part_id === partId ? { ...s, colour: hex } : s)) })),
    setEyes: (hex) => edit((c) => ({ ...c, eye_colour: hex })),
    setNose: (hex) => edit((c) => ({ ...c, nose_colour: hex })),
    setName: (name) => edit((c) => ({ ...c, pet_name: name.slice(0, 24) })),
    paint: (hit) => {
      const { lib, composition, tool, spot, paintColour, symmetry, strokes } = get();
      if (!lib || !composition || composition.stamps.length >= MAX_STAMPS) return;
      const r = tool === 'brush' ? BRUSH_MM : SPOT_MM[spot];
      if (tool === 'spot' && hit.dragging) return;
      if (tool === 'brush' && hit.dragging && lastDab) {
        const d = Math.hypot(hit.p[0] - lastDab[0], hit.p[1] - lastDab[1], hit.p[2] - lastDab[2]);
        if (d < r * 0.6) return;
      }
      lastDab = hit.p;
      const add = [{ p: hit.p, r, colour: paintColour }];
      if (symmetry && Math.abs(hit.p[0]) > r * 0.5) add.push({ p: [-hit.p[0], hit.p[1], hit.p[2]] as [number, number, number], r, colour: paintColour });
      const room = MAX_STAMPS - composition.stamps.length;
      const stamps = add.slice(0, room);
      for (const s of stamps) lib.stamps.add(s);
      uploadStamps(lib);
      const nextStrokes = hit.dragging && strokes.length ? [...strokes.slice(0, -1), strokes[strokes.length - 1] + stamps.length] : [...strokes, stamps.length];
      set({ composition: { ...composition, stamps: [...composition.stamps, ...stamps] }, strokes: nextStrokes });
    },
    undo: () => {
      const { lib, composition, strokes } = get();
      if (!lib || !composition || !strokes.length) return;
      const keep = composition.stamps.length - strokes[strokes.length - 1];
      const stamps = composition.stamps.slice(0, keep);
      syncStamps(lib, stamps);
      set({ composition: { ...composition, stamps }, strokes: strokes.slice(0, -1) });
    },
    placeOrder: async (sessionId) => {
      const { composition } = get();
      if (!composition) return;
      set({ orderError: null });
      try {
        let sid = sessionId;
        if (!sid) sid = (await KioskApi.createSession()).session_id;
        const created = await KioskApi.createComposition(sid, composition as CompositionBody);
        await KioskApi.exportComposition(created.composition_id);
        set({ order: await KioskApi.composition(created.composition_id) });
      } catch (e) {
        set({ orderError: e instanceof ApiFailure && e.status === 422 ? 'This design uses parts that are no longer in the library.' : 'We could not place the order. Please ask a member of staff.' });
      }
    },
    refreshOrder: async () => {
      const { order } = get();
      if (!order) return;
      try {
        set({ order: await KioskApi.composition(order.composition_id) });
      } catch {
        /* the offline overlay handles a dropped API */
      }
    },
    reset: () => {
      lastDab = null;
      const lib = get().lib;
      if (lib) syncStamps(lib, []);
      set({ ...initial, lib });
    },
  };
});

// Studio curation state (BRIEF Section 16, M8): the batch spec builder, the review grid, the parts and pattern
// editors and releases. The single-figurine Generate flow keeps its own state in session.ts.
import { create } from 'zustand';
import { ApiFailure, StudioApi } from '@petpop/core';
import type { Batch, ItemKind, LibraryItem, LibraryItemPatch, ReleaseInfo, ReviewDecision, Species } from '@petpop/core';

export type Area = 'generate' | 'review' | 'library' | 'releases' | 'single';

/** Variants a batch can apply over each breed preset (PetSpec patches; every value is in the vocabulary). */
export const VARIANTS: { label: string; title: string; patch: Record<string, unknown> }[] = [
  { label: 'preset', title: 'Breed preset', patch: {} },
  { label: 'big_ears', title: 'Big ears', patch: { ears: { size: 'large' } } },
  { label: 'stocky', title: 'Stocky', patch: { body: { build: 'stocky' } } },
  { label: 'slim', title: 'Slim', patch: { body: { build: 'slim' } } },
  { label: 'long_tail', title: 'Long tail', patch: { tail: { length: 'long' } } },
  { label: 'short_muzzle', title: 'Short muzzle', patch: { head: { muzzle_length: 'short' } } },
];
export const MAX_FIGURINES = 60;

export interface CurateState {
  species: Species;
  breeds: string[];
  variants: string[];
  seeds: number;
  batches: Batch[];
  batch: Batch | null;
  kind: ItemKind;
  items: LibraryItem[];
  selected: LibraryItem | null;
  releases: ReleaseInfo[];
  busy: boolean;
  error: string | null;
  notice: string | null;
  set: (p: Partial<CurateState>) => void;
  toggleBreed: (id: string) => void;
  toggleVariant: (label: string) => void;
  startBatch: () => Promise<Batch | null>;
  loadBatches: () => Promise<void>;
  openBatch: (id: string) => Promise<void>;
  refreshBatch: () => Promise<void>;
  decide: (decisions: ReviewDecision[]) => Promise<void>;
  loadItems: (kind?: ItemKind) => Promise<void>;
  edit: (patch: LibraryItemPatch) => Promise<void>;
  publish: (item: LibraryItem) => Promise<void>;
  unpublish: (item: LibraryItem) => Promise<void>;
  loadReleases: () => Promise<void>;
  release: () => Promise<void>;
}

const message = (e: unknown) =>
  e instanceof ApiFailure ? (e.status === 403 ? 'Your role cannot do that.' : typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail)) : 'Something went wrong.';

export const useCurate = create<CurateState>((set, get) => {
  const run = async <T,>(f: () => Promise<T>): Promise<T | null> => {
    set({ busy: true, error: null, notice: null });
    try {
      return await f();
    } catch (e) {
      set({ error: message(e) });
      return null;
    } finally {
      set({ busy: false });
    }
  };
  return {
    species: 'dog',
    breeds: [],
    variants: ['preset'],
    seeds: 1,
    batches: [],
    batch: null,
    kind: 'region',
    items: [],
    selected: null,
    releases: [],
    busy: false,
    error: null,
    notice: null,
    set: (p) => set(p),
    toggleBreed: (id) => set((s) => ({ breeds: s.breeds.includes(id) ? s.breeds.filter((b) => b !== id) : [...s.breeds, id] })),
    toggleVariant: (label) =>
      set((s) => {
        const on = s.variants.includes(label) ? s.variants.filter((v) => v !== label) : [...s.variants, label];
        return { variants: on.length ? on : ['preset'] };
      }),
    startBatch: async () => {
      const { species, breeds, variants, seeds } = get();
      const batch = await run(() =>
        StudioApi.createBatch({ species, breeds, seeds, first_seed: 1, variants: VARIANTS.filter((v) => variants.includes(v.label)).map((v) => ({ label: v.label, patch: v.patch })) }),
      );
      if (batch) set({ batch, breeds: [], notice: `Batch started: ${batch.summary.figurines} figurines` });
      return batch;
    },
    loadBatches: async () => {
      const r = await run(() => StudioApi.batches());
      if (r) set({ batches: r.items });
    },
    openBatch: async (id) => {
      const b = await run(() => StudioApi.batch(id));
      if (b) set({ batch: b });
    },
    refreshBatch: async () => {
      const b = get().batch;
      if (!b) return;
      try {
        set({ batch: await StudioApi.batch(b.batch_id) });
      } catch {
        /* the offline overlay handles a dropped API */
      }
    },
    decide: async (decisions) => {
      const b = get().batch;
      if (!b) return;
      const r = await run(() => StudioApi.review(b.batch_id, decisions));
      if (r) set({ batch: r });
    },
    loadItems: async (kind) => {
      const k = kind ?? get().kind;
      const r = await run(() => StudioApi.libraryItems(get().species, k));
      if (r) set({ items: r.items, kind: k, selected: r.items.find((i) => i.id === get().selected?.id) ?? null });
    },
    edit: async (patch) => {
      const it = get().selected;
      if (!it) return;
      const r = await run(() => StudioApi.editItem(it.species, it.kind, it.id, patch));
      if (r) set((s) => ({ selected: r, items: s.items.map((i) => (i.id === r.id ? r : i)), notice: `Saved ${r.name} as version ${r.version}` }));
    },
    publish: async (item) => {
      const r = await run(() => StudioApi.publishItem(item.species, item.kind, item.id));
      if (r) set((s) => ({ selected: s.selected?.id === r.id ? r : s.selected, items: s.items.map((i) => (i.id === r.id ? r : i)), notice: `Published ${r.name} v${r.version}` }));
    },
    unpublish: async (item) => {
      const r = await run(() => StudioApi.unpublishItem(item.species, item.kind, item.id));
      if (r) set((s) => ({ selected: s.selected?.id === r.id ? r : s.selected, items: s.items.map((i) => (i.id === r.id ? r : i)) }));
    },
    loadReleases: async () => {
      const r = await run(() => StudioApi.releases());
      if (r) set({ releases: r.items });
    },
    release: async () => {
      const r = await run(() => StudioApi.createRelease(get().species));
      if (r) {
        await get().loadReleases();
        set({ notice: `${r.release_version} is out: the kiosk loads it within 30 s` });
      }
    },
  };
});

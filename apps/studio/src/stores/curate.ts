// Studio curation state (BRIEF Section 16, M8): the batch spec builder, the review grid, the parts and pattern
// editors and releases. The single-figurine Generate flow keeps its own state in session.ts.
import { defineStore } from 'pinia';
import { ref } from 'vue';
import { ApiFailure, StudioApi } from '@petpop/core';
import { useProfiles } from './profiles';
import type { Batch, ItemKind, LibraryItem, LibraryItemPatch, ReleaseInfo, ReviewDecision, Species } from '@petpop/core';

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

const message = (e: unknown) =>
  e instanceof ApiFailure ? (e.status === 403 ? 'Your role cannot do that.' : typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail)) : 'Something went wrong.';

export const useCurate = defineStore('curate', () => {
  const species = ref<Species>('dog');
  const breeds = ref<string[]>([]);
  const variants = ref<string[]>(['preset']);
  const seeds = ref(1);
  const batches = ref<Batch[]>([]);
  const batch = ref<Batch | null>(null);
  const kind = ref<ItemKind>('region');
  const items = ref<LibraryItem[]>([]);
  const selected = ref<LibraryItem | null>(null);
  const releases = ref<ReleaseInfo[]>([]);
  const busy = ref(false);
  const error = ref<string | null>(null);
  const notice = ref<string | null>(null);

  async function run<T>(f: () => Promise<T>): Promise<T | null> {
    busy.value = true;
    error.value = null;
    notice.value = null;
    try {
      return await f();
    } catch (e) {
      error.value = message(e);
      return null;
    } finally {
      busy.value = false;
    }
  }
  const replace = (r: LibraryItem) => {
    items.value = items.value.map((i) => (i.id === r.id ? r : i));
    if (selected.value?.id === r.id) selected.value = r;
  };

  function setSpecies(s: Species) {
    species.value = s;
    breeds.value = [];
    items.value = [];
    selected.value = null;
  }
  function toggleBreed(id: string) {
    breeds.value = breeds.value.includes(id) ? breeds.value.filter((b) => b !== id) : [...breeds.value, id];
  }
  function toggleVariant(label: string) {
    const on = variants.value.includes(label) ? variants.value.filter((v) => v !== label) : [...variants.value, label];
    variants.value = on.length ? on : ['preset'];
  }
  async function startBatch() {
    const p = useProfiles();
    const b = await run(() =>
      StudioApi.createBatch({
        species: species.value, breeds: breeds.value, seeds: seeds.value, first_seed: 1, genai_profile: p.choice, pipeline: p.pipeline, options: p.options,
        variants: VARIANTS.filter((v) => variants.value.includes(v.label)).map((v) => ({ label: v.label, patch: v.patch })),
      }),
    );
    if (b) {
      batch.value = b;
      breeds.value = [];
      notice.value = `Batch started: ${b.summary.figurines} figurines`;
    }
    return b;
  }
  async function loadBatches() {
    // polled every few seconds: silent, so it never clears the notice or error the curator is reading
    try {
      batches.value = (await StudioApi.batches()).items;
    } catch {
      /* the offline overlay handles a dropped API */
    }
  }
  async function openBatch(id: string) {
    const b = await run(() => StudioApi.batch(id));
    if (b) batch.value = b;
  }
  async function refreshBatch() {
    if (!batch.value) return;
    try {
      batch.value = await StudioApi.batch(batch.value.batch_id);
    } catch {
      /* the offline overlay handles a dropped API */
    }
  }
  async function decide(decisions: ReviewDecision[]) {
    if (!batch.value) return;
    const id = batch.value.batch_id;
    const r = await run(() => StudioApi.review(id, decisions));
    if (r) batch.value = r;
  }
  async function loadItems(k?: ItemKind) {
    const want = k ?? kind.value;
    const r = await run(() => StudioApi.libraryItems(species.value, want));
    if (r) {
      items.value = r.items;
      kind.value = want;
      selected.value = r.items.find((i) => i.id === selected.value?.id) ?? null;
    }
  }
  async function edit(patch: LibraryItemPatch) {
    const it = selected.value;
    if (!it) return;
    const r = await run(() => StudioApi.editItem(it.species, it.kind, it.id, patch));
    if (r) {
      replace(r);
      selected.value = r;
      notice.value = `Saved ${r.name} as version ${r.version}`;
    }
  }
  async function publish(item: Pick<LibraryItem, 'species' | 'kind' | 'id'>) {
    const r = await run(() => StudioApi.publishItem(item.species, item.kind, item.id));
    if (r) {
      replace(r);
      notice.value = `Published ${r.name} v${r.version}`;
    }
  }
  async function unpublish(item: LibraryItem) {
    const r = await run(() => StudioApi.unpublishItem(item.species, item.kind, item.id));
    if (r) replace(r);
  }
  async function loadReleases() {
    const r = await run(() => StudioApi.releases());
    if (r) releases.value = r.items;
  }
  async function release() {
    const r = await run(() => StudioApi.createRelease(species.value));
    if (r) {
      await loadReleases();
      notice.value = `${r.release_version} is out: the kiosk loads it within 30 s`;
    }
  }
  return {
    species, breeds, variants, seeds, batches, batch, kind, items, selected, releases, busy, error, notice,
    setSpecies, toggleBreed, toggleVariant, startBatch, loadBatches, openBatch, refreshBatch, decide, loadItems, edit, publish, unpublish, loadReleases, release,
  };
});

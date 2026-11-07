// Library-mode design state (Pinia): the loaded release mesh, the composition being built, the paint tools and the
// undo history, and the order once placed. Local to the device: only the library release and the /kiosk API.
// A breed with a part kit in the release (decisions 133 to 136) is designed as a figure of parts instead: `kit` and
// `kitComposition` (composition 3.0) replace the mesh library and its composition; `active` is whichever is in use.
// Loaded meshes hold three.js objects, so they stay out of Vue's reactivity (markRaw / shallowRef).
import { defineStore } from 'pinia';
import { computed, markRaw, ref, shallowRef, watch } from 'vue';
import { ApiFailure, KioskApi, apiUrl } from '@petpop/core';
import type { Breed, CompositionBody, CompositionStatus, OrderContact, PaymentMethod, Species } from '@petpop/core';
import { kitFor, loadLibrary, mirrorStamp, partFor, startingComposition, startingKitComposition, syncStamps, uploadStamps, type Composition, type Kind, type Kit,
  type KitComposition, type KitHit, type KitManifest, type KitStamp, type LoadedLibrary, type PaintHit, type Region, type ReleaseManifest } from '@petpop/scene';

export type Tab = 'shape' | 'patterns' | 'paint' | 'extras';
export type ShapeRegion = 'family' | Region;
export type Tool = 'spot' | 'brush';
export const SPOT_MM: Record<'s' | 'm' | 'l', number> = { s: 3, m: 5, l: 8 };
export const BRUSH_MM = 1.5;
export const MAX_STAMPS = 400;
export const MAX_LAYERS = 10;

let libSpecies: Species | null = null;
let release: { manifest: ReleaseManifest; url: (path: string) => string } | null = null;
let lastDab: [number, number, number] | null = null;
let lastSlot: string | null = null;
let breedPreset: unknown = null;
const libs = new Map<string, Promise<LoadedLibrary>>(); // one per mesh of the active release

function meshLibrary(meshId: string): Promise<LoadedLibrary> {
  if (!release) return Promise.reject(new Error('no release loaded'));
  if (!libs.has(meshId)) libs.set(meshId, loadLibrary(release.manifest, release.url, meshId).then((l) => markRaw(l)));
  return libs.get(meshId)!;
}

export const useDesign = defineStore('design', () => {
  const lib = shallowRef<LoadedLibrary | null>(null);
  const loading = ref(false);
  const libError = ref<string | null>(null);
  const composition = ref<Composition | null>(null);
  const strokes = ref<number[]>([]); // stamps per undo step
  const tab = ref<Tab>('shape');
  const region = ref<ShapeRegion>('family');
  const tool = ref<Tool>('spot');
  const spot = ref<'s' | 'm' | 'l'>('m');
  const paintColour = ref('#1E1B1A');
  const symmetry = ref(true);
  const turning = ref(false);
  const order = ref<CompositionStatus | null>(null);
  const orderError = ref<string | null>(null);
  // a figure of part kits (decision 136)
  const kit = shallowRef<Kit | null>(null);
  const kitComposition = ref<KitComposition | null>(null);
  const active = computed<Composition | KitComposition | null>(() => kitComposition.value ?? composition.value);
  const kitMode = computed(() => !!kitComposition.value);
  // the price as the design stands (decision 137), fetched a moment after each change
  const quote = ref<Awaited<ReturnType<typeof KioskApi.quote>> | null>(null);
  let quoting: ReturnType<typeof setTimeout> | null = null;
  let quoteSeq = 0;
  watch(active, (c) => {
    if (quoting) clearTimeout(quoting);
    if (!c) {
      quote.value = null;
      return;
    }
    const seq = ++quoteSeq;
    quoting = setTimeout(() => {
      KioskApi.quote(JSON.parse(JSON.stringify(c)) as CompositionBody)
        .then((q) => { if (seq === quoteSeq) quote.value = q; })
        .catch(() => { if (seq === quoteSeq) quote.value = null; });
    }, 250);
  }, { deep: true });
  const editKit = (f: (c: KitComposition) => KitComposition) => {
    if (kitComposition.value) kitComposition.value = f(kitComposition.value);
  };

  const edit = (f: (c: Composition) => Composition) => {
    if (composition.value) composition.value = f(composition.value);
  };
  function manifest(): ReleaseManifest {
    return release!.manifest;
  }

  async function load(species: Species) {
    if (libSpecies === species && release) return;
    loading.value = true;
    libError.value = null;
    try {
      const rel = await KioskApi.libraryRelease(species);
      release = { manifest: rel.manifest as unknown as ReleaseManifest, url: (path) => apiUrl(`${rel.files_url}${path}`) };
      libs.clear();
      // a release of part kits only has no whole-figure mesh to load
      const first = release.manifest.families[0]?.mesh_id ?? release.manifest.meshes[0]?.id;
      lib.value = first ? await meshLibrary(first) : null;
      libSpecies = species;
    } catch {
      libError.value = 'The parts library is not available right now.';
    } finally {
      loading.value = false;
    }
  }
  async function begin(breed: Breed) {
    await load(breed.species);
    if (!release) return;
    const k = kitFor(release.manifest as unknown as KitManifest, breed.id);
    if (k) {
      kit.value = markRaw(k);
      kitComposition.value = startingKitComposition(release.manifest as unknown as KitManifest, k);
      composition.value = null;
      breedPreset = breed.preset;
      strokes.value = [];
      tab.value = 'shape';
      order.value = null;
      orderError.value = null;
      return;
    }
    kit.value = null;
    kitComposition.value = null;
    if (!lib.value) {
      libError.value = 'This breed is not in the library yet.';
      return;
    }
    const c = startingComposition(release.manifest, breed);
    const l = await meshLibrary(c.mesh_id);
    syncStamps(l, []);
    breedPreset = breed.preset;
    lib.value = l;
    composition.value = c;
    strokes.value = [];
    tab.value = 'shape';
    region.value = 'family';
    order.value = null;
    orderError.value = null;
  }
  async function setFamily(id: string) {
    const c = composition.value;
    const fam = release?.manifest.families.find((f) => f.id === id);
    if (!c || !fam || !release) return;
    if (fam.mesh_id === c.mesh_id) return edit((x) => ({ ...x, family_id: id }));
    // Another mesh (decision 118): its own part variants, and stamps start afresh because they live on the mesh.
    const l = await meshLibrary(fam.mesh_id);
    syncStamps(l, []);
    const parts: Composition['parts'] = {};
    for (const r of Object.keys(fam.default_parts) as Region[]) {
      const pid = partFor(release.manifest, r, breedPreset, fam.default_parts[r], fam.mesh_id);
      if (pid) parts[r] = pid;
    }
    const mesh = release.manifest.meshes.find((x) => x.id === fam.mesh_id);
    const base = mesh?.texture && mesh.coat_hex ? mesh.coat_hex.toUpperCase() : c.base_colour; // untinted on a textured mesh
    lib.value = l;
    composition.value = { ...c, family_id: id, mesh_id: fam.mesh_id, parts, stamps: [], base_colour: base };
    strokes.value = [];
  }
  const setPart = (r: Region, id: string) => edit((c) => ({ ...c, parts: { ...c.parts, [r]: id } }));
  const setBase = (hex: string) => edit((c) => ({ ...c, base_colour: hex }));
  function toggleLayer(pid: string) {
    edit((c) => {
      if (c.layers.some((l) => l.pattern_id === pid)) return { ...c, layers: c.layers.filter((l) => l.pattern_id !== pid) };
      if (c.layers.length >= MAX_LAYERS) return c;
      const p = manifest().pattern_layers.find((x) => x.id === pid)!;
      return { ...c, layers: [...c.layers, { pattern_id: pid, coverage: p.coverage.default, colour: p.default_colour }] };
    });
  }
  const setCoverage = (pid: string, coverage: number) => edit((c) => ({ ...c, layers: c.layers.map((l) => (l.pattern_id === pid ? { ...l, coverage } : l)) }));
  const setLayerColour = (pid: string, hex: string) => edit((c) => ({ ...c, layers: c.layers.map((l) => (l.pattern_id === pid ? { ...l, colour: hex } : l)) }));
  /** The extras, one per socket, on whichever figure is being designed (a figure of parts too, decision 139). */
  function toggledShells(shells: { part_id: string; colour: string }[], partId: string) {
    if (shells.some((s) => s.part_id === partId)) return shells.filter((s) => s.part_id !== partId);
    const item = manifest().shell_parts.find((s) => s.id === partId)!;
    const sameSocket = new Set(manifest().shell_parts.filter((s) => s.socket === item.socket).map((s) => s.id));
    return [...shells.filter((s) => !sameSocket.has(s.part_id)), { part_id: partId, colour: item.default_colour }];
  }
  function toggleShell(partId: string) {
    if (kitMode.value) return editKit((c) => ({ ...c, shells: toggledShells(c.shells ?? [], partId) }));
    edit((c) => ({ ...c, shells: toggledShells(c.shells, partId) }));
  }
  function setShellColour(partId: string, hex: string) {
    const recolour = <T extends { part_id: string; colour: string }>(xs: T[]) => xs.map((s) => (s.part_id === partId ? { ...s, colour: hex } : s));
    if (kitMode.value) return editKit((c) => ({ ...c, shells: recolour(c.shells ?? []) }));
    edit((c) => ({ ...c, shells: recolour(c.shells) }));
  }
  const setEyes = (hex: string) => (kitMode.value ? editKit((c) => ({ ...c, eye_colour: hex })) : edit((c) => ({ ...c, eye_colour: hex })));
  const setNose = (hex: string) => (kitMode.value ? editKit((c) => ({ ...c, nose_colour: hex })) : edit((c) => ({ ...c, nose_colour: hex })));
  const setName = (name: string) => (kitMode.value ? editKit((c) => ({ ...c, pet_name: name.slice(0, 24) })) : edit((c) => ({ ...c, pet_name: name.slice(0, 24) })));

  // ---- a figure of part kits: the parts, the torso's shape, the pose, the colours and markings
  const setKitVariant = (kind: Kind, variant: string) => editKit((c) => ({ ...c, variants: { ...c.variants, [kind]: variant } }));
  const setTorso = (variant: string, presetId: string) => editKit((c) => ({ ...c, variants: { ...c.variants, torso: variant }, preset_id: presetId }));
  const setPose = (poseId: string) => editKit((c) => ({ ...c, pose_id: poseId }));
  function setKitColour(which: 'base' | 'secondary' | 'tertiary', hex: string, name?: string) {
    editKit((c) => ({ ...c, texture: { ...c.texture, [which]: { name: name ?? null, hex } } }));
  }
  function toggleMarking(name: string) {
    editKit((c) => {
      const has = c.texture.markings.includes(name);
      return { ...c, texture: { ...c.texture, markings: has ? c.texture.markings.filter((m) => m !== name) : [...c.texture.markings, name].slice(0, 20) } };
    });
  }
  /** The release's file URL, for the figure of parts' meshes and masks. */
  const fileUrl = (path: string) => release!.url(path);
  const kitManifest = () => release!.manifest as unknown as KitManifest;

  /** A spot or dab on a figure of parts (decision 139): on the part it landed on, in that part's own frame. */
  function paintKit(hit: KitHit & { dragging: boolean }) {
    const c = kitComposition.value;
    const have = c?.stamps ?? [];
    if (!c || have.length >= MAX_STAMPS) return;
    const r = tool.value === 'brush' ? BRUSH_MM : SPOT_MM[spot.value];
    if (tool.value === 'spot' && hit.dragging) return;
    if (tool.value === 'brush' && hit.dragging && lastDab && lastSlot === hit.slot) {
      const d = Math.hypot(hit.p[0] - lastDab[0], hit.p[1] - lastDab[1], hit.p[2] - lastDab[2]);
      if (d < r * 0.6) return;
    }
    lastDab = hit.p;
    lastSlot = hit.slot;
    const first: KitStamp = { slot: hit.slot, p: hit.p, r, colour: paintColour.value };
    const add = [first];
    const leg = hit.slot.startsWith('front_') || hit.slot.startsWith('hind_');
    if (symmetry.value && (leg || Math.abs(hit.p[0]) > r * 0.5)) add.push(mirrorStamp(first));
    const stamps = add.slice(0, MAX_STAMPS - have.length);
    const s = strokes.value;
    strokes.value = hit.dragging && s.length ? [...s.slice(0, -1), s[s.length - 1] + stamps.length] : [...s, stamps.length];
    kitComposition.value = { ...c, stamps: [...have, ...stamps] };
  }
  function paint(hit: PaintHit | (KitHit & { dragging: boolean })) {
    if (kitMode.value) return paintKit(hit as KitHit & { dragging: boolean });
    if (!('p' in hit) || 'slot' in hit) return;
    const l = lib.value;
    const c = composition.value;
    if (!l || !c || c.stamps.length >= MAX_STAMPS) return;
    const r = tool.value === 'brush' ? BRUSH_MM : SPOT_MM[spot.value];
    if (tool.value === 'spot' && hit.dragging) return;
    if (tool.value === 'brush' && hit.dragging && lastDab) {
      const d = Math.hypot(hit.p[0] - lastDab[0], hit.p[1] - lastDab[1], hit.p[2] - lastDab[2]);
      if (d < r * 0.6) return;
    }
    lastDab = hit.p;
    const add = [{ p: hit.p, r, colour: paintColour.value }];
    if (symmetry.value && Math.abs(hit.p[0]) > r * 0.5) add.push({ p: [-hit.p[0], hit.p[1], hit.p[2]] as [number, number, number], r, colour: paintColour.value });
    const stamps = add.slice(0, MAX_STAMPS - c.stamps.length);
    for (const s of stamps) l.stamps.add(s);
    uploadStamps(l);
    const s = strokes.value;
    strokes.value = hit.dragging && s.length ? [...s.slice(0, -1), s[s.length - 1] + stamps.length] : [...s, stamps.length];
    composition.value = { ...c, stamps: [...c.stamps, ...stamps] };
  }
  function undo() {
    const k = kitComposition.value;
    if (k) {
      if (!strokes.value.length) return;
      const have = k.stamps ?? [];
      kitComposition.value = { ...k, stamps: have.slice(0, have.length - strokes.value[strokes.value.length - 1]) };
      strokes.value = strokes.value.slice(0, -1);
      return;
    }
    const l = lib.value;
    const c = composition.value;
    if (!l || !c || !strokes.value.length) return;
    const stamps = c.stamps.slice(0, c.stamps.length - strokes.value[strokes.value.length - 1]);
    syncStamps(l, stamps);
    composition.value = { ...c, stamps };
    strokes.value = strokes.value.slice(0, -1);
  }
  async function placeOrder(sessionId: string | null, contact: OrderContact | null = null) {
    if (!active.value) return;
    orderError.value = null;
    try {
      const sid = sessionId ?? (await KioskApi.createSession()).session_id;
      const created = await KioskApi.createComposition(sid, active.value as unknown as CompositionBody);
      await KioskApi.exportComposition(created.composition_id, contact);
      order.value = await KioskApi.composition(created.composition_id);
    } catch (e) {
      orderError.value = e instanceof ApiFailure && e.status === 422
        ? (typeof e.detail === 'string' ? e.detail : 'This design uses parts that are no longer in the library.')
        : 'We could not place the order. Please ask a member of staff.';
    }
  }
  // Payment for the order (decision 125): start one (PayNow QR or card checkout), or with the fake provider, simulate it.
  const payError = ref<string | null>(null);
  async function pay(method: PaymentMethod) {
    if (!order.value) return;
    payError.value = null;
    try {
      await KioskApi.createPayment(order.value.composition_id, method);
      await refreshOrder();
    } catch (e) {
      payError.value = e instanceof ApiFailure && e.status === 502 ? 'Payment is not available right now. Please pay at the counter.' : 'We could not start the payment. Please try again.';
    }
  }
  async function simulatePay() {
    if (!order.value) return;
    await KioskApi.simulatePayment(order.value.composition_id);
    await refreshOrder();
  }
  async function refreshOrder() {
    if (!order.value) return;
    try {
      // a pending payment is checked with the provider first (the webhook may not have arrived)
      if (order.value.payment?.status === 'pending') await KioskApi.payment(order.value.composition_id);
      order.value = await KioskApi.composition(order.value.composition_id);
    } catch {
      /* the offline overlay handles a dropped API */
    }
  }
  function reset() {
    lastDab = null;
    lastSlot = null;
    if (lib.value) syncStamps(lib.value, []);
    composition.value = null;
    kit.value = null;
    kitComposition.value = null;
    strokes.value = [];
    tab.value = 'shape';
    region.value = 'family';
    tool.value = 'spot';
    spot.value = 'm';
    paintColour.value = '#1E1B1A';
    symmetry.value = true;
    turning.value = false;
    order.value = null;
    orderError.value = null;
    payError.value = null;
  }
  return {
    lib, loading, libError, composition, strokes, tab, region, tool, spot, paintColour, symmetry, turning, order, orderError,
    manifest, load, begin, setFamily, setPart, setBase, toggleLayer, setCoverage, setLayerColour, toggleShell, setShellColour, setEyes, setNose, setName,
    paint, undo, placeOrder, refreshOrder, reset, payError, pay, simulatePay,
    kit, kitComposition, active, kitMode, quote, setKitVariant, setTorso, setPose, setKitColour, toggleMarking, fileUrl, kitManifest,
  };
});

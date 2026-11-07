// The part library (decision 127): the kits of a species, the breed open in the rigging workbench, what is selected
// in it, and the edits (saved as they are made, so a closed tab loses nothing).
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { ApiFailure, StudioApi } from '@petpop/core';
import type { Part, PartKit, PartKitSummary, Pose, Species } from '@petpop/core';
import { PAIRS, mirrorAttachment, mirrorOffset, type AttachmentData, type JointData, type Kind, type Slot, type SocketOffset } from '@petpop/scene';

export type Preset = NonNullable<Part['presets']>[number];

type Vec3 = [number, number, number];

export type Target = { type: 'slot'; slot: Slot } | { type: 'part'; partId: string };
export type View = 'assembled' | 'part';

const message = (e: unknown) =>
  e instanceof ApiFailure ? (e.status === 403 ? 'Your role cannot do that.' : typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail)) : 'Something went wrong.';

export const useParts = defineStore('parts', () => {
  const species = ref<Species>('dog');
  const kits = ref<PartKitSummary[]>([]);
  const kit = ref<PartKit | null>(null);
  const target = ref<Target>({ type: 'slot', slot: 'front_left' });
  const view = ref<View>('assembled');
  const gizmo = ref<'translate' | 'rotate'>('translate');
  const preview = ref<Partial<Record<Kind, string>>>({}); // the variant shown per kind (defaults otherwise)
  const poseId = ref<string | null>(null); // the pose previewed
  const scale = ref(true); // fit uploads to the breed's size guess (parts exported one at a time are not in proportion)
  const busy = ref(false);
  const error = ref<string | null>(null);
  const notice = ref<string | null>(null);

  async function run<T>(f: () => Promise<T>): Promise<T | null> {
    busy.value = true;
    error.value = null;
    try {
      return await f();
    } catch (e) {
      error.value = message(e);
      return null;
    } finally {
      busy.value = false;
    }
  }

  const torso = computed(() => kit.value?.parts.find((p) => p.kind === 'torso' && p.variant === variantOf('torso')) ?? null);
  /** The variant shown: the one picked to preview, else the previewed pose's own (sitting folds the hind legs), else
   *  the default. */
  function variantOf(kind: Kind): string {
    return preview.value[kind] ?? pose.value?.variants?.[kind] ?? kit.value?.defaults[kind] ?? 'default';
  }
  /** Whether a customer may choose this variant on this breed (decision 130). */
  function allowed(kind: Kind, variant: string): boolean {
    return (kit.value?.allowed?.[kind] ?? []).includes(variant);
  }
  async function setAllowed(kind: Kind, variant: string, on: boolean) {
    const now = (kit.value?.allowed?.[kind] ?? []).filter((v) => v !== variant);
    await setup({ allowed: { [kind]: on ? [...now, variant] : now } });
  }
  /** A part's stretch on this breed; null puts the size guess back. */
  async function setStretch(part: Part, s: Vec3 | null) {
    await setup({ stretch: { [`${part.kind}/${part.variant}`]: s } });
  }

  /** The breed's default texture configuration: colours, pattern, markings (saved as it is changed). */
  async function setTexture(t: NonNullable<PartKit['texture']>) {
    await setup({ texture: t });
  }

  // ---- torso presets (decision 131): the customers' shape choices, each a stretch and socket offsets
  const presetId = ref<string>('default'); // the preset previewed
  const presets = computed<Preset[]>(() => torso.value?.presets ?? []);
  const preset = computed<Preset | null>(() => presets.value.find((p) => p.preset_id === presetId.value) ?? presets.value[0] ?? null);
  const torsoStretch = computed(() => preset.value?.stretch ?? torso.value?.stretch ?? null);
  /** Socket edits go to this breed's preset offsets when the torso is shared (its sockets are every breed's) or the
   *  preset is not the default; otherwise to the torso's own sockets. */
  const offsetMode = computed(() => !!torso.value && !!preset.value && kit.value?.breed_id !== 'shared'
    && (preset.value.preset_id !== 'default' || !!torso.value.shared));
  // Preset edits apply to the kit here at once and are sent one save at a time, the latest list each time, so quick
  // edits (a rename, then a stretch) never undo each other; the server's answer is taken once nothing is waiting.
  let presetsSaving = false;
  let presetsDirty = false;
  async function savePresets(next: Preset[]) {
    const t = torso.value;
    if (!t) return;
    t.presets = next;
    presetsDirty = true;
    if (presetsSaving) return;
    presetsSaving = true;
    try {
      while (presetsDirty && kit.value) {
        presetsDirty = false;
        const body = { presets: { [`torso/${t.variant}`]: JSON.parse(JSON.stringify(t.presets)) } } as never;
        const r = await run(() => StudioApi.partKitSetup(species.value, kit.value!.breed_id, body));
        if (r && !presetsDirty) kit.value = r;
      }
    } finally {
      presetsSaving = false;
    }
  }
  async function addPreset() {
    const now = presets.value;
    let n = now.length;
    while (now.some((p) => p.preset_id === `preset_${n}`)) n++;
    const base = preset.value;
    const added: Preset = { preset_id: `preset_${n}`, label: `Preset ${n}`, stretch: base?.stretch ? [...base.stretch] : null, sockets: JSON.parse(JSON.stringify(base?.sockets ?? {})) };
    presetId.value = added.preset_id;
    await savePresets([...now, added]);
  }
  async function removePreset(id: string) {
    if (id === 'default') return;
    presetId.value = 'default';
    await savePresets(presets.value.filter((p) => p.preset_id !== id));
  }
  async function renamePreset(id: string, label: string) {
    if (label.trim()) await savePresets(presets.value.map((p) => (p.preset_id === id ? { ...p, label: label.trim() } : p)));
  }
  /** The previewed preset's stretch: the default's is the torso variant's own. */
  async function setPresetStretch(s: Vec3 | null) {
    const t = torso.value, p = preset.value;
    if (!t || !p) return;
    if (p.preset_id === 'default') await setStretch(t, s);
    else await savePresets(presets.value.map((x) => (x.preset_id === p.preset_id ? { ...x, stretch: s } : x)));
  }
  /** Live, unsaved: a socket's offset in the previewed preset, mirrored to its pair and kept on the centre line for
   *  the head and tail by symmetry. saveOffsets() sends it. */
  function setOffset(slot: Slot, off: { translate: number[]; rotate: number[] }) {
    const p = preset.value;
    if (!p) return;
    const sym = kit.value?.symmetry ?? true;
    const fixed = sym && (slot === 'head' || slot === 'tail') ? { translate: [0, off.translate[1], off.translate[2]], rotate: [off.rotate[0], 0, 0] } : off;
    const sockets = { ...(p.sockets ?? {}), [slot]: fixed } as Record<string, SocketOffset>;
    const pair = PAIRS[slot];
    if (sym && pair) sockets[pair] = mirrorOffset(fixed);
    p.sockets = sockets as never;
  }
  async function saveOffsets() {
    await savePresets(presets.value);
  }
  function partOf(kind: Kind): Part | null {
    return kit.value?.parts.find((p) => p.kind === kind && p.variant === variantOf(kind)) ?? null;
  }
  const selectedPart = computed<Part | null>(() => {
    const t = target.value;
    return t.type === 'part' ? kit.value?.parts.find((p) => p.part_id === t.partId) ?? null : null;
  });
  const pose = computed<Pose | null>(() => kit.value?.poses.find((p) => p.pose_id === (poseId.value ?? kit.value?.default_pose)) ?? null);

  async function loadKits() {
    const r = await run(() => StudioApi.partKits(species.value));
    if (r) kits.value = r.items;
  }
  async function upload(files: File[]) {
    const r = await run(() => StudioApi.uploadParts(species.value, files, undefined, scale.value));
    if (r) {
      notice.value =
        `${r.items.length} part${r.items.length === 1 ? '' : 's'} for ${r.breeds.join(', ') || 'no breed'}` +
        (r.skipped.length ? `; skipped: ${r.skipped.join('; ')}` : '') +
        (r.notes?.length ? `. ${r.notes.join('; ')}` : '');
      await loadKits();
    }
    return r;
  }
  async function open(breedId: string) {
    const r = await run(() => StudioApi.partKit(species.value, breedId));
    if (r) {
      kit.value = r;
      preview.value = {};
      poseId.value = null;
      presetId.value = 'default';
      target.value = { type: 'slot', slot: 'front_left' };
    }
    return !!r;
  }
  function select(t: Target) {
    target.value = t;
    view.value = t.type === 'part' ? 'part' : 'assembled';
  }

  /** Live, unsaved: the viewport shows a drag as it happens; save() sends it. Symmetry mirrors a slot to its pair and
   *  keeps the head and tail slots, and the head's and tail's pivots, on the centre line. */
  function setAttachment(slot: Slot, a: AttachmentData) {
    const t = torso.value;
    if (!t?.attachments) return;
    const sym = kit.value?.symmetry ?? true;
    const fixed = sym && (slot === 'head' || slot === 'tail') ? { ...a, position: [0, a.position[1], a.position[2]], axis: [0, a.axis[1], a.axis[2]] } : a;
    const next = { ...t.attachments, [slot]: fixed } as NonNullable<Part['attachments']>;
    const pair = PAIRS[slot];
    if (sym && pair) next[pair] = mirrorAttachment(fixed) as never;
    t.attachments = next;
  }
  function setJoint(partId: string, j: JointData) {
    const p = kit.value?.parts.find((x) => x.part_id === partId);
    if (!p) return;
    const sym = kit.value?.symmetry ?? true;
    p.joint = (sym && (p.kind === 'head' || p.kind === 'tail') ? { ...j, pivot: [0, j.pivot[1], j.pivot[2]], axis: [0, j.axis[1], j.axis[2]] } : j) as never;
  }

  async function save(partId: string, patch: Parameters<typeof StudioApi.editPartRig>[3]) {
    if (!kit.value) return;
    const r = await run(() => StudioApi.editPartRig(species.value, kit.value!.breed_id, partId, patch));
    if (r) kit.value = r;
  }
  async function saveTorso() {
    const t = torso.value;
    if (t?.attachments) await save(t.part_id, { attachments: t.attachments });
  }
  async function saveJoint(partId: string) {
    const p = kit.value?.parts.find((x) => x.part_id === partId);
    if (p?.joint) await save(partId, { joint: p.joint });
  }
  async function reguess(partId: string) {
    if (!kit.value) return;
    const r = await run(() => StudioApi.reguessPart(species.value, kit.value!.breed_id, partId));
    if (r) kit.value = r;
  }
  async function setup(body: Parameters<typeof StudioApi.partKitSetup>[2]) {
    if (!kit.value) return;
    const r = await run(() => StudioApi.partKitSetup(species.value, kit.value!.breed_id, body));
    if (r) kit.value = r;
  }
  async function commit() {
    if (!kit.value) return;
    const r = await run(() => StudioApi.commitPartKit(species.value, kit.value!.breed_id));
    if (r) {
      kit.value = r;
      notice.value = `Committed ${r.breed_label} kit version ${r.version}`;
    }
  }
  return {
    species, kits, kit, target, view, gizmo, preview, poseId, scale, busy, error, notice, torso, selectedPart, pose,
    variantOf, partOf, allowed, setAllowed, setStretch, setTexture,
    presetId, presets, preset, torsoStretch, offsetMode, addPreset, removePreset, renamePreset, setPresetStretch, setOffset, saveOffsets, loadKits, upload, open, select, setAttachment, setJoint, save, saveTorso, saveJoint, reguess, setup, commit,
  };
});

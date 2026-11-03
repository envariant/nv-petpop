<script setup lang="ts">
// The rigging workbench (decision 127): the viewport on the left, the joints and the kit's settings on the right.
// Select a torso slot (assembled view) or a part's own joint (part view); drag with the gizmo or type the numbers;
// symmetry mirrors a left slot onto the right one. Poses: each leg's twist in thirds and the head's angles within its
// limits. Commit freezes the kit as its next version.
import { computed } from 'vue';
import type { Pose } from '@petpop/core';
import { LEG_SLOTS, SLOTS, SLOT_KIND, headProblems, type Kind, type Slot } from '@petpop/scene';
import { Chip, PButton, PRow, PSection, PTitle, cx } from '@petpop/ui-vue';
import { useParts } from '../stores/parts';
import { useSession } from '../stores/session';
import Notice from '../components/Notice.vue';
import RigView from '../components/RigView.vue';
const ps = useParts();
const s = useSession();
const KINDS: Kind[] = ['head', 'torso', 'front_leg', 'hind_leg', 'tail'];
const label = (x: string) => x.replace(/_/g, ' ');
const head = computed(() => ps.partOf('head'));
const limits = computed(() => head.value?.limits ?? { yaw: [-35, 35], pitch: [-25, 25], roll: [-20, 20] });

// the selected joint's numbers
const sel = computed(() => {
  if (ps.target.type === 'slot') {
    const a = ps.torso?.attachments?.[ps.target.slot];
    return a ? { point: a.position, axis: a.axis, twist: a.twist ?? 0, guess: ps.torso?.guess[ps.target.slot] } : null;
  }
  const p = ps.selectedPart;
  return p?.joint ? { point: p.joint.pivot, axis: p.joint.axis, twist: p.joint.twist ?? 0, guess: p.guess.joint } : null;
});
function setNumber(which: 'point' | 'axis' | 'twist', i: number, raw: string) {
  const v = Number(raw);
  if (!Number.isFinite(v) || !sel.value) return;
  const point = [...sel.value.point];
  const axis = [...sel.value.axis];
  let twist = sel.value.twist;
  if (which === 'point') point[i] = v;
  else if (which === 'axis') axis[i] = v;
  else twist = v;
  if (ps.target.type === 'slot') {
    ps.setAttachment(ps.target.slot, { position: point, axis, twist });
    void ps.saveTorso();
  } else {
    ps.setJoint(ps.target.partId, { pivot: point, axis, twist });
    void ps.saveJoint(ps.target.partId);
  }
}

// poses
const poses = computed<Pose[]>(() => ps.kit?.poses ?? []);
function savePoses(next: Pose[], defaultPose?: string) {
  void ps.setup({ poses: next, ...(defaultPose ? { default_pose: defaultPose } : {}) });
}
function setLeg(p: Pose, slot: (typeof LEG_SLOTS)[number], k: 0 | 1 | 2) {
  const sym = ps.kit?.symmetry ?? true;
  const pair = { front_left: 'front_right', front_right: 'front_left', hind_left: 'hind_right', hind_right: 'hind_left' }[slot] as typeof slot;
  const legs = { ...p.legs, [slot]: k, ...(sym ? { [pair]: k } : {}) };
  savePoses(poses.value.map((x) => (x.pose_id === p.pose_id ? { ...x, legs } : x)));
}
function setHead(p: Pose, axis: 'yaw' | 'pitch' | 'roll', raw: string) {
  savePoses(poses.value.map((x) => (x.pose_id === p.pose_id ? { ...x, head: { ...x.head, [axis]: Number(raw) } } : x)));
}
function addPose() {
  const n = poses.value.length + 1;
  savePoses([...poses.value, { pose_id: `pose_${n}`, label: `Pose ${n}`, legs: {}, head: {} }]);
}
function removePose(id: string) {
  if (poses.value.length > 1) savePoses(poses.value.filter((p) => p.pose_id !== id));
}
function setLimit(axis: 'yaw' | 'pitch' | 'roll', i: 0 | 1, raw: string) {
  if (!head.value) return;
  const next = { ...limits.value, [axis]: [...limits.value[axis]] };
  next[axis][i] = Number(raw);
  void ps.save(head.value.part_id, { limits: next });
}
const conf = (c?: number) => (c == null ? '' : c >= 0.8 ? 'bg-accent/20' : c >= 0.5 ? 'bg-line' : 'bg-accent2/30');
</script>

<template>
  <div v-if="ps.kit" class="flex h-full flex-col lg:flex-row" data-testid="rigging">
    <div class="relative h-[45vh] shrink-0 border-b-2 border-line bg-card/60 lg:h-auto lg:flex-1 lg:border-b-0 lg:border-r-2">
      <RigView />
      <div class="absolute left-3 top-3 flex flex-wrap gap-2">
        <Chip :selected="ps.view === 'assembled'" test-id="view-assembled" @click="ps.view = 'assembled'">Assembled</Chip>
        <Chip :selected="ps.view === 'part'" test-id="view-part" @click="ps.view = 'part'">Part</Chip>
        <Chip :selected="ps.gizmo === 'translate'" test-id="gizmo-move" @click="ps.gizmo = 'translate'">Move</Chip>
        <Chip :selected="ps.gizmo === 'rotate'" test-id="gizmo-rotate" @click="ps.gizmo = 'rotate'">Rotate</Chip>
      </div>
    </div>
    <div class="no-scrollbar min-h-0 overflow-y-auto px-4 pb-8 pt-4 lg:w-[30rem] lg:shrink-0">
      <button class="mb-2 text-base text-muted underline" data-testid="rig-back" @click="s.go('parts')">‹ All kits</button>
      <PTitle :sub="`${ps.kit.version ? `Kit v${ps.kit.version}` : 'Not committed yet'}${ps.kit.dirty ? ' · changes to commit' : ''}`">{{ ps.kit.breed_label }}</PTitle>
      <Notice :error="ps.error" :notice="ps.notice" prefix="rig" />

      <PSection title="Joints" test-id="rig-joints">
        <label class="mb-2 flex items-center gap-2 text-base">
          <input type="checkbox" :checked="ps.kit.symmetry" data-testid="rig-symmetry" @change="ps.setup({ symmetry: ($event.target as HTMLInputElement).checked })" />
          Symmetry (mirror left and right, keep the head and tail on the centre line)
        </label>
        <div class="flex flex-col gap-1">
          <button v-for="slot in (SLOTS as Slot[])" :key="slot" :data-testid="`joint-slot-${slot}`"
            :class="cx('hit flex items-center justify-between rounded-xl px-3 py-1.5 text-left text-base', ps.target.type === 'slot' && ps.target.slot === slot ? 'bg-accent text-white' : 'bg-card')"
            @click="ps.select({ type: 'slot', slot })">
            <span>Torso · {{ label(slot) }}</span>
            <span :class="['rounded-full px-2 text-xs text-ink', conf(ps.torso?.guess[slot]?.confidence)]">{{ ps.torso?.guess[slot]?.method }}</span>
          </button>
          <button v-for="kind in KINDS.filter((k) => k !== 'torso')" :key="kind" :data-testid="`joint-part-${kind}`"
            :class="cx('hit flex items-center justify-between rounded-xl px-3 py-1.5 text-left text-base', ps.target.type === 'part' && ps.target.partId === ps.partOf(kind)?.part_id ? 'bg-accent text-white' : 'bg-card')"
            @click="ps.partOf(kind) && ps.select({ type: 'part', partId: ps.partOf(kind)!.part_id })">
            <span>{{ label(kind) }} pivot <i v-if="ps.partOf(kind)?.edited" class="text-xs">(edited)</i></span>
            <span :class="['rounded-full px-2 text-xs text-ink', conf(ps.partOf(kind)?.guess.joint?.confidence)]">{{ ps.partOf(kind)?.guess.joint?.method ?? 'missing' }}</span>
          </button>
        </div>
      </PSection>

      <PSection v-if="sel" title="Selected joint" test-id="rig-selected">
        <div class="grid grid-cols-[4.5rem_1fr_1fr_1fr] items-center gap-1 text-sm">
          <span>{{ ps.target.type === 'slot' ? 'Position' : 'Pivot' }}</span>
          <input v-for="i in [0, 1, 2]" :key="`p${i}`" type="number" step="0.5" :value="sel.point[i]" :data-testid="`rig-point-${i}`"
            class="min-w-0 rounded-lg border-2 border-line bg-paper px-2 py-1" @change="setNumber('point', i, ($event.target as HTMLInputElement).value)" />
          <span>Axis</span>
          <input v-for="i in [0, 1, 2]" :key="`a${i}`" type="number" step="0.05" :value="Number(sel.axis[i]).toFixed(3)" :data-testid="`rig-axis-${i}`"
            class="min-w-0 rounded-lg border-2 border-line bg-paper px-2 py-1" @change="setNumber('axis', i, ($event.target as HTMLInputElement).value)" />
          <span>Twist °</span>
          <input type="range" min="0" max="359" :value="sel.twist" class="col-span-2" data-testid="rig-twist" @change="setNumber('twist', 0, ($event.target as HTMLInputElement).value)" />
          <span>{{ Math.round(sel.twist) }}</span>
        </div>
        <p v-if="sel.guess" class="mt-1 text-xs text-muted">First guess: {{ sel.guess.method }}, confidence {{ Math.round(sel.guess.confidence * 100) }}%</p>
        <PButton v-if="ps.target.type === 'part'" variant="ghost" test-id="rig-reguess" @click="ps.target.type === 'part' && ps.reguess(ps.target.partId)">Back to the first guess</PButton>
      </PSection>

      <PSection title="Variants" test-id="rig-variants">
        <div v-for="kind in KINDS" :key="kind" class="mb-1 flex flex-wrap items-center gap-2 text-base">
          <span class="w-24 text-muted">{{ label(kind) }}</span>
          <PRow>
            <Chip v-for="p in ps.kit.parts.filter((x) => x.kind === kind)" :key="p.part_id" :selected="ps.variantOf(kind) === p.variant"
              :test-id="`variant-${kind}-${p.variant}`" @click="ps.preview = { ...ps.preview, [kind]: p.variant }">
              {{ p.label }}{{ ps.kit.defaults[kind] === p.variant ? ' ★' : '' }}
            </Chip>
          </PRow>
          <button v-if="ps.kit.defaults[kind] !== ps.variantOf(kind)" class="text-sm underline" :data-testid="`variant-default-${kind}`"
            @click="ps.setup({ defaults: { [kind]: ps.variantOf(kind) } })">make default</button>
        </div>
      </PSection>

      <PSection v-if="head" title="Head limits (degrees)" test-id="rig-limits">
        <div v-for="ax in (['yaw', 'pitch', 'roll'] as const)" :key="ax" class="mb-1 grid grid-cols-[4rem_1fr_1fr] items-center gap-2 text-sm">
          <span>{{ ax }}</span>
          <input v-for="i in ([0, 1] as const)" :key="i" type="number" step="5" :value="limits[ax][i]" :data-testid="`limit-${ax}-${i}`"
            class="min-w-0 rounded-lg border-2 border-line bg-paper px-2 py-1" @change="setLimit(ax, i, ($event.target as HTMLInputElement).value)" />
        </div>
      </PSection>

      <PSection title="Poses" test-id="rig-poses">
        <div v-for="p in poses" :key="p.pose_id" class="mb-3 rounded-tile bg-card p-3 shadow-soft" :data-testid="`pose-${p.pose_id}`">
          <div class="mb-2 flex items-center gap-2">
            <input :value="p.label" class="min-w-0 flex-1 rounded-lg border-2 border-line bg-paper px-2 py-1 text-base" :data-testid="`pose-label-${p.pose_id}`"
              @change="savePoses(poses.map((x) => (x.pose_id === p.pose_id ? { ...x, label: ($event.target as HTMLInputElement).value } : x)))" />
            <Chip :selected="(ps.poseId ?? ps.kit.default_pose) === p.pose_id" :test-id="`pose-preview-${p.pose_id}`" @click="ps.poseId = p.pose_id">Preview</Chip>
            <Chip :selected="ps.kit.default_pose === p.pose_id" :test-id="`pose-default-${p.pose_id}`" @click="savePoses(poses, p.pose_id)">Default</Chip>
            <button v-if="poses.length > 1" class="text-sm underline" :data-testid="`pose-remove-${p.pose_id}`" @click="removePose(p.pose_id)">Remove</button>
          </div>
          <div v-for="leg in LEG_SLOTS" :key="leg" class="flex items-center gap-2 text-sm">
            <span class="w-24">{{ label(leg) }}</span>
            <Chip v-for="k in ([0, 1, 2] as const)" :key="k" :selected="(p.legs?.[leg] ?? 0) === k" :test-id="`pose-${p.pose_id}-${leg}-${k}`" @click="setLeg(p, leg, k)">{{ k * 120 }}°</Chip>
          </div>
          <div v-for="ax in (['yaw', 'pitch', 'roll'] as const)" :key="ax" class="flex items-center gap-2 text-sm">
            <span class="w-24">head {{ ax }}</span>
            <input type="range" :min="limits[ax][0]" :max="limits[ax][1]" :value="p.head?.[ax] ?? 0" class="flex-1" :data-testid="`pose-${p.pose_id}-head-${ax}`"
              @change="setHead(p, ax, ($event.target as HTMLInputElement).value)" />
            <span class="w-10 text-right">{{ p.head?.[ax] ?? 0 }}</span>
          </div>
          <p v-for="w in headProblems(p, limits)" :key="w" class="text-xs text-accent2">{{ w }}</p>
        </div>
        <PButton variant="soft" test-id="pose-add" @click="addPose">Add a pose</PButton>
      </PSection>

      <PSection title="Commit" test-id="rig-commit">
        <ul v-if="ps.kit.problems.length" class="mb-2 list-disc pl-5 text-sm text-accent2" data-testid="rig-problems">
          <li v-for="p in ps.kit.problems" :key="p">{{ p }}</li>
        </ul>
        <PButton :disabled="ps.busy || !!ps.kit.problems.length || !ps.kit.dirty" test-id="rig-commit-button" @click="ps.commit()">
          Commit kit v{{ ps.kit.version + 1 }}
        </PButton>
      </PSection>
      <p class="text-xs text-muted">Slots: {{ SLOTS.map((x) => `${label(x)} (${label(SLOT_KIND[x])})`).join(', ') }}.</p>
    </div>
  </div>
</template>

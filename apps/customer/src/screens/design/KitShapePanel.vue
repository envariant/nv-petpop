<script setup lang="ts">
// Shape for a figure of part kits (decision 136): the body (each torso the breed offers, in each of its shapes), the
// legs, tail and head when the breed offers more than one, and the pose. Each choice re-places the parts at once.
import { computed } from 'vue';
import { offered, partOf, type Kind } from '@petpop/scene';
import { Chip, PRow, PSection, Tile } from '@petpop/ui-vue';
import { useDesign } from '../../stores/design';
const d = useDesign();
const kit = computed(() => d.kit!);
const c = computed(() => d.kitComposition!);
const KIND_LABEL: Partial<Record<Kind, string>> = { head: 'Head', front_leg: 'Front legs', hind_leg: 'Back legs', tail: 'Tail' };
const bodies = computed(() => offered(kit.value, 'torso').flatMap((v) => {
  const part = partOf(kit.value, 'torso', v);
  const presets = part?.presets?.length ? part.presets : [{ preset_id: 'default', label: 'Standard' }];
  return presets.map((p) => ({ variant: v, preset: p.preset_id, label: presets.length > 1 && p.preset_id !== 'default' ? `${part?.label ?? v} · ${p.label}` : part?.label ?? v }));
}));
// a variant a pose swaps in (the sitting hind legs) comes with that pose, not on its own
const posed = computed(() => new Set(kit.value.poses.flatMap((p) => Object.values(p.variants ?? {}))));
const kinds = computed(() => (['front_leg', 'hind_leg', 'tail', 'head'] as Kind[])
  .map((k) => ({ kind: k, variants: offered(kit.value, k).filter((v) => !posed.value.has(v)) }))
  .filter((x) => x.variants.length > 1));
const label = (kind: Kind, v: string) => partOf(kit.value, kind, v)?.label ?? v.replace(/_/g, ' ');
</script>

<template>
  <PSection title="Body" test-id="kit-bodies">
    <div class="grid grid-cols-[repeat(auto-fill,minmax(7rem,1fr))] gap-2">
      <Tile v-for="b in bodies" :key="`${b.variant}-${b.preset}`" :label="b.label" :test-id="`kit-body-${b.variant}-${b.preset}`"
        :selected="c.variants.torso === b.variant && c.preset_id === b.preset" @click="d.setTorso(b.variant, b.preset)" />
    </div>
  </PSection>
  <PSection v-for="k in kinds" :key="k.kind" :title="KIND_LABEL[k.kind]!" :test-id="`kit-kind-${k.kind}`">
    <PRow>
      <Chip v-for="v in k.variants" :key="v" :selected="c.variants[k.kind] === v" :test-id="`kit-${k.kind}-${v}`" @click="d.setKitVariant(k.kind, v)">{{ label(k.kind, v) }}</Chip>
    </PRow>
  </PSection>
  <PSection v-if="kit.poses.length > 1" title="Pose" test-id="kit-poses">
    <PRow>
      <Chip v-for="p in kit.poses" :key="p.pose_id" :selected="c.pose_id === p.pose_id" :test-id="`kit-pose-${p.pose_id}`" @click="d.setPose(p.pose_id)">{{ p.label }}</Chip>
    </PRow>
  </PSection>
</template>

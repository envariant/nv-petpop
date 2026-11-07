<script setup lang="ts">
// Design (BRIEF Section 16): the customer assembles the figurine from the library and paints it. Portrait: the
// preview on top, the tools below; landscape: the preview on the left, the tools in a column on the right. A breed with
// a part kit in the release is a figure of parts (decision 136): its own Shape and Markings tabs, no Paint or Extras.
import { computed, ref, watch } from 'vue';
import { FigureView, KitFigureView, PButton, PTitle, cx } from '@petpop/ui-vue';
import { useDesign, type Tab } from '../stores/design';
import { useSession } from '../stores/session';
import ShapePanel from './design/ShapePanel.vue';
import PatternsPanel from './design/PatternsPanel.vue';
import PaintPanel from './design/PaintPanel.vue';
import ExtrasPanel from './design/ExtrasPanel.vue';
import KitShapePanel from './design/KitShapePanel.vue';
import KitMarkingsPanel from './design/KitMarkingsPanel.vue';
const s = useSession();
const d = useDesign();
const TABS: { id: Tab; label: string }[] = [
  { id: 'shape', label: 'Shape' },
  { id: 'patterns', label: 'Markings' },
  { id: 'paint', label: 'Paint' },
  { id: 'extras', label: 'Extras' },
];
const tabs = computed(() => (d.kitMode ? TABS.filter((t) => t.id === 'shape' || t.id === 'patterns') : TABS));
const panels = computed(() => (d.kitMode ? { shape: KitShapePanel, patterns: KitMarkingsPanel, paint: KitShapePanel, extras: KitShapePanel }
  : { shape: ShapePanel, patterns: PatternsPanel, paint: PaintPanel, extras: ExtrasPanel }));
watch(() => s.breed, (b) => {
  if (b && (!d.active || d.active.breed_id !== b.id || d.active.species !== b.species)) void d.begin(b);
}, { immediate: true });
const showQuote = ref(false);
const ready = computed(() => (d.kitMode ? !!(d.kit && d.kitComposition) : !!(d.lib && d.composition)));
const painting = computed(() => d.tab === 'paint' && !d.turning);
/** Dev and test builds only: gate 7 bakes the on-screen atlas and compares it with the export's (print = screen). */
const onBake = (bake: () => Uint8Array) => {
  if (import.meta.env.DEV) (window as unknown as { __petpop: unknown }).__petpop = { bake, composition: () => d.composition };
};
</script>

<template>
  <div v-if="!s.breed" />
  <div v-else-if="d.libError" class="flex h-full flex-col items-center justify-center gap-4 px-6 text-center" data-testid="design-error">
    <PTitle sub="Please ask a member of staff.">{{ d.libError }}</PTitle>
  </div>
  <div v-else class="flex h-full flex-col gap-3 px-4 pb-4 pt-2 md:px-8 landscape:md:flex-row landscape:md:gap-6" data-testid="design">
    <div :class="cx('relative order-2 h-[42%] min-h-[14rem] shrink-0 overflow-hidden rounded-tile bg-card shadow-soft landscape:md:order-1 landscape:md:h-full landscape:md:flex-1', painting && 'ring-highlight')">
      <KitFigureView v-if="ready && d.kitMode" :manifest="d.kitManifest()" :kit="d.kit!" :composition="d.kitComposition!" :url="d.fileUrl" />
      <FigureView v-else-if="ready" :lib="d.lib!" :composition="d.composition!" :paint="painting" :on-bake="onBake" @paint="d.paint" />
      <div v-else class="flex h-full items-center justify-center text-xl text-muted" data-testid="design-loading">Getting the parts ready…</div>
    </div>
    <div class="contents landscape:md:order-2 landscape:md:flex landscape:md:min-h-0 landscape:md:w-[min(42%,34rem)] landscape:md:flex-col landscape:md:gap-3">
      <h1 class="order-1 font-display text-2xl font-semibold md:text-3xl">Design your {{ s.breed.label }}</h1>
      <div class="order-3 flex gap-2" role="tablist">
        <button v-for="t in tabs" :key="t.id" role="tab" :aria-selected="d.tab === t.id" :data-testid="`tab-${t.id}`"
          :class="cx('press hit flex-1 rounded-tile py-2 font-display text-base font-semibold md:py-3 md:text-xl', d.tab === t.id ? 'bg-accent text-white shadow-soft' : 'bg-card text-ink')"
          @click="d.tab = t.id">{{ t.label }}</button>
      </div>
      <div class="no-scrollbar order-4 min-h-0 flex-1 overflow-y-auto" :data-testid="`panel-${d.tab}`">
        <component :is="panels[d.tab]" v-if="ready" />
      </div>
      <div v-if="showQuote && d.quote" class="order-5 rounded-tile bg-card px-4 py-2 text-base shadow-soft" data-testid="design-quote">
        <div v-for="(it, i) in d.quote.items" :key="i" class="flex justify-between"><span>{{ it.label }}</span><span>S${{ it.amount }}</span></div>
      </div>
      <div class="order-5 flex items-center gap-3">
        <button v-if="d.quote" class="press hit rounded-tile bg-card px-4 py-2 font-display text-lg font-semibold shadow-soft md:text-xl" data-testid="design-price"
          :aria-expanded="showQuote" @click="showQuote = !showQuote">S${{ d.quote.total.amount }}</button>
        <PButton v-if="s.bespokeEnabled" variant="soft" test-id="make-unique" :disabled="!ready" @click="s.go('bespoke')">Make it unique</PButton>
        <PButton class="flex-1" test-id="to-name" :disabled="!ready" @click="s.go('name')">Next: name it ›</PButton>
      </div>
    </div>
  </div>
</template>

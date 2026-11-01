<script setup lang="ts">
// One-off figurine, step 3: Build. The visual selectors (BRIEF Section 4 table) beside the live 3D preview; on a
// narrow screen the preview sits on top. Every tap is a user override and is protected from the brief parser.
import { computed } from 'vue';
import tilesIndex from '@assets/tiles/index.json';
import type { PetSpec } from '@petpop/core';
import { PSection, PreviewView } from '@petpop/ui-vue';
import { useSession } from '../stores/session';
import NavBar from '../components/NavBar.vue';
import TileRow from './build/TileRow.vue';
import ChipPick from './build/ChipPick.vue';
import Palette from './build/Palette.vue';
import Markings from './build/Markings.vue';
import Eyes from './build/Eyes.vue';
import Accessories from './build/Accessories.vue';
import type { Species } from './build/vocab';
const s = useSession();
const tiles = tilesIndex as Record<Species, Record<string, string[]>>;
const t = computed(() => tiles[(s.spec?.species ?? 'dog') as Species]);
</script>

<template>
  <div v-if="s.spec" class="flex h-full flex-col">
    <div class="flex min-h-0 flex-1 flex-col md:flex-row">
      <aside class="relative h-56 shrink-0 border-b-2 border-line bg-card/60 md:order-2 md:h-auto md:w-[min(40%,34rem)] md:border-b-0 md:border-l-2">
        <div class="absolute inset-0"><PreviewView :spec="s.spec as PetSpec" /></div>
        <span class="absolute left-4 top-4 rounded-full bg-ink/80 px-3 py-0.5 text-sm font-semibold uppercase tracking-wider text-paper">Preview</span>
      </aside>
      <div class="no-scrollbar min-h-0 flex-1 overflow-y-auto px-4 pb-8 pt-6 md:order-1 md:px-8" data-testid="build-scroll">
        <h1 class="font-display text-3xl font-semibold md:text-4xl">Build {{ s.spec.breed.id === 'mixed' ? 'your pet' : `your ${s.spec.breed.label}` }}</h1>
        <p class="mb-6 mt-1 text-base text-muted md:text-lg">We filled in the breed look. Pick anything to change it.</p>
        <PSection title="Body size and build" test-id="sel-body">
          <TileRow path="body.size" :values="t['body.size']" />
          <div class="mt-3 flex flex-col gap-2">
            <ChipPick path="body.build" :values="['slim', 'standard', 'stocky']" />
            <ChipPick path="body.leg_length" :values="['short', 'medium', 'long']" />
          </div>
        </PSection>
        <PSection title="Coat length" test-id="sel-coat"><TileRow path="coat.length" :values="t['coat.length']" /></PSection>
        <PSection title="Main colour" test-id="sel-base"><Palette path="colour.base" /></PSection>
        <PSection title="Second colour" test-id="sel-secondary"><Palette path="colour.secondary" optional /></PSection>
        <PSection title="Pattern and markings" test-id="sel-pattern">
          <TileRow path="colour.pattern" :values="t['colour.pattern']" />
          <Markings />
        </PSection>
        <PSection title="Ears" test-id="sel-ears"><TileRow path="ears.shape" :values="t['ears.shape']" /></PSection>
        <PSection title="Tail" test-id="sel-tail"><TileRow path="tail.type" :values="t['tail.type']" /></PSection>
        <PSection title="Muzzle" test-id="sel-muzzle"><TileRow path="head.muzzle_length" :values="t['head.muzzle_length']" /></PSection>
        <PSection title="Eyes" test-id="sel-eyes"><Eyes /></PSection>
        <PSection title="Accessories" test-id="sel-accessories"><Accessories /></PSection>
      </div>
    </div>
    <NavBar :back="() => s.go('breed')" :next="() => s.go('brief')" />
  </div>
</template>

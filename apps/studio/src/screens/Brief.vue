<script setup lang="ts">
// One-off figurine, step 4: Brief (free text parsed into the same PetSpec; a tapped field is never changed).
import { computed, ref } from 'vue';
import { StudioApi } from '@petpop/core';
import { Chip, PButton, PRow, PTitle } from '@petpop/ui-vue';
import { useSession } from '../stores/session';
import NavBar from '../components/NavBar.vue';
import { changedLabels } from './brief';
const s = useSession();
const busy = ref(false);
const failed = ref(false);
const EXAMPLES = ['loves snacks', 'one ear that flops', 'chunky', 'fluffy tail', 'white socks', 'blue eyes', 'red collar', 'cheeky'];
const name = computed(() => (s.spec as { pet_name?: string } | null)?.pet_name || (s.species === 'cat' ? 'your cat' : 'your dog'));
const changed = computed(() => changedLabels(s.highlights));
const add = (e: string) => s.setBrief((s.briefText ? `${s.briefText.replace(/[ ,]+$/, '')}, ` : '') + e);
async function read() {
  if (!s.spec || !s.species) return;
  busy.value = true;
  failed.value = false;
  try {
    s.applyParse(await StudioApi.parse(s.species, JSON.parse(JSON.stringify(s.spec)), s.briefText, [...s.tapped]));
  } catch {
    failed.value = true;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="no-scrollbar min-h-0 flex-1 overflow-y-auto">
      <div class="mx-auto max-w-4xl px-4 pt-6 md:px-8 md:pt-8">
        <PTitle sub="Anything that makes them them. We'll match it to the swatches.">Tell us about {{ name }}</PTitle>
        <textarea :value="s.briefText" rows="3" maxlength="500" placeholder="e.g. a chunky corgi with one floppy ear who loves snacks" data-testid="brief-text"
          class="w-full resize-none rounded-tile border-4 border-line bg-card px-4 py-3 text-lg outline-none focus:border-accent md:text-xl"
          @input="s.setBrief(($event.target as HTMLTextAreaElement).value)" />
        <div class="my-4"><PRow>
          <Chip v-for="e in EXAMPLES" :key="e" :test-id="`example-${e}`" @click="add(e)">+ {{ e }}</Chip>
        </PRow></div>
        <div class="mb-4 flex flex-wrap items-center gap-4">
          <PButton variant="soft" :disabled="busy || !s.briefText.trim()" test-id="brief-apply" @click="read">{{ busy ? 'Reading…' : 'Use my words' }}</PButton>
          <div class="text-base md:text-lg" data-testid="brief-result" aria-live="polite">
            <span v-if="failed || s.parse?.flavour_only" class="text-muted">We'll use your words for flavour only.</span>
            <span v-if="s.parse && !s.parse.flavour_only && changed.length">Updated: <b>{{ changed.join(', ') }}</b></span>
            <span v-if="s.parse?.blocked" class="block text-muted">Some words were skipped.</span>
          </div>
        </div>
        <button v-if="s.parse && changed.length" class="mb-4 text-lg text-accent underline" data-testid="brief-review" @click="s.go('build')">See the changes on the swatches</button>
      </div>
    </div>
    <NavBar :back="() => s.go('build')" :next="() => s.go('name')" :next-label="s.briefText.trim() && !s.parse ? 'Skip' : 'Next'" />
  </div>
</template>

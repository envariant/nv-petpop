<script setup lang="ts">
// One-off figurine, step 5: name, summary and where it runs, then Generate.
import { computed } from 'vue';
import { label } from '@petpop/core';
import { PTitle } from '@petpop/ui-vue';
import { useSession } from '../stores/session';
import NavBar from '../components/NavBar.vue';
import ProfilePicker from '../components/ProfilePicker.vue';
const s = useSession();
const petName = computed(() => (s.spec as { pet_name?: string } | null)?.pet_name ?? '');
const facts = computed<[string, string][]>(() => {
  const spec = s.spec;
  if (!spec) return [];
  const f: [string, string][] = [
    ['Breed', spec.breed.label],
    ['Colour', `${label(spec.colour.base.name)}${spec.colour.secondary ? ` & ${label(spec.colour.secondary.name)}` : ''}, ${label(spec.colour.pattern)}`],
    ['Ears / tail', `${label(spec.ears.shape)} ears, ${label(spec.tail.type)} tail`],
    ['Eyes', label(spec.eyes.colour)],
    ['Accessories', spec.accessories.length ? spec.accessories.map((a) => label(a.type)).join(', ') : 'None'],
  ];
  if (spec.personality?.length) f.push(['Personality', spec.personality.join(', ')]);
  return f;
});
</script>

<template>
  <div v-if="s.spec" class="flex h-full flex-col">
    <div class="no-scrollbar min-h-0 flex-1 overflow-y-auto">
      <div class="mx-auto grid max-w-6xl gap-6 px-4 pt-6 md:px-8 md:pt-8 lg:grid-cols-2">
        <div>
          <PTitle sub="This name goes on the figurine's page.">What's their name?</PTitle>
          <input :value="petName" placeholder="Pet name" maxlength="24" data-testid="name-text" autocomplete="off"
            class="w-full rounded-tile border-4 border-line bg-card px-4 py-3 text-lg outline-none focus:border-accent md:text-xl"
            @input="s.setName(($event.target as HTMLInputElement).value)" />
          <div class="mt-6 rounded-tile bg-card p-6 shadow-soft" data-testid="summary-card">
            <h2 class="mb-4 font-display text-3xl font-semibold">{{ petName || 'Your pet' }}</h2>
            <dl class="grid grid-cols-[8rem_1fr] gap-y-2 text-base md:text-lg">
              <div v-for="[k, v] in facts" :key="k" class="contents"><dt class="text-muted">{{ k }}</dt><dd>{{ v }}</dd></div>
            </dl>
          </div>
        </div>
        <div>
          <ProfilePicker />
          <p v-if="s.error" class="mt-4 text-lg font-semibold text-accent2" data-testid="generate-error">{{ s.error }}</p>
        </div>
      </div>
    </div>
    <NavBar :back="() => s.go('brief')" :next="() => void s.generate()" next-label="Generate" :next-disabled="!petName.trim()" />
  </div>
</template>

<script setup lang="ts">
// A breed's default texture configuration (decision 131), edited in the workbench: up to three colours (each a swatch
// and a name), the pattern, and the markings (names the per-part masks are made for: blaze, socks, ...). Every change
// is saved as it is made; the kit then has changes to commit. Edits go to a working copy at once and are sent one save
// at a time, the latest copy each time, so quick edits never undo each other.
import { computed, ref, watch } from 'vue';
import type { PartKit } from '@petpop/core';
import { Chip, PButton, PRow } from '@petpop/ui-vue';
import { useParts } from '../stores/parts';
import LazyInput from './LazyInput.vue';
import { MARKINGS, PATTERNS, slug, words } from '../texture';

type Texture = NonNullable<PartKit['texture']>;
type Colour = Texture['base'];
const ps = useParts();
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
const t = ref<Texture | null>(clone(ps.kit?.texture ?? null));
let saving = false;
let dirty = false;
watch(() => ps.kit?.texture, (now) => {
  if (!saving && !dirty) t.value = clone(now ?? null); // the server's, unless edits are on their way
}, { deep: true });
async function flush() {
  if (saving) return;
  saving = true;
  try {
    while (dirty && t.value) {
      dirty = false;
      await ps.setTexture(clone(t.value));
    }
  } finally {
    saving = false;
  }
}
const SLOTS = [['base', 'Colour A'], ['secondary', 'Colour B'], ['tertiary', 'Colour C']] as const;
type Which = (typeof SLOTS)[number][0];
const newMarking = ref('');

function save(next: Partial<Texture>) {
  if (!t.value) return;
  t.value = { ...t.value, ...next } as Texture;
  dirty = true;
  void flush();
}
function setColour(which: Which, part: 'hex' | 'name', raw: string) {
  const now = (t.value?.[which] ?? { hex: '#ffffff' }) as Colour;
  const value = part === 'hex' ? raw.toUpperCase() : raw.trim() || null;
  save({ [which]: { ...now, [part]: value } });
}
// a colour picker fires input as it moves and change when it closes (not in every browser): save once it settles
let pending: ReturnType<typeof setTimeout> | null = null;
function pickColour(which: Which, raw: string) {
  if (pending) clearTimeout(pending);
  pending = setTimeout(() => {
    pending = null;
    if (t.value?.[which]?.hex?.toUpperCase() !== raw.toUpperCase()) setColour(which, 'hex', raw);
  }, 300);
}
function dropColour(which: 'secondary' | 'tertiary') {
  save(which === 'secondary' && t.value?.tertiary ? { secondary: t.value.tertiary, tertiary: null } : { [which]: null });
}
function addMarking(raw: string) {
  const m = slug(raw);
  if (m && t.value && !t.value.markings?.includes(m)) save({ markings: [...(t.value.markings ?? []), m] });
  newMarking.value = '';
}
function dropMarking(m: string) {
  save({ markings: (t.value?.markings ?? []).filter((x) => x !== m) });
}
const patterns = computed(() => [...new Set([...PATTERNS, ...(t.value?.pattern ? [t.value.pattern] : [])])]);
const unused = computed(() => MARKINGS.filter((m) => !(t.value?.markings ?? []).includes(m)));
const shown = (which: Which) => which === 'base' || !!t.value?.[which];
</script>

<template>
  <div data-testid="texture-editor">
    <PButton v-if="!t" variant="soft" test-id="texture-start" @click="t = { base: { name: null, hex: '#C8763A' }, secondary: null, tertiary: null, pattern: 'solid', markings: [] }; save({})">
      Give this breed a default texture
    </PButton>
    <template v-else>
      <div v-for="[which, title] in SLOTS" :key="which" class="mb-1 flex items-center gap-2 text-sm">
        <template v-if="shown(which)">
          <span class="w-20 text-muted">{{ title }}</span>
          <input type="color" :value="t[which]!.hex" class="h-8 w-10 cursor-pointer rounded border-2 border-line bg-paper" :data-testid="`texture-${which}-hex`"
            @input="pickColour(which, ($event.target as HTMLInputElement).value)" @change="pickColour(which, ($event.target as HTMLInputElement).value)" />
          <LazyInput :value="t[which]!.name ?? ''" placeholder="name (e.g. red)" class="w-32 min-w-0 rounded-lg border-2 border-line bg-paper px-2 py-1" :data-testid="`texture-${which}-name`"
            @commit="(v) => setColour(which, 'name', v)" />
          <span class="font-mono text-xs text-muted">{{ t[which]!.hex }}</span>
          <button v-if="which !== 'base'" class="underline" :data-testid="`texture-${which}-remove`" @click="dropColour(which)">remove</button>
        </template>
      </div>
      <button v-if="!t.secondary" class="mb-1 text-sm underline" data-testid="texture-secondary-add" @click="setColour('secondary', 'hex', '#F4EFE6')">add colour B</button>
      <button v-else-if="!t.tertiary" class="mb-1 text-sm underline" data-testid="texture-tertiary-add" @click="setColour('tertiary', 'hex', '#3B2412')">add colour C</button>
      <label class="mt-1 flex items-center gap-2 text-sm">
        <span class="w-20 text-muted">Pattern</span>
        <select :value="t.pattern ?? ''" class="rounded-lg border-2 border-line bg-paper px-2 py-1" data-testid="texture-pattern"
          @change="save({ pattern: ($event.target as HTMLSelectElement).value || null })">
          <option value="">none</option>
          <option v-for="p in patterns" :key="p" :value="p">{{ words(p) }}</option>
        </select>
      </label>
      <div class="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <span class="w-20 text-muted">Markings</span>
        <PRow>
          <Chip v-for="mk in t.markings ?? []" :key="mk" :test-id="`marking-${mk}`" @click="dropMarking(mk)">{{ words(mk) }} ×</Chip>
        </PRow>
      </div>
      <div class="ml-[5.5rem] mt-1 flex flex-wrap items-center gap-2 text-sm">
        <button v-for="mk in unused" :key="mk" class="underline" :data-testid="`marking-add-${mk}`" @click="addMarking(mk)">+ {{ words(mk) }}</button>
        <input v-model="newMarking" placeholder="another marking" class="w-36 rounded-lg border-2 border-line bg-paper px-2 py-1" data-testid="marking-new"
          @keydown.enter="addMarking(newMarking)" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
// The part library (decision 127): each breed's kit of parts. Upload labelled GLBs (<breed>__<kind>[__<variant>].glb,
// docs/PARTS.md); Studio guesses every joint; open a breed to rig it in the workbench and commit it.
import { onMounted, ref, watch } from 'vue';
import { PButton, PTitle, cx } from '@petpop/ui-vue';
import { useParts } from '../stores/parts';
import { useSession } from '../stores/session';
import Notice from '../components/Notice.vue';
import Page from '../components/Page.vue';
const ps = useParts();
const s = useSession();
const input = ref<HTMLInputElement | null>(null);
const KINDS = ['head', 'torso', 'front_leg', 'hind_leg', 'tail'] as const;
onMounted(() => void ps.loadKits());
watch(() => ps.species, () => void ps.loadKits());
async function upload(e: Event) {
  const files = Array.from((e.target as HTMLInputElement).files ?? []);
  if (files.length) await ps.upload(files);
  if (input.value) input.value.value = '';
}
async function open(breedId: string) {
  if (await ps.open(breedId)) s.go('rigging');
}
</script>

<template>
  <Page test-id="parts" wide>
    <PTitle sub="Each breed is a kit of five parts rigged at joints. Upload labelled GLBs or OBJs, then open a breed to place its joints and poses, and commit it.">Parts</PTitle>
    <Notice :error="ps.error" :notice="ps.notice" prefix="parts" />
    <div class="mb-6 flex flex-wrap items-center gap-3">
      <button v-for="sp in (['dog', 'cat'] as const)" :key="sp" :data-testid="`parts-species-${sp}`"
        :class="cx('hit rounded-full border-4 px-4 py-1.5 font-display', ps.species === sp ? 'border-accent bg-accent text-white' : 'border-line bg-card')"
        @click="ps.species = sp">{{ sp === 'dog' ? 'Dogs' : 'Cats' }}</button>
      <label class="ml-auto flex cursor-pointer items-center gap-2 text-base" title="Each part exported on its own comes at its own scale: fit it to the breed's size guess (decision 128). Turn off for parts split from one figure.">
        <input v-model="ps.scale" type="checkbox" class="h-5 w-5" data-testid="parts-scale" />
        Scale to size guess
      </label>
      <label class="press hit cursor-pointer rounded-tile bg-accent px-5 py-2.5 font-display text-lg font-semibold text-white shadow-soft">
        {{ ps.busy ? 'Uploading…' : 'Upload parts' }}
        <input ref="input" type="file" accept=".glb,.obj,.mtl,.png,.jpg,.jpeg" multiple class="hidden" data-testid="parts-upload" @change="upload" />
      </label>
    </div>
    <p class="mb-4 text-sm text-muted md:text-base">Name files <code>&lt;breed&gt;__&lt;kind&gt;[__&lt;variant&gt;].glb</code> (or <code>.obj</code> with its <code>.mtl</code> and textures in the same upload, quads welcome: Blender composes from the original), kind one of head, torso, front_leg (or fore_leg), hind_leg, hind_leg_sitting, tail; breed <code>shared</code> for the shared library of torsos, legs and tails every breed draws on, a head per breed; +Y up, the pet facing +Z. Each part is fitted to its size guess unless you turn that off. Marking and pattern masks: <code>&lt;template&gt;__&lt;name&gt;.png</code>, e.g. <code>dog-torso-1__white_chest.png</code> (docs/PARTS.md).</p>
    <p v-if="!ps.kits.length" class="text-base text-muted" data-testid="parts-empty">No kits yet.</p>
    <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="parts-kits">
      <div v-for="k in ps.kits" :key="k.breed_id" class="flex flex-col gap-2 rounded-tile bg-card p-4 shadow-soft" :data-testid="`kit-${k.breed_id}`">
        <div class="flex items-center justify-between gap-2">
          <b class="font-display text-xl">{{ k.breed_label }}</b>
          <span class="rounded-full px-3 py-0.5 text-sm" :class="k.version && !k.dirty ? 'bg-ink text-white' : 'bg-line'">
            {{ k.version ? `v${k.version}${k.dirty ? ' + edits' : ''}` : 'not committed' }}
          </span>
        </div>
        <div class="flex flex-wrap gap-1 text-sm">
          <span v-for="kind in KINDS" :key="kind" :class="['rounded-full px-2 py-0.5', k.kinds.includes(kind) ? 'bg-accent/20' : 'bg-line text-muted line-through']">{{ kind.replace('_', ' ') }}</span>
        </div>
        <span class="text-sm text-muted">{{ k.parts }} parts · {{ k.problems ? `${k.problems} to fix before commit` : 'ready to commit' }}</span>
        <PButton variant="soft" :test-id="`open-kit-${k.breed_id}`" @click="open(k.breed_id)">Rig ›</PButton>
      </div>
    </div>
  </Page>
</template>

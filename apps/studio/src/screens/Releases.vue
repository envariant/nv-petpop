<script setup lang="ts">
// Curation: releases (Contract 1). Only an admin publishes one; kiosks load it and switch atomically.
import { onMounted } from 'vue';
import { PButton, PTitle } from '@petpop/ui-vue';
import { useCurate } from '../stores/curate';
import { useSession } from '../stores/session';
import Notice from '../components/Notice.vue';
import Page from '../components/Page.vue';
import SpeciesChips from '../components/SpeciesChips.vue';
const c = useCurate();
const s = useSession();
onMounted(() => void c.loadReleases());
</script>

<template>
  <Page test-id="releases">
    <PTitle sub="A release packs the latest published version of every family, part, accessory and pattern into a signed bundle. Kiosks load it and switch atomically.">Releases</PTitle>
    <Notice :error="c.error" :notice="c.notice" />
    <SpeciesChips />
    <PButton class="my-4" :disabled="c.busy || s.user?.role !== 'admin'" test-id="create-release" @click="c.release()">
      {{ s.user?.role === 'admin' ? `Publish a ${c.species} release` : 'Publishing a release needs the admin role' }}
    </PButton>
    <div v-for="r in c.releases" :key="r.release_version" class="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-tile bg-card p-4 text-base shadow-soft md:text-lg" :data-testid="`release-${r.release_version}`">
      <span><b>{{ r.release_version }}</b> · {{ r.counts.families }} families · {{ r.counts.region_deltas }} parts · {{ r.counts.shell_parts }} accessories · {{ r.counts.pattern_layers }} patterns · by {{ r.created_by }}</span>
      <a v-if="r.url" class="underline" :href="r.url" download>Download</a>
    </div>
  </Page>
</template>

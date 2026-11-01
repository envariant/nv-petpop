<script setup lang="ts">
// The result page /r/:token, opened from the QR code (public, signed, expires in 7 days).
import { onMounted, ref } from 'vue';
import { KioskApi } from '@petpop/core';
import type { ResultPage } from '@petpop/core';
import { GlbView } from '@petpop/ui-vue';
const props = defineProps<{ token: string }>();
const page = ref<ResultPage | null>(null);
const err = ref<string | null>(null);
onMounted(() => {
  KioskApi.result(props.token).then((p) => (page.value = p)).catch((e: { status?: number }) => (err.value = e.status === 410 ? 'This link has expired.' : 'We could not find this figurine.'));
});
</script>

<template>
  <div class="kiosk flex min-h-full flex-col items-center overflow-y-auto px-6 py-10" data-theme="candy" data-testid="phone-result">
    <div class="font-display text-5xl font-semibold">Pet<span class="text-accent">Pop</span></div>
    <p v-if="err" class="mt-10 text-xl">{{ err }}</p>
    <template v-if="page">
      <h1 class="mt-6 font-display text-4xl">{{ page.pet_name ?? 'Your pet' }}</h1>
      <p class="text-lg text-muted">{{ page.breed_label }}</p>
      <div class="my-6 h-[60vh] w-full max-w-md rounded-[28px] bg-card shadow-soft">
        <GlbView :url="page.glb_url" interactive :fallback-image="page.thumbnail_url ?? undefined" />
      </div>
      <a class="rounded-full bg-accent px-8 py-4 font-display text-2xl text-white" :href="page.glb_url" :download="`${page.pet_name ?? 'petpop'}.glb`">Download 3D file</a>
      <p class="mt-4 text-sm text-muted">Link expires {{ new Date(page.expires_at).toLocaleDateString() }}</p>
    </template>
  </div>
</template>

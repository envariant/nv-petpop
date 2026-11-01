<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue';
import { apiUrl } from '@petpop/core';
import { FigureView, GlbView, PButton, PTitle, QrCode } from '@petpop/ui-vue';
import { useDesign } from '../stores/design';
import { useSession } from '../stores/session';
const s = useSession();
const d = useDesign();
const o = computed(() => d.order);
const ready = computed(() => o.value?.status === 'ready');
let t = 0;
watch(() => o.value?.status, (st) => {
  clearInterval(t);
  if (st && st !== 'ready' && st !== 'failed') t = window.setInterval(() => void d.refreshOrder(), 1000);
}, { immediate: true });
onBeforeUnmount(() => clearInterval(t));
</script>

<template>
  <div v-if="o" class="flex h-full flex-col items-center gap-4 px-4 pb-4 pt-2 text-center md:px-8 landscape:md:flex-row landscape:md:items-stretch landscape:md:text-left" data-testid="order">
    <div class="relative h-[45%] min-h-[14rem] w-full shrink-0 overflow-hidden rounded-tile bg-card shadow-soft landscape:md:h-full landscape:md:flex-1">
      <GlbView v-if="ready && o.previews.glb" :url="apiUrl(o.previews.glb)" :fallback-image="o.previews.thumbnail ? apiUrl(o.previews.thumbnail) : undefined" spin test-id="order-figure" />
      <FigureView v-else-if="d.lib && d.composition" :lib="d.lib" :composition="d.composition" spin :interactive="false" test-id="order-preview" />
    </div>
    <div class="flex w-full min-h-0 flex-1 flex-col items-center gap-4 landscape:md:w-[min(42%,30rem)] landscape:md:flex-none landscape:md:items-start landscape:md:justify-center">
      <PTitle :sub="ready ? 'Show this ticket at the counter. Scan the code to keep a copy on your phone.' : (o.export?.message ?? 'Preparing your order')">
        {{ ready ? `${o.pet_name || 'Your figurine'} is on the way!` : 'Placing your order…' }}
      </PTitle>
      <div v-if="!ready && o.status !== 'failed'" class="h-3 w-full overflow-hidden rounded-full bg-line" data-testid="order-progress">
        <div class="h-full bg-accent transition-all" :style="{ width: `${o.export?.pct ?? 5}%` }" />
      </div>
      <p v-if="o.status === 'failed'" class="text-lg font-semibold text-accent2" data-testid="order-failed">
        Something went wrong preparing the print. A member of staff can reprint ticket {{ o.ticket }}.
      </p>
      <div class="flex w-full flex-wrap items-center justify-center gap-4 landscape:md:justify-start">
        <div class="rounded-tile bg-accent px-6 py-3 font-display text-2xl text-white md:text-3xl" data-testid="order-ticket">Ticket <b>{{ o.ticket }}</b></div>
        <div v-if="ready && o.result_url" class="rounded-tile bg-white p-3" data-testid="order-qr"><QrCode :value="o.result_url" :size="140" /></div>
      </div>
      <PButton class="mt-auto w-full" test-id="order-done" @click="s.reset()">Done</PButton>
    </div>
  </div>
</template>

<script setup lang="ts">
// One-off figurine, step 7: the result, a QR to the phone page, send to print, tweak or start again.
import { computed, ref } from 'vue';
import { Chip, GlbView, PButton, PTitle, QrCode } from '@petpop/ui-vue';
import { useSession } from '../stores/session';
const s = useSession();
const clay = ref(false);
const sending = ref(false);
const glb = computed(() => s.job?.previews.glb ?? s.job?.artefacts.find((a) => a.kind === 'glb')?.url);
async function send() {
  sending.value = true;
  try {
    await s.fulfil();
  } finally {
    sending.value = false;
  }
}
</script>

<template>
  <div v-if="s.job" class="mx-auto flex h-full max-w-6xl flex-col px-4 pb-6 pt-6 md:px-8 md:pt-8" data-testid="result">
    <PTitle :sub="s.job.fallback !== 'none' ? 'We used our classic figure shape this time; the colours are all yours.' : 'Pinch to zoom, drag to turn.'">
      Meet {{ s.job.pet_name ?? 'Your pet' }}!
    </PTitle>
    <div class="flex min-h-0 flex-1 flex-col gap-6 md:flex-row">
      <div class="relative min-h-[16rem] flex-1 overflow-hidden rounded-tile bg-card shadow-soft" data-testid="result-viewer">
        <GlbView v-if="glb" :url="glb" :clay="clay" interactive :fallback-image="s.job.previews.thumbnail" />
        <div class="absolute right-4 top-4 flex gap-2">
          <Chip :selected="!clay" test-id="toggle-textured" @click="clay = false">Painted</Chip>
          <Chip :selected="clay" test-id="toggle-clay" @click="clay = true">Clay</Chip>
        </div>
      </div>
      <div class="flex shrink-0 flex-col gap-4 md:w-72">
        <div class="flex items-center gap-4 md:flex-col md:items-start">
          <div class="rounded-3xl bg-white p-3 shadow-soft" data-testid="result-qr"><QrCode v-if="s.job.result_url" :value="s.job.result_url" :size="160" /></div>
          <p class="text-base text-muted md:text-lg">Scan to open {{ s.job.pet_name ?? 'Your pet' }} on your phone.</p>
        </div>
        <div v-if="s.ticket" class="rounded-tile bg-accent p-4 font-display text-2xl text-white" data-testid="ticket">Sent to print! Ticket <b>{{ s.ticket }}</b></div>
        <PButton v-else :disabled="sending" test-id="send-to-print" @click="send">{{ sending ? 'Sending…' : 'Send to print' }}</PButton>
        <div class="mt-auto flex justify-between gap-2">
          <PButton variant="soft" test-id="tweak" @click="s.tweak()">Tweak</PButton>
          <PButton variant="ghost" test-id="start-over" @click="s.clearFigure()">New figurine</PButton>
        </div>
      </div>
    </div>
  </div>
</template>

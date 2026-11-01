<script setup lang="ts">
// "Make it unique" (KIOSK_BESPOKE): the design goes to the studio as a bespoke job's starting point, and the customer
// gets a ticket and a "we'll message you" promise, never a Generating screen.
import { ref } from 'vue';
import { PButton, PTitle, TextEntry } from '@petpop/ui-vue';
import { useSession } from '../stores/session';
const s = useSession();
const contact = ref('');
const busy = ref(false);
async function send() {
  if (busy.value) return;
  busy.value = true;
  try {
    await s.requestBespoke(contact.value);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div v-if="s.bespoke" class="flex h-full flex-col items-center justify-center gap-6 px-6 text-center" data-testid="bespoke-accepted">
    <div class="text-7xl">💌</div>
    <PTitle :sub="s.bespoke.message">We're on it!</PTitle>
    <div class="rounded-tile bg-accent px-6 py-3 font-display text-2xl text-white md:text-3xl" data-testid="bespoke-ticket">Ticket <b>{{ s.bespoke.ticket }}</b></div>
    <PButton test-id="bespoke-done" @click="s.reset()">Done</PButton>
  </div>
  <div v-else class="mx-auto flex h-full max-w-3xl flex-col px-4 pb-4 pt-2 md:px-8" data-testid="bespoke">
    <PTitle sub="Our studio sculpts a one-off figure from your design. It takes a while, so we'll message you when it's ready.">Make it unique</PTitle>
    <p class="mb-2 text-base text-muted md:text-lg">Phone or email (optional; staff can also look it up by ticket)</p>
    <TextEntry v-model="contact" placeholder="07700 900123" test-id="bespoke-contact" :max-length="80" :done-label="busy ? 'Sending…' : 'Send'" compact :capitalize="false" contact input-type="email" @done="send" />
    <p v-if="s.error" class="mt-4 text-lg font-semibold text-accent2" data-testid="bespoke-error">{{ s.error }}</p>
    <PButton variant="ghost" class="mt-auto self-start" test-id="bespoke-back" @click="s.go('design')">‹ Back to design</PButton>
  </div>
</template>

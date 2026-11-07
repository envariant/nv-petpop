<script setup lang="ts">
// Checkout (decision 126): how we tell the customer the figurine is ready. Signed in: the account's own email or phone
// (or another one for this order). A guest gives an email or a phone, and may create an account with it on the spot
// (a code proves it is theirs). Then the order is placed and the payment step follows.
import { computed, ref } from 'vue';
import type { Channel, OrderContact } from '@petpop/core';
import { Chip, PButton, PRow, PTitle, TextEntry, isKiosk } from '@petpop/ui-vue';
import { useAccount } from '../stores/account';
import { useDesign } from '../stores/design';
import { useSession } from '../stores/session';
import SignIn from './account/SignIn.vue';
const s = useSession();
const d = useDesign();
const a = useAccount();
const channel = ref<Channel>('email');
const to = ref('');
const create = ref(false);
const other = ref(false);
const signingIn = ref(false);
const busy = ref(false);
const mine = computed(() => a.account && (a.account.email || a.account.phone));

async function place(contact: OrderContact | null) {
  if (busy.value) return;
  busy.value = true;
  try {
    await d.placeOrder(s.sessionId, contact);
    if (!d.orderError) s.go('order');
  } finally {
    busy.value = false;
  }
}
async function guest() {
  if (!to.value.trim()) return;
  if (create.value) {
    signingIn.value = true; // the code step: SignIn sends the code and signs in; then the order goes as the account
    return;
  }
  await place(channel.value === 'email' ? { email: to.value } : { phone: to.value });
}
async function signedIn() {
  signingIn.value = false;
  await place(null);
}
</script>

<template>
  <div v-if="d.active" class="no-scrollbar mx-auto flex h-full max-w-3xl flex-col overflow-y-auto px-4 pb-4 pt-2 md:px-8" data-testid="contact">
    <PTitle sub="We'll tell you when it is ready to collect.">How should we reach you?</PTitle>

    <!-- creating an account: the code step (first, so signing in does not swap it out before the order goes) -->
    <SignIn v-if="signingIn" :channel="channel" :to="to" @done="signedIn" />

    <!-- signed in: the account's own contact -->
    <template v-else-if="a.account && mine && !other">
      <p class="mb-4 text-lg" data-testid="contact-account">We'll tell you at <b>{{ a.account.email ?? a.account.phone }}</b><span v-if="!isKiosk"> and in the app</span>.</p>
      <PButton test-id="contact-place" :disabled="busy" @click="place(null)">{{ busy ? 'Ordering…' : 'Place my order' }}</PButton>
      <button class="mt-3 self-start text-base text-muted underline" data-testid="contact-other" @click="other = true">Use another email or phone for this order</button>
    </template>

    <!-- a guest, or another contact for this order -->
    <template v-else>
      <PRow>
        <Chip :selected="channel === 'email'" test-id="contact-email" @click="channel = 'email'">Email</Chip>
        <Chip :selected="channel === 'phone'" test-id="contact-phone" @click="channel = 'phone'">Phone</Chip>
      </PRow>
      <div class="mt-3">
        <TextEntry v-model="to" :placeholder="channel === 'email' ? 'you@example.com' : '9123 4567'" test-id="contact-to" :max-length="80"
          :done-label="busy ? 'Ordering…' : create ? 'Send me a code' : 'Place my order'" compact :capitalize="false" contact
          :input-type="channel === 'email' ? 'email' : 'tel'" @done="guest" />
      </div>
      <label v-if="!a.account" class="mt-3 flex cursor-pointer items-center gap-3 text-base md:text-lg" data-testid="contact-create">
        <input v-model="create" type="checkbox" class="h-6 w-6 accent-[rgb(var(--pp-accent))]" data-testid="contact-create-box" />
        Create a PetPop account with it (we'll send you a code)
      </label>
      <p v-if="!a.account && !isKiosk" class="mt-3 text-base text-muted">
        Have an account? <button class="underline" data-testid="contact-signin" @click="s.go('account')">Sign in</button>
      </p>
    </template>

    <p v-if="d.orderError" class="mt-4 text-lg font-semibold text-accent2" data-testid="order-error">{{ d.orderError }}</p>
    <PButton variant="ghost" class="mt-auto self-start" test-id="contact-back" @click="s.go('name')">‹ Back</PButton>
  </div>
</template>

<script setup lang="ts">
// The customer's account (decision 126): sign in or create one; then the profile, its email and phone (each unique
// across accounts, added with a code), Apple and Google, past orders, sign out and deleting the account.
import { onMounted, ref, watch } from 'vue';
import type { Channel } from '@petpop/core';
import { PButton, PSection, PTitle, TextEntry } from '@petpop/ui-vue';
import { useAccount } from '../stores/account';
import { useSession } from '../stores/session';
import SignIn from './account/SignIn.vue';
const a = useAccount();
const s = useSession();
const name = ref(a.account?.name ?? '');
const adding = ref<Channel | null>(null);
const addTo = ref('');
const addCode = ref('');
const codeSent = ref<string | null>(null);
const devCode = ref<string | null>(null);
const confirmDelete = ref(false);
watch(() => a.account, (acc) => {
  name.value = acc?.name ?? '';
  if (acc) void a.loadOrders();
}, { immediate: true });
onMounted(() => !a.config && void a.load());

function startAdd(c: Channel) {
  adding.value = c;
  addTo.value = '';
  addCode.value = '';
  codeSent.value = null;
}
async function sendAdd() {
  const r = await a.sendCode(adding.value!, addTo.value);
  if (r) {
    codeSent.value = r.to;
    devCode.value = r.dev_code ?? null;
  }
}
async function confirmAdd() {
  if (await a.addContact(adding.value!, addTo.value, addCode.value)) adding.value = null;
}
const label = (p: string) => (p === 'apple' ? 'Apple' : 'Google');
</script>

<template>
  <div class="no-scrollbar mx-auto h-full max-w-3xl overflow-y-auto px-4 pb-8 pt-2 md:px-8" data-testid="account">
    <template v-if="!a.account">
      <PTitle sub="Track your orders, get a message when your figurine is ready, and order again.">Sign in or create an account</PTitle>
      <p v-if="a.notice" class="mb-3 text-base text-accent" data-testid="account-notice">{{ a.notice }}</p>
      <div class="max-w-md"><SignIn /></div>
    </template>
    <template v-else>
      <PTitle :sub="a.notice ?? undefined">Hello{{ a.account.name ? `, ${a.account.name}` : '' }}</PTitle>
      <p v-if="a.error" class="mb-3 text-base font-semibold text-accent2" data-testid="account-error">{{ a.error }}</p>
      <PSection title="Name">
        <form class="flex gap-2" @submit.prevent="a.rename(name)">
          <input v-model="name" maxlength="60" placeholder="Your name" data-testid="account-name"
            class="min-w-0 flex-1 rounded-tile border-4 border-line bg-card px-4 py-2 text-lg outline-none focus:border-accent" />
          <PButton variant="soft" test-id="account-name-save" @click="a.rename(name)">Save</PButton>
        </form>
      </PSection>
      <PSection title="Email and phone" test-id="account-contacts">
        <div v-for="c in (['email', 'phone'] as const)" :key="c" class="mb-2 flex flex-wrap items-center gap-3 text-lg">
          <span class="w-16 text-muted">{{ c === 'email' ? 'Email' : 'Phone' }}</span>
          <b class="min-w-0 flex-1 truncate" :data-testid="`account-${c}`">{{ (c === 'email' ? a.account.email : a.account.phone) ?? '—' }}</b>
          <button class="text-base underline" :data-testid="`account-add-${c}`" @click="startAdd(c)">{{ (c === 'email' ? a.account.email : a.account.phone) ? 'Change' : 'Add' }}</button>
          <button v-if="c === 'email' ? a.account.email : a.account.phone" class="text-base text-muted underline" :data-testid="`account-remove-${c}`" @click="a.removeContact(c)">Remove</button>
        </div>
        <div v-if="adding" class="mt-2 flex flex-col gap-2 rounded-tile bg-card p-4 shadow-soft" data-testid="account-adding">
          <template v-if="!codeSent">
            <TextEntry v-model="addTo" :placeholder="adding === 'email' ? 'you@example.com' : '9123 4567'" test-id="account-add-to" :max-length="80"
              done-label="Send code" compact :capitalize="false" contact :input-type="adding === 'email' ? 'email' : 'tel'" @done="sendAdd" />
          </template>
          <template v-else>
            <p class="text-base text-muted">Enter the code we sent to <b>{{ codeSent }}</b>.</p>
            <p v-if="devCode" class="text-sm text-muted" data-testid="account-dev-code">Development server: the code is <b>{{ devCode }}</b></p>
            <TextEntry v-model="addCode" placeholder="123456" test-id="account-add-code" :max-length="6" done-label="Confirm" compact :capitalize="false" contact @done="confirmAdd" />
          </template>
          <button class="self-start text-base text-muted underline" @click="adding = null">Cancel</button>
        </div>
      </PSection>
      <PSection title="Sign in with" test-id="account-providers">
        <div v-for="p in (['apple', 'google'] as const)" :key="p" class="mb-2 flex items-center gap-3 text-lg">
          <span class="flex-1">{{ label(p) }}</span>
          <button v-if="a.account.providers.includes(p)" class="text-base underline" :data-testid="`account-unlink-${p}`" @click="a.unlink(p)">Unlink</button>
          <button v-else-if="a.config?.[`${p}_client_id`]" class="text-base underline" :data-testid="`account-link-${p}`" @click="a.link(p)">Link</button>
        </div>
      </PSection>
      <PSection title="Your orders" test-id="account-orders">
        <p v-if="!a.orders.length" class="text-base text-muted">No orders yet.</p>
        <div v-for="o in a.orders" :key="o.composition_id" class="mb-2 flex items-center gap-3 rounded-tile bg-card p-3 shadow-soft" :data-testid="`account-order-${o.composition_id}`">
          <img v-if="o.thumbnail_url" :src="o.thumbnail_url" alt="" class="h-12 w-12 object-contain" />
          <span class="flex-1 text-lg"><b>{{ o.pet_name || 'Figurine' }}</b> · {{ o.ticket }}</span>
          <span class="text-base text-muted">{{ o.status }}</span>
        </div>
      </PSection>
      <div class="mt-6 flex flex-wrap gap-3">
        <PButton variant="soft" test-id="account-design" @click="s.start()">Design a figurine</PButton>
        <PButton variant="ghost" test-id="account-sign-out" @click="a.signOut()">Sign out</PButton>
      </div>
      <div class="mt-8 border-t-2 border-line pt-4">
        <button v-if="!confirmDelete" class="text-base text-accent2 underline" data-testid="account-delete" @click="confirmDelete = true">Delete my account</button>
        <div v-else class="flex flex-col gap-2" data-testid="account-delete-confirm-box">
          <p class="text-base">This deletes your account and your sign-in methods. Past orders stay with the shop, without your details.</p>
          <div class="flex gap-3">
            <PButton test-id="account-delete-confirm" @click="a.remove()">Delete it</PButton>
            <PButton variant="ghost" @click="confirmDelete = false">Keep it</PButton>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

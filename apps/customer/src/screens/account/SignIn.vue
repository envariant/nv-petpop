<script setup lang="ts">
// Sign in or create an account (decision 126): Apple, Google (in the app and the browser, not on a shared kiosk), or a
// six-digit code sent to an email or phone. The first sign-in to an address creates its account.
import { computed, onMounted, ref } from 'vue';
import type { Channel } from '@petpop/core';
import { PButton, TextEntry, cx, isKiosk } from '@petpop/ui-vue';
import { useAccount } from '../../stores/account';
const emit = defineEmits<{ done: [] }>();
const props = defineProps<{ channel?: Channel; to?: string }>();
const a = useAccount();
const step = ref<'choose' | 'to' | 'code'>(props.channel && props.to ? 'to' : 'choose');
const channel = ref<Channel>(props.channel ?? 'email');
const to = ref(props.to ?? '');
const code = ref('');
const sentTo = ref('');
const devCode = ref<string | null>(null);
const providers = computed(() => (isKiosk ? [] : (['apple', 'google'] as const).filter((p) => a.config?.[`${p}_client_id`])));

function pick(c: Channel) {
  channel.value = c;
  to.value = '';
  step.value = 'to';
}
async function send() {
  const r = await a.sendCode(channel.value, to.value);
  if (!r) return;
  sentTo.value = r.to;
  devCode.value = r.dev_code ?? null;
  code.value = '';
  step.value = 'code';
}
async function verify() {
  if (await a.verify(channel.value, to.value, code.value)) emit('done');
}
async function provider(p: 'apple' | 'google') {
  if (await a.withProvider(p)) emit('done');
}
onMounted(() => props.channel && props.to && void send()); // given an address (checkout): straight to its code
</script>

<template>
  <div class="flex w-full flex-col gap-3" data-testid="signin">
    <template v-if="step === 'choose'">
      <button v-for="p in providers" :key="p" :data-testid="`signin-${p}`" :disabled="a.busy"
        :class="cx('press hit flex items-center justify-center gap-3 rounded-tile px-4 py-3 font-display text-lg font-semibold shadow-soft', p === 'apple' ? 'bg-ink text-paper' : 'bg-card text-ink')"
        @click="provider(p)">
        <span aria-hidden="true">{{ p === 'apple' ? '' : 'G' }}</span> Continue with {{ p === 'apple' ? 'Apple' : 'Google' }}
      </button>
      <PButton variant="soft" test-id="signin-email" @click="pick('email')">Continue with email</PButton>
      <PButton variant="soft" test-id="signin-phone" @click="pick('phone')">Continue with phone</PButton>
    </template>
    <template v-else-if="step === 'to'">
      <p class="text-base text-muted">{{ channel === 'email' ? 'Your email' : 'Your mobile number' }}: we send you a six-digit code.</p>
      <TextEntry v-model="to" :placeholder="channel === 'email' ? 'you@example.com' : '9123 4567'" test-id="signin-to" :max-length="80"
        :done-label="a.busy ? 'Sending…' : 'Send code'" compact :capitalize="false" contact :input-type="channel === 'email' ? 'email' : 'tel'" @done="send" />
      <button class="self-start text-base text-muted underline" data-testid="signin-back" @click="step = 'choose'">‹ Other ways to sign in</button>
    </template>
    <template v-else>
      <p class="text-base text-muted">We sent a code to <b>{{ sentTo || to }}</b>.</p>
      <p v-if="devCode" class="text-sm text-muted" data-testid="signin-dev-code">Development server: the code is <b>{{ devCode }}</b></p>
      <TextEntry v-model="code" placeholder="123456" test-id="signin-code" :max-length="6" :done-label="a.busy ? 'Checking…' : 'Sign in'"
        compact :capitalize="false" contact input-type="text" @done="verify" />
      <button class="self-start text-base text-muted underline" data-testid="signin-resend" @click="send">Send a new code</button>
    </template>
    <p v-if="a.error" class="text-base font-semibold text-accent2" data-testid="signin-error">{{ a.error }}</p>
  </div>
</template>

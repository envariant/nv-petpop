<script setup lang="ts">
// Staff sign-in (BRIEF Section 17): local accounts with the roles operator, curator and admin.
import { ref } from 'vue';
import { PTitle } from '@petpop/ui-vue';
import { useSession } from '../stores/session';
const s = useSession();
const username = ref('');
const password = ref('');
const busy = ref(false);
async function submit() {
  busy.value = true;
  try {
    await s.login(username.value.trim(), password.value);
  } finally {
    busy.value = false;
  }
}
const field = 'w-full rounded-tile border-4 border-line bg-card px-4 py-3 text-lg outline-none focus:border-accent md:text-xl';
</script>

<template>
  <div class="flex h-full items-center justify-center overflow-y-auto px-4">
    <form class="flex w-full max-w-md flex-col gap-4" data-testid="login" @submit.prevent="submit">
      <div class="font-display text-5xl font-semibold tracking-tight">Pet<span class="text-accent">Pop</span> Studio</div>
      <PTitle sub="Staff only: generate, curate and publish library content.">Sign in</PTitle>
      <input v-model="username" :class="field" placeholder="Username" autocomplete="username" data-testid="login-username" />
      <input v-model="password" :class="field" placeholder="Password" type="password" autocomplete="current-password" data-testid="login-password" />
      <p v-if="s.loginError" class="text-lg font-semibold text-accent2" data-testid="login-error">{{ s.loginError }}</p>
      <button type="submit" :disabled="busy || !username.trim() || !password" data-testid="login-submit"
        class="press hit rounded-tile bg-accent px-6 py-3 font-display text-xl font-semibold text-white shadow-soft disabled:opacity-40">
        {{ busy ? 'Signing in…' : 'Sign in' }}
      </button>
    </form>
  </div>
</template>

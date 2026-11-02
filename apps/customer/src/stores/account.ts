// The customer's account (decision 126): sign-in by email or phone code, or with Apple or Google; the profile, its
// orders and push. In the app the sign-in is remembered on the device; on a kiosk it lasts until the session ends.
import { defineStore } from 'pinia';
import { ref } from 'vue';
import { AccountApi, ApiFailure, setAccountToken } from '@petpop/core';
import type { Account, AccountSession, AuthConfig, Channel, CodeSent, KioskOrder, Provider } from '@petpop/core';
import { isKiosk } from '@petpop/ui-vue';
import { providerToken } from '../social';
import { registerPush, unregisterPush } from '../push';

const KEY = 'pp-account';

export function failure(e: unknown, fallback = 'Something went wrong. Please try again.'): string {
  return e instanceof ApiFailure && typeof e.detail === 'string' ? e.detail : fallback;
}

export const useAccount = defineStore('account', () => {
  const config = ref<AuthConfig | null>(null);
  const account = ref<Account | null>(null);
  const orders = ref<KioskOrder[]>([]);
  const busy = ref(false);
  const error = ref<string | null>(null);
  const notice = ref<string | null>(null);

  function remember(token: string | null) {
    setAccountToken(token);
    if (isKiosk) return; // a kiosk never keeps a customer signed in
    try {
      if (token) localStorage.setItem(KEY, token);
      else localStorage.removeItem(KEY);
    } catch {
      /* storage may be blocked: the sign-in lasts until the app closes */
    }
  }

  async function run<T>(f: () => Promise<T>, fallback?: string): Promise<T | null> {
    busy.value = true;
    error.value = null;
    notice.value = null;
    try {
      return await f();
    } catch (e) {
      error.value = failure(e, fallback);
      return null;
    } finally {
      busy.value = false;
    }
  }

  async function load() {
    try {
      config.value = await AccountApi.config();
    } catch {
      /* the offline overlay handles a dropped API */
    }
    if (isKiosk) return;
    let token: string | null = null;
    try {
      token = localStorage.getItem(KEY);
    } catch {
      token = null;
    }
    if (!token) return;
    setAccountToken(token);
    try {
      account.value = await AccountApi.me();
      void registerPush();
    } catch {
      remember(null);
    }
  }

  function signedIn(s: AccountSession) {
    remember(s.token);
    account.value = s.account;
    notice.value = s.linked ? `Signed in: your ${s.linked === 'apple' ? 'Apple' : 'Google'} sign-in is now linked to this account.` : null;
    void registerPush();
  }

  const sendCode = (channel: Channel, to: string): Promise<CodeSent | null> =>
    run(() => AccountApi.sendCode(channel, to), 'We could not send a code.');

  async function verify(channel: Channel, to: string, code: string, name?: string) {
    const s = await run(() => AccountApi.verify(channel, to, code, name));
    if (s) signedIn(s);
    return !!s;
  }

  async function withProvider(provider: Provider) {
    const s = await run(async () => {
      const t = await providerToken(provider, config.value);
      return AccountApi.provider(provider, t.idToken, t.nonce, t.name);
    }, `Sign in with ${provider === 'apple' ? 'Apple' : 'Google'} did not finish.`);
    if (s) signedIn(s);
    return !!s;
  }

  async function rename(name: string) {
    const a = await run(() => AccountApi.rename(name));
    if (a) account.value = a;
  }
  async function addContact(channel: Channel, to: string, code: string) {
    const a = await run(() => AccountApi.addContact(channel, to, code));
    if (a) account.value = a;
    return !!a;
  }
  async function removeContact(channel: Channel) {
    const a = await run(() => AccountApi.removeContact(channel));
    if (a) account.value = a;
  }
  async function link(provider: Provider) {
    const a = await run(async () => {
      const t = await providerToken(provider, config.value);
      return AccountApi.link(provider, t.idToken, t.nonce);
    }, `Linking ${provider === 'apple' ? 'Apple' : 'Google'} did not finish.`);
    if (a) account.value = a;
  }
  async function unlink(provider: Provider) {
    const a = await run(() => AccountApi.unlink(provider));
    if (a) account.value = a;
  }
  async function loadOrders() {
    const r = await run(() => AccountApi.orders());
    if (r) orders.value = r.items;
  }
  async function signOut() {
    await unregisterPush();
    try {
      await AccountApi.signOut();
    } catch {
      /* signed out here either way */
    }
    remember(null);
    account.value = null;
    orders.value = [];
  }
  async function remove() {
    const ok = await run(async () => {
      await unregisterPush();
      await AccountApi.remove();
      return true;
    }, 'We could not delete the account.');
    if (ok) {
      remember(null);
      account.value = null;
      orders.value = [];
      notice.value = 'Your account is deleted.';
    }
  }
  return { config, account, orders, busy, error, notice, load, sendCode, verify, withProvider, rename, addContact, removeContact, link, unlink, loadOrders, signOut, remove };
});

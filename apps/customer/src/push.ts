// Push notifications for signed-in app users (decision 126): Firebase Cloud Messaging on iOS and Android through
// @capacitor-firebase/messaging; the token is registered with the account and dropped on sign-out. Browsers and
// kiosks get none (the email or SMS still goes).
import { AccountApi } from '@petpop/core';
import { isKiosk } from '@petpop/ui-vue';

let current: string | null = null;

async function native(): Promise<'ios' | 'android' | null> {
  if (isKiosk) return null;
  const { Capacitor } = await import('@capacitor/core');
  const p = Capacitor.getPlatform();
  return p === 'ios' || p === 'android' ? p : null;
}

export async function registerPush(): Promise<void> {
  const platform = await native();
  if (!platform) return;
  try {
    const { FirebaseMessaging } = await import('@capacitor-firebase/messaging');
    const perm = await FirebaseMessaging.requestPermissions();
    if (perm.receive !== 'granted') return;
    const { token } = await FirebaseMessaging.getToken();
    if (token && token !== current) {
      await AccountApi.addDevice(token, platform);
      current = token;
    }
  } catch {
    /* no push on this device (no Firebase config yet, or refused): orders still notify by email or SMS */
  }
}

export async function unregisterPush(): Promise<void> {
  if (!current) return;
  try {
    await AccountApi.removeDevice(current);
    const { FirebaseMessaging } = await import('@capacitor-firebase/messaging');
    await FirebaseMessaging.deleteToken();
  } catch {
    /* the server drops a stale token on its own */
  }
  current = null;
}

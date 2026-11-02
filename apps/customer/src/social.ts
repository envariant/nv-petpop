// Sign in with Apple and Google (decision 126) through @capgo/capacitor-social-login: the native sheets in the iOS and
// Android apps, Google Identity Services and Sign in with Apple JS on the web. The server verifies the id token it
// returns. With the server's fake providers (tests, demos) no provider is involved.
import type { AuthConfig, Provider } from '@petpop/core';

export interface ProviderToken { idToken: string; nonce?: string; name?: string }

let initialised = '';

function randomNonce(): string {
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  return Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
}

export async function providerToken(provider: Provider, config: AuthConfig | null): Promise<ProviderToken> {
  if (!config) throw new Error('sign-in is not available right now');
  if (config.fake_providers) {
    // tests and demos: a stable fake identity per provider; its email joins an account that has it (decision 126)
    const email = (typeof localStorage !== 'undefined' && localStorage.getItem('pp-fake-email')) || `demo.${provider}@example.com`;
    return { idToken: `fake:${provider}-${email}:${email}`, name: provider === 'apple' ? 'Apple Demo' : undefined };
  }
  const { SocialLogin } = await import('@capgo/capacitor-social-login');
  const key = `${config.google_client_id}|${config.apple_client_id}`;
  if (initialised !== key) {
    const { Capacitor } = await import('@capacitor/core');
    const web = !Capacitor.isNativePlatform();
    await SocialLogin.initialize({
      google: config.google_client_id ? { webClientId: config.google_client_id, iOSClientId: import.meta.env.VITE_GOOGLE_IOS_CLIENT_ID, iOSServerClientId: config.google_client_id } : undefined,
      apple: config.apple_client_id ? { clientId: config.apple_client_id, redirectUrl: web ? `${location.origin}/` : '' } : undefined,
    });
    initialised = key;
  }
  const nonce = randomNonce();
  if (provider === 'google') {
    const r = await SocialLogin.login({ provider: 'google', options: { nonce } });
    const idToken = (r.result as { idToken?: string | null }).idToken;
    if (!idToken) throw new Error('Google did not return an id token');
    return { idToken, nonce };
  }
  const r = await SocialLogin.login({ provider: 'apple', options: { scopes: ['name', 'email'], nonce } });
  const res = r.result as { idToken?: string | null; profile?: { givenName?: string | null; familyName?: string | null } };
  if (!res.idToken) throw new Error('Apple did not return an id token');
  const name = [res.profile?.givenName, res.profile?.familyName].filter(Boolean).join(' ') || undefined;
  return { idToken: res.idToken, nonce, name };
}

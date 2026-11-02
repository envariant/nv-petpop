import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

/** The kiosk project runs kiosk mode (on-screen keyboard, idle wipe, staff panel); the others run the app. */
export const kiosk = () => test.info().project.name === 'kiosk';

export async function typeOnKeyboard(page: Page, text: string) {
  for (const ch of text.toLowerCase()) {
    const named: Record<string, string> = { ' ': 'key-space', ',': 'key-comma', '.': 'key-dot', '@': 'key-at', '+': 'key-plus' };
    const id = named[ch] ?? `key-${ch}`;
    await page.getByTestId(id).first().tap();
  }
}

/** Type into a text field the way the mode does: the on-screen keyboard on a kiosk, the field itself in the app. */
export async function enter(page: Page, testId: string, text: string) {
  if (kiosk()) await typeOnKeyboard(page, text);
  else await page.getByTestId(testId).fill(text);
}

/** Checkout (decision 126): a guest's email or phone on the contact step, then the order is placed. */
export async function checkout(page: Page, contact = 'rex@example.com') {
  await expect(page.locator('[data-screen=contact]')).toBeVisible();
  await page.getByTestId(contact.includes('@') ? 'contact-email' : 'contact-phone').tap();
  await enter(page, 'contact-to', contact);
  await page.getByTestId('key-done').tap();
  await expect(page.locator('[data-screen=order]')).toBeVisible();
}

/** The six-digit code a development server shows instead of sending (decision 126). */
export async function devCode(page: Page, testId = 'signin-dev-code'): Promise<string> {
  return (await page.getByTestId(testId).locator('b').textContent())!.trim();
}

export async function expectEntered(page: Page, testId: string, text: string) {
  if (kiosk()) await expect(page.getByTestId(testId)).toContainText(text);
  else await expect(page.getByTestId(testId)).toHaveValue(text);
}

export async function toDesign(page: Page, species: 'dog' | 'cat' = 'dog', breed = 'corgi_pembroke') {
  await page.goto('/');
  await page.getByTestId('attract').tap();
  await page.getByTestId(`species-${species}`).tap();
  await page.getByTestId(`breed-${breed}`).tap();
  await expect(page.locator('[data-screen=design]')).toBeVisible();
}

/** A finished figurine's public result URL, made through the studio API (the kiosk itself never generates). */
export async function resultUrl(page: Page, request: APIRequestContext): Promise<string> {
  const login = await (await request.post('/api/v1/studio/auth/login', { data: { username: 'operator', password: 'petpop-dev' } })).json();
  const headers = { Authorization: `Bearer ${login.token}` };
  const spec = await (await request.get('/fixtures/sunny/spec.json')).json();
  const job = await (await request.post('/api/v1/studio/jobs', { data: { spec }, headers })).json();
  for (let i = 0; i < 200; i++) {
    const j = await (await request.get(`/api/v1/studio/jobs/${job.job_id}`, { headers })).json();
    if (j.result_url) return j.result_url;
    await page.waitForTimeout(300);
  }
  throw new Error('no result');
}

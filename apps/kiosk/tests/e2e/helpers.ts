import { expect, type APIRequestContext, type Page } from '@playwright/test';

export async function typeOnKeyboard(page: Page, text: string) {
  for (const ch of text.toLowerCase()) {
    const id = ch === ' ' ? 'key-space' : ch === ',' ? 'key-comma' : ch === '.' ? 'key-dot' : `key-${ch}`;
    await page.getByTestId(id).first().tap();
  }
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

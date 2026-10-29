import { expect, type Page } from '@playwright/test';

export const PASSWORD = 'petpop-dev';

export async function typeOnKeyboard(page: Page, text: string) {
  for (const ch of text.toLowerCase()) {
    const id = ch === ' ' ? 'key-space' : ch === ',' ? 'key-comma' : ch === '.' ? 'key-dot' : `key-${ch}`;
    await page.getByTestId(id).first().tap();
  }
}

/** Sign in and stay in the Generate workspace (the batch builder). */
export async function signInHome(page: Page, username = 'operator') {
  await page.goto('/studio/');
  await page.getByTestId('login-username').fill(username);
  await page.getByTestId('login-password').fill(PASSWORD);
  await page.getByTestId('login-submit').tap();
  await expect(page.locator('[data-screen=generate]')).toBeVisible();
}

/** Start a one-figurine-per-breed batch and wait until every figurine is curated. Returns the review screen. */
export async function runBatch(page: Page, breeds: string[], species: 'dog' | 'cat' = 'dog') {
  await page.getByTestId(`curate-species-${species}`).tap();
  for (const b of breeds) await page.getByTestId(`batch-breed-${b}`).tap();
  await page.getByTestId('start-batch').tap();
  await expect(page.getByTestId('curate-notice')).toContainText('Batch started');
  await page.getByTestId('nav-review').tap();
  await expect(page.getByTestId('review')).toContainText(`${breeds.length}/${breeds.length} figurines done`, { timeout: 120_000 });
}

export async function signIn(page: Page, username = 'operator', query = '') {
  await page.goto(`/studio/${query}`);
  await page.getByTestId('login-username').fill(username);
  await page.getByTestId('login-password').fill(PASSWORD);
  await page.getByTestId('login-submit').tap();
  await expect(page.locator('[data-screen=generate]')).toBeVisible();
  await page.getByTestId('one-off').tap(); // the one-off figurine flow (bespoke jobs)
  await expect(page.locator('[data-screen=species]')).toBeVisible();
}

export async function toBuild(page: Page, species: 'dog' | 'cat' = 'dog', breed = 'corgi_pembroke') {
  await signIn(page);
  await page.getByTestId(`species-${species}`).tap();
  await page.getByTestId(`breed-${breed}`).tap();
  await expect(page.locator('[data-screen=build]')).toBeVisible();
}

export async function toGenerate(page: Page, name: string, breed = 'corgi_pembroke') {
  await toBuild(page, 'dog', breed);
  await page.getByTestId('nav-next').tap();
  await page.getByTestId('nav-next').tap();
  await typeOnKeyboard(page, name);
  await page.getByTestId('nav-next').tap();
  await expect(page.locator('[data-screen=generating]')).toBeVisible();
}

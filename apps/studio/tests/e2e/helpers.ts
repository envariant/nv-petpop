import { expect, type Page } from '@playwright/test';

export const PASSWORD = 'petpop-dev';

export async function typeOnKeyboard(page: Page, text: string) {
  for (const ch of text.toLowerCase()) {
    const id = ch === ' ' ? 'key-space' : ch === ',' ? 'key-comma' : ch === '.' ? 'key-dot' : `key-${ch}`;
    await page.getByTestId(id).first().tap();
  }
}

export async function signIn(page: Page, username = 'operator', query = '') {
  await page.goto(`/studio/${query}`);
  await page.getByTestId('login-username').fill(username);
  await page.getByTestId('login-password').fill(PASSWORD);
  await page.getByTestId('login-submit').tap();
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

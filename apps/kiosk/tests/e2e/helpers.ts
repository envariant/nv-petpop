import { expect, type Page } from '@playwright/test';

export async function typeOnKeyboard(page: Page, text: string) {
  for (const ch of text.toLowerCase()) {
    const id = ch === ' ' ? 'key-space' : ch === ',' ? 'key-comma' : ch === '.' ? 'key-dot' : `key-${ch}`;
    await page.getByTestId(id).first().tap();
  }
}

export async function toBuild(page: Page, species: 'dog' | 'cat' = 'dog', breed = 'corgi_pembroke') {
  await page.goto('/');
  await page.getByTestId('attract').tap();
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

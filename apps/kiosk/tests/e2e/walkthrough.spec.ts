// Gate 1 (Kiosk): the automated touch walkthrough of the customer journey against the mock server. Library mode
// (assemble, paint, order) arrives in M7; until then the journey ends at Design or at "Make it unique".
import { expect, test } from '@playwright/test';
import { typeOnKeyboard } from './helpers';

test('gate-1 kiosk walkthrough: attract to design, make it unique, back to attract', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('pageerror', (e) => consoleErrors.push(String(e)));
  const shot = (n: string) => page.screenshot({ path: `test-results/walkthrough/${n}.png` });

  await page.goto('/');
  await expect(page.locator('[data-screen=attract]')).toBeVisible();
  await shot('1-attract');
  await page.getByTestId('attract').tap();

  await page.getByTestId('species-dog').tap();
  await shot('2-species');

  await page.getByTestId('breed-search').tap();
  await typeOnKeyboard(page, 'corgi');
  await page.getByTestId('key-done').tap();
  await shot('3-breed');
  await page.getByTestId('breed-corgi_pembroke').tap();

  await expect(page.getByTestId('design-preview').locator('canvas')).toBeVisible();
  await shot('4-design');
  await page.getByTestId('make-unique').tap();
  await typeOnKeyboard(page, '07700900123');
  await page.getByTestId('key-done').tap();
  await expect(page.getByTestId('bespoke-ticket')).toContainText('PP-');
  await shot('5-bespoke');
  await expect(page.locator('[data-screen=generating]')).toHaveCount(0); // never a Generating screen
  await page.getByTestId('bespoke-done').tap();
  await expect(page.locator('[data-screen=attract]')).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

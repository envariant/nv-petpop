// Gate 1 (Studio): the automated touch walkthrough of the Generate workspace against the mock server, from staff
// sign-in to a printed ticket.
import { expect, test } from '@playwright/test';
import { PASSWORD, typeOnKeyboard } from './helpers';

test('gate-1 studio walkthrough: sign in, generate, print, new figurine', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('pageerror', (e) => consoleErrors.push(String(e)));
  const shot = (n: string) => page.screenshot({ path: `test-results/walkthrough/${n}.png` });

  await page.goto('/studio/');
  await expect(page.getByTestId('login')).toBeVisible();
  await page.getByTestId('login-username').fill('operator');
  await page.getByTestId('login-password').fill(PASSWORD);
  await shot('0-login');
  await page.getByTestId('login-submit').tap();
  await expect(page.getByTestId('studio-user')).toContainText('operator');

  await page.getByTestId('species-dog').tap();
  await shot('1-species');

  await page.getByTestId('breed-search').tap();
  await typeOnKeyboard(page, 'corgi');
  await page.getByTestId('key-done').tap();
  await shot('2-breed');
  await page.getByTestId('breed-corgi_pembroke').tap();

  await expect(page.getByTestId('live-preview').locator('canvas')).toBeVisible();
  await page.getByTestId('chip-body.build-stocky').tap();
  await page.getByTestId('chip-acc-collar').tap();
  await shot('3-build');
  await page.getByTestId('nav-next').tap();

  await page.getByTestId('example-one ear that flops').tap();
  await page.getByTestId('example-loves snacks').tap();
  await page.getByTestId('brief-apply').tap();
  await expect(page.getByTestId('brief-result')).toContainText('Updated');
  await shot('4-brief');
  await page.getByTestId('nav-next').tap();

  await typeOnKeyboard(page, 'biscuit');
  await expect(page.getByTestId('summary-card')).toContainText('Biscuit');
  await shot('5-name');
  await page.getByTestId('nav-next').tap();

  await expect(page.locator('[data-screen=generating]')).toBeVisible();
  await expect(page.getByTestId('preview-stage').locator('img, canvas').first()).toBeVisible({ timeout: 30_000 });
  await shot('6-generating');

  await expect(page.locator('[data-screen=result]')).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId('result-viewer').locator('canvas')).toBeVisible();
  await shot('7-result');
  await page.getByTestId('send-to-print').tap();
  await expect(page.getByTestId('ticket')).toContainText('PP-');
  await page.getByTestId('start-over').tap();
  await expect(page.locator('[data-screen=species]')).toBeVisible();
  await page.getByTestId('open-queue').tap();
  await expect(page.getByTestId('staff-queue')).toContainText('Biscuit');
  expect(consoleErrors).toEqual([]);
});

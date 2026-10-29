// One Playwright test per kiosk screen and behaviour (BRIEF Sections 2, 4, 16 and 17).
import { expect, test } from '@playwright/test';
import { resultUrl, toDesign, typeOnKeyboard } from './helpers';

test('1 attract loop shows a figurine, caption and starts a session on touch', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Tap to make yours')).toBeVisible();
  await expect(page.getByTestId('attract-caption')).toContainText('the');
  await expect(page.locator('[data-screen=attract] canvas')).toBeVisible();
  await page.getByTestId('attract').tap();
  await expect(page.locator('[data-screen=species]')).toBeVisible();
});

test('2 species tiles set the species accent', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('attract').tap();
  await page.getByTestId('species-cat').tap();
  await expect(page.locator('.kiosk')).toHaveAttribute('data-species', 'cat');
  await expect(page.getByTestId('breed-siamese')).toBeVisible();
});

test('3 breed search with the on-screen keyboard and the Mixed tile', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('attract').tap();
  await page.getByTestId('species-dog').tap();
  await expect(page.getByTestId('breed-mixed')).toBeAttached();
  await page.getByTestId('breed-search').tap();
  await typeOnKeyboard(page, 'cor');
  await expect(page.getByTestId('breed-corgi_pembroke')).toBeVisible();
  await expect(page.getByTestId('breed-beagle')).toHaveCount(0);
  await page.getByTestId('breed-corgi_pembroke').tap();
  await expect(page.getByText('Design your Pembroke Welsh Corgi')).toBeVisible();
});

test('4 design shows the breed live on the kiosk GPU', async ({ page }) => {
  await toDesign(page, 'cat', 'siamese');
  await expect(page.getByTestId('design-preview').locator('canvas')).toBeVisible();
  await expect(page.getByText('Design your Siamese')).toBeVisible();
});

test('5 bespoke: make it unique is a studio request with a ticket, never a Generating screen', async ({ page }) => {
  await toDesign(page);
  await page.getByTestId('make-unique').tap();
  await expect(page.locator('[data-screen=bespoke]')).toBeVisible();
  await page.getByTestId('key-done').tap(); // contact is optional
  await expect(page.getByTestId('bespoke-accepted')).toContainText("We'll message you");
  await expect(page.getByTestId('bespoke-ticket')).toContainText('PP-');
  await page.getByTestId('bespoke-done').tap();
  await expect(page.locator('[data-screen=attract]')).toBeVisible();
});

test('phone result page opens from the QR link', async ({ page, request }) => {
  const url = await resultUrl(page, request);
  await page.goto(new URL(url).pathname);
  await expect(page.getByTestId('phone-result')).toContainText('Sunny');
  await expect(page.getByText('Download 3D file')).toBeVisible();
});

test('idle: "Still there?" countdown, then the session is wiped', async ({ page }) => {
  await page.goto('/?idle=6&countdown=4'); // the 90 s + 15 s policy, shortened
  await page.getByTestId('attract').tap();
  await page.getByTestId('species-dog').tap();
  await expect(page.getByTestId('still-there')).toBeVisible({ timeout: 20_000 });
  await page.getByTestId('still-there-stay').tap();
  await expect(page.getByTestId('still-there')).toBeHidden();
  await expect(page.getByTestId('still-there')).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('[data-screen=attract]')).toBeVisible({ timeout: 20_000 });
});

test('offline: "Back in a moment" while the API is down, auto-recovers', async ({ page }) => {
  await page.goto('/');
  await page.route('**/api/v1/health', (r) => r.abort());
  await expect(page.getByTestId('offline')).toBeVisible({ timeout: 15_000 });
  await page.unroute('**/api/v1/health');
  await expect(page.getByTestId('offline')).toBeHidden({ timeout: 15_000 });
});

test('staff panel opens with five corner taps and shows release and health, no generation controls', async ({ page }) => {
  await page.goto('/');
  for (let i = 0; i < 5; i++) await page.getByTestId('staff-corner').tap();
  await expect(page.getByTestId('staff-panel')).toBeVisible();
  await typeOnKeyboard(page, 'x');
  await page.getByTestId('key-done').tap();
  await expect(page.getByText('PIN not accepted')).toBeVisible();
  await page.getByTestId('key-backspace').tap();
  await typeOnKeyboard(page, 'staffpin');
  await page.getByTestId('key-done').tap();
  await expect(page.getByTestId('staff-ops')).toContainText('Library release');
  await expect(page.getByRole('button', { name: /retry|generate/i })).toHaveCount(0);
  await page.getByTestId('staff-close').tap();
  await expect(page.getByTestId('staff-panel')).toBeHidden();
});

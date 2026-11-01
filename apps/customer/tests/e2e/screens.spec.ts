// One Playwright test per customer-app screen and behaviour (BRIEF Sections 2, 4, 16 and 17; decision 122), on a
// kiosk and on a phone, a tablet and a desktop in app mode.
import { expect, test } from '@playwright/test';
import { enter, expectEntered, kiosk, resultUrl, toDesign, typeOnKeyboard } from './helpers';

test('1 attract loop shows a figurine, caption and starts a session on touch', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText(kiosk() ? 'Tap to make yours' : 'Make yours')).toBeVisible();
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

test('3 breed search (on-screen keyboard on a kiosk) and the Mixed tile', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('attract').tap();
  await page.getByTestId('species-dog').tap();
  await expect(page.getByTestId('breed-mixed')).toBeAttached();
  if (kiosk()) {
    await page.getByTestId('breed-search').tap();
    await typeOnKeyboard(page, 'cor');
  } else await page.getByTestId('breed-search-input').fill('cor');
  await expect(page.getByTestId('breed-corgi_pembroke')).toBeVisible();
  await expect(page.getByTestId('breed-beagle')).toHaveCount(0);
  await page.getByTestId('breed-corgi_pembroke').tap();
  await expect(page.getByText('Design your Pembroke Welsh Corgi')).toBeVisible();
});

test('4 design: the library assembler swaps parts live on the kiosk GPU', async ({ page }) => {
  await toDesign(page, 'cat', 'siamese');
  await expect(page.getByText('Design your Siamese')).toBeVisible();
  await expect(page.getByTestId('design-preview').locator('canvas')).toBeVisible();
  await expect(page.getByTestId('part-tiles').locator('button').first()).toBeVisible();
  await page.getByTestId('region-ears').tap();
  const tiles = page.getByTestId('part-tiles').locator('button');
  const other = page.getByTestId((await tiles.and(page.locator('[aria-pressed=false]')).first().getAttribute('data-testid'))!);
  await other.tap();
  await expect(other).toHaveAttribute('aria-pressed', 'true');
  await expect(tiles.and(page.locator('[aria-pressed=true]'))).toHaveCount(1);
  await page.getByTestId('region-family').tap();
  await expect(page.getByTestId('part-tiles').locator('[aria-pressed=true]')).toHaveCount(1);
  // Breeds built on the same mesh are labelled so (decision 118); the proxy library has one mesh per species.
  await expect(page.getByTestId('shared-mesh')).toContainText('Same figure shape as');
});

test('layout: the design preview and its tools share the screen without scrolling the page', async ({ page }) => {
  await toDesign(page);
  const preview = (await page.getByTestId('design-preview').boundingBox())!;
  const tabs = (await page.getByTestId('tab-shape').boundingBox())!;
  const view = page.viewportSize()!;
  expect(preview.width * preview.height).toBeGreaterThan(0.18 * view.width * view.height); // a large preview
  expect(tabs.y + tabs.height).toBeLessThanOrEqual(view.height); // tools on screen
  if (view.width > view.height && view.width >= 768) expect(tabs.x).toBeGreaterThan(preview.x + preview.width * 0.9); // side by side
  else expect(tabs.y).toBeGreaterThan(preview.y); // stacked
  expect(await page.evaluate(() => document.scrollingElement!.scrollHeight <= window.innerHeight + 1)).toBe(true);
});

test('design tools: pattern layers with a coverage slider and a colour per layer', async ({ page }) => {
  await toDesign(page);
  await page.getByTestId('tab-patterns').tap();
  const layer = page.getByTestId('pattern-tiles').locator('[aria-pressed=false]').first();
  const id = (await layer.getAttribute('data-testid'))!.replace('pattern-', '');
  await layer.tap();
  await expect(page.getByTestId(`layer-${id}`)).toBeVisible();
  await page.getByTestId(`coverage-${id}`).fill('0.8');
  await expect(page.getByTestId(`coverage-${id}`)).toHaveValue(/0\.8/);
  await page.getByTestId(`layer-colour-${id}-black`).tap();
  await expect(page.getByTestId(`layer-colour-${id}-black`)).toHaveAttribute('aria-pressed', 'true');
  await page.getByTestId('base-cream').tap();
  await expect(page.getByTestId('base-cream')).toHaveAttribute('aria-pressed', 'true');
});

test('design tools: tap-to-stamp with symmetry, brush and undo', async ({ page }) => {
  await toDesign(page);
  await page.getByTestId('tab-paint').tap();
  await page.getByTestId('tool-spot-l').tap();
  const box = (await page.getByTestId('design-preview').boundingBox())!;
  await page.getByTestId('design-preview').locator('canvas').tap({ position: { x: box.width * 0.42, y: box.height * 0.6 } });
  await expect(page.getByTestId('stamp-count')).toContainText(/^[12]\//);
  await page.getByTestId('undo').tap();
  await expect(page.getByTestId('stamp-count')).toContainText(/^0\//);
  await page.getByTestId('symmetry').tap();
  await expect(page.getByTestId('symmetry')).toHaveAttribute('aria-pressed', 'false');
  await page.getByTestId('tool-brush').tap();
  await page.getByTestId('design-preview').locator('canvas').tap({ position: { x: box.width * 0.42, y: box.height * 0.6 } });
  await expect(page.getByTestId('stamp-count')).toContainText(/^1\//);
});

test('design tools: accessories on sockets, eye and nose colours', async ({ page }) => {
  await toDesign(page);
  await page.getByTestId('tab-extras').tap();
  await page.getByTestId('shell-shell_bandana').tap();
  await expect(page.getByTestId('shell-shell_bandana')).toHaveAttribute('aria-pressed', 'true');
  await page.getByTestId('shell-shell_collar').tap(); // same socket: replaces the bandana
  await expect(page.getByTestId('shell-shell_bandana')).toHaveAttribute('aria-pressed', 'false');
  await page.getByTestId('eye-blue').tap();
  await expect(page.getByTestId('eye-blue')).toHaveAttribute('aria-pressed', 'true');
});

test('5 name: the figurine is named before ordering', async ({ page }) => {
  await toDesign(page);
  await page.getByTestId('to-name').tap();
  await expect(page.locator('[data-screen=name]')).toBeVisible();
  await enter(page, 'pet-name', 'Rex');
  await expectEntered(page, 'pet-name', 'Rex');
  await page.getByTestId('name-back').tap();
  await expect(page.locator('[data-screen=design]')).toBeVisible();
});

test('6 order: Stage F export to a ticket, QR and the printed figurine', async ({ page }) => {
  await toDesign(page);
  await page.getByTestId('to-name').tap();
  await enter(page, 'pet-name', 'Rex');
  await page.getByTestId('key-done').tap();
  await expect(page.locator('[data-screen=order]')).toBeVisible();
  await expect(page.getByTestId('order-ticket')).toContainText('PP-');
  await expect(page.getByTestId('order-qr')).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText('Rex is on the way!')).toBeVisible();
  await page.getByTestId('order-done').tap();
  await expect(page.locator('[data-screen=attract]')).toBeVisible();
});

test('7 bespoke: make it unique is a studio request with a ticket, never a Generating screen', async ({ page }) => {
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
  test.skip(!kiosk(), 'kiosk mode only');
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
  test.skip(!kiosk(), 'kiosk mode only');
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
  await expect(page.getByTestId('ops-release')).toContainText('release-dog-');
  await expect(page.getByRole('button', { name: /retry|generate/i })).toHaveCount(0);
  await page.getByTestId('staff-close').tap();
  await expect(page.getByTestId('staff-panel')).toBeHidden();
});

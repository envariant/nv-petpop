// Gate 1 (Kiosk) and gate 7: the automated touch walkthrough of the library-mode customer journey (BRIEF
// Sections 2 and 16): attract, species, breed, design (swap a part, add a marking and set its coverage, stamp a
// spot, add an accessory), name, order, then the ticket and QR once the Stage-F-only export is done.
import { expect, test } from '@playwright/test';
import { typeOnKeyboard } from './helpers';

test('kiosk walkthrough: attract to an ordered figurine from the library', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('pageerror', (e) => consoleErrors.push(String(e)));
  const shot = (n: string) => page.screenshot({ path: `test-results/walkthrough/${n}.png` });
  const t0 = Date.now();

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

  // Design: assemble from the library.
  await expect(page.getByTestId('design-preview').locator('canvas')).toBeVisible();
  await page.getByTestId('region-ears').tap();
  const partId = (await page.getByTestId('part-tiles').locator('[aria-pressed=false]').first().getAttribute('data-testid'))!;
  const part = page.getByTestId(partId);
  await part.tap();
  await expect(part).toHaveAttribute('aria-pressed', 'true');
  await shot('4-design-shape');

  await page.getByTestId('tab-patterns').tap();
  const layer = page.getByTestId('pattern-tiles').locator('[aria-pressed=false]').first();
  const id = (await layer.getAttribute('data-testid'))!.replace('pattern-', '');
  await layer.tap();
  await page.getByTestId(`coverage-${id}`).fill('0.7');
  await shot('5-design-markings');

  await page.getByTestId('tab-paint').tap();
  const box = (await page.getByTestId('design-preview').boundingBox())!;
  await page.getByTestId('design-preview').locator('canvas').tap({ position: { x: box.width * 0.42, y: box.height * 0.6 } });
  await expect(page.getByTestId('stamp-count')).not.toContainText(/^0\//);
  await shot('6-design-paint');

  await page.getByTestId('tab-extras').tap();
  await page.getByTestId('shell-shell_collar').tap();
  await shot('7-design-extras');

  // Name and order: Stage F only, on the kiosk queue.
  await page.getByTestId('to-name').tap();
  await typeOnKeyboard(page, 'rex');
  await shot('8-name');
  await page.getByTestId('key-done').tap();
  await expect(page.getByTestId('order-ticket')).toContainText('PP-');
  await expect(page.getByTestId('order-qr')).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText('Rex is on the way!')).toBeVisible();
  await shot('9-order');
  await expect(page.locator('[data-screen=generating]')).toHaveCount(0); // never a Generating screen
  console.log(`walkthrough: attract to ordered figurine in ${((Date.now() - t0) / 1000).toFixed(1)} s`);

  await page.getByTestId('order-done').tap();
  await expect(page.locator('[data-screen=attract]')).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

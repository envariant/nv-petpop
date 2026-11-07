// Gate 9 (M9, BRIEF Section 16): the library-mode journey from attract to a paid order in under 3 minutes, for a
// breed designed as a figure of parts (decisions 136, 139): a shape, a marking, a spot and an extra, named, paid,
// printed. The whole-figure journey is tests/e2e/walkthrough.spec.ts. Each run's time goes to
// test-results/gate9/<project>-kit.json for the gate's report; the 3-minute budget is the test's own timeout.
import { mkdirSync, writeFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { checkout, enter, kiosk, typeOnKeyboard } from '../e2e/helpers';

test('gate 9: attract to a paid order for a figure of parts in under 3 minutes', async ({ page }) => {
  test.setTimeout(180_000);
  const t0 = Date.now();
  const marks: Record<string, number> = {};
  const mark = (n: string) => (marks[n] = (Date.now() - t0) / 1000);
  await page.goto('/');
  await page.getByTestId('attract').tap();
  await page.getByTestId('species-dog').tap();
  if (kiosk()) {
    await page.getByTestId('breed-search').tap();
    await typeOnKeyboard(page, 'labrador');
  } else await page.getByTestId('breed-search-input').fill('labrador');
  await page.getByTestId('breed-labrador').tap();
  const view = page.getByTestId('design-preview');
  await expect(view).toHaveAttribute('data-ready', 'true', { timeout: 30_000 });
  mark('design');
  await page.getByTestId('kit-body-default-stocky').tap();
  await page.getByTestId('tab-patterns').tap();
  await page.getByTestId('kit-marking-white_socks').tap();
  await page.getByTestId('tab-paint').tap();
  const box = (await view.locator('canvas').boundingBox())!;
  await view.locator('canvas').tap({ position: { x: box.width * 0.5, y: box.height * 0.5 } });
  await expect(page.getByTestId('stamp-count')).not.toContainText(/^0\//);
  await page.getByTestId('tab-extras').tap();
  await page.getByTestId('shell-shell_bandana').tap();
  await expect(view).toHaveAttribute('data-extras', 'shell_bandana');
  mark('designed');
  await page.getByTestId('to-name').tap();
  await enter(page, 'pet-name', 'Biscuit');
  await page.getByTestId('key-done').tap();
  await checkout(page, 'biscuit@example.com');
  await page.getByTestId('pay-paynow').tap();
  await page.getByTestId('pay-simulate').tap();
  await expect(page.getByTestId('order-ticket')).toContainText('PP-');
  mark('paid');
  await expect(page.getByTestId('order-qr')).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText('Biscuit is on the way!')).toBeVisible();
  mark('printed');
  const total = (Date.now() - t0) / 1000;
  console.log(`gate 9 walkthrough (figure of parts, ${test.info().project.name}): ${total.toFixed(1)} s ${JSON.stringify(marks)}`);
  mkdirSync('test-results/gate9', { recursive: true });
  writeFileSync(`test-results/gate9/${test.info().project.name}-kit.json`, JSON.stringify({ total_s: total, marks }, null, 1));
  expect(total).toBeLessThan(180);
});

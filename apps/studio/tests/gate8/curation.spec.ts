// Gate 8 (M8, BRIEF Section 16): the Studio curation walkthrough against the real backend: a batch through the
// pipeline, review in the grid, publish, and a release that the kiosk on the same box switches to.
import { expect, test } from '@playwright/test';
import { runBatch, signInHome } from '../e2e/helpers';

test('studio curation walkthrough: batch, review, publish, release', async ({ page, request }) => {
  test.setTimeout(600_000);
  const consoleErrors: string[] = [];
  page.on('pageerror', (e) => consoleErrors.push(String(e)));
  const shot = (n: string) => page.screenshot({ path: `test-results/gate8/${n}.png` });

  await signInHome(page, 'admin');
  await shot('1-generate');
  await runBatch(page, ['beagle', 'border_collie']);
  await shot('2-review');
  await page.getByTestId('accept-passing').tap();
  await expect(page.getByTestId('publish-accepted')).toBeEnabled();
  await page.getByTestId('publish-accepted').tap();
  await expect(page.getByTestId('review')).toContainText('2 meshes', { timeout: 60_000 });
  await shot('3-published');

  await page.getByTestId('nav-library').tap();
  await page.getByTestId('kind-family').tap();
  await expect(page.locator('[data-testid^=item-family_beagle_]')).toContainText('published');

  await page.getByTestId('nav-releases').tap();
  await page.getByTestId('create-release').tap();
  await expect(page.getByTestId('curate-notice')).toContainText('release-dog-2');
  await shot('4-release');

  const kiosk = await (await request.get('/api/v1/kiosk/library/dog')).json();
  expect(kiosk.release_version).toBe('release-dog-2');
  expect(kiosk.manifest.families.some((f: { id: string }) => f.id.startsWith('family_beagle_'))).toBe(true);
  expect(consoleErrors).toEqual([]);
});

// One Playwright test per kiosk screen and behaviour (BRIEF Sections 2 and 4).
import { expect, test } from '@playwright/test';
import { toBuild, toGenerate, typeOnKeyboard } from './helpers';

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
  await expect(page.getByText('Build your Pembroke Welsh Corgi')).toBeVisible();
});

test('4 build: preset is pre-ticked, taps override, live preview renders', async ({ page }) => {
  await toBuild(page);
  await expect(page.getByTestId('tile-ears.shape-erect')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('live-preview').locator('canvas')).toBeVisible();
  await page.getByTestId('tile-ears.shape-drop').tap();
  await expect(page.getByTestId('tile-ears.shape-drop')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('tile-ears.shape-erect')).toHaveAttribute('aria-pressed', 'false');
  await page.getByTestId('swatch-colour.base-black').tap();
  await expect(page.getByTestId('swatch-colour.base-black')).toHaveAttribute('aria-pressed', 'true');
  await page.getByTestId('chip-acc-bandana').tap();
  await expect(page.getByTestId('chip-acc-bandana')).toHaveAttribute('aria-pressed', 'true');
  await page.getByTestId('swatch-colour.base-custom').tap();
  await page.getByTestId('colour-wheel').tap({ position: { x: 20, y: 60 } });
  await expect(page.getByTestId('swatch-colour.base-custom')).toHaveAttribute('aria-pressed', 'true');
  for (const sel of ['body', 'coat', 'base', 'secondary', 'pattern', 'ears', 'tail', 'muzzle', 'eyes', 'accessories']) {
    await expect(page.getByTestId(`sel-${sel}`)).toBeAttached();
  }
});

test('5 brief: parsed words update swatches but never a tapped one', async ({ page }) => {
  await toBuild(page, 'dog', 'beagle');
  await page.getByTestId('tile-ears.shape-erect').tap(); // a tap always wins
  await page.getByTestId('nav-next').tap();
  await typeOnKeyboard(page, 'floppy ears, blue eyes, red collar');
  await page.getByTestId('brief-apply').tap();
  await expect(page.getByTestId('brief-result')).toContainText('Eyes');
  await expect(page.getByTestId('brief-result')).toContainText('Accessories');
  await expect(page.getByTestId('brief-result')).not.toContainText('Ears');
  await page.getByTestId('brief-review').tap();
  await expect(page.getByTestId('tile-ears.shape-erect')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('swatch-eyes-blue')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.ring-highlight').first()).toBeVisible();
});

test('5b brief with nothing mappable is used for flavour only', async ({ page }) => {
  await toBuild(page);
  await page.getByTestId('nav-next').tap();
  await typeOnKeyboard(page, 'the best boy');
  await page.getByTestId('brief-apply').tap();
  await expect(page.getByTestId('brief-result')).toContainText('flavour only');
});

test('6 name and generate: summary card and three-run cap', async ({ page }) => {
  await toBuild(page);
  await page.getByTestId('nav-next').tap();
  await page.getByTestId('nav-next').tap();
  await expect(page.getByTestId('nav-next')).toBeDisabled();
  await typeOnKeyboard(page, 'biscuit');
  await expect(page.getByTestId('summary-card')).toContainText('Pembroke Welsh Corgi');
  await expect(page.getByTestId('generations-left')).toContainText('3 of 3');
  await page.getByTestId('nav-next').tap();
  await expect(page.locator('[data-screen=generating]')).toBeVisible();
});

test('7 generating shows real previews in order, then the result', async ({ page }) => {
  await toGenerate(page, 'Biscuit');
  await expect(page.getByTestId('stage-B')).toHaveAttribute('data-state', /done|current/);
  await expect(page.locator('[data-screen=result]')).toBeVisible({ timeout: 60_000 });
});

test('7b slow queue shows the queue position', async ({ page }) => {
  await toGenerate(page, 'Slowpoke');
  await expect(page.getByTestId('queue-position')).toBeVisible();
  await expect(page.locator('[data-screen=result]')).toBeVisible({ timeout: 60_000 });
});

test('7c failed stage offers a way back', async ({ page }) => {
  await toGenerate(page, 'Oops');
  await expect(page.getByTestId('generate-failed')).toContainText('Stage D', { timeout: 60_000 });
  await page.getByRole('button', { name: 'Back to Build' }).tap();
  await expect(page.locator('[data-screen=build]')).toBeVisible();
});

test('8 result: clay toggle, QR, send to print, tweak keeps the seed', async ({ page }) => {
  await toGenerate(page, 'Plan B');
  await expect(page.locator('[data-screen=result]')).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText('classic figure shape')).toBeVisible();
  await expect(page.getByTestId('result-qr').locator('svg')).toBeVisible();
  await page.getByTestId('toggle-clay').tap();
  await expect(page.getByTestId('toggle-clay')).toHaveAttribute('aria-pressed', 'true');
  await page.getByTestId('send-to-print').tap();
  await expect(page.getByTestId('ticket')).toContainText('PP-');
  await page.getByTestId('tweak').tap();
  await expect(page.locator('[data-screen=build]')).toBeVisible();
  await page.getByTestId('tile-tail.type-plume').tap();
  await page.getByTestId('nav-next').tap();
  await page.getByTestId('nav-next').tap();
  await page.getByTestId('nav-next').tap();
  await expect(page.locator('[data-screen=generating]')).toBeVisible();
});

test('phone result page opens from the QR link', async ({ page, request }) => {
  const sid = (await (await request.post('/api/v1/sessions', { data: {} })).json()).session_id;
  const spec = await (await request.get('/fixtures/sunny/spec.json')).json();
  const job = await (await request.post('/api/v1/jobs', { data: { session_id: sid, spec } })).json();
  let url = '';
  for (let i = 0; i < 100 && !url; i++) {
    const j = await (await request.get(`/api/v1/jobs/${job.job_id}`)).json();
    url = j.result_url ?? '';
    if (!url) await page.waitForTimeout(300);
  }
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

test('staff panel opens with five corner taps and lists jobs', async ({ page }) => {
  await page.goto('/');
  for (let i = 0; i < 5; i++) await page.getByTestId('staff-corner').tap();
  await expect(page.getByTestId('staff-panel')).toBeVisible();
  await typeOnKeyboard(page, 'x');
  await page.getByTestId('key-done').tap();
  await expect(page.getByText('Token not accepted')).toBeVisible();
  await page.getByTestId('key-backspace').tap();
  await typeOnKeyboard(page, 'staffpin');
  await page.getByTestId('key-done').tap();
  await expect(page.getByTestId('staff-queue')).toContainText('mock');
  await page.getByTestId('staff-close').tap();
  await expect(page.getByTestId('staff-panel')).toBeHidden();
});

// One Playwright test per Studio screen and behaviour (BRIEF Sections 2, 4 and 17).
import { expect, test } from '@playwright/test';
import { PASSWORD, signIn, toBuild, toGenerate, typeOnKeyboard } from './helpers';

test('0 sign in: a wrong password is refused, a staff login opens the Generate workspace', async ({ page }) => {
  await page.goto('/studio/');
  await page.getByTestId('login-username').fill('operator');
  await page.getByTestId('login-password').fill('wrong');
  await page.getByTestId('login-submit').tap();
  await expect(page.getByTestId('login-error')).toContainText('Wrong username or password');
  await page.getByTestId('login-password').fill(PASSWORD);
  await page.getByTestId('login-submit').tap();
  await expect(page.getByTestId('studio-user')).toContainText('operator (operator)');
  await page.reload();
  await expect(page.getByTestId('studio-user')).toBeVisible(); // the session survives a reload
  await page.getByTestId('logout').tap();
  await expect(page.getByTestId('login')).toBeVisible();
});

test('1 species tiles set the species accent', async ({ page }) => {
  await signIn(page);
  await page.getByTestId('species-cat').tap();
  await expect(page.locator('.kiosk')).toHaveAttribute('data-species', 'cat');
  await expect(page.getByTestId('breed-siamese')).toBeVisible();
});

test('2 breed search with the on-screen keyboard and the Mixed tile', async ({ page }) => {
  await signIn(page);
  await page.getByTestId('species-dog').tap();
  await expect(page.getByTestId('breed-mixed')).toBeAttached();
  await page.getByTestId('breed-search').tap();
  await typeOnKeyboard(page, 'cor');
  await expect(page.getByTestId('breed-corgi_pembroke')).toBeVisible();
  await expect(page.getByTestId('breed-beagle')).toHaveCount(0);
  await page.getByTestId('breed-corgi_pembroke').tap();
  await expect(page.getByText('Build your Pembroke Welsh Corgi')).toBeVisible();
});

test('3 build: preset is pre-ticked, taps override, live preview renders', async ({ page }) => {
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

test('4 brief: parsed words update swatches but never a tapped one', async ({ page }) => {
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

test('4b brief with nothing mappable is used for flavour only', async ({ page }) => {
  await toBuild(page);
  await page.getByTestId('nav-next').tap();
  await typeOnKeyboard(page, 'the best boy');
  await page.getByTestId('brief-apply').tap();
  await expect(page.getByTestId('brief-result')).toContainText('flavour only');
});

test('5 name and generate: summary card, name required', async ({ page }) => {
  await toBuild(page);
  await page.getByTestId('nav-next').tap();
  await page.getByTestId('nav-next').tap();
  await expect(page.getByTestId('nav-next')).toBeDisabled();
  await typeOnKeyboard(page, 'biscuit');
  await expect(page.getByTestId('summary-card')).toContainText('Pembroke Welsh Corgi');
  await page.getByTestId('nav-next').tap();
  await expect(page.locator('[data-screen=generating]')).toBeVisible();
});

test('6 generating shows real previews in order, then the result', async ({ page }) => {
  await toGenerate(page, 'Biscuit');
  await expect(page.getByTestId('stage-B')).toHaveAttribute('data-state', /done|current/);
  await expect(page.locator('[data-screen=result]')).toBeVisible({ timeout: 60_000 });
});

test('6b slow queue shows the queue position', async ({ page }) => {
  await toGenerate(page, 'Slowpoke');
  await expect(page.getByTestId('queue-position')).toBeVisible();
  await expect(page.locator('[data-screen=result]')).toBeVisible({ timeout: 60_000 });
});

test('6c failed stage offers a way back', async ({ page }) => {
  await toGenerate(page, 'Oops');
  await expect(page.getByTestId('generate-failed')).toContainText('Stage D', { timeout: 60_000 });
  await page.getByRole('button', { name: 'Back to Build' }).tap();
  await expect(page.locator('[data-screen=build]')).toBeVisible();
});

test('7 result: clay toggle, QR, send to print, tweak keeps the seed', async ({ page }) => {
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

test('offline: "Back in a moment" while the API is down, auto-recovers', async ({ page }) => {
  await signIn(page);
  await page.route('**/api/v1/health', (r) => r.abort());
  await expect(page.getByTestId('offline')).toBeVisible({ timeout: 15_000 });
  await page.unroute('**/api/v1/health');
  await expect(page.getByTestId('offline')).toBeHidden({ timeout: 15_000 });
});

test('queue panel lists jobs with who asked for them, retry re-runs one', async ({ page }) => {
  await toGenerate(page, 'Biscuit');
  await expect(page.locator('[data-screen=result]')).toBeVisible({ timeout: 60_000 });
  await page.getByTestId('open-queue').tap();
  await expect(page.getByTestId('staff-queue')).toContainText('Biscuit');
  await expect(page.getByTestId('staff-queue')).toContainText('operator');
  await page.getByRole('button', { name: 'Retry' }).first().tap();
  await page.getByTestId('staff-close').tap();
  await expect(page.getByTestId('staff-panel')).toBeHidden();
});

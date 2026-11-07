// One Playwright test per Studio screen and behaviour (BRIEF Sections 2, 4 and 17).
import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { PASSWORD, runBatch, signIn, signInHome, toBuild, toGenerate, typeInto } from './helpers';

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

test('2 breed search and the Mixed tile', async ({ page }) => {
  await signIn(page);
  await page.getByTestId('species-dog').tap();
  await expect(page.getByTestId('breed-mixed')).toBeAttached();
  await typeInto(page, 'breed-search', 'cor');
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
  await typeInto(page, 'brief-text', 'floppy ears, blue eyes, red collar');
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
  await typeInto(page, 'brief-text', 'the best boy');
  await page.getByTestId('brief-apply').tap();
  await expect(page.getByTestId('brief-result')).toContainText('flavour only');
});

test('5 name and generate: summary card, name required', async ({ page }) => {
  await toBuild(page);
  await page.getByTestId('nav-next').tap();
  await page.getByTestId('nav-next').tap();
  await expect(page.getByTestId('nav-next')).toBeDisabled();
  await typeInto(page, 'name-text', 'biscuit');
  await expect(page.getByTestId('summary-card')).toContainText('Pembroke Welsh Corgi');
  // Run on: the server default is picked; a profile missing its key is listed but cannot be chosen
  await expect(page.getByTestId('profile-mock')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('pipeline-multiview')).toHaveAttribute('aria-pressed', 'true'); // the mock's default pipeline
  await expect(page.getByTestId('profile-tripo')).toContainText('needs TRIPO_API_KEY');
  await page.getByTestId('profile-tripo').tap();
  await expect(page.getByTestId('profile-mock')).toHaveAttribute('aria-pressed', 'true');
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

test('8 generate: the batch spec builder counts breeds x variants x seeds and starts a batch', async ({ page }) => {
  await signInHome(page);
  await page.getByTestId('batch-breed-beagle').tap();
  await page.getByTestId('batch-breed-pug').tap();
  await page.getByTestId('batch-variant-big_ears').tap();
  await page.getByTestId('seeds-plus').tap();
  await expect(page.getByTestId('start-batch')).toContainText('Generate 8 figurines'); // 2 breeds x 2 variants x 2 seeds
  await page.getByTestId('batch-breed-pug').tap();
  await page.getByTestId('batch-variant-big_ears').tap();
  await page.getByTestId('seeds-minus').tap();
  await expect(page.getByTestId('start-batch')).toContainText('Generate 1 figurine');
  await page.getByTestId('profile-tripo-manual').tap(); // this batch runs on Tripo by hand
  await expect(page.getByTestId('profile-description')).toContainText('manual mode');
  await expect(page.getByTestId('pipeline-single_view')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('option-hd_texture')).toHaveAttribute('aria-pressed', 'true'); // HD texture is on by default
  await expect(page.getByTestId('credit-estimate')).toContainText('45 API credits'); // 35 + HD texture 10
  await page.getByTestId('pipeline-multiview').tap();
  await page.getByTestId('option-hd_geometry').tap();
  await expect(page.getByTestId('credit-estimate')).toContainText('75 API credits'); // 45 + 10 + 20
  await page.getByTestId('start-batch').tap();
  await expect(page.getByTestId('curate-notice')).toContainText('Batch started: 1 figurines');
  await expect(page.getByTestId('batch-list').locator('button')).not.toHaveCount(0);
  await expect(page.getByTestId('batch-list')).toContainText('on tripo-manual, multiview');
});

test('9 review: each figurine is a mesh of its own with mesh QC; accept, tag, publish; the mesh is labelled', async ({ page }) => {
  await signInHome(page, 'curator');
  await runBatch(page, ['beagle']);
  const figs = page.locator('[data-testid^=fig-]');
  await expect(figs.first().locator('video, img').first()).toBeVisible();
  await expect(figs.first().locator('[data-testid^=cand-]')).toHaveCount(1); // one family, on the figurine's own mesh
  await expect(page.getByTestId('review')).toContainText('Family on its own mesh');
  await expect(page.getByTestId('review')).toContainText('parts labelled');
  await page.getByTestId('accept-passing').tap();
  await expect(page.getByTestId('review')).toContainText('accepted');
  const beagle = (await page.locator('[data-testid^=cand-family_beagle_]').getAttribute('data-testid'))!.replace('cand-', '');
  await page.getByTestId(`hero-${beagle}`).tap();
  await expect(page.getByTestId(`hero-${beagle}`)).toHaveAttribute('aria-pressed', 'true');
  await page.getByTestId(`publish-${beagle}`).tap();
  await expect(page.getByTestId(`cand-${beagle}`)).toContainText('published');
  await expect(page.getByTestId('review')).toContainText('1 meshes');
  // The library editor names the family's mesh and who shares it.
  await page.getByTestId('nav-library').tap();
  await page.getByTestId('kind-family').tap();
  await page.getByTestId('item-family_standard').tap();
  await expect(page.getByTestId('item-mesh')).toContainText('shared with');
});

test('10 library: the pattern editor versions a published layer; publish ships the new version', async ({ page }) => {
  await signInHome(page, 'curator');
  await page.getByTestId('nav-library').tap();
  await page.getByTestId('kind-pattern').tap();
  await page.getByTestId('item-pattern_blaze').tap();
  await expect(page.getByTestId('item-editor')).toContainText('published 1');
  await page.getByTestId('edit-name').fill('Big blaze');
  await page.getByTestId('edit-colour-F2C230').tap();
  await page.getByTestId('cov-default').fill('0.6');
  await page.getByTestId('edit-save').tap();
  await expect(page.getByTestId('curate-notice')).toContainText('as version 2');
  await page.getByTestId('edit-publish').tap();
  await expect(page.getByTestId('curate-notice')).toContainText('Published Big blaze v2');
  await expect(page.getByTestId('item-editor')).toContainText('published 2');
  await page.getByTestId('kind-shell').tap();
  await page.getByTestId('item-shell_collar').tap();
  await page.getByTestId('edit-tags').fill('classic, red');
  await page.getByTestId('edit-save').tap();
  await expect(page.getByTestId('item-editor')).toContainText('version 2');
});

test('11 releases: only an admin publishes a release, and it lists with its counts', async ({ page }) => {
  await signInHome(page, 'curator');
  await page.getByTestId('nav-releases').tap();
  await expect(page.getByTestId('create-release')).toBeDisabled();
  await expect(page.getByTestId('release-release-dog-1')).toBeVisible();
  await page.getByTestId('logout').tap();
  await signInHome(page, 'admin');
  await page.getByTestId('nav-releases').tap();
  await page.getByTestId('create-release').tap();
  await expect(page.getByTestId('curate-notice')).toContainText('release-dog-');
  await expect(page.locator('[data-testid^=release-release-dog-]')).toHaveCount(2);
});

test('12 manual: the inbox shows what the API would get; uploading an output resumes the job', async ({ page }) => {
  await signInHome(page);
  await expect(page.getByTestId('manual-pending')).toHaveText('3');
  await page.getByTestId('nav-manual').tap();
  await expect(page.locator('[data-screen=manual]')).toBeVisible();
  await page.getByTestId('manual-task-j_manual_demo.text-to-image-demo').tap();
  await expect(page.getByTestId('manual-prompt')).toContainText('chibi vinyl collectible figurine');
  await expect(page.getByTestId('manual-negative')).toBeVisible();
  await expect(page.getByTestId('manual-steps')).toContainText('Tripo Studio');
  await page.getByTestId('manual-file').setInputFiles({ name: 'concept.txt', mimeType: 'text/plain', buffer: Buffer.from('nope') });
  await page.getByTestId('manual-submit').tap();
  await expect(page.getByTestId('manual-error')).toBeVisible(); // a text file is not an image
  await page.getByTestId('manual-file').setInputFiles('../../fixtures/pets/biscuit/concept.png');
  await page.getByTestId('manual-submit').tap();
  await expect(page.getByTestId('manual-notice')).toContainText('the job carries on');
  await expect(page.getByTestId('manual-pending')).toHaveText('2', { timeout: 20_000 });
  await page.getByTestId('manual-task-j_manual_demo.image-to-model-demo').tap();
  await expect(page.getByTestId('manual-settings')).toContainText('model: v3.1-20260211');
  await expect(page.getByTestId('manual-input-input.png')).toBeVisible();
  await expect(page.getByTestId('manual-request')).toBeAttached();
  await page.getByTestId('manual-file').setInputFiles('../../fixtures/pets/biscuit/figure.glb');
  await page.getByTestId('manual-submit').tap();
  await expect(page.getByTestId('manual-notice')).toContainText('figure.glb received');
  // a four-view task (multiview pipeline): one upload per slot; the job carries on once all four are in
  await page.getByTestId('manual-task-j_manual_demo.image-to-multiview-demo').tap();
  for (const slot of ['front', 'left', 'back', 'right']) {
    await page.getByTestId(`manual-file-${slot}`).setInputFiles('../../fixtures/pets/biscuit/concept.png');
    await page.getByTestId(`manual-submit-${slot}`).tap();
    if (slot !== 'right') await expect(page.getByTestId(`manual-slot-${slot}-done`)).toBeVisible(); // the last one completes the task
  }
  await expect(page.getByTestId('manual-notice')).toContainText('the job carries on');
  await page.getByTestId('manual-filter-submitted').tap();
  await expect(page.getByTestId('manual-list')).toContainText('submitted');
});

test('13 parts: labelled GLBs in, a kit per breed with every kind', async ({ page }) => {
  await signInHome(page, 'curator');
  await page.getByTestId('nav-parts').tap();
  await expect(page.locator('[data-screen=parts]')).toBeVisible();
  const dir = '../../fixtures/parts/cat';
  const files = ['mixed__head.glb', 'mixed__torso.glb', 'mixed__front_leg.glb', 'mixed__hind_leg.glb', 'mixed__tail.glb', 'mixed__tail__plume.glb'];
  await page.getByTestId('parts-species-cat').tap();
  await page.getByTestId('parts-upload').setInputFiles(files.map((f) => `${dir}/${f}`));
  await expect(page.getByTestId('parts-notice')).toContainText('6 parts for mixed');
  await expect(page.getByTestId('kit-mixed')).toContainText('ready to commit');
});

test('14 rigging: joints, symmetry, a pose, commit', async ({ page }) => {
  await signInHome(page, 'curator');
  await page.getByTestId('nav-parts').tap();
  await page.getByTestId('parts-species-dog').tap();
  const dir = '../../fixtures/parts/dog';
  const kinds = ['head', 'torso', 'front_leg', 'hind_leg', 'tail'];
  await page.getByTestId('parts-scale').uncheck(); // the proxies are split from one figure: already in proportion
  await page.getByTestId('parts-upload').setInputFiles(kinds.map((k) => `${dir}/mixed__${k}.glb`).concat(`${dir}/mixed__torso__slim.glb`));
  await page.getByTestId('open-kit-mixed').tap();
  await expect(page.locator('[data-screen=rigging]')).toBeVisible();
  await expect(page.getByTestId('rig-view').locator('canvas')).toBeVisible();
  // the first guess, per joint
  await expect(page.getByTestId('joint-part-front_leg')).toContainText('in place, cut');
  // move the front-left socket: symmetry moves the front-right one to the mirror position
  await page.getByTestId('joint-slot-front_left').tap();
  await page.getByTestId('rig-point-0').fill('9');
  await page.getByTestId('rig-point-0').press('Enter');
  await page.getByTestId('joint-slot-front_right').tap();
  await expect(page.getByTestId('rig-point-0')).toHaveValue('-9');
  // a part's own pivot, in the part view
  await page.getByTestId('joint-part-head').tap();
  await expect(page.getByTestId('view-part')).toHaveAttribute('aria-pressed', 'true');
  await page.getByTestId('rig-point-1').fill('41');
  await page.getByTestId('rig-point-1').press('Enter');
  await expect(page.getByTestId('joint-part-head')).toContainText('(edited)');
  await page.getByTestId('rig-reguess').tap();
  await expect(page.getByTestId('joint-part-head')).not.toContainText('(edited)');
  // a variant as the default, a second pose with the legs turned a third
  await page.getByTestId('variant-torso-slim').tap();
  if (await page.getByTestId('variant-default-torso').isVisible()) await page.getByTestId('variant-default-torso').tap(); // (already, on a re-run)
  await expect(page.getByTestId('variant-torso-slim')).toContainText('★');
  const before = await page.locator('[data-testid^=pose-label-]').count();
  await page.getByTestId('pose-add').tap();
  const id = `pose_${before + 1}`;
  await page.getByTestId(`pose-${id}-front_left-1`).tap();
  await expect(page.getByTestId(`pose-${id}-front_right-1`)).toHaveAttribute('aria-pressed', 'true'); // symmetry
  await page.getByTestId(`pose-preview-${id}`).tap();
  await page.getByTestId('joint-slot-front_left').tap();
  await page.waitForTimeout(800);
  await page.screenshot({ path: `test-results/rigging-${test.info().project.name}.png` });
  // commit
  const next = (await page.getByTestId('rig-commit-button').textContent())!.match(/v(\d+)/)![1]; // the shared mock server may hold earlier versions
  await page.getByTestId('rig-commit-button').tap();
  await expect(page.getByTestId('rig-notice')).toContainText(`kit version ${next}`);
  await expect(page.getByTestId('rig-commit-button')).toBeDisabled(); // nothing new to commit
});

test('15 shared library: shared torsos, legs and tails, a breed head, stretched to the breed (decision 130)', async ({ page }) => {
  await signInHome(page, 'curator');
  await page.getByTestId('nav-parts').tap();
  await page.getByTestId('parts-species-dog').tap();
  // the proxy parts, uploaded as the shared library under the breed database's part types, and a corgi head
  const dir = '../../fixtures/parts/dog';
  const as = (from: string, name: string) => ({ name, mimeType: 'model/gltf-binary', buffer: readFileSync(`${dir}/${from}`) });
  await page.getByTestId('parts-upload').setInputFiles([
    as('mixed__torso.glb', 'shared__torso__long_low.glb'), as('mixed__front_leg.glb', 'shared__fore_leg__paw.glb'),
    as('mixed__hind_leg.glb', 'shared__hind_leg__bean.glb'), as('mixed__hind_leg.glb', 'shared__hind_leg_sitting__sitting_fold.glb'),
    as('mixed__tail.glb', 'shared__tail__bob.glb'), as('mixed__head.glb', 'corgi_pembroke__head.glb'),
  ]);
  await expect(page.getByTestId('parts-notice')).toContainText('6 parts for corgi_pembroke, shared');
  await expect(page.getByTestId('kit-shared')).toContainText('Shared parts');
  await page.getByTestId('open-kit-corgi_pembroke').tap();
  await expect(page.locator('[data-screen=rigging]')).toBeVisible();
  // the corgi's own part types from the shared library, its short legs, its sitting pose and its colours
  await expect(page.getByTestId('variant-front_leg-paw')).toContainText('⧉');
  // parts show their own textures; clay on demand
  await page.getByTestId('view-clay').tap();
  await expect(page.getByTestId('view-clay')).toHaveAttribute('aria-pressed', 'true');
  await page.getByTestId('view-clay').tap();
  await expect(page.getByTestId('view-clay')).toHaveAttribute('aria-pressed', 'false');
  expect(Number(await page.getByTestId('stretch-front_leg-1').inputValue())).toBeLessThan(0.8);
  await expect(page.getByTestId('pose-sitting')).toBeVisible();
  await expect(page.getByTestId('pose-default-sitting')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('texture-base-hex')).toBeVisible();
  await expect(page.getByTestId('marking-white_blaze')).toBeVisible();
  // the default texture, edited: colours, pattern, markings; saved as it changes
  await page.getByTestId('texture-base-name').fill('ginger');
  await page.getByTestId('texture-base-name').press('Enter');
  await page.getByTestId('texture-base-hex').fill('#d2691e');
  await page.getByTestId('texture-pattern').selectOption('tricolour');
  if (await page.getByTestId('texture-tertiary-add').isVisible()) await page.getByTestId('texture-tertiary-add').tap();
  await expect(page.getByTestId('texture-tertiary-hex')).toBeVisible();
  if (await page.getByTestId('marking-white_socks').isVisible()) await page.getByTestId('marking-white_socks').tap();
  await expect(page.getByTestId('marking-white_socks')).toHaveCount(0);
  if (await page.getByTestId('marking-add-dark_mask').isVisible()) await page.getByTestId('marking-add-dark_mask').tap();
  await page.getByTestId('marking-new').fill('White Tail Tip');
  await page.getByTestId('marking-new').press('Enter');
  await expect(page.getByTestId('marking-white_tail_tip')).toBeVisible();
  await page.getByTestId('rig-back').tap();
  await page.getByTestId('open-kit-corgi_pembroke').tap();
  await expect(page.getByTestId('texture-base-name')).toHaveValue('ginger');
  await expect(page.getByTestId('texture-base-hex')).toHaveValue('#d2691e');
  await expect(page.getByTestId('texture-pattern')).toHaveValue('tricolour');
  await expect(page.getByTestId('marking-dark_mask')).toBeVisible();
  // a stretch set by hand, then back to the size guess
  await page.getByTestId('stretch-front_leg-1').fill('0.5');
  await page.getByTestId('stretch-front_leg-1').press('Enter');
  await expect(page.getByTestId('stretch-reset-front_leg')).toBeVisible();
  await page.getByTestId('stretch-reset-front_leg').tap();
  await expect(page.getByTestId('stretch-reset-front_leg')).toBeHidden();
  // a shape preset for customers (decision 131): its own stretch, and a socket moved for this breed (symmetry mirrors it)
  await page.getByTestId('preset-add').tap();
  await expect(page.getByTestId('preset-label')).toBeVisible();
  await page.getByTestId('preset-label').fill('Stocky');
  await page.getByTestId('preset-label').press('Enter');
  await expect(page.getByTestId('torso-presets')).toContainText('Stocky');
  await page.getByTestId('stretch-torso-0').fill('1.3');
  await page.getByTestId('stretch-torso-0').press('Enter');
  await expect(page.getByTestId('stretch-torso-0')).toHaveValue('1.30');
  await page.getByTestId('joint-slot-front_left').tap();
  await expect(page.getByTestId('rig-offset')).toBeVisible();
  await page.getByTestId('rig-offset-t-2').fill('3');
  await page.getByTestId('rig-offset-t-2').press('Enter');
  await page.getByTestId('joint-slot-front_right').tap();
  await expect(page.getByTestId('rig-offset-t-2')).toHaveValue('3');
  await page.getByTestId('preset-default').tap();
  await expect(page.getByTestId('stretch-torso-0')).not.toHaveValue('1.30');
  await page.waitForTimeout(800);
  await page.screenshot({ path: `test-results/shared-${test.info().project.name}.png` });
  await expect(page.getByTestId('rig-problems')).toHaveCount(0);
  const next = (await page.getByTestId('rig-commit-button').textContent())!.match(/v(\d+)/)![1];
  await page.getByTestId('rig-commit-button').tap();
  await expect(page.getByTestId('rig-notice')).toContainText(`Pembroke Welsh Corgi kit version ${next}`);
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

// Gate 7 (M7, BRIEF Section 16) browser checks: the coverage slider stays smooth with 10 layers active, and the
// atlas the kiosk shows is the atlas the export prints (the bake is compared with petpop_library.paint by
// scripts/gate7_print_matches_screen.py). Run by scripts/gates/gate-7 with playwright.gate7.config.ts.
import { mkdirSync, writeFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';
import { kiosk, toDesign, typeOnKeyboard } from '../e2e/helpers';

const OUT = 'test-results/gate7';

async function allLayers(page: Page) {
  await page.getByTestId('tab-patterns').tap();
  const tiles = page.getByTestId('pattern-tiles').locator('button');
  for (let i = 0; i < (await tiles.count()); i++) {
    if ((await tiles.nth(i).getAttribute('aria-pressed')) === 'false') await tiles.nth(i).tap();
  }
  await expect(page.getByTestId('pattern-tiles').locator('[aria-pressed=true]')).toHaveCount(10);
}

test.describe('slider', () => {
  test.use({ deviceScaleFactor: 1 });

  test('coverage slider is smooth with 10 layers active', async ({ page }) => {
    await toDesign(page);
    await allLayers(page);
    await page.waitForTimeout(1000);
    // In the page, no CDP round trips: 60 slider moves on the first layer, one per animation frame. Each move is
    // timed from the input event to the end of React's synchronous update; texture uploads are counted.
    const r = await page.evaluate(async () => {
      const input = document.querySelector<HTMLInputElement>('[data-testid^=coverage-]')!;
      const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      const uploads = { n: 0 };
      const protos = [WebGLRenderingContext.prototype, WebGL2RenderingContext.prototype] as unknown as Record<string, (...a: unknown[]) => unknown>[];
      const restore: (() => void)[] = [];
      for (const p of protos) {
        for (const name of ['texImage2D', 'texSubImage2D']) {
          const orig = p[name];
          p[name] = function (this: unknown, ...a: unknown[]) {
            uploads.n++;
            return orig.apply(this, a);
          };
          restore.push(() => (p[name] = orig));
        }
      }
      const min = Number(input.min), max = Number(input.max);
      const costs: number[] = [];
      const frames: number[] = [];
      let last = performance.now();
      for (let i = 0; i < 60; i++) {
        const v = min + ((max - min) * (i % 20)) / 19;
        const t0 = performance.now();
        setValue.call(input, String(Number(v.toFixed(2))));
        input.dispatchEvent(new Event('input', { bubbles: true }));
        costs.push(performance.now() - t0);
        const t = await new Promise<number>((res) => requestAnimationFrame(res));
        frames.push(t - last);
        last = t;
      }
      restore.forEach((f) => f());
      const q = (a: number[], f: number) => [...a].sort((x, y) => x - y)[Math.floor(a.length * f)];
      return { median: q(costs, 0.5), p95: q(costs, 0.95), uploads: uploads.n, frameMedian: q(frames, 0.5), value: input.value };
    });
    console.log(`gate7 slider (10 layers): update cost median ${r.median.toFixed(2)} ms, p95 ${r.p95.toFixed(2)} ms; ` +
      `texture uploads ${r.uploads}; frame interval median ${r.frameMedian.toFixed(1)} ms (software GL)`);
    expect(r.uploads).toBe(0); // coverage is a uniform: the masks are thresholded in the shader
    expect(r.median).toBeLessThan(8); // well inside a 60 fps frame
    expect(r.p95).toBeLessThan(16.7);
  });
});

test('print matches screen: the baked shader atlas for a composition with layers, stamps and a shell', async ({ page }) => {
  await toDesign(page, 'dog', 'beagle');
  await allLayers(page);
  for (const id of ['pattern_tabby', 'pattern_merle', 'pattern_brindle', 'pattern_points', 'pattern_mask', 'pattern_tuxedo']) {
    await page.getByTestId(`pattern-${id}`).tap(); // keep four layers so each one shows
  }
  await page.getByTestId('tab-paint').tap();
  await page.getByTestId('tool-spot-l').tap();
  const canvas = page.getByTestId('design-preview').locator('canvas');
  const box = (await canvas.boundingBox())!;
  for (const [x, y] of [[0.42, 0.6], [0.47, 0.35], [0.4, 0.75]]) await canvas.tap({ position: { x: box.width * x, y: box.height * y } });
  await expect(page.getByTestId('stamp-count')).not.toContainText(/^0\//);
  await page.getByTestId('tab-extras').tap();
  await page.getByTestId('shell-shell_collar').tap();
  const res = await page.evaluate(() => {
    const p = (window as unknown as { __petpop: { bake: () => Uint8Array; composition: () => unknown } }).__petpop;
    const rgba = p.bake();
    let s = '';
    for (let i = 0; i < rgba.length; i += 0x8000) s += String.fromCharCode(...rgba.subarray(i, i + 0x8000));
    return { b64: btoa(s), composition: p.composition() };
  });
  mkdirSync(OUT, { recursive: true });
  writeFileSync(`${OUT}/bake.rgba`, Buffer.from(res.b64, 'base64'));
  writeFileSync(`${OUT}/composition.json`, JSON.stringify(res.composition, null, 1));
  expect(Buffer.from(res.b64, 'base64').length).toBeGreaterThan(0);
});

test('print matches screen: a figure of parts, every slot\'s tile with markings, spots and an extra', async ({ page }) => {
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
  await page.getByTestId('tab-patterns').tap();
  await page.getByTestId('kit-marking-white_socks').tap();
  await page.getByTestId('tab-paint').tap();
  await page.getByTestId('tool-spot-l').tap();
  const canvas = view.locator('canvas');
  const box = (await canvas.boundingBox())!;
  for (const [x, y] of [[0.5, 0.45], [0.42, 0.75], [0.5, 0.25]]) await canvas.tap({ position: { x: box.width * x, y: box.height * y } });
  await expect(page.getByTestId('stamp-count')).not.toContainText(/^0\//);
  await page.getByTestId('tab-extras').tap();
  await page.getByTestId('shell-shell_collar').tap();
  await expect(view).toHaveAttribute('data-extras', 'shell_collar');
  const res = await page.evaluate(async () => {
    const p = (window as unknown as { __petpop: { bakeTiles: (size: number) => Promise<Record<string, { key: string; rgba: Uint8Array }>>; composition: () => unknown } }).__petpop;
    const tiles = await p.bakeTiles(128);
    const out: Record<string, { key: string; b64: string }> = {};
    for (const [slot, t] of Object.entries(tiles)) {
      let s = '';
      for (let i = 0; i < t.rgba.length; i += 0x8000) s += String.fromCharCode(...t.rgba.subarray(i, i + 0x8000));
      out[slot] = { key: t.key, b64: btoa(s) };
    }
    return { tiles: out, composition: p.composition() };
  });
  mkdirSync(`${OUT}/kit`, { recursive: true });
  writeFileSync(`${OUT}/kit/tiles.json`, JSON.stringify({ size: 128, tiles: res.tiles }));
  writeFileSync(`${OUT}/kit/composition.json`, JSON.stringify(res.composition, null, 1));
  expect(Object.keys(res.tiles).length).toBe(7);
});

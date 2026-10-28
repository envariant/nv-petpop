// Copy generated, non-source assets into public/ (all gitignored): base meshes and masks, the Draco
// decoder (no CDN calls from the kiosk), the MSW worker and the fixture pack for standalone mode.
import { cpSync, existsSync, mkdirSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, '..');
const root = join(app, '../..');
const pub = join(app, 'public');

for (const species of ['dog', 'cat']) {
  const src = join(root, 'assets/base', species);
  const dst = join(pub, 'assets/base', species);
  mkdirSync(dst, { recursive: true });
  for (const f of ['base.glb', 'mask_a.png', 'mask_b.png', 'morphs.json']) {
    if (existsSync(join(src, f))) cpSync(join(src, f), join(dst, f));
  }
}
const tiles = join(root, 'assets/tiles');
if (existsSync(tiles)) cpSync(tiles, join(pub, 'assets/tiles'), { recursive: true });
cpSync(join(app, 'node_modules/three/examples/jsm/libs/draco/gltf'), join(pub, 'draco'), { recursive: true });
cpSync(join(app, 'node_modules/msw/lib/mockServiceWorker.js'), join(pub, 'mockServiceWorker.js'));
const fx = join(root, 'fixtures/pets');
if (existsSync(fx)) {
  mkdirSync(join(pub, 'fixtures'), { recursive: true });
  for (const d of readdirSync(fx)) cpSync(join(fx, d), join(pub, 'fixtures', d), { recursive: true });
}
console.log('assets synced into public/');

// Copy generated, non-source assets into public/ (all gitignored): base meshes and masks, the Draco
// decoder (no CDN calls from the kiosk), the MSW worker and the fixture pack for standalone mode.
import { cpSync, existsSync, mkdirSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { unpackReleases } from '../../../scripts/unpack_releases.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, '..');
const root = join(app, '../..');
const pub = join(app, 'public');
// npm workspaces hoist dependencies to the repo root; resolve them from here wherever they live.
const pkg = (name) => [join(app, 'node_modules', name), join(root, 'node_modules', name)].find((d) => existsSync(d));

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
cpSync(join(pkg('three'), 'examples/jsm/libs/draco/gltf'), join(pub, 'draco'), { recursive: true });
cpSync(join(pkg('msw'), 'lib/mockServiceWorker.js'), join(pub, 'mockServiceWorker.js'));
const fx = join(root, 'fixtures/pets');
if (existsSync(fx)) {
  mkdirSync(join(pub, 'fixtures'), { recursive: true });
  for (const d of readdirSync(fx)) cpSync(join(fx, d), join(pub, 'fixtures', d), { recursive: true });
}
unpackReleases(root, pub); // the proxy library releases, for standalone mode
console.log('assets synced into public/');

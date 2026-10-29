// Copy generated, non-source assets into public/ (all gitignored): base meshes and masks, the Draco
// decoder (no CDN calls from the kiosk), the MSW worker and the fixture pack for standalone mode.
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

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
// The committed proxy library releases, unpacked for standalone mode (the real kiosk serves them from its API).
function untar(buf, dst) {
  for (let off = 0; off + 512 <= buf.length; ) {
    const name = buf.toString('utf8', off, off + 100).replace(/\0.*$/s, '');
    if (!name) break;
    const size = parseInt(buf.toString('utf8', off + 124, off + 136).replace(/\0.*$/s, '').trim() || '0', 8);
    const type = buf[off + 156];
    if (type === 0 || type === 48) {
      if (name.split('/').includes('..') || name.startsWith('/')) throw new Error(`unsafe path ${name}`);
      mkdirSync(dirname(join(dst, name)), { recursive: true });
      writeFileSync(join(dst, name), buf.subarray(off + 512, off + 512 + size));
    }
    off += 512 + Math.ceil(size / 512) * 512;
  }
}
const lib = join(root, 'fixtures/library');
if (existsSync(lib)) {
  for (const f of readdirSync(lib).filter((n) => /^release-(dog|cat)-\d+\.tar$/.test(n))) {
    untar(readFileSync(join(lib, f)), join(pub, 'library', f.split('-')[1]));
  }
}
console.log('assets synced into public/');

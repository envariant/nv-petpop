// Unpack the committed proxy library releases (fixtures/library/release-<species>-<n>.tar) into an app's public/
// folder for standalone mode and Storybook; the real kiosk serves releases from its API. Used by both apps'
// scripts/sync-assets.mjs. A minimal ustar reader: regular files only, no absolute or parent paths.
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

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

export function unpackReleases(root, pub) {
  const lib = join(root, 'fixtures/library');
  if (!existsSync(lib)) return;
  for (const f of readdirSync(lib).filter((n) => /^release-(dog|cat)-\d+\.tar$/.test(n))) {
    untar(readFileSync(join(lib, f)), join(pub, 'library', f.split('-')[1]));
  }
}

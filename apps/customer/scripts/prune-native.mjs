// The native bundle (Capacitor, decision 122): the web build minus what only mock or standalone mode uses. On a
// device the library, the result previews and every order come from the API, so the app ships its code, the Draco
// decoder (WebAssembly only: every supported WebView has it) and the attract loop's showcase figurines.
// Usage: node scripts/prune-native.mjs [dir]  (default dist-native); fails if anything needed is missing or the
// bundle is over the budget.
import { existsSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const app = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(app, process.argv[2] ?? 'dist-native');
const BUDGET_MB = 12;
const showcase = JSON.parse(readFileSync(join(app, 'src/showcase.json'), 'utf8')).pets;

const rm = (p) => rmSync(join(out, p), { recursive: true, force: true });
rm('library'); // proxy releases for standalone mode; devices load the release from the API
rm('mockServiceWorker.js');
rm('assets/base'); // morph-preview base meshes: the studio's viewer, not the customer app
rm('assets/tiles');
for (const f of ['draco_decoder.js', 'draco_encoder.js']) rm(`draco/${f}`);
if (existsSync(join(out, 'fixtures'))) {
  for (const d of readdirSync(join(out, 'fixtures'))) {
    if (!showcase.includes(d)) {
      rm(`fixtures/${d}`);
      continue;
    }
    for (const f of readdirSync(join(out, 'fixtures', d))) if (!['figure.glb', 'thumbnail.png'].includes(f)) rm(`fixtures/${d}/${f}`);
  }
}

const need = ['index.html', 'draco/draco_decoder.wasm', 'draco/draco_wasm_wrapper.js', ...showcase.flatMap((p) => [`fixtures/${p}/figure.glb`, `fixtures/${p}/thumbnail.png`])];
const missing = need.filter((p) => !existsSync(join(out, p)));
const files = [];
const walk = (d) => readdirSync(d).forEach((n) => (statSync(join(d, n)).isDirectory() ? walk(join(d, n)) : files.push(join(d, n))));
walk(out);
const bytes = files.reduce((t, f) => t + statSync(f).size, 0);
const mb = bytes / 2 ** 20;
console.log(`native bundle: ${files.length} files, ${mb.toFixed(1)} MB (budget ${BUDGET_MB} MB) in ${relative(app, out)}/`);
if (missing.length) {
  console.error(`missing: ${missing.join(', ')}`);
  process.exit(1);
}
if (mb > BUDGET_MB) {
  console.error('over budget; largest files:');
  files.sort((a, b) => statSync(b).size - statSync(a).size).slice(0, 8).forEach((f) => console.error(`  ${(statSync(f).size / 2 ** 20).toFixed(2)} MB  ${relative(out, f)}`));
  process.exit(1);
}

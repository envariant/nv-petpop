import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

// The MSW layer must cover every path in the committed OpenAPI document.
describe('MSW handlers', () => {
  it('cover every OpenAPI path', async () => {
    const doc = JSON.parse(readFileSync(new URL('../../../../data/schema/openapi.json', import.meta.url), 'utf8'));
    const src = readFileSync(new URL('./handlers.ts', import.meta.url), 'utf8');
    const list = src.match(/HANDLED_PATHS = \[([\s\S]*?)\];/)![1];
    const handled = [...list.matchAll(/'([^']+)'/g)].map((m) => m[1]).sort();
    expect(handled).toEqual(Object.keys(doc.paths).sort());
  });
});

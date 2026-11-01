import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

// The kiosk's MSW layer must cover every kiosk and meta path in the committed OpenAPI document, and no studio path.
describe('MSW handlers', () => {
  it('cover every kiosk and meta OpenAPI path', async () => {
    const doc = JSON.parse(readFileSync(new URL('../../../../data/schema/openapi.json', import.meta.url), 'utf8'));
    const src = readFileSync(new URL('./handlers.ts', import.meta.url), 'utf8');
    const list = src.match(/HANDLED_PATHS = \[([\s\S]*?)\];/)![1];
    const handled = [...list.matchAll(/'([^']+)'/g)].map((m) => m[1]).sort();
    const mine = Object.keys(doc.paths).filter((p) => !p.startsWith('/api/v1/studio/'));
    expect(handled).toEqual(mine.sort());
  });
});

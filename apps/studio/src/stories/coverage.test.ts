import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// CLAUDE.md: every screen has a Storybook story and a Playwright test.
const SCREENS = ['species', 'breed', 'build', 'brief', 'name', 'generating', 'result', 'generate', 'review', 'library', 'releases', 'manual'];
const STORY_NAMES: Record<string, string> = { species: 'Species', breed: 'Breed', build: 'Build', brief: 'Brief', name: 'NameAndGenerate', generating: 'GeneratingViews', result: 'Result', generate: 'Generate', review: 'Review', library: 'Library', releases: 'Releases', manual: 'Manual' };
const read = (p: string) => readFileSync(new URL(p, import.meta.url), 'utf8');

describe('studio screen coverage', () => {
  it('every screen has a story', () => {
    const stories = read('./Screens.stories.tsx');
    for (const s of SCREENS) expect(stories).toMatch(new RegExp(`export const ${STORY_NAMES[s]}: Story = \\{ args: \\{ screen: '${s}'`));
    for (const o of ['Login', 'QueueOverlay', 'OfflineOverlay']) expect(stories).toContain(`export const ${o}`);
  });
  it('every screen has a Playwright test', () => {
    const spec = read('../../tests/e2e/screens.spec.ts');
    for (let i = 0; i <= SCREENS.length; i++) expect(spec).toMatch(new RegExp(`test\\('${i} `));
    for (const t of ['offline:', 'queue panel']) expect(spec).toContain(`test('${t}`);
  });
});

import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// CLAUDE.md: every screen has a Storybook story and a Playwright test.
const SCREENS = ['attract', 'species', 'breed', 'design', 'bespoke'];
const STORY_NAMES: Record<string, string> = { attract: 'Attract', species: 'Species', breed: 'Breed', design: 'Design', bespoke: 'Bespoke' };
const read = (p: string) => readFileSync(new URL(p, import.meta.url), 'utf8');

describe('kiosk screen coverage', () => {
  it('every screen has a story', () => {
    const stories = read('./Screens.stories.tsx');
    for (const s of SCREENS) expect(stories).toMatch(new RegExp(`export const ${STORY_NAMES[s]}: Story = \\{ args: \\{ screen: '${s}'`));
    for (const o of ['StillThereOverlay', 'OfflineOverlay', 'StaffPanelLocked', 'PhoneResultPage']) expect(stories).toContain(`export const ${o}`);
  });
  it('every screen has a Playwright test', () => {
    const spec = read('../../tests/e2e/screens.spec.ts');
    SCREENS.forEach((_, i) => expect(spec).toMatch(new RegExp(`test\\('${i + 1} `)));
    for (const t of ['phone result page', 'idle:', 'offline:', 'staff panel']) expect(spec).toContain(`test('${t}`);
  });
});

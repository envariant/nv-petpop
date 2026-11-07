// Every pattern and marking the breed database uses is offered in the workbench's texture editor.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { MARKINGS, PATTERNS, slug } from './texture';

const db = JSON.parse(readFileSync(new URL('../../../data/breeds/dog_pebbles_simple.json', import.meta.url), 'utf8')) as {
  breeds: { preset: { colour: { pattern?: string; markings?: string[] } } }[];
};

describe('texture vocabulary', () => {
  it('covers the breed database', () => {
    const patterns = new Set(db.breeds.map((b) => b.preset.colour.pattern).filter(Boolean));
    const markings = new Set(db.breeds.flatMap((b) => b.preset.colour.markings ?? []));
    expect([...patterns].filter((p) => !PATTERNS.includes(p!))).toEqual([]);
    expect([...markings].filter((m) => !MARKINGS.includes(m))).toEqual([]);
  });
  it('turns typed names into stored ones', () => {
    expect(slug('  White Tail-Tip! ')).toBe('white_tail_tip');
  });
});

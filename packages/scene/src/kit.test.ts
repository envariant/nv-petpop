// A composition of parts (decision 134): the variants a pose swaps in. Painting is kitPaint.test.ts.
import { describe, expect, it } from 'vitest';
import { effectiveVariants, type Kit, type KitComposition } from './kit';

describe('a composition of parts', () => {
  it('takes the variants a pose swaps in (the sitting hind legs)', () => {
    const kit = { poses: [{ pose_id: 'standing', label: 'S' }, { pose_id: 'sitting', label: 'Sit', variants: { hind_leg: 'sitting_fold' } }] } as unknown as Kit;
    const c = { variants: { head: 'default', torso: 'standard', front_leg: 'paw', hind_leg: 'bean', tail: 'bob' }, pose_id: 'sitting' } as KitComposition;
    expect(effectiveVariants(kit, c).hind_leg).toBe('sitting_fold');
    expect(effectiveVariants(kit, { ...c, pose_id: 'standing' }).hind_leg).toBe('bean');
  });
});

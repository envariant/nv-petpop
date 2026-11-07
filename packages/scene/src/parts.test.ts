// parts.ts against petpop_library.parts (fixtures/parts/golden.json, scripts/make_parts_golden.py): the same placement
// for every slot and pose, mirrored right legs included.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { SLOT_KIND, mirrorOffset, offsetBetween, offsetSocket, placement, type AttachmentData, type JointData, type Slot, type SocketOffset } from './parts';

const golden = JSON.parse(readFileSync(new URL('../../../fixtures/parts/golden.json', import.meta.url), 'utf8'));
type GoldenPart = { kind: string; variant: string; joint?: JointData; attachments?: Record<Slot, AttachmentData> };
const by = (kind: string) => (golden.parts as GoldenPart[]).find((p) => p.kind === kind && p.variant === 'default')!;

describe('part placement', () => {
  it('matches Python for every slot and pose', () => {
    const torso = by('torso');
    type G = { slot: Slot; pose: object; joint_twist: number; stretch: number[] | null; torso_stretch: number[] | null; offset: SocketOffset | null; matrix: number[] };
    expect((golden.placements as G[]).some((g) => g.stretch)).toBe(true); // stretched cases are in the golden data
    expect((golden.placements as G[]).some((g) => g.offset)).toBe(true); // and socket offsets (decision 131)
    for (const g of golden.placements as G[]) {
      const part = { ...by(SLOT_KIND[g.slot]).joint!, twist: g.joint_twist };
      const m = placement(part, torso.attachments![g.slot], g.slot, g.pose, g.stretch, g.torso_stretch, g.offset);
      m.elements.forEach((x, i) => expect(x, `${g.slot} ${JSON.stringify(g.pose)} [${i}]`).toBeCloseTo(g.matrix[i], 4));
    }
  });
  it('inverts and mirrors socket offsets', () => {
    const a: AttachmentData = { position: [3, -2, 5], axis: [0.2, -0.9, 0.3], twist: 40 };
    const off = { translate: [1, 2, -3], rotate: [15, -25, 30] };
    const b = offsetSocket(a, off);
    const back = offsetBetween(a, b);
    back.translate.forEach((x, i) => expect(x).toBeCloseTo(off.translate[i], 6));
    back.rotate.forEach((x, i) => expect(x).toBeCloseTo(off.rotate[i], 4));
    const m = mirrorOffset(off);
    expect(m).toEqual({ translate: [-1, 2, -3], rotate: [15, 25, -30] });
  });
  it('mirrors the right legs (negative determinant: three.js flips their faces)', () => {
    const torso = by('torso');
    const m = placement(by('front_leg').joint!, torso.attachments!.front_right, 'front_right');
    expect(m.determinant()).toBeLessThan(0);
  });
});

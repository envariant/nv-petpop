// The screen paints a figure of parts as the print does (decision 136): paintTile and maskLayers against
// petpop_library.kit_figure's paint_tile and mask_layers on the same masks (values from Python).
import { describe, expect, it } from 'vitest';
import { effectiveVariants, maskLayers, paintTile, type Kit, type KitComposition, type KitTexture } from './kit';

const t: KitTexture = { base: { hex: '#C8763A' }, secondary: { hex: '#F4EFE6' }, tertiary: { hex: '#1E1B1A' }, pattern: 'tricolour', markings: ['white_chest', 'white_socks'] };
const masks = new Map<string, Uint8Array>([
  ['white_chest', Uint8Array.from([0, 64, 128, 255, 0, 64, 128, 255, 0, 64, 128, 255, 0, 64, 128, 255])],
  ['tricolour_c', Uint8Array.from([255, 255, 255, 255, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])],
  ['nose', Uint8Array.from([200, 0, 0, 0, 0, 200, 0, 0, 0, 0, 200, 0, 0, 0, 0, 200])],
]);
// petpop_library.kit_figure.paint_tile(4, t, masks, eye="#3B2412", nose="#101010"), RGB per pixel
const PYTHON = [19, 18, 18, 84, 80, 77, 137, 133, 128, 244, 239, 230, 200, 118, 58, 58, 45, 34, 222, 179, 144, 244, 239, 230, 200, 118, 58, 211, 148, 101,
  60, 51, 44, 244, 239, 230, 200, 118, 58, 211, 148, 101, 222, 179, 144, 65, 64, 62];

describe('painting a part', () => {
  it('layers the masks in the print\'s order and colours', () => {
    expect(maskLayers(t, '#3B2412', '#101010').map(([n, c]) => [n, c])).toEqual([
      ['tricolour', [244, 239, 230]], ['tricolour_c', [30, 27, 26]], ['white_chest', [244, 239, 230]], ['white_chest_c', [30, 27, 26]],
      ['white_socks', [244, 239, 230]], ['white_socks_c', [30, 27, 26]], ['eye', [59, 36, 18]], ['nose', [16, 16, 16]]]);
  });
  it('paints the same pixels as the print', () => {
    const rgba = paintTile(4, t, masks, '#3B2412', '#101010');
    const rgb = [...rgba].filter((_, i) => i % 4 !== 3);
    rgb.forEach((v, i) => expect(Math.abs(v - PYTHON[i]), `channel ${i}`).toBeLessThanOrEqual(1));
    expect([...rgba].filter((_, i) => i % 4 === 3).every((a) => a === 255)).toBe(true);
  });
});

describe('a composition of parts', () => {
  it('takes the variants a pose swaps in (the sitting hind legs)', () => {
    const kit = { poses: [{ pose_id: 'standing', label: 'S' }, { pose_id: 'sitting', label: 'Sit', variants: { hind_leg: 'sitting_fold' } }] } as unknown as Kit;
    const c = { variants: { head: 'default', torso: 'standard', front_leg: 'paw', hind_leg: 'bean', tail: 'bob' }, pose_id: 'sitting' } as KitComposition;
    expect(effectiveVariants(kit, c).hind_leg).toBe('sitting_fold');
    expect(effectiveVariants(kit, { ...c, pose_id: 'standing' }).hind_leg).toBe('bean');
  });
});

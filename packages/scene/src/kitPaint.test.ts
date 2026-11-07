// The screen paints a figure of parts as the print does, byte for byte (decisions 136, 139): paintKitTile against
// petpop_library.kit_figure.paint_tile on the same masks, part and stamps (values from Python, below).
import * as THREE from 'three';
import { describe, expect, it } from 'vitest';
import type { BaseData } from './atlas';
import { kitLandmarks, mirrorStamp, paintKitTile, partBase, sampleMask, type MaskImage } from './kitPaint';
import { maskLayers, type KitTexture } from './kit';

const t: KitTexture = { base: { hex: '#C8763A' }, secondary: { hex: '#F4EFE6' }, tertiary: { hex: '#1E1B1A' }, pattern: 'tricolour', markings: ['white_chest'] };
const img = (w: number, h: number, data: number[]): MaskImage => ({ w, h, data: Uint8Array.from(data) });
const masks = new Map<string, MaskImage>([
  ['white_chest', img(5, 3, [205, 206, 131, 72, 13, 97, 104, 11, 12, 254, 166, 59, 110, 248, 228])],
  ['tricolour_c', img(4, 4, [255, 255, 255, 255, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])],
  ['nose', img(2, 2, [0, 0, 0, 200])],
]);
// a pyramid of four triangles over the UV square (trimesh's v), its apex at the centre, in mm
const part: BaseData = {
  n: 5, t: 4, co: Float32Array.from([0, 0, 0, 10, 0, 0, 10, 10, 0, 0, 10, 0, 5, 5, 4]),
  tri: Uint32Array.from([0, 1, 4, 1, 2, 4, 2, 3, 4, 3, 0, 4]),
  uv: Float32Array.from([[0.05, 0.05], [0.95, 0.05], [0.5, 0.5], [0.95, 0.05], [0.95, 0.95], [0.5, 0.5], [0.95, 0.95], [0.05, 0.95], [0.5, 0.5],
    [0.05, 0.95], [0.05, 0.05], [0.5, 0.5]].flat()),
  shell: new Uint8Array(5),
};
const stamps = [{ p: [5, 5, 4] as [number, number, number], r: 2.5, colour: '#102030' }, { p: [9, 1, 0] as [number, number, number], r: 3, colour: '#FF0000' }];
// kit_figure.paint_tile(8, t, masks, "#3B2412", "#101010", (v, faces, uv), stamps), RGB per texel
const PYTHON = [202, 197, 190, 202, 198, 190, 199, 194, 187, 160, 155, 150, 124, 121, 116, 94, 90, 87, 63, 59, 57, 41, 38, 36, 206, 197, 186, 206, 197, 187, 204, 194, 184, 172, 159, 147, 144, 129, 116, 121, 103, 89, 103, 84, 69, 91, 71, 56, 211, 184, 161, 212, 185, 162, 208, 181, 158, 186, 149, 120, 171, 127, 93, 160, 113, 78, 170, 132, 102, 180, 148, 122, 220, 174, 137, 221, 175, 139, 213, 168, 133, 16, 32, 48, 16, 32, 48, 156, 100, 59, 161, 131, 106, 171, 158, 145, 219, 170, 132, 218, 167, 128, 204, 152, 113, 16, 32, 48, 16, 32, 48, 126, 89, 61, 124, 108, 94, 132, 128, 123, 223, 182, 150, 219, 171, 133, 197, 143, 102, 162, 117, 82, 130, 99, 75, 99, 83, 70, 255, 0, 0, 255, 0, 0, 228, 195, 167, 220, 174, 138, 192, 136, 93, 157, 118, 89, 122, 103, 87, 255, 0, 0, 255, 0, 0, 255, 0, 0, 229, 197, 170, 221, 175, 138, 192, 135, 92, 157, 120, 90, 123, 105, 90, 255, 0, 0, 255, 0, 0, 255, 0, 0];
const rgbOf = (rgba: Uint8Array) => [...rgba].filter((_, i) => i % 4 !== 3);

describe('painting a part', () => {
  it('layers the masks in the print\'s order and colours', () => {
    expect(maskLayers(t, '#3B2412', '#101010').map(([n, c]) => [n, c])).toEqual([
      ['tricolour', [244, 239, 230]], ['tricolour_c', [30, 27, 26]], ['white_chest', [244, 239, 230]], ['white_chest_c', [30, 27, 26]],
      ['eye', [59, 36, 18]], ['nose', [16, 16, 16]]]);
  });
  it('samples a mask at texel centres', () => {
    const m = img(4, 4, Array.from({ length: 16 }, (_, i) => i * 16));
    expect([...sampleMask(m, 4)].map((x) => Math.round(x * 255))).toEqual([...m.data]);
    expect(sampleMask(m, 2)[0]).toBeCloseTo((0 + 16 + 64 + 80) / 4 / 255, 12);
  });
  it('paints the same bytes as the print, stamps and all', () => {
    const rgba = paintKitTile(8, t, masks, '#3B2412', '#101010', part, stamps);
    expect(rgbOf(rgba)).toEqual(PYTHON);
    expect([...rgba].filter((_, i) => i % 4 === 3).every((a) => a === 255)).toBe(true);
    const plain = rgbOf(paintKitTile(8, t, masks, '#3B2412', '#101010'));
    expect(plain.filter((v, i) => v !== PYTHON[i]).length).toBeGreaterThan(0); // the stamps changed it
  });
});

describe('a part as the rasteriser reads it', () => {
  it('flips glTF\'s v as the export does and joins every mesh', () => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(Float32Array.from([0, 0, 0, 1, 0, 0, 0, 1, 0]), 3));
    g.setAttribute('uv', new THREE.BufferAttribute(Float32Array.from([0, 0, 1, 0.25, 0, 1.5]), 2));
    const b = partBase([g, g]);
    expect(b.n).toBe(6);
    expect(b.t).toBe(2);
    expect([...b.tri]).toEqual([0, 1, 2, 3, 4, 5]);
    expect([...b.uv.slice(0, 6)]).toEqual([0, 1, 1, 0.75, 0, 0]);
  });
});

describe('the mirror rule and landmarks', () => {
  it('puts a leg\'s mirror on the other leg and a centre part\'s at -x', () => {
    expect(mirrorStamp({ slot: 'front_left', p: [1, 2, 3], r: 2, colour: '#000000' })).toEqual({ slot: 'front_right', p: [1, 2, 3], r: 2, colour: '#000000' });
    expect(mirrorStamp({ slot: 'head', p: [1, 2, 3], r: 2, colour: '#000000' }).p).toEqual([-1, 2, 3]);
  });
  it('finds the nose at the head\'s front and the eyes either side', () => {
    // torso vertex 0, head vertices 1..4: left, right, front (nose), top
    const co = Float64Array.from([0, 0, 0, 3, 10, 5, -3, 10, 5, 0, 8, 9, 0, 14, 2]);
    const lm = kitLandmarks(co, Uint8Array.from([0, 1, 1, 1, 1]));
    expect(lm.nose_tip).toBe(3);
    expect(lm.eye_L).toBe(1);
    expect(lm.eye_R).toBe(2);
    expect(lm.ear_tip_L).toBe(1);
  });
});

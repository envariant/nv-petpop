import { EYE_PALETTE, PALETTE, PALETTE_ORDER } from '@petpop/core';
export const FUR = PALETTE_ORDER.map((n) => ({ name: n, hex: PALETTE[n].hex }));
export const EYES = Object.entries(EYE_PALETTE).map(([n, e]) => ({ name: n, hex: e.hex }));
export const NOSES = [
  { name: 'black', hex: '#1E1B1A' },
  { name: 'liver', hex: '#6B3A2A' },
  { name: 'pink', hex: '#D9908C' },
  { name: 'grey', hex: '#6E6A68' },
];
export const SHELL_COLOURS = ['#C8102E', '#1F4E9C', '#2E8B57', '#F2B705', '#7B3FA0', '#F4EFE6', '#1E1B1A'].map((hex, i) => ({ name: `c${i}`, hex }));

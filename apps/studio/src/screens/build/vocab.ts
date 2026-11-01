import { getPath } from '@petpop/core';
import { useSession } from '../../stores/session';

export type Species = 'dog' | 'cat';
export const ACC = ['collar', 'bandana', 'bow', 'hat', 'glasses'] as const;
export const ACC_COLOURS = ['#DD3333', '#3366CC', '#2E9E5B', '#F2C230', '#E04A8A', '#1E1B1A'];
export const ACC_ICON: Record<string, string> = { collar: '📿', bandana: '🧣', bow: '🎀', hat: '🎩', glasses: '👓' };
export const MARK_LABEL: Record<string, string> = { white_blaze: 'Blaze', white_socks: 'Socks', white_chest: 'Chest', dark_mask: 'Mask', points: 'Points' };
export const TILE_LABEL: Record<string, string> = { semi_erect: 'semi-erect', long_thin: 'long thin', saddle_with_white_chest: 'saddle' };

/** Whether the brief parser just changed this field (the ring on its swatch). */
export function useHighlight() {
  const s = useSession();
  return (path: string) => s.highlights.some((h) => h === path || h.startsWith(`${path}.`));
}

/** The spec's value at a path, for the current figure. */
export function useValue() {
  const s = useSession();
  return (path: string) => (s.spec ? getPath(s.spec, path) : undefined);
}

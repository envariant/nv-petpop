// Kiosk session state (Zustand). One session = one visitor; reset() wipes everything (idle or Start over).
// The kiosk never depends on the GenAI host (BRIEF Section 17): it only talks to the /kiosk routes. The design
// itself (library, composition, paint tools, order) lives in store/design.ts.
import { create } from 'zustand';
import { ApiFailure, KioskApi, randomSeed, specFromBreed } from '@petpop/core';
import type { BespokeAccepted, Breed, CompositionBody, PetSpec, Species } from '@petpop/core';
import { useDesign } from './design';

export type Screen = 'attract' | 'species' | 'breed' | 'design' | 'name' | 'order' | 'bespoke';
export const FLOW: Screen[] = ['attract', 'species', 'breed', 'design', 'name', 'order'];

export interface SessionState {
  screen: Screen;
  sessionId: string | null;
  idleSeconds: number;
  countdownSeconds: number;
  bespokeEnabled: boolean;
  species: Species | null;
  breed: Breed | null;
  spec: PetSpec | null;
  bespoke: BespokeAccepted | null;
  error: string | null;
  // actions
  go: (s: Screen) => void;
  start: () => Promise<void>;
  chooseSpecies: (s: Species) => void;
  chooseBreed: (b: Breed) => void;
  requestBespoke: (contact: string) => Promise<void>;
  reset: () => void;
  hydrate: (p: Partial<SessionState>) => void;
}

const initial = {
  screen: 'attract' as Screen,
  sessionId: null,
  idleSeconds: 90,
  countdownSeconds: 15,
  bespokeEnabled: false,
  species: null,
  breed: null,
  spec: null,
  bespoke: null,
  error: null,
};

export const useSession = create<SessionState>((set, get) => ({
  ...initial,
  go: (screen) => set({ screen, error: null }),
  start: async () => {
    set({ ...initial, screen: 'species' });
    try {
      const s = await KioskApi.createSession();
      set({ sessionId: s.session_id, idleSeconds: s.idle_policy.idle_seconds, countdownSeconds: s.idle_policy.countdown_seconds, bespokeEnabled: s.bespoke_enabled });
    } catch {
      /* offline overlay retries */
    }
  },
  chooseSpecies: (species) => set({ species, breed: null, spec: null, screen: 'breed' }),
  chooseBreed: (breed) => {
    const { species } = get();
    set({ breed, spec: specFromBreed(species!, breed, randomSeed()), screen: 'design' });
  },
  requestBespoke: async (contact) => {
    const { sessionId } = get();
    const composition = useDesign.getState().composition;
    if (!sessionId || !composition) return;
    set({ error: null });
    try {
      // The design goes to the studio as the bespoke job's starting point (BRIEF Section 17).
      const created = await KioskApi.createComposition(sessionId, composition as CompositionBody);
      set({ bespoke: await KioskApi.bespoke(created.composition_id, contact.trim() || undefined) });
    } catch (e) {
      set({ error: e instanceof ApiFailure && e.status === 409 ? String(e.detail) : 'Something went wrong. Please ask a member of staff.' });
    }
  },
  reset: () => {
    useDesign.getState().reset();
    set({ ...initial });
  },
  hydrate: (p) => set(p),
}));

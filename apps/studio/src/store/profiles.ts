// Per-job GenAI profiles (decision 113): what this server lets Studio run a job on, and the operator's choice,
// shared by the batch builder and the one-off figurine flow. The kiosk never chooses: its jobs use the default.
import { create } from 'zustand';
import { StudioApi } from '@petpop/core';
import type { GenaiProfiles } from '@petpop/core';

export interface ProfilesState {
  offered: GenaiProfiles | null;
  choice: string | null;
  set: (p: Partial<ProfilesState>) => void;
  load: () => Promise<void>;
  choose: (name: string) => void;
}

export const useProfiles = create<ProfilesState>((set, get) => ({
  offered: null,
  choice: null,
  set: (p) => set(p),
  load: async () => {
    try {
      const offered = await StudioApi.profiles();
      const keep = offered.items.some((p) => p.name === get().choice && p.ready);
      set({ offered, choice: keep ? get().choice : offered.default });
    } catch {
      /* the offline overlay handles a dropped API; jobs then use the server default */
    }
  },
  choose: (name) => set({ choice: name }),
}));

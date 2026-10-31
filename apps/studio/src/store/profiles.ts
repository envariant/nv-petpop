// Per-job GenAI choices (decisions 113 to 115): the profile ("Run on"), its pipeline (single view or multiview) and
// its quality switches, shared by the batch builder and the one-off figurine flow. The kiosk never chooses: its jobs
// use the server default. The credit estimate is the provider's API price per figurine, where it prices by credit.
import { create } from 'zustand';
import { StudioApi } from '@petpop/core';
import type { GenaiProfileInfo, GenaiProfiles } from '@petpop/core';

export interface ProfilesState {
  offered: GenaiProfiles | null;
  choice: string | null;
  pipeline: string | null;
  options: Record<string, boolean>;
  set: (p: Partial<ProfilesState>) => void;
  load: () => Promise<void>;
  choose: (name: string) => void;
  choosePipeline: (name: string) => void;
  toggle: (option: string) => void;
}

export function current(s: Pick<ProfilesState, 'offered' | 'choice'>): GenaiProfileInfo | null {
  return s.offered?.items.find((p) => p.name === s.choice) ?? null;
}

/** API credits per figurine for the current choices, or null when the profile does not price by credit. */
export function estimate(s: Pick<ProfilesState, 'offered' | 'choice' | 'pipeline' | 'options'>): number | null {
  const p = current(s);
  const pipe = p?.pipelines.find((x) => x.name === s.pipeline);
  if (!p || pipe?.credits == null) return null;
  return pipe.credits + p.options.reduce((sum, o) => sum + (s.options[o.name] ? (o.credits ?? 0) : 0), 0);
}

function defaults(p: GenaiProfileInfo | null): Pick<ProfilesState, 'pipeline' | 'options'> {
  return {
    pipeline: p?.pipelines.find((x) => x.default)?.name ?? null,
    options: Object.fromEntries((p?.options ?? []).map((o) => [o.name, o.default])),
  };
}

export const useProfiles = create<ProfilesState>((set, get) => ({
  offered: null,
  choice: null,
  pipeline: null,
  options: {},
  set: (p) => set(p),
  load: async () => {
    try {
      const offered = await StudioApi.profiles();
      const keep = offered.items.some((p) => p.name === get().choice && p.ready);
      const choice = keep ? get().choice : offered.default;
      set({ offered, choice, ...(keep ? {} : defaults(offered.items.find((p) => p.name === choice) ?? null)) });
    } catch {
      /* the offline overlay handles a dropped API; jobs then use the server default */
    }
  },
  choose: (name) => set((s) => ({ choice: name, ...defaults(s.offered?.items.find((p) => p.name === name) ?? null) })),
  choosePipeline: (name) => set({ pipeline: name }),
  toggle: (option) => set((s) => ({ options: { ...s.options, [option]: !s.options[option] } })),
}));

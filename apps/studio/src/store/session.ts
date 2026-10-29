// Studio state (Zustand): the signed-in staff user and the Generate workspace's current figurine.
import { create } from 'zustand';
import { ApiFailure, StudioApi, applyPatch, clone, randomSeed, setPath, setStaffToken, specFromBreed } from '@petpop/core';
import type { Breed, Job, ParseResponse, PetSpec, ProgressEvent, Species, StaffUser } from '@petpop/core';

export type Screen = 'species' | 'breed' | 'build' | 'brief' | 'name' | 'generating' | 'result';
export const FLOW: Screen[] = ['species', 'breed', 'build', 'brief', 'name', 'generating', 'result'];
const TOKEN_KEY = 'pp-studio-token';

export interface Previews { [kind: string]: string }

export interface SessionState {
  user: StaffUser | null;
  loginError: string | null;
  screen: Screen;
  species: Species | null;
  breed: Breed | null;
  spec: PetSpec | null;
  tapped: string[];
  briefText: string;
  parse: ParseResponse | null;
  highlights: string[];
  jobId: string | null;
  job: Job | null;
  events: ProgressEvent[];
  previews: Previews;
  ticket: string | null;
  tweakOf: string | null;
  error: string | null;
  // actions
  login: (username: string, password: string) => Promise<void>;
  restore: () => Promise<void>;
  logout: () => void;
  go: (s: Screen) => void;
  chooseSpecies: (s: Species) => void;
  chooseBreed: (b: Breed) => void;
  tap: (path: string, value: unknown) => void;
  setBrief: (t: string) => void;
  applyParse: (r: ParseResponse) => void;
  setName: (n: string) => void;
  generate: () => Promise<void>;
  onEvent: (e: ProgressEvent) => void;
  onJob: (j: Job) => void;
  fulfil: () => Promise<void>;
  tweak: () => void;
  newFigure: () => void;
  reset: () => void;
  hydrate: (p: Partial<SessionState>) => void;
}

const figure = {
  screen: 'species' as Screen,
  species: null,
  breed: null,
  spec: null,
  tapped: [],
  briefText: '',
  parse: null,
  highlights: [],
  jobId: null,
  job: null,
  events: [],
  previews: {},
  ticket: null,
  tweakOf: null,
  error: null,
};

function store(token: string | null): void {
  setStaffToken(token);
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage may be blocked; the login lasts until reload */
  }
}

export const useSession = create<SessionState>((set, get) => ({
  user: null,
  loginError: null,
  ...figure,
  login: async (username, password) => {
    try {
      const t = await StudioApi.login(username, password);
      store(t.token);
      set({ user: t.user, loginError: null, ...figure });
    } catch (e) {
      set({ loginError: e instanceof ApiFailure && e.status === 401 ? 'Wrong username or password.' : 'Could not reach the studio.' });
    }
  },
  restore: async () => {
    let token: string | null = null;
    try {
      token = sessionStorage.getItem(TOKEN_KEY);
    } catch {
      token = null;
    }
    if (!token) return;
    setStaffToken(token);
    try {
      set({ user: await StudioApi.me() });
    } catch {
      store(null);
    }
  },
  logout: () => {
    store(null);
    set({ user: null, ...figure });
  },
  go: (screen) => set({ screen, error: null }),
  chooseSpecies: (species) => set({ species, breed: null, spec: null, tapped: [], screen: 'breed' }),
  chooseBreed: (breed) => {
    const { species, spec } = get();
    const seed = spec?.seed ?? randomSeed();
    const name = (spec as { pet_name?: string } | null)?.pet_name;
    set({ breed, spec: specFromBreed(species!, breed, seed, name), tapped: [], highlights: [], parse: null, screen: 'build' });
  },
  tap: (path, value) => {
    const { spec, tapped } = get();
    if (!spec) return;
    const next = clone(spec) as unknown as Record<string, unknown>;
    setPath(next, path, value);
    set({ spec: next as unknown as PetSpec, tapped: tapped.includes(path) ? tapped : [...tapped, path], highlights: [] });
  },
  setBrief: (briefText) => set({ briefText }),
  applyParse: (r) => {
    const { spec, tapped, briefText } = get();
    if (!spec) return;
    const { spec: next, changed } = applyPatch(spec, r.patch, tapped);
    (next as unknown as Record<string, unknown>).free_text = briefText.slice(0, 500);
    set({ spec: next, parse: r, highlights: changed });
  },
  setName: (n) => {
    const { spec } = get();
    if (!spec) return;
    set({ spec: { ...spec, pet_name: n.slice(0, 24) } as PetSpec });
  },
  generate: async () => {
    const { spec, tweakOf } = get();
    if (!spec) return;
    set({ error: null });
    try {
      const created = tweakOf ? await StudioApi.tweak(tweakOf, tweakPatch(spec)) : await StudioApi.createJob(spec);
      set({ jobId: created.job_id, job: null, events: [], previews: {}, ticket: null, screen: 'generating', tweakOf: null });
    } catch (e) {
      const msg = e instanceof ApiFailure && (e.status === 409 || e.status === 422) ? String(e.detail) : 'Something went wrong. Please try again.';
      set({ error: msg });
    }
  },
  onEvent: (e) => {
    const { events, previews } = get();
    const next = { ...previews };
    if (e.preview_url && e.preview_kind) next[e.preview_kind] = e.preview_url;
    set({ events: [...events, e], previews: next });
  },
  onJob: (j) => set({ job: j, previews: { ...get().previews, ...j.previews }, ticket: j.status === 'fulfilled' ? j.ticket ?? get().ticket : get().ticket }),
  fulfil: async () => {
    const { jobId } = get();
    if (!jobId) return;
    const r = await StudioApi.fulfil(jobId);
    set({ ticket: r.ticket });
  },
  tweak: () => {
    const { jobId, job } = get();
    set({ tweakOf: jobId, spec: job?.spec ?? get().spec, screen: 'build', highlights: [] });
  },
  newFigure: () => set({ ...figure }),
  reset: () => set({ ...figure }),
  hydrate: (p) => set(p),
}));

/** Tweak sends the user-editable part of the spec; the server keeps the seed. */
export function tweakPatch(spec: PetSpec): Record<string, unknown> {
  const { seed: _seed, spec_version: _v, species: _s, ...rest } = spec as unknown as Record<string, unknown>;
  void _seed; void _v; void _s;
  return rest;
}

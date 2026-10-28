// Kiosk session state (Zustand). One session = one visitor; reset() wipes everything (idle or Start over).
import { create } from 'zustand';
import { Api, ApiFailure } from '../api/client';
import type { Breed, Job, ParseResponse, PetSpec, ProgressEvent, Species } from '../api/types';
import { applyPatch, clone, randomSeed, setPath, specFromBreed } from '../lib/spec';

export type Screen = 'attract' | 'species' | 'breed' | 'build' | 'brief' | 'name' | 'generating' | 'result';
export const FLOW: Screen[] = ['attract', 'species', 'breed', 'build', 'brief', 'name', 'generating', 'result'];

export interface Previews { [kind: string]: string }

export interface SessionState {
  screen: Screen;
  sessionId: string | null;
  idleSeconds: number;
  countdownSeconds: number;
  generationsLeft: number;
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
  go: (s: Screen) => void;
  start: () => Promise<void>;
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
  reset: () => void;
  hydrate: (p: Partial<SessionState>) => void;
}

const initial = {
  screen: 'attract' as Screen,
  sessionId: null,
  idleSeconds: 90,
  countdownSeconds: 15,
  generationsLeft: 3,
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

export const useSession = create<SessionState>((set, get) => ({
  ...initial,
  go: (screen) => set({ screen, error: null }),
  start: async () => {
    set({ ...initial, screen: 'species' });
    try {
      const s = await Api.createSession();
      set({ sessionId: s.session_id, idleSeconds: s.idle_policy.idle_seconds, countdownSeconds: s.idle_policy.countdown_seconds, generationsLeft: s.generations_left });
    } catch {
      /* offline overlay retries; session is created lazily on Generate */
    }
  },
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
    let { sessionId } = get();
    const { spec, tweakOf } = get();
    if (!spec) return;
    set({ error: null });
    try {
      if (!sessionId) {
        const s = await Api.createSession();
        sessionId = s.session_id;
        set({ sessionId, generationsLeft: s.generations_left });
      }
      const created = tweakOf ? await Api.tweak(tweakOf, sessionId, tweakPatch(spec)) : await Api.createJob(sessionId, spec);
      set({ jobId: created.job_id, job: null, events: [], previews: {}, ticket: null, generationsLeft: created.generations_left, screen: 'generating', tweakOf: null });
    } catch (e) {
      const msg = e instanceof ApiFailure && e.status === 409 ? String(e.detail) : 'Something went wrong. Please try again.';
      set({ error: msg });
    }
  },
  onEvent: (e) => {
    const { events, previews } = get();
    const next = { ...previews };
    if (e.preview_url && e.preview_kind) next[e.preview_kind] = e.preview_url;
    set({ events: [...events, e], previews: next });
  },
  onJob: (j) => set({ job: j, previews: { ...get().previews, ...j.previews }, ticket: j.ticket ?? get().ticket }),
  fulfil: async () => {
    const { jobId } = get();
    if (!jobId) return;
    const r = await Api.fulfil(jobId);
    set({ ticket: r.ticket });
  },
  tweak: () => {
    const { jobId, job } = get();
    set({ tweakOf: jobId, spec: job?.spec ?? get().spec, screen: 'build', highlights: [] });
  },
  reset: () => set({ ...initial }),
  hydrate: (p) => set(p),
}));

/** Tweak sends the user-editable part of the spec; the server keeps the seed. */
export function tweakPatch(spec: PetSpec): Record<string, unknown> {
  const { seed: _seed, spec_version: _v, species: _s, ...rest } = spec as unknown as Record<string, unknown>;
  void _seed; void _v; void _s;
  return rest;
}

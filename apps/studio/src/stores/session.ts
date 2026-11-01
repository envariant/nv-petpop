// Studio state (Pinia): the signed-in staff user and the one-off figurine flow (species to result).
import { defineStore } from 'pinia';
import { ref } from 'vue';
import { useProfiles } from './profiles';
import { ApiFailure, StudioApi, applyPatch, clone, randomSeed, setPath, setStaffToken, specFromBreed } from '@petpop/core';
import type { Breed, Job, ParseResponse, PetSpec, ProgressEvent, Species, StaffUser } from '@petpop/core';

// The Generate workspace (batch builder), Review, Library and Releases (M8), Manual, and the one-off figurine flow.
export type Screen = 'generate' | 'review' | 'library' | 'releases' | 'manual' | 'species' | 'breed' | 'build' | 'brief' | 'name' | 'generating' | 'result';
const TOKEN_KEY = 'pp-studio-token';

export type Previews = Record<string, string>;

function remember(token: string | null): void {
  setStaffToken(token);
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage may be blocked; the login lasts until reload */
  }
}

/** Tweak sends the user-editable part of the spec; the server keeps the seed. */
export function tweakPatch(spec: PetSpec): Record<string, unknown> {
  const { seed: _seed, spec_version: _v, species: _s, ...rest } = spec as unknown as Record<string, unknown>;
  void _seed; void _v; void _s;
  return rest;
}

export const useSession = defineStore('session', () => {
  const user = ref<StaffUser | null>(null);
  const loginError = ref<string | null>(null);
  const screen = ref<Screen>('species');
  const species = ref<Species | null>(null);
  const breed = ref<Breed | null>(null);
  const spec = ref<PetSpec | null>(null);
  const tapped = ref<string[]>([]);
  const briefText = ref('');
  const parse = ref<ParseResponse | null>(null);
  const highlights = ref<string[]>([]);
  const jobId = ref<string | null>(null);
  const job = ref<Job | null>(null);
  const events = ref<ProgressEvent[]>([]);
  const previews = ref<Previews>({});
  const ticket = ref<string | null>(null);
  const tweakOf = ref<string | null>(null);
  const error = ref<string | null>(null);

  /** Back to an empty figure, on the given screen. */
  function clearFigure(to: Screen = 'species') {
    screen.value = to;
    species.value = null;
    breed.value = null;
    spec.value = null;
    tapped.value = [];
    briefText.value = '';
    parse.value = null;
    highlights.value = [];
    jobId.value = null;
    job.value = null;
    events.value = [];
    previews.value = {};
    ticket.value = null;
    tweakOf.value = null;
    error.value = null;
  }

  async function login(username: string, password: string) {
    try {
      const t = await StudioApi.login(username, password);
      remember(t.token);
      clearFigure('generate');
      user.value = t.user;
      loginError.value = null;
    } catch (e) {
      loginError.value = e instanceof ApiFailure && e.status === 401 ? 'Wrong username or password.' : 'Could not reach the studio.';
    }
  }
  async function restore() {
    let token: string | null = null;
    try {
      token = sessionStorage.getItem(TOKEN_KEY);
    } catch {
      token = null;
    }
    if (!token) return;
    setStaffToken(token);
    try {
      user.value = await StudioApi.me();
      screen.value = 'generate';
    } catch {
      remember(null);
    }
  }
  function logout() {
    remember(null);
    user.value = null;
    clearFigure();
  }
  function go(s: Screen) {
    screen.value = s;
    error.value = null;
  }
  function chooseSpecies(s: Species) {
    species.value = s;
    breed.value = null;
    spec.value = null;
    tapped.value = [];
    screen.value = 'breed';
  }
  function chooseBreed(b: Breed) {
    const seed = spec.value?.seed ?? randomSeed();
    const name = (spec.value as { pet_name?: string } | null)?.pet_name;
    breed.value = b;
    spec.value = specFromBreed(species.value!, b, seed, name);
    tapped.value = [];
    highlights.value = [];
    parse.value = null;
    screen.value = 'build';
  }
  function tap(path: string, value: unknown) {
    if (!spec.value) return;
    const next = clone(spec.value) as unknown as Record<string, unknown>;
    setPath(next, path, value);
    spec.value = next as unknown as PetSpec;
    if (!tapped.value.includes(path)) tapped.value = [...tapped.value, path];
    highlights.value = [];
  }
  function setBrief(t: string) {
    briefText.value = t;
  }
  function applyParse(r: ParseResponse) {
    if (!spec.value) return;
    const { spec: next, changed } = applyPatch(clone(spec.value), r.patch, tapped.value);
    (next as unknown as Record<string, unknown>).free_text = briefText.value.slice(0, 500);
    spec.value = next;
    parse.value = r;
    highlights.value = changed;
  }
  function setName(n: string) {
    if (spec.value) spec.value = { ...spec.value, pet_name: n.slice(0, 24) } as PetSpec;
  }
  async function generate() {
    if (!spec.value) return;
    error.value = null;
    const p = useProfiles();
    try {
      const plain = clone(spec.value);
      const created = tweakOf.value ? await StudioApi.tweak(tweakOf.value, tweakPatch(plain)) : await StudioApi.createJob(plain, p.choice, p.pipeline, p.options);
      jobId.value = created.job_id;
      job.value = null;
      events.value = [];
      previews.value = {};
      ticket.value = null;
      tweakOf.value = null;
      screen.value = 'generating';
    } catch (e) {
      error.value = e instanceof ApiFailure && (e.status === 409 || e.status === 422) ? String(e.detail) : 'Something went wrong. Please try again.';
    }
  }
  function onEvent(e: ProgressEvent) {
    events.value = [...events.value, e];
    if (e.preview_url && e.preview_kind) previews.value = { ...previews.value, [e.preview_kind]: e.preview_url };
  }
  function onJob(j: Job) {
    job.value = j;
    previews.value = { ...previews.value, ...j.previews };
    if (j.status === 'fulfilled') ticket.value = j.ticket ?? ticket.value;
  }
  async function fulfil() {
    if (!jobId.value) return;
    ticket.value = (await StudioApi.fulfil(jobId.value)).ticket;
  }
  function tweak() {
    tweakOf.value = jobId.value;
    spec.value = job.value?.spec ?? spec.value;
    screen.value = 'build';
    highlights.value = [];
  }
  return {
    user, loginError, screen, species, breed, spec, tapped, briefText, parse, highlights, jobId, job, events, previews, ticket, tweakOf, error,
    clearFigure, login, restore, logout, go, chooseSpecies, chooseBreed, tap, setBrief, applyParse, setName, generate, onEvent, onJob, fulfil, tweak,
  };
});

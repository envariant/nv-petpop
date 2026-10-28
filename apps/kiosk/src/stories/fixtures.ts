// Story and test data built from the fixture pack (fixtures/pets/biscuit).
import biscuit from '@fixtures/pets/biscuit/spec.json';
import manifest from '@fixtures/pets/biscuit/manifest.json';
import type { Artefact, Breed, Job, PetSpec } from '../api/types';
import dogs from '@data/breeds/dog.json';

export const SPEC = biscuit as unknown as PetSpec;
export const CORGI = (dogs.breeds as unknown as Breed[]).find((b) => b.id === 'corgi_pembroke')!;
const f = (name: string) => `/fixtures/biscuit/${name}`;
const artefacts = (manifest.files as { name: string; kind: Artefact['kind']; stage: string; bytes: number }[]).map((x) => ({ ...x, url: f(x.name) }));

export function job(status: Job['status'], extra: Partial<Job> = {}): Job {
  const done = status === 'done' || status === 'fulfilled';
  return {
    job_id: 'j_story', session_id: 's_story', status, stage: done ? 'done' : status === 'queued' ? 'queued' : 'C', pct: done ? 100 : 45, message: done ? 'Your figurine is ready' : 'Four views ready',
    queue_position: status === 'queued' ? 2 : 0, seed: SPEC.seed, species: 'dog', pet_name: 'Biscuit', created_at: new Date().toISOString(), finished_at: null,
    error: status === 'failed' ? 'Stage D (shape) timed out after 150 s' : null, fallback: 'none', fidelity: 'low', timings: [], artefacts: done ? artefacts : [],
    previews: done ? { concept: f('concept.png'), glb: f('figure.glb'), thumbnail: f('thumbnail.png') } : {}, result_url: done ? 'http://localhost/r/demo' : null, ticket: null, spec: SPEC,
    ...extra,
  };
}

export const VIEW_PREVIEWS = { concept: f('concept.png'), view_front: f('views/front.png'), view_left: f('views/left.png'), view_back: f('views/back.png'), view_right: f('views/right.png') };

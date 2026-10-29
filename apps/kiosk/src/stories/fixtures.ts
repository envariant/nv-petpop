// Story and test data built from the fixture pack (fixtures/pets/biscuit).
import biscuit from '@fixtures/pets/biscuit/spec.json';
import type { Breed, CompositionStatus, PetSpec } from '@petpop/core';
import dogs from '@data/breeds/dog.json';

export const SPEC = biscuit as unknown as PetSpec;
export const CORGI = (dogs.breeds as unknown as Breed[]).find((b) => b.id === 'corgi_pembroke')!;

/** A finished library order (the Order screen once Stage F is done), with the fixture pack's figurine. */
export const ORDER_READY = {
  composition_id: 'c_story', session_id: 's_story', status: 'ready', pet_name: 'Biscuit', species: 'dog', release_version: 'release-dog-1',
  created_at: '2026-10-29T10:00:00Z', ticket: 'PP-4821', result_url: 'http://kiosk.local/r/c_story.0.mock',
  export: { job_id: 'j_story', status: 'done', stage: 'done', pct: 100, message: 'Your figurine is ready' },
  artefacts: [], previews: { glb: '/fixtures/biscuit/figure.glb', thumbnail: '/fixtures/biscuit/thumbnail.png' }, error: null, composition: {},
} as unknown as CompositionStatus;

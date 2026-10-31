// Story and test data built from the fixture pack (fixtures/pets/biscuit).
import biscuit from '@fixtures/pets/biscuit/spec.json';
import manifest from '@fixtures/pets/biscuit/manifest.json';
import { assetUrl, type Artefact, type Batch, type Breed, type Job, type LibraryCandidate, type LibraryItem, type PetSpec, type ReleaseInfo } from '@petpop/core';
import dogs from '@data/breeds/dog.json';

export const SPEC = biscuit as unknown as PetSpec;
export const CORGI = (dogs.breeds as unknown as Breed[]).find((b) => b.id === 'corgi_pembroke')!;
const f = (name: string) => assetUrl(`fixtures/biscuit/${name}`);
const artefacts = (manifest.files as { name: string; kind: Artefact['kind']; stage: string; bytes: number }[]).map((x) => ({ ...x, url: f(x.name) }));

export function job(status: Job['status'], extra: Partial<Job> = {}): Job {
  const done = status === 'done' || status === 'fulfilled';
  return {
    job_id: 'j_story', kind: 'pipeline', session_id: null, requested_by: 'operator', status, stage: done ? 'done' : status === 'queued' ? 'queued' : 'C', pct: done ? 100 : 45, message: done ? 'Your figurine is ready' : 'Four views ready',
    queue_position: status === 'queued' ? 2 : 0, seed: SPEC.seed, species: 'dog', pet_name: 'Biscuit', created_at: new Date().toISOString(), finished_at: null,
    error: status === 'failed' ? 'Stage D (shape) timed out after 150 s' : null, fallback: 'none', fidelity: 'low', timings: [], artefacts: done ? artefacts : [],
    previews: done ? { concept: f('concept.png'), glb: f('figure.glb'), thumbnail: f('thumbnail.png') } : {}, result_url: done ? 'http://localhost/r/demo' : null, ticket: null, spec: SPEC,
    ...extra,
  };
}

export const VIEW_PREVIEWS = { concept: f('concept.png'), view_front: f('views/front.png'), view_left: f('views/left.png'), view_back: f('views/back.png'), view_right: f('views/right.png') };

// ------------------------------------------------------------------ curation (M8)
const qc = (ok: boolean) => ({ segmentation_valid: ok, print_watertight: true, min_wall_mm: 2.1, figure_tris: 14512, passed: ok, reasons: ok ? [] : ['segmentation: missing muzzle'] });
const cand = (id: string, status: LibraryCandidate['status'], ok = true): LibraryCandidate => ({
  id, version: 1, kind: 'family', region: null, mesh_id: 'm_0a1b2c3d4e5f6789', name: id, status, tags: ['breed:pug'], qc: qc(ok), auto_rejected: !ok,
  thumbnail_url: '/studio/fixtures/mochi/thumbnail.png',
});
export const BATCH: Batch = {
  batch_id: 'b_story', species: 'dog', status: 'review', created_by: 'operator', created_at: '2026-10-29T10:00:00Z',
  request: { species: 'dog', breeds: ['pug', 'beagle'], variants: [{ label: 'preset', patch: {} }], seeds: 1 },
  summary: { figurines: 3, finished: 2, failed: 0, candidates: 2, passed_qc: 1, accepted: 0, rejected: 1, published: 1, meshes_published: 1 },
  figurines: [
    {
      job_id: 'j_story1', breed_id: 'pug', variant: 'preset', seed: 1, status: 'done', stage: 'done', error: null,
      glb_url: '/studio/fixtures/mochi/figure.glb', thumbnail_url: '/studio/fixtures/mochi/thumbnail.png', turntable_url: null,
      candidates: [cand('family_pug_a1', 'published')],
    },
    {
      job_id: 'j_story3', breed_id: 'pug', variant: 'preset', seed: 2, status: 'done', stage: 'done', error: null,
      glb_url: '/studio/fixtures/mochi/figure.glb', thumbnail_url: '/studio/fixtures/mochi/thumbnail.png', turntable_url: null,
      candidates: [cand('family_pug_b2', 'rejected', false)],
    },
    { job_id: 'j_story2', breed_id: 'beagle', variant: 'preset', seed: 1, status: 'running', stage: 'D', error: null, glb_url: null, thumbnail_url: null, turntable_url: null, candidates: [] },
  ],
};
export const PATTERN_ITEM: LibraryItem = {
  kind: 'pattern', id: 'pattern_blaze', version: 2, versions: [1, 2], published_version: 1, species: 'dog', name: 'Big blaze', status: 'draft', tags: ['marking:blaze'],
  region: null, socket: null, default_colour: '#F4EFE6', coverage: { min: 0.1, max: 0.9, default: 0.5 }, breeds: null, default_parts: null, qc: null,
  source_job: null, batch_id: null, thumbnail_url: '/studio/library/dog/thumbs/pattern_blaze.png', published_at: null,
};
export const RELEASES: ReleaseInfo[] = [
  { release_version: 'release-dog-2', species: 'dog', number: 2, created_by: 'admin', created_at: '2026-10-29T11:00:00Z', counts: { families: 5, region_deltas: 29, shell_parts: 5, pattern_layers: 10 }, bytes: 3900000, sha256: '', url: null },
  { release_version: 'release-dog-1', species: 'dog', number: 1, created_by: 'import:proxy', created_at: '2026-10-29T00:00:00Z', counts: { families: 4, region_deltas: 24, shell_parts: 5, pattern_layers: 10 }, bytes: 3502080, sha256: '', url: null },
];

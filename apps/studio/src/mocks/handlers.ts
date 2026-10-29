// MSW handlers for VITE_MOCK=1: the Studio runs with no backend at all (BRIEF Section 13).
// One handler per studio and meta path of the OpenAPI document (HANDLED_PATHS, checked against openapi.json by
// handlers.test.ts), a timer-driven fake job that replays mock-server/scripts/*.json, and artefacts from the
// fixture pack served as static files under fixtures/. Logins: operator, curator or admin, password petpop-dev.
import { http, HttpResponse, ws } from 'msw';
import dogs from '@data/breeds/dog.json';
import cats from '@data/breeds/cat.json';
import normal from '@mockscripts/normal.json';
import slow from '@mockscripts/slow_queue.json';
import failed from '@mockscripts/failed_stage.json';
import fallback from '@mockscripts/fallback_figurine.json';
import fixtureIndex from '@fixtures/pets/index.json';
import type { Artefact, Breed, Job, PetSpec, ProgressEvent, StaffJob } from '@petpop/core';
import { applyPatch, assetUrl } from '@petpop/core';
import { mockParse } from './parse';

type Step = { stage: string; at_s: number; pct: number; message: string; preview?: string; preview_kind?: string; also?: string[][] };
type Script = { name: string; trigger_names: string[]; queue_ahead: number; queue_job_s: number; outcome: string; fallback: string; error?: string; steps: Step[] };
type FileEntry = { name: string; kind: Artefact['kind']; stage: string; bytes: number };

const SCRIPTS: Script[] = [normal, slow, failed, fallback] as Script[];
const manifests = import.meta.glob('../../../../fixtures/pets/*/manifest.json', { eager: true, import: 'default' }) as Record<string, { files: FileEntry[]; fidelity: 'high' | 'low' }>;
const PRINT_BUNDLE = ['figure.3mf', 'figure.stl', 'albedo.png', 'figure_uv.obj', 'paint_mask.png', 'manifest.json'];

export const HANDLED_PATHS = [
  '/api/v1/health', '/api/v1/r/{token}', '/api/v1/files/{key}',
  '/api/v1/studio/auth/login', '/api/v1/studio/auth/me', '/api/v1/studio/breeds', '/api/v1/studio/spec/parse', '/api/v1/studio/jobs',
  '/api/v1/studio/jobs/{job_id}', '/api/v1/studio/jobs/{job_id}/events', '/api/v1/studio/jobs/{job_id}/tweak',
  '/api/v1/studio/jobs/{job_id}/fulfil', '/api/v1/studio/jobs/{job_id}/retry', '/api/v1/studio/queue',
];
const ROLES = ['operator', 'curator', 'admin'];
const MOCK_PASSWORD = 'petpop-dev';

const speed = () => Number(import.meta.env.VITE_MOCK_SPEED ?? (globalThis as { __PP_MOCK_SPEED?: number }).__PP_MOCK_SPEED ?? 0.1);

interface FakeJob { id: string; by: string; spec: PetSpec; script: Script; pet: string; created: number; start: number; speed: number; ticket?: string }
const jobs = new Map<string, FakeJob>();
const rid = (p: string) => `${p}_${Math.random().toString(16).slice(2, 14)}`;
const iso = (t: number) => new Date(t).toISOString();

function manifestFor(pet: string) {
  const key = Object.keys(manifests).find((k) => k.includes(`/pets/${pet}/`));
  return key ? manifests[key] : { files: [], fidelity: 'low' as const };
}

function pickScript(spec: PetSpec): Script {
  const name = ((spec as { pet_name?: string }).pet_name ?? '').trim().toLowerCase();
  return SCRIPTS.find((s) => name && s.trigger_names.includes(name)) ?? SCRIPTS[0];
}

function pickPet(spec: PetSpec): string {
  const pets = fixtureIndex.pets.filter((p) => p.species === spec.species);
  const exact = pets.filter((p) => p.breed === spec.breed.id);
  const pool = exact.length ? exact : pets;
  return pool[spec.seed % pool.length].id;
}

function endOf(j: FakeJob) {
  return j.start + j.script.steps[j.script.steps.length - 1].at_s * 1000 * j.speed;
}

function enqueue(by: string, spec: PetSpec, script?: Script): FakeJob {
  const now = Date.now();
  const s = script ?? pickScript(spec);
  const sp = speed();
  const busy = Math.max(now, ...[...jobs.values()].map(endOf));
  const job: FakeJob = { id: rid('j'), by, spec, script: s, pet: pickPet(spec), created: now, start: busy + s.queue_ahead * s.queue_job_s * 1000 * sp, speed: sp };
  jobs.set(job.id, job);
  return job;
}

function state(j: FakeJob, now = Date.now()) {
  if (now < j.start) {
    const q = j.script.queue_job_s * 1000 * j.speed;
    return { status: 'queued' as const, stage: 'queued' as const, pct: 0, message: 'Waiting for the studio', queue_position: Math.max(1, q ? Math.floor((j.start - now) / q) + 1 : 1), step: -1 };
  }
  let idx = 0;
  j.script.steps.forEach((s, i) => {
    if (j.start + s.at_s * 1000 * j.speed <= now) idx = i;
  });
  const step = j.script.steps[idx];
  const last = idx === j.script.steps.length - 1;
  const status = last ? (j.script.outcome === 'failed' ? 'failed' : j.ticket ? 'fulfilled' : 'done') : 'running';
  return { status: status as Job['status'], stage: step.stage as Job['stage'], pct: step.pct, message: step.message, queue_position: 0, step: idx };
}

const url = (j: FakeJob, name: string) => assetUrl(`fixtures/${j.pet}/${name}`);

function toJob(j: FakeJob): Job {
  const st = state(j);
  const steps = j.script.steps.slice(0, st.step + 1);
  const done = st.status === 'done' || st.status === 'fulfilled';
  const kinds = new Set(steps.map((s) => s.preview_kind));
  const reached = (stage: string) =>
    ({ A: st.step >= 1, control: st.step >= 1, B: kinds.has('concept'), C: kinds.has('view_front'), D: kinds.has('shape'), E: done, F: done })[stage] ?? false;
  const artefacts: Artefact[] = manifestFor(j.pet)
    .files.filter((f) => reached(f.stage))
    .map((f) => ({ name: f.name, kind: f.kind, stage: f.stage, url: url(j, f.name), bytes: f.bytes }));
  if (done) artefacts.push({ name: 'manifest.json', kind: 'manifest', stage: 'F', url: url(j, 'manifest.json'), bytes: 1 });
  const previews: Record<string, string> = {};
  for (const s of steps) {
    if (s.preview && s.preview_kind) previews[s.preview_kind] = url(j, s.preview);
    for (const [n, k] of s.also ?? []) previews[k] = url(j, n);
  }
  if (done) previews.thumbnail = url(j, 'thumbnail.png');
  return {
    job_id: j.id, kind: 'pipeline', session_id: null, requested_by: j.by, status: st.status, stage: st.stage, pct: st.pct, message: st.message, queue_position: st.queue_position,
    seed: j.spec.seed, species: j.spec.species, pet_name: (j.spec as { pet_name?: string }).pet_name ?? null, created_at: iso(j.created),
    finished_at: done || st.status === 'failed' ? iso(endOf(j)) : null, error: st.status === 'failed' ? (j.script.error ?? 'failed') : null,
    fallback: (done ? j.script.fallback : 'none') as Job['fallback'], fidelity: manifestFor(j.pet).fidelity, timings: [], artefacts, previews,
    result_url: done ? `${location.origin}/r/mock.${j.id}` : null, ticket: j.ticket ?? null, spec: j.spec,
  };
}

function staffJob(j: FakeJob): StaffJob {
  const job = toJob(j);
  return { job_id: j.id, kind: job.kind, requested_by: job.requested_by, status: job.status, stage: job.stage, pet_name: job.pet_name ?? null, species: job.species, created_at: job.created_at, finished_at: job.finished_at ?? null, fallback: job.fallback, total_ms: null, thumbnail_url: job.previews.thumbnail ?? null, error: job.error ?? null };
}

const notFound = (what: string) => HttpResponse.json({ detail: `unknown ${what}` }, { status: 404 });
const breedDocs = { dog: dogs, cat: cats } as Record<string, { accent: string; breeds: Breed[] }>;

const events = ws.link(/\/api\/v1\/studio\/jobs\/[^/]+\/events(\?.*)?$/);
const userOf = (request: Request) => {
  const m = /^Bearer mock\.(\w+)$/.exec(request.headers.get('Authorization') ?? '');
  return m && ROLES.includes(m[1]) ? m[1] : null;
};
const unauthorised = () => HttpResponse.json({ detail: 'staff login required' }, { status: 401 });

export const handlers = [
  http.get('/api/v1/health', () => HttpResponse.json({ status: 'ok', mode: 'mock', api_version: '3.0.0', server: 'mock-server' })),
  http.post('/api/v1/studio/auth/login', async ({ request }) => {
    const body = (await request.json()) as { username: string; password: string };
    if (!ROLES.includes(body.username) || body.password !== MOCK_PASSWORD) return HttpResponse.json({ detail: 'wrong username or password' }, { status: 401 });
    return HttpResponse.json({ token: `mock.${body.username}`, user: { username: body.username, role: body.username }, expires_at: iso(Date.now() + 12 * 36e5) });
  }),
  http.get('/api/v1/studio/auth/me', ({ request }) => {
    const user = userOf(request);
    return user ? HttpResponse.json({ username: user, role: user }) : unauthorised();
  }),
  http.get('/api/v1/studio/breeds', ({ request }) => {
    const u = new URL(request.url);
    const species = u.searchParams.get('species') ?? 'dog';
    const q = (u.searchParams.get('q') ?? '').toLowerCase();
    const doc = breedDocs[species];
    if (!doc) return HttpResponse.json({ detail: 'bad species' }, { status: 422 });
    let items = doc.breeds.filter((b) => !q || b.label.toLowerCase().includes(q) || b.id.includes(q));
    items = items.sort((a, b) => (a.id === 'mixed' ? 1 : b.id === 'mixed' ? -1 : a.label.localeCompare(b.label)));
    return HttpResponse.json({ species, accent: doc.accent, total: items.length, items });
  }),
  http.post('/api/v1/studio/spec/parse', async ({ request }) => {
    const body = (await request.json()) as { current_spec: PetSpec; text: string; tapped_fields?: string[] };
    return HttpResponse.json(mockParse(body.text, body.current_spec, body.tapped_fields ?? []));
  }),
  http.post('/api/v1/studio/jobs', async ({ request }) => {
    const user = userOf(request);
    if (!user) return unauthorised();
    const body = (await request.json()) as { spec: PetSpec };
    const j = enqueue(user, body.spec);
    const st = state(j);
    return HttpResponse.json({ job_id: j.id, status: st.status, queue_position: st.queue_position }, { status: 201 });
  }),
  http.get('/api/v1/studio/jobs/:id', ({ params }) => {
    const j = jobs.get(params.id as string);
    return j ? HttpResponse.json(toJob(j)) : notFound('job');
  }),
  http.post('/api/v1/studio/jobs/:id/tweak', async ({ params, request }) => {
    const user = userOf(request);
    if (!user) return unauthorised();
    const old = jobs.get(params.id as string);
    if (!old) return notFound('job');
    const body = (await request.json()) as { patch: Record<string, unknown> };
    const { spec } = applyPatch(old.spec, body.patch);
    const j = enqueue(user, { ...spec, seed: old.spec.seed });
    const st = state(j);
    return HttpResponse.json({ job_id: j.id, status: st.status, queue_position: st.queue_position }, { status: 201 });
  }),
  http.post('/api/v1/studio/jobs/:id/fulfil', ({ params }) => {
    const j = jobs.get(params.id as string);
    if (!j) return notFound('job');
    if (!['done', 'fulfilled'].includes(state(j).status)) return HttpResponse.json({ detail: 'job is not finished' }, { status: 409 });
    j.ticket ??= `PP-${1000 + Math.floor(Math.random() * 9000)}`;
    return HttpResponse.json({ job_id: j.id, ticket: j.ticket, files: PRINT_BUNDLE });
  }),
  http.get('/api/v1/r/:token', ({ params }) => {
    const j = jobs.get(String(params.token).replace(/^mock\./, '')) ?? [...jobs.values()][0];
    if (!j) {
      const pet = fixtureIndex.pets[0];
      return HttpResponse.json({ job_id: pet.job_id, pet_name: pet.pet_name, species: pet.species, breed_label: pet.breed, glb_url: assetUrl(`fixtures/${pet.id}/figure.glb`), thumbnail_url: assetUrl(`fixtures/${pet.id}/thumbnail.png`), turntable_url: null, created_at: iso(Date.now()), expires_at: iso(Date.now() + 7 * 864e5) });
    }
    return HttpResponse.json({ job_id: j.id, pet_name: (j.spec as { pet_name?: string }).pet_name ?? null, species: j.spec.species, breed_label: j.spec.breed.label, glb_url: url(j, 'figure.glb'), thumbnail_url: url(j, 'thumbnail.png'), turntable_url: null, created_at: iso(j.created), expires_at: iso(j.created + 7 * 864e5) });
  }),
  http.get('/api/v1/files/*', () => HttpResponse.json({ detail: 'standalone mode serves artefacts from /fixtures' }, { status: 404 })),
  http.get('/api/v1/studio/queue', ({ request }) => {
    if (!userOf(request)) return unauthorised();
    const all = [...jobs.values()];
    const sts = all.map((j) => [j, state(j).status] as const);
    return HttpResponse.json({
      mode: 'mock',
      running: sts.filter(([, s]) => s === 'running').map(([j]) => staffJob(j))[0] ?? null,
      queued: sts.filter(([, s]) => s === 'queued').map(([j]) => staffJob(j)),
      recent: sts.filter(([, s]) => ['done', 'failed', 'fulfilled'].includes(s)).map(([j]) => staffJob(j)).reverse().slice(0, 20),
      gpu: { name: 'mock (no GPU)', temp_c: 41, vram_used_mb: 0, mock: true },
    });
  }),
  http.post('/api/v1/studio/jobs/:id/retry', ({ params, request }) => {
    const user = userOf(request);
    if (!user) return unauthorised();
    const old = jobs.get(params.id as string);
    if (!old) return notFound('job');
    const j = enqueue(user, old.spec, SCRIPTS[0]);
    const st = state(j);
    return HttpResponse.json({ job_id: j.id, status: st.status, queue_position: st.queue_position });
  }),
  events.addEventListener('connection', ({ client }) => {
    const id = client.url.pathname.split('/').slice(-2)[0];
    const j = jobs.get(id);
    if (!j) {
      client.close(4404, 'unknown job');
      return;
    }
    let sent = -1;
    let lastQueue = -1;
    const timer = setInterval(() => {
      const st = state(j);
      if (st.step < 0 && st.queue_position !== lastQueue) {
        lastQueue = st.queue_position;
        const ev: ProgressEvent = { job_id: j.id, status: 'queued', stage: 'queued', pct: 0, message: st.message, queue_position: st.queue_position, preview_url: null, preview_kind: null };
        client.send(JSON.stringify(ev));
      }
      for (let i = sent + 1; i <= st.step; i++) {
        const s = j.script.steps[i];
        const last = i === j.script.steps.length - 1;
        const ev: ProgressEvent = { job_id: j.id, status: last ? st.status : 'running', stage: s.stage as ProgressEvent['stage'], pct: s.pct, message: s.message, queue_position: 0, preview_url: s.preview ? url(j, s.preview) : null, preview_kind: s.preview_kind ?? null };
        client.send(JSON.stringify(ev));
        for (const [n, k] of s.also ?? []) client.send(JSON.stringify({ ...ev, status: 'running', preview_url: url(j, n), preview_kind: k }));
        sent = i;
      }
      if (['done', 'failed', 'fulfilled'].includes(st.status)) {
        clearInterval(timer);
        client.close(1000, 'done');
      }
    }, 100);
  }),
];

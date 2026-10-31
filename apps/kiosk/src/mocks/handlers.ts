// MSW handlers for VITE_MOCK=1: the kiosk runs with no backend at all (BRIEF Section 13). One handler per kiosk
// and meta path of the OpenAPI document (HANDLED_PATHS, checked against openapi.json by handlers.test.ts). The
// library comes from the committed proxy releases, unpacked into public/library/ by scripts/sync-assets.mjs.
import { http, HttpResponse } from 'msw';
import dogs from '@data/breeds/dog.json';
import cats from '@data/breeds/cat.json';
import fixtureIndex from '@fixtures/pets/index.json';
import type { Breed, CompositionBody } from '@petpop/core';
import { assetUrl } from '@petpop/core';
import type { ReleaseManifest } from '@petpop/viewer';

export const HANDLED_PATHS = [
  '/api/v1/health', '/api/v1/r/{token}', '/api/v1/files/{key}', '/api/v1/kiosk/sessions', '/api/v1/kiosk/breeds', '/api/v1/kiosk/ops',
  '/api/v1/kiosk/ops/orders/{composition_id}/reprint', '/api/v1/kiosk/library/{species}', '/api/v1/kiosk/library/{species}/families',
  '/api/v1/kiosk/library/{species}/parts', '/api/v1/kiosk/library/{species}/patterns', '/api/v1/kiosk/library/{species}/files/{path}',
  '/api/v1/kiosk/compositions', '/api/v1/kiosk/compositions/{composition_id}', '/api/v1/kiosk/compositions/{composition_id}/export',
  '/api/v1/kiosk/compositions/{composition_id}/bespoke',
];

const API_VERSION = '3.5.0';
const EXPORT_MS = 3000; // scripted Stage-F export
const rid = (p: string) => `${p}_${Math.random().toString(16).slice(2, 14)}`;
const iso = (t: number) => new Date(t).toISOString();
const ticket = () => `PP-${1000 + Math.floor(Math.random() * 9000)}`;
const sessions = new Map<string, { bespoke: number }>();
interface MockComp { id: string; session_id: string; body: CompositionBody; created: number; exported: number | null; ticket: string | null; bespoke: boolean }
const compositions = new Map<string, MockComp>();
const breedDocs = { dog: dogs, cat: cats } as Record<string, { accent: string; breeds: Breed[] }>;
// ?bespoke=1 turns "Make it unique" on in standalone mode (KIOSK_BESPOKE on a real kiosk).
const bespokeOn = () => typeof location !== 'undefined' && new URLSearchParams(location.search).get('bespoke') === '1';
const notFound = (detail: string) => HttpResponse.json({ detail }, { status: 404 });

const manifests = new Map<string, Promise<ReleaseManifest>>();
function manifest(species: string): Promise<ReleaseManifest> {
  if (!manifests.has(species)) manifests.set(species, fetch(assetUrl(`library/${species}/manifest.json`)).then((r) => r.json()));
  return manifests.get(species)!;
}
const filesUrl = (species: string) => assetUrl(`library/${species}/`);

function exportState(c: MockComp) {
  if (c.exported === null) return { status: 'draft' as const, export: null };
  const t = (Date.now() - c.exported) / EXPORT_MS;
  const ready = t >= 1;
  return {
    status: ready ? ('ready' as const) : ('exporting' as const),
    export: { job_id: `j_${c.id.slice(2)}`, status: ready ? 'done' : 'running', stage: ready ? 'done' : 'F', pct: ready ? 100 : Math.round(10 + 85 * t), message: ready ? 'Your figurine is ready' : 'Preparing the print file' },
  };
}

function petFor(c: MockComp) {
  const same = fixtureIndex.pets.filter((p) => p.species === c.body.species);
  return (same.find((p) => p.breed === c.body.breed_id) ?? same[0] ?? fixtureIndex.pets[0]).id;
}

function compositionStatus(c: MockComp) {
  const st = exportState(c);
  const ready = st.status === 'ready';
  const pet = petFor(c);
  const f = (name: string) => assetUrl(`fixtures/${pet}/${name}`);
  return {
    composition_id: c.id, session_id: c.session_id, status: st.status, pet_name: c.body.pet_name ?? null, species: c.body.species,
    release_version: c.body.release_version, created_at: iso(c.created), export: st.export, ticket: c.ticket,
    result_url: ready ? `${location.origin}/r/${c.id}.0.mock` : null,
    artefacts: ready ? ['figure.3mf', 'figure.stl', 'albedo.png', 'figure.glb', 'thumbnail.png'].map((n) => ({ name: n, kind: n === 'figure.3mf' ? '3mf' : n === 'figure.stl' ? 'stl' : n === 'albedo.png' ? 'albedo' : n === 'figure.glb' ? 'glb' : 'thumbnail', stage: 'F', url: f(n), bytes: 1 })) : [],
    previews: ready ? { glb: f('figure.glb'), thumbnail: f('thumbnail.png') } : {},
    error: null, composition: c.body,
  };
}

function order(c: MockComp) {
  const st = compositionStatus(c);
  return { composition_id: c.id, ticket: c.ticket, pet_name: st.pet_name, species: st.species, status: st.status, created_at: st.created_at, thumbnail_url: st.previews.thumbnail ?? null };
}

/** The same id checks as petpop_library.composition.check_ids, so standalone mode refuses what the API refuses. */
function compositionErrors(m: ReleaseManifest, c: CompositionBody): string[] {
  const errs: string[] = [];
  if (c.release_version !== m.release_version) errs.push(`release_version: this kiosk serves ${m.release_version}`);
  if (!m.families.some((f) => f.id === c.family_id)) errs.push(`family_id: unknown ${c.family_id}`);
  for (const [region, id] of Object.entries(c.parts ?? {})) if (m.region_deltas.find((d) => d.id === id)?.region !== region) errs.push(`parts.${region}: unknown ${id}`);
  for (const s of c.shells ?? []) if (!m.shell_parts.some((p) => p.id === s.part_id)) errs.push(`shells: unknown ${s.part_id}`);
  for (const l of c.layers ?? []) if (!m.pattern_layers.some((p) => p.id === l.pattern_id)) errs.push(`layers: unknown ${l.pattern_id}`);
  if ((c.stamps ?? []).length > 400) errs.push('stamps: at most 400');
  return errs;
}

export const handlers = [
  http.get('/api/v1/health', () => HttpResponse.json({ status: 'ok', mode: 'mock', api_version: API_VERSION, server: 'mock-server' })),
  http.post('/api/v1/kiosk/sessions', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { kiosk_id?: string };
    const id = rid('s');
    sessions.set(id, { bespoke: 0 });
    return HttpResponse.json(
      { session_id: id, kiosk_id: body.kiosk_id ?? 'kiosk-1', started_at: iso(Date.now()), idle_policy: { idle_seconds: 90, countdown_seconds: 15 }, bespoke_enabled: bespokeOn() },
      { status: 201 },
    );
  }),
  http.get('/api/v1/kiosk/breeds', ({ request }) => {
    const u = new URL(request.url);
    const species = u.searchParams.get('species') ?? 'dog';
    const q = (u.searchParams.get('q') ?? '').toLowerCase();
    const doc = breedDocs[species];
    if (!doc) return HttpResponse.json({ detail: 'bad species' }, { status: 422 });
    let items = doc.breeds.filter((b) => !q || b.label.toLowerCase().includes(q) || b.id.includes(q));
    items = items.sort((a, b) => (a.id === 'mixed' ? 1 : b.id === 'mixed' ? -1 : a.label.localeCompare(b.label)));
    return HttpResponse.json({ species, accent: doc.accent, total: items.length, items });
  }),
  // ------------------------------------------------------------------ library
  http.get('/api/v1/kiosk/library/:species', async ({ params }) => {
    const sp = String(params.species);
    if (!breedDocs[sp]) return HttpResponse.json({ detail: 'bad species' }, { status: 422 });
    const m = await manifest(sp);
    return HttpResponse.json({ species: sp, release_version: m.release_version, base_mesh_version: m.base_mesh_version, files_url: filesUrl(sp), manifest: m });
  }),
  http.get('/api/v1/kiosk/library/:species/families', async ({ params }) => {
    const sp = String(params.species);
    const m = await manifest(sp);
    const u = filesUrl(sp);
    return HttpResponse.json({ species: sp, release_version: m.release_version, items: m.families.map((f) => ({ id: f.id, name: f.name, default_parts: f.default_parts, breeds: f.breeds, tags: f.tags, version: f.version, delta_url: u + f.delta, thumbnail_url: u + f.thumbnail })) });
  }),
  http.get('/api/v1/kiosk/library/:species/parts', async ({ params, request }) => {
    const sp = String(params.species);
    const region = new URL(request.url).searchParams.get('region');
    const m = await manifest(sp);
    const u = filesUrl(sp);
    const items: unknown[] = m.region_deltas.filter((d) => !region || d.region === region).map((d) => ({ id: d.id, name: d.name, kind: 'delta', region: d.region, socket: null, tags: d.tags, version: d.version, url: u + d.delta, thumbnail_url: u + d.thumbnail, default_colour: null }));
    if (!region || region === 'shells') items.push(...m.shell_parts.map((s) => ({ id: s.id, name: s.name, kind: 'shell', region: null, socket: s.socket, tags: s.tags ?? [], version: s.version, url: u + s.mesh, thumbnail_url: u + s.thumbnail, default_colour: s.default_colour })));
    return HttpResponse.json({ species: sp, release_version: m.release_version, items });
  }),
  http.get('/api/v1/kiosk/library/:species/patterns', async ({ params }) => {
    const sp = String(params.species);
    const m = await manifest(sp);
    const u = filesUrl(sp);
    return HttpResponse.json({ species: sp, release_version: m.release_version, items: m.pattern_layers.map((p) => ({ id: p.id, name: p.name, channel: p.channel, default_colour: p.default_colour, coverage: p.coverage, version: p.version, thumbnail_url: u + p.thumbnail })) });
  }),
  http.get('/api/v1/kiosk/library/:species/files/*', async ({ params, request }) => {
    const path = new URL(request.url).pathname.split('/files/')[1];
    const r = await fetch(filesUrl(String(params.species)) + path);
    return r.ok ? new HttpResponse(await r.arrayBuffer(), { headers: { 'Content-Type': r.headers.get('Content-Type') ?? 'application/octet-stream' } }) : notFound('unknown library file');
  }),
  // ------------------------------------------------------------------ compositions
  http.post('/api/v1/kiosk/compositions', async ({ request }) => {
    const body = (await request.json()) as { session_id: string; composition: CompositionBody };
    if (!sessions.has(body.session_id)) return notFound('unknown session');
    const errs = compositionErrors(await manifest(body.composition.species), body.composition);
    if (errs.length) return HttpResponse.json({ detail: { composition: errs } }, { status: 422 });
    const c: MockComp = { id: rid('c'), session_id: body.session_id, body: body.composition, created: Date.now(), exported: null, ticket: null, bespoke: false };
    compositions.set(c.id, c);
    return HttpResponse.json(compositionStatus(c), { status: 201 });
  }),
  http.get('/api/v1/kiosk/compositions/:id', ({ params }) => {
    const c = compositions.get(String(params.id));
    return c ? HttpResponse.json(compositionStatus(c)) : notFound('unknown composition');
  }),
  http.post('/api/v1/kiosk/compositions/:id/export', ({ params }) => {
    const c = compositions.get(String(params.id));
    if (!c) return notFound('unknown composition');
    if (c.exported === null) [c.exported, c.ticket] = [Date.now(), ticket()];
    return HttpResponse.json({ composition_id: c.id, job_id: `j_${c.id.slice(2)}`, ticket: c.ticket, queue_position: 0 }, { status: 202 });
  }),
  http.post('/api/v1/kiosk/compositions/:id/bespoke', ({ params }) => {
    if (!bespokeOn()) return HttpResponse.json({ detail: 'bespoke mode is off on this kiosk' }, { status: 403 });
    const c = compositions.get(String(params.id));
    if (!c) return notFound('unknown composition');
    const s = sessions.get(c.session_id);
    if (!s) return notFound('unknown session');
    if (s.bespoke || c.bespoke) return HttpResponse.json({ detail: 'This session has already asked for a one-off figurine.' }, { status: 409 });
    s.bespoke += 1;
    c.bespoke = true;
    return HttpResponse.json({ request_id: rid('j'), ticket: ticket(), message: "We'll message you when your one-off figurine is ready." }, { status: 201 });
  }),
  // ------------------------------------------------------------------ ops (five-tap panel)
  http.get('/api/v1/kiosk/ops', async ({ request }) => {
    if (!request.headers.get('X-Staff-Token')) return HttpResponse.json({ detail: 'staff PIN required' }, { status: 403 });
    const [dog, cat] = await Promise.all([manifest('dog'), manifest('cat')]);
    const comps = [...compositions.values()].filter((c) => c.exported !== null).sort((a, b) => b.created - a.created);
    return HttpResponse.json({
      api_version: API_VERSION, mode: 'mock', kiosk_id: 'kiosk-1', releases: { dog: dog.release_version, cat: cat.release_version }, bespoke_enabled: bespokeOn(),
      exports_queued: 0, exports_running: comps.filter((c) => exportState(c).status === 'exporting').length, orders: comps.slice(0, 20).map(order),
    });
  }),
  http.post('/api/v1/kiosk/ops/orders/:id/reprint', ({ params, request }) => {
    if (!request.headers.get('X-Staff-Token')) return HttpResponse.json({ detail: 'staff PIN required' }, { status: 403 });
    const c = compositions.get(String(params.id));
    if (!c) return notFound('unknown composition');
    if (exportState(c).status !== 'ready') return HttpResponse.json({ detail: 'the order has no finished print bundle yet' }, { status: 409 });
    return HttpResponse.json(order(c));
  }),
  http.get('/api/v1/r/:token', () => {
    const pet = fixtureIndex.pets[0];
    return HttpResponse.json({ job_id: pet.job_id, pet_name: pet.pet_name, species: pet.species, breed_label: pet.breed, glb_url: assetUrl(`fixtures/${pet.id}/figure.glb`), thumbnail_url: assetUrl(`fixtures/${pet.id}/thumbnail.png`), turntable_url: null, created_at: iso(Date.now()), expires_at: iso(Date.now() + 7 * 864e5) });
  }),
  http.get('/api/v1/files/*', () => HttpResponse.json({ detail: 'standalone mode serves artefacts from /fixtures' }, { status: 404 })),
];

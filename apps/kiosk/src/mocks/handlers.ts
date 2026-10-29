// MSW handlers for VITE_MOCK=1: the kiosk runs with no backend at all (BRIEF Section 13). One handler per kiosk
// and meta path of the OpenAPI document (HANDLED_PATHS, checked against openapi.json by handlers.test.ts).
import { http, HttpResponse } from 'msw';
import dogs from '@data/breeds/dog.json';
import cats from '@data/breeds/cat.json';
import fixtureIndex from '@fixtures/pets/index.json';
import type { Breed } from '@petpop/core';
import { assetUrl } from '@petpop/core';

export const HANDLED_PATHS = ['/api/v1/health', '/api/v1/r/{token}', '/api/v1/files/{key}', '/api/v1/kiosk/sessions', '/api/v1/kiosk/breeds', '/api/v1/kiosk/bespoke', '/api/v1/kiosk/ops'];

const rid = (p: string) => `${p}_${Math.random().toString(16).slice(2, 14)}`;
const iso = (t: number) => new Date(t).toISOString();
const sessions = new Map<string, { bespoke: number }>();
const breedDocs = { dog: dogs, cat: cats } as Record<string, { accent: string; breeds: Breed[] }>;
// ?bespoke=1 turns "Make it unique" on in standalone mode (KIOSK_BESPOKE on a real kiosk).
const bespokeOn = () => typeof location !== 'undefined' && new URLSearchParams(location.search).get('bespoke') === '1';

export const handlers = [
  http.get('/api/v1/health', () => HttpResponse.json({ status: 'ok', mode: 'mock', api_version: '2.0.0', server: 'mock-server' })),
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
  http.post('/api/v1/kiosk/bespoke', async ({ request }) => {
    if (!bespokeOn()) return HttpResponse.json({ detail: 'bespoke mode is off on this kiosk' }, { status: 403 });
    const body = (await request.json()) as { session_id: string };
    const s = sessions.get(body.session_id);
    if (!s) return HttpResponse.json({ detail: 'unknown session' }, { status: 404 });
    if (s.bespoke) return HttpResponse.json({ detail: 'This session has already asked for a one-off figurine.' }, { status: 409 });
    s.bespoke += 1;
    return HttpResponse.json({ request_id: rid('j'), ticket: `PP-${1000 + Math.floor(Math.random() * 9000)}`, message: "We'll message you when your one-off figurine is ready." }, { status: 201 });
  }),
  http.get('/api/v1/kiosk/ops', ({ request }) => {
    if (!request.headers.get('X-Staff-Token')) return HttpResponse.json({ detail: 'staff PIN required' }, { status: 403 });
    return HttpResponse.json({ api_version: '2.0.0', mode: 'mock', kiosk_id: 'kiosk-1', release_version: null, bespoke_enabled: bespokeOn(), exports_queued: 0, exports_running: 0 });
  }),
  http.get('/api/v1/r/:token', () => {
    const pet = fixtureIndex.pets[0];
    return HttpResponse.json({ job_id: pet.job_id, pet_name: pet.pet_name, species: pet.species, breed_label: pet.breed, glb_url: assetUrl(`fixtures/${pet.id}/figure.glb`), thumbnail_url: assetUrl(`fixtures/${pet.id}/thumbnail.png`), turntable_url: null, created_at: iso(Date.now()), expires_at: iso(Date.now() + 7 * 864e5) });
  }),
  http.get('/api/v1/files/*', () => HttpResponse.json({ detail: 'standalone mode serves artefacts from /fixtures' }, { status: 404 })),
];

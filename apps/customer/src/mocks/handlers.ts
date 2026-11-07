// MSW handlers for VITE_MOCK=1: the kiosk runs with no backend at all (BRIEF Section 13). One handler per kiosk
// and meta path of the OpenAPI document (HANDLED_PATHS, checked against openapi.json by handlers.test.ts). The
// library comes from the committed proxy releases, unpacked into public/library/ by scripts/sync-assets.mjs.
import { http, HttpResponse } from 'msw';
import dogs from '@data/breeds/dog.json';
import cats from '@data/breeds/cat.json';
import pricing from '@config/pricing.json';
import fixtureIndex from '@fixtures/pets/index.json';
import type { Breed, CompositionBody } from '@petpop/core';
import { assetUrl } from '@petpop/core';
import { kitFor, offered, presetsOf, type Kind, type KitComposition, type KitManifest, type ReleaseManifest } from '@petpop/scene';

export const HANDLED_PATHS = [
  '/api/v1/health', '/api/v1/r/{token}', '/api/v1/files/{key}', '/api/v1/kiosk/sessions', '/api/v1/kiosk/breeds', '/api/v1/kiosk/ops',
  '/api/v1/kiosk/ops/orders/{composition_id}/reprint', '/api/v1/kiosk/library/{species}', '/api/v1/kiosk/library/{species}/families',
  '/api/v1/kiosk/library/{species}/parts', '/api/v1/kiosk/library/{species}/patterns', '/api/v1/kiosk/library/{species}/files/{path}',
  '/api/v1/kiosk/quote', '/api/v1/kiosk/compositions', '/api/v1/kiosk/compositions/{composition_id}', '/api/v1/kiosk/compositions/{composition_id}/export',
  '/api/v1/kiosk/compositions/{composition_id}/bespoke', '/api/v1/kiosk/compositions/{composition_id}/payment',
  '/api/v1/kiosk/compositions/{composition_id}/payment/simulate', '/api/v1/kiosk/ops/orders/{composition_id}/ready',
  '/api/v1/account/config', '/api/v1/account/code', '/api/v1/account/verify', '/api/v1/account/oauth/{provider}', '/api/v1/account/me',
  '/api/v1/account/me/contact', '/api/v1/account/me/contact/{channel}', '/api/v1/account/me/providers/{provider}',
  '/api/v1/account/sign-out', '/api/v1/account/me/orders', '/api/v1/account/me/devices',
];

const API_VERSION = '3.18.0';
const EXPORT_MS = 3000; // scripted Stage-F export
const rid = (p: string) => `${p}_${Math.random().toString(16).slice(2, 14)}`;
const iso = (t: number) => new Date(t).toISOString();
const ticket = () => `PP-${1000 + Math.floor(Math.random() * 9000)}`;
const sessions = new Map<string, { bespoke: number }>();
interface MockPayment { payment_id: string; composition_id: string; method: 'paynow' | 'card'; status: 'pending' | 'paid' | 'failed' | 'expired'; price: { amount: string; currency: 'SGD' }; provider: 'fake'; qr: string | null; checkout_url: string | null; created_at: string; expires_at: string | null; paid_at: string | null }
interface MockComp { id: string; session_id: string; body: CompositionBody; created: number; exported: number | null; ticket: string | null; bespoke: boolean; payments: MockPayment[]; account: string | null; contact: { email?: string | null; phone?: string | null } | null }
// Customer accounts in standalone mode (decision 126): in memory, codes shown on screen ("dev codes"), fake Apple/Google.
interface MockAccount { account_id: string; name: string | null; email: string | null; phone: string | null; providers: ('apple' | 'google')[]; created_at: string }
const accounts = new Map<string, MockAccount>();
const accountTokens = new Map<string, string>(); // token -> account id
const identities = new Map<string, string>(); // provider:subject -> account id
const codes = new Map<string, string>(); // channel:to -> code
const normal = (channel: string, to: string) => (channel === 'email' ? to.trim().toLowerCase() : (to.replace(/[\s\-().]/g, '').startsWith('+') ? to.replace(/[\s\-().]/g, '') : `+65${to.replace(/[\s\-().]/g, '')}`));
const signedIn = (request: Request) => {
  const tok = (request.headers.get('Authorization') ?? '').replace(/^Bearer /, '');
  const id = accountTokens.get(tok);
  return id ? accounts.get(id) ?? null : null;
};
const unauthorised = () => HttpResponse.json({ detail: 'sign in first' }, { status: 401 });
function session(acc: MockAccount, created: boolean, linked: string | null = null) {
  const token = rid('pa');
  accountTokens.set(token, acc.account_id);
  return { token, account: acc, created, linked };
}
function accountFor(field: 'email' | 'phone', value: string): MockAccount | undefined {
  return [...accounts.values()].find((a) => a[field] === value);
}
function newAccount(patch: Partial<MockAccount>): MockAccount {
  const a: MockAccount = { account_id: rid('a'), name: null, email: null, phone: null, providers: [], created_at: iso(Date.now()), ...patch };
  accounts.set(a.account_id, a);
  return a;
}
const compositions = new Map<string, MockComp>();
const breedDocs = { dog: dogs, cat: cats } as Record<string, { accent: string; breeds: Breed[] }>;
// ?bespoke=1 turns "Make it unique" on in standalone mode (KIOSK_BESPOKE on a real kiosk).
const bespokeOn = () => typeof location !== 'undefined' && new URLSearchParams(location.search).get('bespoke') === '1';
// ?pay=1 turns payment on in standalone mode, with the fake provider (decision 125).
const payOn = () => typeof location !== 'undefined' && new URLSearchParams(location.search).get('pay') === '1';
const PRICE = { amount: '39.00', currency: 'SGD' as const };
const paid = (c: MockComp) => c.payments.some((p) => p.status === 'paid');
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
    result_url: ready && (!payOn() || paid(c)) ? `${location.origin}/r/${c.id}.0.mock` : null,
    artefacts: ready ? ['figure.3mf', 'figure.stl', 'albedo.png', 'figure.glb', 'thumbnail.png'].map((n) => ({ name: n, kind: n === 'figure.3mf' ? '3mf' : n === 'figure.stl' ? 'stl' : n === 'albedo.png' ? 'albedo' : n === 'figure.glb' ? 'glb' : 'thumbnail', stage: 'F', url: f(n), bytes: 1 })) : [],
    previews: ready ? { glb: f('figure.glb'), thumbnail: f('thumbnail.png') } : {},
    error: null, composition: c.body, payment: c.payments[c.payments.length - 1] ?? null,
    quote: payOn() ? { items: [{ label: 'Figurine', amount: PRICE.amount }], total: PRICE } : null,
    contact: c.contact ? { email: c.contact.email ?? null, phone: c.contact.phone ?? null } : null, account_id: c.account,
  };
}

function order(c: MockComp) {
  const st = compositionStatus(c);
  return { composition_id: c.id, ticket: c.ticket, pet_name: st.pet_name, species: st.species, status: st.status, created_at: st.created_at, thumbnail_url: st.previews.thumbnail ?? null };
}

/** The same id checks as petpop_library.composition.check_ids, so standalone mode refuses what the API refuses. */
function compositionErrors(m: ReleaseManifest, body: CompositionBody): string[] {
  const errs: string[] = [];
  if (body.release_version !== m.release_version) errs.push(`release_version: this kiosk serves ${m.release_version}`);
  if (body.composition_version === '3.0') return [...errs, ...kitErrors(m as unknown as KitManifest, body as unknown as KitComposition)];
  const c = body as Extract<CompositionBody, { composition_version: '2.0' }>;
  if (!m.meshes.some((x) => x.id === c.mesh_id)) errs.push(`mesh_id: unknown ${c.mesh_id}`);
  const fam = m.families.find((f) => f.id === c.family_id);
  if (!fam) errs.push(`family_id: unknown ${c.family_id}`);
  else if (fam.mesh_id !== c.mesh_id) errs.push(`family_id: ${c.family_id} is built on another mesh`);
  for (const [region, id] of Object.entries(c.parts ?? {})) {
    const d = m.region_deltas.find((x) => x.id === id);
    if (d?.region !== region) errs.push(`parts.${region}: unknown ${id}`);
    else if (d.mesh_id !== c.mesh_id) errs.push(`parts.${region}: ${id} belongs to another mesh (part variants never cross meshes)`);
  }
  for (const s of c.shells ?? []) if (!m.shell_parts.some((p) => p.id === s.part_id)) errs.push(`shells: unknown ${s.part_id}`);
  for (const l of c.layers ?? []) if (!m.pattern_layers.some((p) => p.id === l.pattern_id)) errs.push(`layers: unknown ${l.pattern_id}`);
  if ((c.stamps ?? []).length > 400) errs.push('stamps: at most 400');
  return errs;
}

/** petpop_library.composition.check_kit: a composition 3.0 against the breed's kit in the release (decision 134). */
function kitErrors(m: KitManifest, c: KitComposition): string[] {
  const kit = kitFor(m, c.breed_id);
  if (!kit) return [`breed_id: no part kit for ${c.breed_id} in ${m.release_version}`];
  const errs: string[] = [];
  if (c.kit_version !== kit.version) errs.push(`kit_version: ${m.release_version} has kit version ${kit.version} for ${c.breed_id}`);
  const pose = kit.poses.find((p) => p.pose_id === c.pose_id);
  if (!pose) errs.push(`pose_id: ${c.breed_id} has no pose ${c.pose_id}`);
  for (const [kind, v] of Object.entries(c.variants) as [Kind, string][]) {
    if (!pose?.variants?.[kind] && !offered(kit, kind).includes(v)) errs.push(`variants.${kind}: ${v} is not offered on ${c.breed_id}`);
  }
  const presets = presetsOf(kit, c.variants.torso);
  if (!(presets.length ? presets : [{ preset_id: 'default' }]).some((x) => x.preset_id === c.preset_id)) errs.push(`preset_id: torso ${c.variants.torso} has no shape ${c.preset_id}`);
  return errs;
}

/** backend/api/pricing.py on config/pricing.json (decision 137): the figurine, extras by kind, options by rule. */
function quoteOf(c: Record<string, unknown>) {
  const P = pricing as unknown as { currency: string; figurine: { label: string; price: string }; extras: Record<string, { label: string | null; price: string }>;
    options: { id: string; label: string; price?: string; free?: number | string[]; each?: string; prices?: Record<string, string> }[] };
  const words = (x: string) => x.replace(/_/g, ' ').trim().replace(/^./, (ch) => ch.toUpperCase());
  const lines: [string, number][] = [[P.figurine.label, Number(P.figurine.price)]];
  for (const s of (c.shells as { part_id: string }[] | undefined) ?? []) {
    const kind = s.part_id.replace(/^shell_/, '');
    const rule = P.extras[kind] ?? P.extras['*'];
    if (rule) lines.push([rule.label ?? words(kind), Number(rule.price)]);
  }
  const kit = c.composition_version === '3.0';
  for (const o of P.options) {
    if (o.id === 'stamps' && ((c.stamps as unknown[]) ?? []).length) lines.push([o.label, Number(o.price)]);
    if (o.id === 'markings_over') {
      const n = kit ? ((c.texture as { markings?: string[] })?.markings ?? []).length : ((c.layers as unknown[]) ?? []).length;
      const extra = Math.max(0, n - Number(o.free ?? 0));
      if (extra) lines.push([`${o.label} (${extra})`, extra * Number(o.each)]);
    }
    if (o.id === 'shape' && kit && c.preset_id && c.preset_id !== 'default') lines.push([o.label.replace('{name}', words(String(c.preset_id))), Number(o.prices?.[String(c.preset_id)] ?? o.prices?.['*'] ?? 0)]);
    if (o.id === 'pose' && kit && !((o.free as string[]) ?? []).includes(String(c.pose_id))) lines.push([o.label.replace('{name}', words(String(c.pose_id))), Number(o.prices?.[String(c.pose_id)] ?? o.prices?.['*'] ?? 0)]);
  }
  const kept = [lines[0], ...lines.slice(1).filter(([, a]) => a !== 0)];
  const total = kept.reduce((t, [, a]) => t + a, 0);
  return { items: kept.map(([label, a]) => ({ label, amount: a.toFixed(2) })), total: { amount: total.toFixed(2), currency: P.currency } };
}

export const handlers = [
  http.get('/api/v1/health', () => HttpResponse.json({ status: 'ok', mode: 'mock', api_version: API_VERSION, server: 'mock-server' })),
  http.post('/api/v1/kiosk/sessions', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { kiosk_id?: string };
    const id = rid('s');
    sessions.set(id, { bespoke: 0 });
    return HttpResponse.json(
      { session_id: id, kiosk_id: body.kiosk_id ?? 'kiosk-1', started_at: iso(Date.now()), idle_policy: { idle_seconds: 90, countdown_seconds: 15 }, bespoke_enabled: bespokeOn(),
        payment: payOn() ? { price: PRICE, methods: ['paynow', 'card'], provider: 'fake' } : null },
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
    return HttpResponse.json({ species: sp, release_version: m.release_version, segmentation_version: m.segmentation_version, files_url: filesUrl(sp), manifest: m });
  }),
  http.get('/api/v1/kiosk/library/:species/families', async ({ params }) => {
    const sp = String(params.species);
    const m = await manifest(sp);
    const u = filesUrl(sp);
    return HttpResponse.json({
      species: sp,
      release_version: m.release_version,
      items: m.families.map((f) => ({ id: f.id, name: f.name, mesh_id: f.mesh_id, default_parts: f.default_parts, breeds: f.breeds, tags: f.tags, version: f.version, delta_url: f.delta ? u + f.delta : null, thumbnail_url: u + f.thumbnail })),
      meshes: m.meshes.map((x) => ({ id: x.id, name: x.name, breeds: x.breeds, family_ids: m.families.filter((f) => f.mesh_id === x.id).map((f) => f.id), bin_url: u + x.bin, info_url: u + x.info, texture_url: x.texture ? u + x.texture : null, thumbnail_url: u + x.thumbnail })),
    });
  }),
  http.get('/api/v1/kiosk/library/:species/parts', async ({ params, request }) => {
    const sp = String(params.species);
    const region = new URL(request.url).searchParams.get('region');
    const m = await manifest(sp);
    const u = filesUrl(sp);
    const items: unknown[] = m.region_deltas.filter((d) => !region || d.region === region).map((d) => ({ id: d.id, name: d.name, kind: 'delta', region: d.region, mesh_id: d.mesh_id, socket: null, tags: d.tags, version: d.version, url: u + d.delta, thumbnail_url: u + d.thumbnail, default_colour: null }));
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
  http.post('/api/v1/kiosk/quote', async ({ request }) => {
    const { composition } = (await request.json()) as { composition: Record<string, unknown> };
    if (composition?.species !== 'dog' && composition?.species !== 'cat') return HttpResponse.json({ detail: { composition: ['species: must be dog or cat'] } }, { status: 422 });
    return HttpResponse.json(quoteOf(composition));
  }),
  http.post('/api/v1/kiosk/compositions', async ({ request }) => {
    const body = (await request.json()) as { session_id: string; composition: CompositionBody };
    if (!sessions.has(body.session_id)) return notFound('unknown session');
    const errs = compositionErrors(await manifest(body.composition.species), body.composition);
    if (errs.length) return HttpResponse.json({ detail: { composition: errs } }, { status: 422 });
    const c: MockComp = { id: rid('c'), session_id: body.session_id, body: body.composition, created: Date.now(), exported: null, ticket: null, bespoke: false, payments: [], account: null, contact: null };
    compositions.set(c.id, c);
    return HttpResponse.json(compositionStatus(c), { status: 201 });
  }),
  http.get('/api/v1/kiosk/compositions/:id', ({ params }) => {
    const c = compositions.get(String(params.id));
    return c ? HttpResponse.json(compositionStatus(c)) : notFound('unknown composition');
  }),
  http.post('/api/v1/kiosk/compositions/:id/export', async ({ params, request }) => {
    const c = compositions.get(String(params.id));
    if (!c) return notFound('unknown composition');
    const body = (await request.json().catch(() => ({}))) as { contact?: { email?: string | null; phone?: string | null } | null };
    const acc = signedIn(request);
    if (c.exported === null) {
      if (!acc && !body.contact?.email && !body.contact?.phone) return HttpResponse.json({ detail: 'an email or a phone number is needed so we can tell you when it is ready' }, { status: 422 });
      c.account = acc?.account_id ?? null;
      c.contact = body.contact?.email || body.contact?.phone ? body.contact : { email: acc?.email ?? null, phone: acc?.phone ?? null };
    }
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
  // ------------------------------------------------------------------ payment (decision 125)
  http.post('/api/v1/kiosk/compositions/:id/payment', async ({ params, request }) => {
    const c = compositions.get(String(params.id));
    if (!c) return notFound('unknown composition');
    if (!payOn()) return HttpResponse.json({ detail: 'payments are off on this server: pay at the counter' }, { status: 409 });
    if (c.exported === null) return HttpResponse.json({ detail: 'order the figurine first' }, { status: 409 });
    if (paid(c)) return HttpResponse.json({ detail: 'this order is already paid' }, { status: 409 });
    const { method } = (await request.json()) as { method: 'paynow' | 'card' };
    c.payments.forEach((p) => p.status === 'pending' && (p.status = 'expired'));
    const id = rid('p');
    const p: MockPayment = { payment_id: id, composition_id: c.id, method, status: 'pending', price: PRICE, provider: 'fake',
      qr: method === 'paynow' ? `PETPOP-FAKE-PAYNOW|${id}|SGD39.00` : null, checkout_url: method === 'card' ? `${location.origin}/paid?fake_checkout=${id}` : null,
      created_at: iso(Date.now()), expires_at: method === 'paynow' ? iso(Date.now() + 15 * 60_000) : null, paid_at: null };
    c.payments.push(p);
    return HttpResponse.json(p, { status: 201 });
  }),
  http.get('/api/v1/kiosk/compositions/:id/payment', ({ params }) => {
    const c = compositions.get(String(params.id));
    const p = c?.payments[c.payments.length - 1];
    return p ? HttpResponse.json(p) : notFound('no payment for this order');
  }),
  http.post('/api/v1/kiosk/compositions/:id/payment/simulate', ({ params }) => {
    if (!payOn()) return HttpResponse.json({ detail: 'only the fake payment provider can be simulated' }, { status: 403 });
    const c = compositions.get(String(params.id));
    const p = c?.payments[c.payments.length - 1];
    if (!p) return notFound('no payment for this order');
    if (p.status !== 'paid') Object.assign(p, { status: 'paid', paid_at: iso(Date.now()) });
    return HttpResponse.json(p);
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
  http.post('/api/v1/kiosk/ops/orders/:id/ready', ({ params, request }) => {
    if (!request.headers.get('X-Staff-Token')) return HttpResponse.json({ detail: 'staff PIN required' }, { status: 403 });
    const c = compositions.get(String(params.id));
    return c ? HttpResponse.json(order(c)) : notFound('unknown order');
  }),
  // ------------------------------------------------------------------ accounts (decision 126)
  http.get('/api/v1/account/config', () =>
    HttpResponse.json({ email: true, phone: true, apple_client_id: 'fake', google_client_id: 'fake', dev_codes: true, fake_providers: true })),
  http.post('/api/v1/account/code', async ({ request }) => {
    const { channel, to } = (await request.json()) as { channel: 'email' | 'phone'; to: string };
    const code = String(100000 + Math.floor(Math.random() * 900000));
    codes.set(`${channel}:${normal(channel, to)}`, code);
    return HttpResponse.json({ channel, to: normal(channel, to), expires_in: 600, dev_code: code }, { status: 202 });
  }),
  http.post('/api/v1/account/verify', async ({ request }) => {
    const { channel, to, code, name } = (await request.json()) as { channel: 'email' | 'phone'; to: string; code: string; name?: string | null };
    const key = `${channel}:${normal(channel, to)}`;
    if (codes.get(key) !== code) return HttpResponse.json({ detail: 'that code is not right' }, { status: 400 });
    codes.delete(key);
    const found = accountFor(channel, normal(channel, to));
    return HttpResponse.json(session(found ?? newAccount({ [channel]: normal(channel, to), name: name ?? null }), !found));
  }),
  http.post('/api/v1/account/oauth/:provider', async ({ params, request }) => {
    const provider = String(params.provider) as 'apple' | 'google';
    const { id_token, name } = (await request.json()) as { id_token: string; name?: string | null };
    const [, sub, email] = id_token.split(':');
    const known = identities.get(`${provider}:${sub}`);
    let acc = known ? accounts.get(known) : email ? accountFor('email', email.toLowerCase()) : undefined;
    const linked = !known && acc ? provider : null;
    const created = !acc;
    acc = acc ?? newAccount({ email: email?.toLowerCase() || null, name: name ?? null });
    identities.set(`${provider}:${sub}`, acc.account_id);
    if (!acc.providers.includes(provider)) acc.providers.push(provider);
    return HttpResponse.json(session(acc, created, linked));
  }),
  http.get('/api/v1/account/me', ({ request }) => {
    const a = signedIn(request);
    return a ? HttpResponse.json(a) : unauthorised();
  }),
  http.patch('/api/v1/account/me', async ({ request }) => {
    const a = signedIn(request);
    if (!a) return unauthorised();
    a.name = ((await request.json()) as { name?: string | null }).name ?? a.name;
    return HttpResponse.json(a);
  }),
  http.delete('/api/v1/account/me', ({ request }) => {
    const a = signedIn(request);
    if (!a) return unauthorised();
    accounts.delete(a.account_id);
    return new HttpResponse(null, { status: 204 });
  }),
  http.post('/api/v1/account/me/contact', async ({ request }) => {
    const a = signedIn(request);
    if (!a) return unauthorised();
    const { channel, to, code } = (await request.json()) as { channel: 'email' | 'phone'; to: string; code: string };
    const value = normal(channel, to);
    const other = accountFor(channel, value);
    if (other && other.account_id !== a.account_id) return HttpResponse.json({ detail: `that ${channel} belongs to another account` }, { status: 409 });
    if (codes.get(`${channel}:${value}`) !== code) return HttpResponse.json({ detail: 'that code is not right' }, { status: 400 });
    a[channel] = value;
    return HttpResponse.json(a);
  }),
  http.delete('/api/v1/account/me/contact/:channel', ({ params, request }) => {
    const a = signedIn(request);
    if (!a) return unauthorised();
    const ch = String(params.channel) as 'email' | 'phone';
    const ways = a.providers.length + (a.email ? 1 : 0) + (a.phone ? 1 : 0);
    if (ways <= 1) return HttpResponse.json({ detail: 'that is your only way to sign in; add another first' }, { status: 409 });
    a[ch] = null;
    return HttpResponse.json(a);
  }),
  http.post('/api/v1/account/me/providers/:provider', async ({ params, request }) => {
    const a = signedIn(request);
    if (!a) return unauthorised();
    const provider = String(params.provider) as 'apple' | 'google';
    const [, sub] = ((await request.json()) as { id_token: string }).id_token.split(':');
    identities.set(`${provider}:${sub}`, a.account_id);
    if (!a.providers.includes(provider)) a.providers.push(provider);
    return HttpResponse.json(a);
  }),
  http.delete('/api/v1/account/me/providers/:provider', ({ params, request }) => {
    const a = signedIn(request);
    if (!a) return unauthorised();
    a.providers = a.providers.filter((p) => p !== params.provider);
    return HttpResponse.json(a);
  }),
  http.post('/api/v1/account/sign-out', ({ request }) => {
    accountTokens.delete((request.headers.get('Authorization') ?? '').replace(/^Bearer /, ''));
    return new HttpResponse(null, { status: 204 });
  }),
  http.get('/api/v1/account/me/orders', ({ request }) => {
    const a = signedIn(request);
    if (!a) return unauthorised();
    return HttpResponse.json({ items: [...compositions.values()].filter((c) => c.account === a.account_id && c.exported !== null).map(order) });
  }),
  http.post('/api/v1/account/me/devices', async ({ request }) => (signedIn(request) ? HttpResponse.json(await request.json(), { status: 201 }) : unauthorised())),
  http.delete('/api/v1/account/me/devices', ({ request }) => (signedIn(request) ? new HttpResponse(null, { status: 204 }) : unauthorised())),
  http.get('/api/v1/r/:token', () => {
    const pet = fixtureIndex.pets[0];
    return HttpResponse.json({ job_id: pet.job_id, pet_name: pet.pet_name, species: pet.species, breed_label: pet.breed, glb_url: assetUrl(`fixtures/${pet.id}/figure.glb`), thumbnail_url: assetUrl(`fixtures/${pet.id}/thumbnail.png`), turntable_url: null, created_at: iso(Date.now()), expires_at: iso(Date.now() + 7 * 864e5) });
  }),
  http.get('/api/v1/files/*', () => HttpResponse.json({ detail: 'standalone mode serves artefacts from /fixtures' }, { status: 404 })),
];

// MSW handlers for Studio curation (M8) in standalone mode: the library is the proxy release unpacked into
// public/library/ (all published), batches finish on a timer with the fixture pack's figurines as stand-ins, and
// review, the editors, publish and releases keep their state in memory. Same shapes as the contract.
import { http, HttpResponse } from 'msw';
import fixtureIndex from '@fixtures/pets/index.json';
import type { Batch, BatchCreate, BatchFigurine, ItemKind, LibraryCandidate, LibraryItem, LibraryItemPatch, ReleaseInfo, ReviewDecision, Species } from '@petpop/core';
import { assetUrl } from '@petpop/core';

type Manifest = {
  release_version: string; number: number;
  families: { id: string; name: string; tags: string[]; version: number; thumbnail: string; breeds: string[]; default_parts: Record<string, string> }[];
  region_deltas: { id: string; name: string; region: string; tags: string[]; version: number; thumbnail: string }[];
  shell_parts: { id: string; name: string; socket: string; default_colour: string; tags?: string[]; version: number; thumbnail: string }[];
  pattern_layers: { id: string; name: string; default_colour: string; coverage: { min: number; max: number; default: number }; tags?: string[]; version: number; thumbnail: string }[];
};
const REGIONS = ['ears', 'tail', 'muzzle', 'head', 'legs'];
const FIGURINE_MS = 2500;
const iso = (t: number) => new Date(t).toISOString();
const rid = (p: string) => `${p}_${Math.random().toString(16).slice(2, 12)}`;

const items = new Map<string, LibraryItem>(); // `${species}/${id}`
const releases: ReleaseInfo[] = [];
interface MockBatch { id: string; species: Species; by: string; created: number; request: BatchCreate; figs: { job_id: string; breed: string; variant: string; seed: number; at: number; pet: string }[] }
const batches = new Map<string, MockBatch>();
let seeded: Promise<void> | null = null;

function seed(): Promise<void> {
  seeded ??= Promise.all((['dog', 'cat'] as Species[]).map(async (sp) => {
    const m = (await (await fetch(assetUrl(`library/${sp}/manifest.json`))).json()) as Manifest;
    const t = (p: string) => assetUrl(`library/${sp}/${p}`);
    const add = (it: Partial<LibraryItem> & { kind: ItemKind; id: string; name: string; thumbnail: string }) =>
      items.set(`${sp}/${it.id}`, {
        version: 1, versions: [1], published_version: 1, species: sp, status: 'published', tags: [], region: null, socket: null, default_colour: null,
        coverage: null, breeds: null, default_parts: null, qc: null, source_job: null, batch_id: null, published_at: iso(Date.now()), ...it,
        thumbnail_url: t(it.thumbnail),
      } as LibraryItem);
    m.families.forEach((f) => add({ kind: 'family', id: f.id, name: f.name, tags: f.tags, thumbnail: f.thumbnail, breeds: f.breeds, default_parts: f.default_parts }));
    m.region_deltas.forEach((d) => add({ kind: 'region', id: d.id, name: d.name, tags: d.tags, thumbnail: d.thumbnail, region: d.region as LibraryItem['region'] }));
    m.shell_parts.forEach((s) => add({ kind: 'shell', id: s.id, name: s.name, tags: s.tags ?? [], thumbnail: s.thumbnail, socket: s.socket as LibraryItem['socket'], default_colour: s.default_colour }));
    m.pattern_layers.forEach((p) => add({ kind: 'pattern', id: p.id, name: p.name, tags: p.tags ?? [], thumbnail: p.thumbnail, default_colour: p.default_colour, coverage: p.coverage }));
    releases.push({ release_version: m.release_version, species: sp, number: m.number, created_by: 'import:proxy', created_at: iso(Date.now()), counts: { families: m.families.length, region_deltas: m.region_deltas.length, shell_parts: m.shell_parts.length, pattern_layers: m.pattern_layers.length }, bytes: 0, sha256: '', url: null });
  })).then(() => undefined);
  return seeded;
}

/** A finished figurine's candidates: deterministic stand-in QC (a pug's muzzle folds, as on the real pipeline). */
function candidates(b: MockBatch, f: MockBatch['figs'][number]): LibraryCandidate[] {
  const tag = f.job_id.slice(2, 8);
  const thumb = assetUrl(`fixtures/${f.pet}/thumbnail.png`);
  const make = (kind: 'family' | 'region', region: string | null): LibraryCandidate => {
    const id = kind === 'family' ? `family_${f.breed}_${tag}` : `${region}_${f.breed}_${tag}`;
    const folded = region === 'muzzle' && /pug|bulldog|persian/.test(f.breed);
    const qc = { symmetry_mm: region === 'tail' ? 1.2 : 0.3, boundary_strain: region === 'muzzle' ? 1.2 : 0.4, self_intersections: folded ? 58 : 0, passed: !folded, reasons: folded ? ['58 self-intersecting vertices'] : [] };
    const existing = items.get(`${b.species}/${id}`);
    return { id, version: existing?.version ?? 1, kind, region: region as LibraryCandidate['region'], name: `${f.breed} ${region ?? 'body'} (${f.variant})`, status: existing?.status ?? (folded ? 'rejected' : 'draft'), tags: existing?.tags ?? [`breed:${f.breed}`], qc, auto_rejected: folded, thumbnail_url: thumb };
  };
  return [make('family', null), ...REGIONS.map((r) => make('region', r))];
}

function batchOf(b: MockBatch): Batch {
  const now = Date.now();
  const figurines: BatchFigurine[] = b.figs.map((f) => {
    const done = now >= f.at;
    if (done) for (const c of candidates(b, f)) if (!items.has(`${b.species}/${c.id}`)) items.set(`${b.species}/${c.id}`, { kind: c.kind, id: c.id, version: 1, versions: [1], published_version: null, species: b.species, name: c.name, status: c.status, tags: c.tags, region: c.region, socket: null, default_colour: null, coverage: null, breeds: c.kind === 'family' ? [f.breed] : null, default_parts: null, qc: c.qc, source_job: f.job_id, batch_id: b.id, thumbnail_url: c.thumbnail_url, published_at: null });
    return {
      job_id: f.job_id, breed_id: f.breed, variant: f.variant, seed: f.seed, status: done ? 'done' : 'running', stage: done ? 'done' : 'D', error: null,
      glb_url: done ? assetUrl(`fixtures/${f.pet}/figure.glb`) : null, thumbnail_url: done ? assetUrl(`fixtures/${f.pet}/thumbnail.png`) : null,
      turntable_url: done ? assetUrl(`fixtures/${f.pet}/turntable.mp4`) : null, candidates: done ? candidates(b, f) : [],
    };
  });
  const cands = figurines.flatMap((f) => f.candidates);
  const finished = figurines.filter((f) => f.status === 'done').length;
  const sets = figurines.filter((f) => f.candidates.some((c) => c.kind === 'family' && c.status === 'published') && f.candidates.filter((c) => c.kind === 'region' && c.status === 'published').length >= 4).length;
  return {
    batch_id: b.id, species: b.species, status: finished < figurines.length ? 'running' : cands.some((c) => c.status === 'draft' || c.status === 'accepted') ? 'review' : 'done',
    created_by: b.by, created_at: iso(b.created), request: b.request as unknown as Record<string, unknown>, figurines,
    summary: { figurines: figurines.length, finished, failed: 0, candidates: cands.length, passed_qc: cands.filter((c) => !c.auto_rejected).length, accepted: cands.filter((c) => c.status === 'accepted').length, rejected: cands.filter((c) => c.status === 'rejected').length, published: cands.filter((c) => c.status === 'published').length, parts_sets_published: sets },
  };
}

const notFound = (d: string) => HttpResponse.json({ detail: d }, { status: 404 });
const forbidden = (role: string) => HttpResponse.json({ detail: `needs the ${role} role` }, { status: 403 });
const RANK: Record<string, number> = { operator: 1, curator: 2, admin: 3 };

export function curationHandlers(userOf: (r: Request) => string | null, unauthorised: () => Response) {
  const guard = (request: Request, role = 'operator') => {
    const u = userOf(request);
    if (!u) return { error: unauthorised() };
    if (RANK[u] < RANK[role]) return { error: forbidden(role) };
    return { user: u };
  };
  return [
    http.post('/api/v1/studio/batches', async ({ request }) => {
      const g = guard(request);
      if (g.error) return g.error;
      await seed();
      const body = (await request.json()) as BatchCreate;
      const variants = body.variants?.length ? body.variants : [{ label: 'preset', patch: {} }];
      const seeds = body.seeds ?? 1;
      const total = body.breeds.length * variants.length * seeds;
      if (!total || total > 60) return HttpResponse.json({ detail: { batch: [`${total} figurines; at most 60 per batch`] } }, { status: 422 });
      const b: MockBatch = { id: rid('b'), species: body.species, by: g.user!, created: Date.now(), request: body, figs: [] };
      const pets = fixtureIndex.pets.filter((p) => p.species === body.species);
      let i = 0;
      for (const breed of body.breeds) for (const v of variants) for (let k = 0; k < seeds; k++) {
        i++;
        b.figs.push({ job_id: rid('j'), breed, variant: v.label, seed: (body.first_seed ?? 1) + k, at: Date.now() + i * FIGURINE_MS, pet: (pets.find((p) => p.breed === breed) ?? pets[i % pets.length]).id });
      }
      batches.set(b.id, b);
      return HttpResponse.json(batchOf(b), { status: 201 });
    }),
    http.get('/api/v1/studio/batches', ({ request }) => {
      const g = guard(request);
      if (g.error) return g.error;
      return HttpResponse.json({ items: [...batches.values()].reverse().map((b) => ({ ...batchOf(b), figurines: [] })) });
    }),
    http.get('/api/v1/studio/batches/:id', ({ params, request }) => {
      const g = guard(request);
      if (g.error) return g.error;
      const b = batches.get(String(params.id));
      return b ? HttpResponse.json(batchOf(b)) : notFound('unknown batch');
    }),
    http.post('/api/v1/studio/batches/:id/review', async ({ params, request }) => {
      const g = guard(request, 'curator');
      if (g.error) return g.error;
      const b = batches.get(String(params.id));
      if (!b) return notFound('unknown batch');
      batchOf(b);
      const { decisions } = (await request.json()) as { decisions: ReviewDecision[] };
      for (const d of decisions) {
        const it = items.get(`${b.species}/${d.item_id}`);
        if (!it || it.batch_id !== b.id) return notFound(`${d.item_id} is not in batch ${b.id}`);
        it.status = d.action === 'accept' ? 'accepted' : 'rejected';
        if (d.tags) it.tags = [...new Set(d.tags)].sort();
      }
      return HttpResponse.json(batchOf(b));
    }),
    http.get('/api/v1/studio/library/:species', async ({ params, request }) => {
      const g = guard(request);
      if (g.error) return g.error;
      await seed();
      const u = new URL(request.url);
      const kind = u.searchParams.get('kind');
      const status = u.searchParams.get('status');
      const sp = String(params.species);
      return HttpResponse.json({ species: sp, items: [...items.values()].filter((i) => i.species === sp && (!kind || i.kind === kind) && (!status || i.status === status)) });
    }),
    http.patch('/api/v1/studio/library/:species/:kind/:id', async ({ params, request }) => {
      const g = guard(request, 'curator');
      if (g.error) return g.error;
      const it = items.get(`${params.species}/${params.id}`);
      if (!it || it.kind !== params.kind) return notFound('unknown item');
      const patch = (await request.json()) as LibraryItemPatch;
      if (patch.coverage && !(0 <= patch.coverage.min && patch.coverage.min <= patch.coverage.default && patch.coverage.default <= patch.coverage.max && patch.coverage.max <= 1)) {
        return HttpResponse.json({ detail: { coverage: ['needs 0 <= min <= default <= max <= 1'] } }, { status: 422 });
      }
      const next: LibraryItem = it.status === 'published' ? { ...it, version: it.version + 1, versions: [...it.versions, it.version + 1], status: 'draft' } : { ...it };
      Object.assign(next, Object.fromEntries(Object.entries(patch).filter(([, v]) => v !== null && v !== undefined)));
      if (next.default_colour) next.default_colour = next.default_colour.toUpperCase();
      items.set(`${params.species}/${params.id}`, next);
      return HttpResponse.json(next);
    }),
    http.post('/api/v1/studio/library/:species/:kind/:id/publish', ({ params, request }) => {
      const g = guard(request, 'curator');
      if (g.error) return g.error;
      const it = items.get(`${params.species}/${params.id}`);
      if (!it || it.kind !== params.kind) return notFound('unknown item');
      if (it.status === 'rejected') return HttpResponse.json({ detail: `${it.id} is rejected; accept it in review first` }, { status: 409 });
      Object.assign(it, { status: 'published', published_version: it.version, published_at: iso(Date.now()) });
      return HttpResponse.json(it);
    }),
    http.post('/api/v1/studio/library/:species/:kind/:id/unpublish', ({ params, request }) => {
      const g = guard(request, 'curator');
      if (g.error) return g.error;
      const it = items.get(`${params.species}/${params.id}`);
      if (!it || it.published_version === null) return notFound('no published version');
      Object.assign(it, { status: 'accepted', published_version: null });
      return HttpResponse.json(it);
    }),
    http.get('/api/v1/studio/releases', async ({ request }) => {
      const g = guard(request);
      if (g.error) return g.error;
      await seed();
      return HttpResponse.json({ items: [...releases].reverse() });
    }),
    http.post('/api/v1/studio/releases', async ({ request }) => {
      const g = guard(request, 'admin');
      if (g.error) return g.error;
      await seed();
      const { species } = (await request.json()) as { species: Species };
      const pub = [...items.values()].filter((i) => i.species === species && i.status === 'published');
      const number = Math.max(0, ...releases.filter((r) => r.species === species).map((r) => r.number)) + 1;
      const r: ReleaseInfo = { release_version: `release-${species}-${number}`, species, number, created_by: g.user!, created_at: iso(Date.now()), bytes: 0, sha256: '', url: null,
        counts: { families: pub.filter((i) => i.kind === 'family').length, region_deltas: pub.filter((i) => i.kind === 'region').length, shell_parts: pub.filter((i) => i.kind === 'shell').length, pattern_layers: pub.filter((i) => i.kind === 'pattern').length } };
      releases.push(r);
      return HttpResponse.json(r, { status: 201 });
    }),
  ];
}

// The part library in standalone mode (decisions 127, 130): kits kept in memory (each breed's own parts only: the
// shared library is the backend's), seeded from the proxy kit's golden rig
// (fixtures/parts/golden.json, the Python first guess), meshes from public/parts/ (scripts/sync-assets.mjs).
import { http, HttpResponse } from 'msw';
import golden from '@fixtures/parts/golden.json';
import { assetUrl } from '@petpop/core';
import type { Part, PartKit, Pose } from '@petpop/core';
import { KINDS, headProblems } from '@petpop/scene';

type Golden = { kind: Part['kind']; variant: string; file: string; tris: number; joint?: Part['joint']; attachments?: Part['attachments']; limits?: Part['limits']; guess: Part['guess'] };
const G = golden.parts as unknown as Golden[];
const NAME = /^([a-z0-9_]+)__(head|torso|front_leg|fore_leg|hind_leg_sitting|hind_leg|tail)(?:__([a-z0-9_]{1,40}))?\.glb$/;
const STANDING: Pose = { pose_id: 'standing', label: 'Standing', legs: { front_left: 0, front_right: 0, hind_left: 0, hind_right: 0 }, head: { yaw: 0, pitch: 0, roll: 0 }, variants: {} };
const kits = new Map<string, PartKit>(); // "<species>/<breed>"
const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x));
const label = (b: string) => b.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

function guessFor(kind: Part['kind'], variant: string): Golden {
  return G.find((g) => g.kind === kind && g.variant === variant) ?? G.find((g) => g.kind === kind && g.variant === 'default')!;
}
function problems(k: PartKit): string[] {
  const out: string[] = [];
  for (const kind of KINDS) if (!k.parts.some((p) => p.kind === kind)) out.push(`no ${kind.replace('_', ' ')} part`);
  const head = k.parts.find((p) => p.kind === 'head' && p.variant === k.defaults.head);
  if (head?.limits) for (const p of k.poses) out.push(...headProblems(p, head.limits as never).map((x) => `pose ${p.pose_id}: ${x}`));
  return out;
}
function refresh(k: PartKit): PartKit {
  const allowed: NonNullable<PartKit['allowed']> = {};
  for (const kind of KINDS) {
    const vs = k.parts.filter((p) => p.kind === kind).map((p) => p.variant);
    if (!vs.includes(k.defaults[kind] ?? '')) {
      if (vs.length) k.defaults[kind] = vs.includes('default') ? 'default' : vs[0];
      else delete k.defaults[kind];
    }
    if (vs.length) allowed[kind] = vs; // a breed's own parts are always allowed
  }
  k.allowed = allowed;
  for (const p of k.parts) {
    Object.assign(p, { shared: false, stretch: p.stretch ?? [1, 1, 1], stretch_edited: p.stretch_edited ?? false });
    // a torso's presets (decision 131): the default's stretch is the part's own
    const rest = (p.presets ?? []).filter((x) => x.preset_id !== 'default');
    const first = (p.presets ?? []).find((x) => x.preset_id === 'default');
    p.presets = p.kind === 'torso' ? [{ preset_id: 'default', label: first?.label ?? 'Standard', stretch: p.stretch, sockets: first?.sockets ?? {} },
      ...rest.map((x) => ({ ...x, stretch: x.stretch ?? p.stretch }))] : [];
  }
  k.problems = problems(k);
  return k;
}
const dirty = (k: PartKit) => ((k.dirty = true), refresh(k));
function kitOf(params: Record<string, unknown>) {
  return kits.get(`${params.species}/${params.breed}`);
}
const notFound = (d: string) => HttpResponse.json({ detail: d }, { status: 404 });

// standalone mode starts with the proxy dog kit, rigged by the first guess
kits.set('dog/mixed', refresh({
  species: 'dog', breed_id: 'mixed', breed_label: 'Mixed / not sure', defaults: {}, poses: [clone(STANDING)], default_pose: 'standing', symmetry: true,
  version: 0, committed_at: null, committed_by: null, dirty: true, problems: [], notes: [],
  parts: G.map((g) => ({
    part_id: `pt_mixed_${g.kind}_${g.variant}`, kind: g.kind, variant: g.variant, label: g.variant === 'default' ? 'Standard' : label(g.variant),
    mesh_url: assetUrl(`parts/dog/${g.file}`), tris: g.tris, sha256: '0'.repeat(64), joint: clone(g.joint ?? null), attachments: clone(g.attachments ?? null),
    limits: clone(g.limits ?? null), guess: clone(g.guess), edited: false, mirrored: false, shared: false, stretch: [1, 1, 1], stretch_edited: false, presets: [],
  })),
} as unknown as PartKit));

export const partHandlers = (userOf: (r: Request) => string | null, unauthorised: () => Response) => [
  http.get('/api/v1/studio/parts/:species', ({ params, request }) => {
    if (!userOf(request)) return unauthorised();
    const items = [...kits.values()].filter((k) => k.species === params.species).map((k) => ({
      breed_id: k.breed_id, breed_label: k.breed_label, kinds: KINDS.filter((kind) => k.parts.some((p) => p.kind === kind)),
      parts: k.parts.length, version: k.version, dirty: k.dirty, problems: k.problems.length,
    }));
    return HttpResponse.json({ items });
  }),
  http.post('/api/v1/studio/parts/:species/upload', async ({ params, request }) => {
    const user = userOf(request);
    if (!user) return unauthorised();
    if (user === 'operator') return HttpResponse.json({ detail: 'curator role required' }, { status: 403 });
    const form = await request.formData();
    const items: Part[] = [];
    const skipped: string[] = [];
    const breeds = new Set<string>();
    for (const f of form.getAll('files') as File[]) {
      if (f.name.toLowerCase().endsWith('.png')) {
        skipped.push(`${f.name}: masks need the backend (standalone mode keeps parts only)`);
        continue;
      }
      const m = NAME.exec(f.name.toLowerCase());
      if (!m) {
        skipped.push(`${f.name}: expected <breed>__<kind>[__<variant>].glb`);
        continue;
      }
      // the breed database's names: fore_leg is the front leg, hind_leg_sitting the hind leg's "sitting" variant
      const [, breed, named, given] = m as unknown as [string, string, string, string | undefined];
      const kind = (named === 'fore_leg' ? 'front_leg' : named === 'hind_leg_sitting' ? 'hind_leg' : named) as Part['kind'];
      const variant = named === 'hind_leg_sitting' ? (given ? `sitting_${given}` : 'sitting') : given ?? 'default';
      const key = `${params.species}/${breed}`;
      const kit = kits.get(key) ?? { species: params.species, breed_id: breed, breed_label: label(breed), parts: [], defaults: {}, poses: [clone(STANDING)],
        default_pose: 'standing', symmetry: true, version: 0, committed_at: null, committed_by: null, dirty: true, problems: [], notes: [] } as unknown as PartKit;
      kits.set(key, kit);
      const g = guessFor(kind, variant);
      const part: Part = { part_id: `pt_${breed}_${kind}_${variant}`, kind, variant, label: variant === 'default' ? 'Standard' : label(variant),
        mesh_url: assetUrl(`parts/dog/${g.file}`), tris: g.tris, sha256: '0'.repeat(64), joint: clone(g.joint ?? null), attachments: clone(g.attachments ?? null),
        limits: clone(g.limits ?? null), guess: clone(g.guess), edited: false, mirrored: false, shared: false, stretch: [1, 1, 1], stretch_edited: false, presets: [] };
      kit.parts = [...kit.parts.filter((p) => !(p.kind === kind && p.variant === variant)), part];
      dirty(kit);
      items.push(part);
      breeds.add(breed);
    }
    return HttpResponse.json({ items, breeds: [...breeds].sort(), skipped, notes: [] }, { status: 201 });
  }),
  http.get('/api/v1/studio/parts/:species/:breed', ({ params, request }) => {
    if (!userOf(request)) return unauthorised();
    const k = kitOf(params);
    return k ? HttpResponse.json(k) : notFound(`no parts for ${params.breed} yet`);
  }),
  http.patch('/api/v1/studio/parts/:species/:breed/parts/:part', async ({ params, request }) => {
    if (!userOf(request)) return unauthorised();
    const k = kitOf(params);
    const p = k?.parts.find((x) => x.part_id === params.part);
    if (!k || !p) return notFound('unknown part');
    const patch = (await request.json()) as Partial<Part>;
    if (patch.label) p.label = patch.label;
    if (patch.joint) Object.assign(p, { joint: patch.joint, edited: true });
    if (patch.attachments) Object.assign(p, { attachments: { ...p.attachments, ...patch.attachments }, edited: true });
    if (patch.limits) Object.assign(p, { limits: patch.limits, edited: true });
    return HttpResponse.json(dirty(k));
  }),
  http.post('/api/v1/studio/parts/:species/:breed/parts/:part/guess', ({ params, request }) => {
    if (!userOf(request)) return unauthorised();
    const k = kitOf(params);
    const p = k?.parts.find((x) => x.part_id === params.part);
    if (!k || !p) return notFound('unknown part');
    const g = guessFor(p.kind, p.variant);
    Object.assign(p, { joint: clone(g.joint ?? null), attachments: clone(g.attachments ?? null), edited: false });
    return HttpResponse.json(dirty(k));
  }),
  http.delete('/api/v1/studio/parts/:species/:breed/parts/:part', ({ params, request }) => {
    if (!userOf(request)) return unauthorised();
    const k = kitOf(params);
    if (!k) return notFound('unknown part');
    k.parts = k.parts.filter((x) => x.part_id !== params.part);
    return HttpResponse.json(dirty(k));
  }),
  http.put('/api/v1/studio/parts/:species/:breed/setup', async ({ params, request }) => {
    if (!userOf(request)) return unauthorised();
    const k = kitOf(params);
    if (!k) return notFound('no kit');
    const body = (await request.json()) as { defaults?: PartKit['defaults']; poses?: Pose[]; default_pose?: string; symmetry?: boolean;
      stretch?: Record<string, number[] | null>; texture?: PartKit['texture']; presets?: Record<string, Part['presets']> };
    for (const [key, list] of Object.entries(body.presets ?? {})) {
      const p = k.parts.find((x) => x.kind === 'torso' && x.variant === key.split('/')[1]);
      if (!p) return HttpResponse.json({ detail: `no torso variant ${key}` }, { status: 422 });
      const ids = (list ?? []).map((x) => x.preset_id);
      if (new Set(ids).size !== ids.length) return HttpResponse.json({ detail: 'preset ids must be unique' }, { status: 422 });
      p.presets = list ?? [];
    }
    for (const [key, s] of Object.entries(body.stretch ?? {})) {
      const [kind, variant] = key.split('/');
      const p = k.parts.find((x) => x.kind === kind && x.variant === variant);
      if (!p) return HttpResponse.json({ detail: `no ${kind} variant ${variant}` }, { status: 422 });
      if (s && s.some((x) => x <= 0)) return HttpResponse.json({ detail: 'a stretch must be positive' }, { status: 422 });
      Object.assign(p, { stretch: s ?? [1, 1, 1], stretch_edited: !!s });
    }
    if (body.texture) k.texture = body.texture;
    if (body.defaults) k.defaults = { ...k.defaults, ...body.defaults };
    if (body.poses) {
      k.poses = body.poses;
      if (!k.poses.some((p) => p.pose_id === k.default_pose)) k.default_pose = k.poses[0].pose_id;
    }
    if (body.default_pose) k.default_pose = body.default_pose;
    if (body.symmetry !== undefined) k.symmetry = body.symmetry;
    return HttpResponse.json(dirty(k));
  }),
  http.post('/api/v1/studio/parts/:species/:breed/commit', ({ params, request }) => {
    const user = userOf(request);
    if (!user) return unauthorised();
    const k = kitOf(params);
    if (!k) return notFound('no kit');
    refresh(k);
    if (k.problems.length) return HttpResponse.json({ detail: { kit: k.problems } }, { status: 409 });
    Object.assign(k, { version: k.version + 1, dirty: false, committed_by: user, committed_at: new Date().toISOString() });
    return HttpResponse.json(k);
  }),
];

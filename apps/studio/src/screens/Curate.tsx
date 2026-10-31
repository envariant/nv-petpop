// Studio curation (BRIEF Section 16, M8): the Generate workspace as a batch spec builder (breeds x variants x
// seeds), the review grid (turntables, QC, accept, reject and tag per region), the parts and pattern editors with
// publish and versioning, and releases. One-off figurines (bespoke jobs) keep the Build, Brief and Name flow.
import { useEffect, useMemo, useState } from 'react';
import { StudioApi, label } from '@petpop/core';
import type { Batch, BatchFigurine, Breed, ItemKind, LibraryCandidate, LibraryItem, Species } from '@petpop/core';
import { Button, Chip, Row, Section, Swatch, Title, cx } from '@petpop/ui';
import { MAX_FIGURINES, VARIANTS, useCurate } from '../store/curate';
import { useSession } from '../store/session';
import { ProfilePicker } from './ProfilePicker';

const STATUS_STYLE: Record<string, string> = {
  draft: 'bg-line text-ink', accepted: 'bg-accent text-white', rejected: 'bg-accent2 text-white', published: 'bg-ink text-white', superseded: 'bg-line text-muted',
};
const field = 'w-full rounded-tile border-4 border-line bg-card px-6 py-4 text-3xl outline-none focus:border-accent';

function Status({ status }: { status: string }) {
  return <span className={cx('rounded-full px-4 py-1 font-display text-xl', STATUS_STYLE[status] ?? 'bg-line')}>{status}</span>;
}

function Notice() {
  const { error, notice } = useCurate();
  if (!error && !notice) return null;
  return (
    <p className={cx('mb-4 text-2xl font-semibold', error ? 'text-accent2' : 'text-accent')} data-testid={error ? 'curate-error' : 'curate-notice'}>
      {error ?? notice}
    </p>
  );
}

function SpeciesChips() {
  const species = useCurate((s) => s.species);
  const set = useCurate((s) => s.set);
  return (
    <Row>
      {(['dog', 'cat'] as Species[]).map((sp) => (
        <Chip key={sp} selected={species === sp} onClick={() => set({ species: sp, breeds: [], items: [], selected: null })} testId={`curate-species-${sp}`}>
          {sp === 'dog' ? 'Dogs' : 'Cats'}
        </Chip>
      ))}
    </Row>
  );
}

// ------------------------------------------------------------------ Generate: the batch spec builder
export function GenerateScreen() {
  const c = useCurate();
  const go = useSession((s) => s.go);
  const [breeds, setBreeds] = useState<Breed[]>([]);
  useEffect(() => {
    void StudioApi.breeds(c.species).then((r) => setBreeds(r.items)).catch(() => setBreeds([]));
  }, [c.species]);
  useEffect(() => {
    void c.loadBatches();
    const t = setInterval(() => void useCurate.getState().loadBatches(), 3000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const total = c.breeds.length * c.variants.length * c.seeds;
  return (
    <div className="no-scrollbar flex h-full flex-col overflow-y-auto px-12 pb-10 pt-24" data-testid="generate">
      <Title sub="Breeds x variants x seeds, each a full pipeline run; every figurine is split into library parts and checked.">New batch</Title>
      <Notice />
      <Section title="Species">
        <SpeciesChips />
      </Section>
      <Section title={`Breeds (${c.breeds.length})`} testId="batch-breeds">
        <div className="flex flex-wrap gap-3">
          {breeds.map((b) => (
            <Chip key={b.id} selected={c.breeds.includes(b.id)} onClick={() => c.toggleBreed(b.id)} testId={`batch-breed-${b.id}`}>
              {b.label}
            </Chip>
          ))}
        </div>
      </Section>
      <Section title="Variants" testId="batch-variants">
        <div className="flex flex-wrap gap-3">
          {VARIANTS.map((v) => (
            <Chip key={v.label} selected={c.variants.includes(v.label)} onClick={() => c.toggleVariant(v.label)} testId={`batch-variant-${v.label}`}>
              {v.title}
            </Chip>
          ))}
        </div>
      </Section>
      <Section title="Seeds per variant">
        <div className="flex items-center gap-6">
          <Button variant="soft" onClick={() => c.set({ seeds: Math.max(1, c.seeds - 1) })} data-testid="seeds-minus">
            −
          </Button>
          <span className="w-16 text-center font-display text-5xl" data-testid="seeds">
            {c.seeds}
          </span>
          <Button variant="soft" onClick={() => c.set({ seeds: Math.min(10, c.seeds + 1) })} data-testid="seeds-plus">
            +
          </Button>
        </div>
      </Section>
      <ProfilePicker />
      <div className="flex items-center gap-6">
        <Button className="flex-1" disabled={!total || total > MAX_FIGURINES || c.busy} onClick={() => void c.startBatch()} data-testid="start-batch">
          {total > MAX_FIGURINES ? `${total} figurines: at most ${MAX_FIGURINES}` : `Generate ${total} figurine${total === 1 ? '' : 's'}`}
        </Button>
        <Button variant="ghost" onClick={() => go('species')} data-testid="one-off">
          One-off figurine ›
        </Button>
      </div>
      <Section title="Batches" testId="batch-list">
        {c.batches.length === 0 && <p className="text-2xl text-muted">No batches yet.</p>}
        {c.batches.map((b) => (
          <button
            key={b.batch_id}
            className="hit mb-3 flex w-full items-center justify-between rounded-tile bg-card p-5 text-left text-2xl shadow-soft"
            onClick={() => {
              void c.openBatch(b.batch_id);
              go('review');
            }}
            data-testid={`batch-${b.batch_id}`}
          >
            <span>
              <b>{b.species}</b> · {b.summary.finished}/{b.summary.figurines} done · {b.summary.passed_qc}/{b.summary.candidates} parts pass QC · by {b.created_by}
              {b.genai_profile ? (
                <span data-testid={`batch-profile-${b.batch_id}`}>
                  {' '}· on {b.genai_profile}
                  {b.pipeline ? `, ${b.pipeline.replace('_', ' ')}` : ''}
                </span>
              ) : null}
            </span>
            <Status status={b.status} />
          </button>
        ))}
      </Section>
    </div>
  );
}

// ------------------------------------------------------------------ Review grid
function QcLine({ c }: { c: LibraryCandidate }) {
  const q = c.qc as { symmetry_mm?: number; boundary_strain?: number; self_intersections?: number; reasons?: string[] };
  return (
    <span className={cx('text-xl', c.auto_rejected ? 'text-accent2' : 'text-muted')} title={(q.reasons ?? []).join('; ')}>
      sym {q.symmetry_mm?.toFixed(2)} mm · strain {q.boundary_strain?.toFixed(2)} · x {q.self_intersections}
      {c.auto_rejected && ` · ${(q.reasons ?? [])[0] ?? 'rejected'}`}
    </span>
  );
}

function CandidateRow({ c }: { c: LibraryCandidate }) {
  const decide = useCurate((s) => s.decide);
  const publish = useCurate((s) => s.publish);
  const species = useCurate((s) => s.batch?.species ?? 'dog');
  const hero = c.tags.includes('hero');
  return (
    <div className="flex items-center gap-4 border-t-2 border-line py-3" data-testid={`cand-${c.id}`}>
      {c.thumbnail_url && <img src={c.thumbnail_url} alt="" className="h-20 w-20 object-contain" />}
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-display text-2xl">{c.kind === 'family' ? 'Family' : label(c.region ?? '')}</span>
        <QcLine c={c} />
      </div>
      <Status status={c.status} />
      {c.status !== 'published' && (
        <>
          <Chip selected={c.status === 'accepted'} onClick={() => void decide([{ item_id: c.id, action: 'accept' }])} testId={`accept-${c.id}`}>
            ✓
          </Chip>
          <Chip selected={c.status === 'rejected'} onClick={() => void decide([{ item_id: c.id, action: 'reject' }])} testId={`reject-${c.id}`}>
            ✕
          </Chip>
          <Chip selected={hero} onClick={() => void decide([{ item_id: c.id, action: c.status === 'rejected' ? 'reject' : 'accept', tags: hero ? c.tags.filter((t) => t !== 'hero') : [...c.tags, 'hero'] }])} testId={`hero-${c.id}`}>
            ★
          </Chip>
        </>
      )}
      {c.status === 'accepted' && (
        <Chip onClick={() => void publish({ species, kind: c.kind, id: c.id } as LibraryItem).then(() => useCurate.getState().refreshBatch())} testId={`publish-${c.id}`}>
          Publish
        </Chip>
      )}
    </div>
  );
}

function FigurineCard({ f }: { f: BatchFigurine }) {
  return (
    <div className="mb-6 rounded-tile bg-card p-5 shadow-soft" data-testid={`fig-${f.job_id}`}>
      <div className="flex gap-5">
        <div className="h-[260px] w-[260px] shrink-0 overflow-hidden rounded-tile bg-paper">
          {f.turntable_url ? (
            <video src={f.turntable_url} poster={f.thumbnail_url ?? undefined} autoPlay loop muted playsInline className="h-full w-full object-contain" />
          ) : f.thumbnail_url ? (
            <img src={f.thumbnail_url} alt="" className="h-full w-full object-contain" />
          ) : (
            <div className="flex h-full items-center justify-center text-2xl text-muted">{f.stage}…</div>
          )}
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="font-display text-3xl">
            {label(f.breed_id)} · {f.variant} · seed {f.seed}
          </span>
          <span className="text-2xl text-muted">
            {f.status}
            {f.error && ` · ${f.error}`}
          </span>
          {f.candidates.map((c) => (
            <CandidateRow key={c.id} c={c} />
          ))}
        </div>
      </div>
    </div>
  );
}

export function ReviewScreen() {
  const c = useCurate();
  const go = useSession((s) => s.go);
  useEffect(() => {
    if (!c.batch) void c.loadBatches().then(() => {
      const first = useCurate.getState().batches[0];
      if (first) void useCurate.getState().openBatch(first.batch_id);
    });
    const t = setInterval(() => void useCurate.getState().refreshBatch(), 2000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const b: Batch | null = c.batch;
  const passing = useMemo(() => (b ? b.figurines.flatMap((f) => f.candidates).filter((x) => !x.auto_rejected && x.status === 'draft') : []), [b]);
  const accepted = useMemo(() => (b ? b.figurines.flatMap((f) => f.candidates).filter((x) => x.status === 'accepted') : []), [b]);
  const publishAll = async () => {
    for (const x of accepted) await c.publish({ species: b!.species, kind: x.kind, id: x.id } as LibraryItem);
    await c.refreshBatch();
  };
  if (!b) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-8 px-16 text-center" data-testid="review">
        <Title sub="Start a batch in Generate.">Nothing to review</Title>
        <Button onClick={() => go('generate')}>New batch</Button>
      </div>
    );
  }
  const s = b.summary;
  return (
    <div className="no-scrollbar flex h-full flex-col overflow-y-auto px-12 pb-10 pt-24" data-testid="review">
      <Title sub={`${s.finished}/${s.figurines} figurines done · ${s.passed_qc}/${s.candidates} parts pass QC · ${s.accepted} accepted · ${s.published} published · ${s.parts_sets_published} parts sets`}>
        Review {b.species} batch
      </Title>
      <Notice />
      <div className="mb-6 flex gap-4">
        <Button variant="soft" disabled={!passing.length || c.busy} onClick={() => void c.decide(passing.map((x) => ({ item_id: x.id, action: 'accept' as const })))} data-testid="accept-passing">
          Accept {passing.length} that passed QC
        </Button>
        <Button disabled={!accepted.length || c.busy} onClick={() => void publishAll()} data-testid="publish-accepted">
          Publish {accepted.length} accepted
        </Button>
      </div>
      <p className="mb-4 text-xl text-muted">Fix in Blender: download a figurine's GLB from the queue, edit it on the base topology, and re-run it as a one-off; its parts come back here for review.</p>
      {b.figurines.map((f) => (
        <FigurineCard key={f.job_id} f={f} />
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ Library: parts and pattern editors
const KINDS: { kind: ItemKind; title: string }[] = [
  { kind: 'family', title: 'Families' },
  { kind: 'region', title: 'Parts' },
  { kind: 'shell', title: 'Accessories' },
  { kind: 'pattern', title: 'Patterns' },
];
const COLOURS = ['#F4EFE6', '#1E1B1A', '#C8763A', '#8A5A3B', '#E8D8B8', '#6E6A68', '#DD3333', '#3366CC', '#F2C230', '#E04A8A'];

function Editor({ item }: { item: LibraryItem }) {
  const c = useCurate();
  const [name, setName] = useState(item.name);
  const [tags, setTags] = useState(item.tags.join(', '));
  const [colour, setColour] = useState(item.default_colour ?? '');
  const [cov, setCov] = useState(item.coverage ?? { min: 0, max: 1, default: 0.5 });
  const [breeds, setBreeds] = useState((item.breeds ?? []).join(', '));
  useEffect(() => {
    setName(item.name);
    setTags(item.tags.join(', '));
    setColour(item.default_colour ?? '');
    setCov(item.coverage ?? { min: 0, max: 1, default: 0.5 });
    setBreeds((item.breeds ?? []).join(', '));
  }, [item]);
  const list = (t: string) => t.split(',').map((x) => x.trim()).filter(Boolean);
  const save = () =>
    c.edit({
      name, tags: list(tags),
      ...(item.kind === 'shell' || item.kind === 'pattern' ? { default_colour: colour } : {}),
      ...(item.kind === 'pattern' ? { coverage: cov } : {}),
      ...(item.kind === 'family' ? { breeds: list(breeds) } : {}),
    });
  const slider = (k: 'min' | 'default' | 'max') => (
    <label className="flex items-center gap-4 text-2xl" key={k}>
      <span className="w-28">{k}</span>
      <input type="range" min={0} max={1} step={0.01} value={cov[k]} onChange={(e) => setCov({ ...cov, [k]: Number(e.target.value) })} className="flex-1" data-testid={`cov-${k}`} />
      <span className="w-16">{cov[k].toFixed(2)}</span>
    </label>
  );
  return (
    <div className="mt-6 rounded-tile bg-card p-6 shadow-soft" data-testid="item-editor">
      <div className="mb-4 flex items-center gap-4">
        {item.thumbnail_url && <img src={item.thumbnail_url} alt="" className="h-28 w-28 object-contain" />}
        <div className="flex flex-col">
          <span className="font-display text-3xl">{item.id}</span>
          <span className="text-2xl text-muted">
            version {item.version} of {item.versions.join(', ')} · published {item.published_version ?? 'none'}
          </span>
        </div>
        <span className="ml-auto">
          <Status status={item.status} />
        </span>
      </div>
      <div className="flex flex-col gap-4">
        <input className={field} value={name} onChange={(e) => setName(e.target.value)} data-testid="edit-name" aria-label="Name" />
        <input className={field} value={tags} onChange={(e) => setTags(e.target.value)} data-testid="edit-tags" aria-label="Tags" placeholder="tags, comma separated" />
        {item.kind === 'family' && <input className={field} value={breeds} onChange={(e) => setBreeds(e.target.value)} data-testid="edit-breeds" aria-label="Breeds" placeholder="breed ids" />}
        {(item.kind === 'shell' || item.kind === 'pattern') && (
          <Row>
            {COLOURS.map((h) => (
              <Swatch key={h} hex={h} label={h} size={60} selected={colour.toUpperCase() === h} onClick={() => setColour(h)} testId={`edit-colour-${h.slice(1)}`} />
            ))}
          </Row>
        )}
        {item.kind === 'pattern' && (['min', 'default', 'max'] as const).map(slider)}
        {item.qc && <p className="text-xl text-muted">QC: {JSON.stringify(item.qc)}</p>}
      </div>
      <div className="mt-6 flex gap-4">
        <Button variant="soft" disabled={c.busy} onClick={() => void save()} data-testid="edit-save">
          Save
        </Button>
        <Button disabled={c.busy || item.status === 'published' || item.status === 'rejected'} onClick={() => void c.publish(item)} data-testid="edit-publish">
          Publish v{item.version}
        </Button>
        <Button variant="ghost" disabled={c.busy || item.published_version === null} onClick={() => void c.unpublish(item)} data-testid="edit-unpublish">
          Unpublish
        </Button>
      </div>
    </div>
  );
}

export function LibraryScreen() {
  const c = useCurate();
  useEffect(() => {
    void c.loadItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [c.species]);
  return (
    <div className="no-scrollbar flex h-full flex-col overflow-y-auto px-12 pb-10 pt-24" data-testid="library">
      <Title sub="Edit names, tags, colours and coverage. Editing a published item starts its next version; publish it to ship it in the next release.">Library</Title>
      <Notice />
      <SpeciesChips />
      <div className="my-4">
        <Row>
          {KINDS.map((k) => (
            <Chip key={k.kind} selected={c.kind === k.kind} onClick={() => void c.loadItems(k.kind)} testId={`kind-${k.kind}`}>
              {k.title}
            </Chip>
          ))}
        </Row>
      </div>
      {c.selected && <Editor item={c.selected} />}
      <div className="mt-6 grid grid-cols-4 gap-4" data-testid="library-items">
        {c.items.map((it) => (
          <button
            key={it.id}
            className={cx('hit flex flex-col items-center gap-1 rounded-tile border-4 bg-card p-3 shadow-soft', c.selected?.id === it.id ? 'border-accent' : 'border-transparent')}
            onClick={() => c.set({ selected: it })}
            data-testid={`item-${it.id}`}
          >
            {it.thumbnail_url && <img src={it.thumbnail_url} alt="" className="h-24 w-24 object-contain" />}
            <span className="w-full truncate text-center font-display text-xl">{it.name}</span>
            <span className="text-lg text-muted">
              v{it.version} · {it.status}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Releases (Contract 1)
export function ReleasesScreen() {
  const c = useCurate();
  const role = useSession((s) => s.user?.role);
  useEffect(() => {
    void c.loadReleases();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="no-scrollbar flex h-full flex-col overflow-y-auto px-12 pb-10 pt-24" data-testid="releases">
      <Title sub="A release packs the latest published version of every family, part, accessory and pattern into a signed bundle. Kiosks load it and switch atomically.">Releases</Title>
      <Notice />
      <SpeciesChips />
      <Button className="my-6" disabled={c.busy || role !== 'admin'} onClick={() => void c.release()} data-testid="create-release">
        {role === 'admin' ? `Publish a ${c.species} release` : 'Publishing a release needs the admin role'}
      </Button>
      {c.releases.map((r) => (
        <div key={r.release_version} className="mb-3 flex items-center justify-between rounded-tile bg-card p-5 text-2xl shadow-soft" data-testid={`release-${r.release_version}`}>
          <span>
            <b>{r.release_version}</b> · {r.counts.families} families · {r.counts.region_deltas} parts · {r.counts.shell_parts} accessories · {r.counts.pattern_layers} patterns · by {r.created_by}
          </span>
          {r.url && (
            <a className="underline" href={r.url} download>
              Download
            </a>
          )}
        </div>
      ))}
    </div>
  );
}

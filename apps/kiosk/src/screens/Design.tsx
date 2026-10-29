// Design, Name and Order (BRIEF Sections 16 and 17): the customer assembles the figurine from the library release,
// paints it, names it and orders it. Everything renders from the release in the kiosk's own viewer; the export
// runs Stage F only on the kiosk queue. No screen here waits on, or even knows about, the GenAI host.
import { motion } from 'framer-motion';
import { QRCodeSVG } from 'qrcode.react';
import { memo, useCallback, useEffect, useState } from 'react';
import { EYE_PALETTE, PALETTE, PALETTE_ORDER, label } from '@petpop/core';
import { GlbFigure, LibraryFigure, REGIONS, type Composition, type LoadedLibrary, type PatternItem, type Region } from '@petpop/viewer';
import { Button, Chip, Keyboard, Row, Section, Swatch, TextDisplay, Tile, Title, cx } from '@petpop/ui';
import { MAX_LAYERS, MAX_STAMPS, SPOT_MM, useDesign, type ShapeRegion, type Tab } from '../store/design';
import { useSession } from '../store/session';

const FUR = PALETTE_ORDER.map((n) => ({ name: n, hex: PALETTE[n].hex }));
const EYES = Object.entries(EYE_PALETTE).map(([n, e]) => ({ name: n, hex: e.hex }));
const NOSES = [
  { name: 'black', hex: '#1E1B1A' },
  { name: 'liver', hex: '#6B3A2A' },
  { name: 'pink', hex: '#D9908C' },
  { name: 'grey', hex: '#6E6A68' },
];
const SHELL_COLOURS = ['#C8102E', '#1F4E9C', '#2E8B57', '#F2B705', '#7B3FA0', '#F4EFE6', '#1E1B1A'];
const TABS: { id: Tab; label: string }[] = [
  { id: 'shape', label: 'Shape' },
  { id: 'patterns', label: 'Markings' },
  { id: 'paint', label: 'Paint' },
  { id: 'extras', label: 'Extras' },
];
const REGION_LABEL: Record<ShapeRegion, string> = { family: 'Body', ears: 'Ears', tail: 'Tail', muzzle: 'Muzzle', head: 'Head', legs: 'Legs' };

// Memoised: a coverage slider re-renders only the preview and its own layer row, never every swatch on screen.
const Swatches = memo(function Swatches({ value, options, onPick, testId, size = 72 }: { value: string; options: { name: string; hex: string }[]; onPick: (hex: string) => void; testId: string; size?: number }) {
  return (
    <Row>
      {options.map((o) => (
        <Swatch key={o.name} hex={o.hex} label={label(o.name)} size={size} selected={o.hex.toUpperCase() === value.toUpperCase()} onClick={() => onPick(o.hex.toUpperCase())} testId={`${testId}-${o.name}`} />
      ))}
    </Row>
  );
});

function ShapePanel() {
  const d = useDesign();
  const lib = d.lib!;
  const c = d.composition!;
  const m = lib.manifest;
  const regions: ShapeRegion[] = ['family', ...REGIONS.filter((r) => m.region_deltas.some((p) => p.region === r))];
  const items =
    d.region === 'family'
      ? m.families.map((f) => ({ id: f.id, name: f.name, thumb: f.thumbnail, selected: c.family_id === f.id, pick: () => d.setFamily(f.id) }))
      : m.region_deltas
          .filter((p) => p.region === d.region)
          .map((p) => ({ id: p.id, name: p.name, thumb: p.thumbnail, selected: c.parts[d.region as Region] === p.id, pick: () => d.setPart(d.region as Region, p.id) }));
  return (
    <>
      <Row>
        {regions.map((r) => (
          <Chip key={r} selected={d.region === r} onClick={() => d.set({ region: r })} testId={`region-${r}`}>
            {REGION_LABEL[r]}
          </Chip>
        ))}
      </Row>
      <div className="mt-6 grid grid-cols-4 gap-4" data-testid="part-tiles">
        {items.map((it) => (
          <Tile key={it.id} label={it.name} selected={it.selected} onClick={it.pick} testId={`part-${it.id}`} className="h-[220px]">
            <img src={lib.url(it.thumb)} alt="" className="h-[150px] w-[150px] object-contain" draggable={false} />
          </Tile>
        ))}
      </div>
    </>
  );
}

const PatternTiles = memo(function PatternTiles({ lib, active }: { lib: LoadedLibrary; active: string }) {
  const toggle = useDesign((d) => d.toggleLayer);
  const on = new Set(active.split(','));
  return (
    <div className="grid grid-cols-5 gap-3" data-testid="pattern-tiles">
      {lib.manifest.pattern_layers.map((p) => (
        <Tile key={p.id} label={p.name} selected={on.has(p.id)} onClick={() => toggle(p.id)} testId={`pattern-${p.id}`} className="h-[170px]">
          <img src={lib.url(p.thumbnail)} alt="" className="h-[110px] w-[110px] object-contain" draggable={false} />
        </Tile>
      ))}
    </div>
  );
});

const LayerRow = memo(function LayerRow({ layer, pattern }: { layer: Composition['layers'][number]; pattern: PatternItem }) {
  const setCoverage = useDesign((d) => d.setCoverage);
  const setLayerColour = useDesign((d) => d.setLayerColour);
  const id = layer.pattern_id;
  const pick = useCallback((hex: string) => setLayerColour(id, hex), [id, setLayerColour]);
  return (
    <div className="mb-6 rounded-tile bg-card p-5 shadow-soft" data-testid={`layer-${id}`}>
      <div className="mb-3 flex items-center gap-6">
        <span className="w-40 font-display text-3xl">{pattern.name}</span>
        <input
          type="range"
          min={pattern.coverage.min}
          max={pattern.coverage.max}
          step={0.01}
          value={layer.coverage}
          onChange={(e) => setCoverage(id, Number(e.target.value))}
          className="h-14 flex-1 accent-[var(--accent)]"
          aria-label={`${pattern.name} coverage`}
          data-testid={`coverage-${id}`}
        />
      </div>
      <Swatches value={layer.colour} options={FUR} onPick={pick} testId={`layer-colour-${id}`} size={60} />
    </div>
  );
});

function PatternsPanel() {
  const lib = useDesign((d) => d.lib)!;
  const base = useDesign((d) => d.composition!.base_colour);
  const layers = useDesign((d) => d.composition!.layers);
  const setBase = useDesign((d) => d.setBase);
  const patterns = lib.manifest.pattern_layers;
  return (
    <>
      <Section title="Coat colour" testId="base-colour">
        <Swatches value={base} options={FUR} onPick={setBase} testId="base" />
      </Section>
      <Section title={`Markings (${layers.length}/${MAX_LAYERS})`}>
        <PatternTiles lib={lib} active={layers.map((l) => l.pattern_id).join(',')} />
      </Section>
      {layers.map((l) => (
        <LayerRow key={l.pattern_id} layer={l} pattern={patterns.find((p) => p.id === l.pattern_id)!} />
      ))}
    </>
  );
}

function PaintPanel() {
  const d = useDesign();
  const c = d.composition!;
  return (
    <>
      <Row>
        {(['s', 'm', 'l'] as const).map((s) => (
          <Chip key={s} selected={d.tool === 'spot' && d.spot === s} onClick={() => d.set({ tool: 'spot', spot: s, turning: false })} testId={`tool-spot-${s}`}>
            {{ s: 'Small spot', m: 'Spot', l: 'Patch' }[s]} · {SPOT_MM[s]} mm
          </Chip>
        ))}
        <Chip selected={d.tool === 'brush'} onClick={() => d.set({ tool: 'brush', turning: false })} testId="tool-brush">
          Brush
        </Chip>
      </Row>
      <div className="mt-6">
        <Swatches value={d.paintColour} options={FUR} onPick={(hex) => d.set({ paintColour: hex })} testId="paint" />
      </div>
      <div className="mt-6 flex flex-wrap items-center gap-4">
        <Chip selected={d.symmetry} onClick={() => d.set({ symmetry: !d.symmetry })} testId="symmetry">
          Mirror both sides
        </Chip>
        <Chip selected={d.turning} onClick={() => d.set({ turning: !d.turning })} testId="turn">
          ⟳ Turn figure
        </Chip>
        <Chip onClick={d.undo} testId="undo">
          ↶ Undo
        </Chip>
        <span className="text-2xl text-muted" data-testid="stamp-count">
          {c.stamps.length}/{MAX_STAMPS} dabs
        </span>
      </div>
      <p className="mt-4 text-2xl text-muted">Tap the figure to add a spot, or drag with the brush.</p>
    </>
  );
}

function ExtrasPanel() {
  const d = useDesign();
  const lib = d.lib!;
  const c = d.composition!;
  return (
    <>
      <Section title="Accessories">
        <div className="grid grid-cols-5 gap-3">
          {lib.manifest.shell_parts.map((s) => (
            <Tile key={s.id} label={s.name} selected={c.shells.some((x) => x.part_id === s.id)} onClick={() => d.toggleShell(s.id)} testId={`shell-${s.id}`} className="h-[170px]">
              <img src={lib.url(s.thumbnail)} alt="" className="h-[110px] w-[110px] object-contain" draggable={false} />
            </Tile>
          ))}
        </div>
        {c.shells.map((s) => (
          <div key={s.part_id} className="mt-4">
            <Swatches value={s.colour} options={SHELL_COLOURS.map((h, i) => ({ name: `c${i}`, hex: h }))} onPick={(hex) => d.setShellColour(s.part_id, hex)} testId={`shell-colour-${s.part_id}`} size={60} />
          </div>
        ))}
      </Section>
      <Section title="Eyes" testId="eyes">
        <Swatches value={c.eye_colour} options={EYES} onPick={d.setEyes} testId="eye" />
      </Section>
      <Section title="Nose" testId="nose">
        <Swatches value={c.nose_colour} options={NOSES} onPick={d.setNose} testId="nose" />
      </Section>
    </>
  );
}

/** Dev and test builds only: gate 7 bakes the on-screen atlas and compares it with the export's (print = screen). */
const onBake = (bake: () => Uint8Array) => {
  if (import.meta.env.DEV) (window as unknown as { __petpop: unknown }).__petpop = { bake, composition: () => useDesign.getState().composition };
};

export function DesignScreen() {
  const s = useSession();
  const d = useDesign();
  useEffect(() => {
    if (s.breed && (!d.composition || d.composition.breed_id !== s.breed.id || d.composition.species !== s.breed.species)) void d.begin(s.breed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.breed]);
  if (!s.breed) return null;
  if (d.libError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-8 px-16 text-center" data-testid="design-error">
        <Title sub="Please ask a member of staff.">{d.libError}</Title>
      </div>
    );
  }
  const ready = d.lib && d.composition;
  const painting = d.tab === 'paint' && !d.turning;
  return (
    <div className="flex h-full flex-col px-12 pb-10 pt-24" data-testid="design">
      <h1 className="mb-4 font-display text-6xl font-semibold">Design your {s.breed.label}</h1>
      <div className={cx('relative h-[860px] shrink-0 overflow-hidden rounded-tile bg-card shadow-soft', painting && 'ring-highlight')}>
        {ready ? (
          <LibraryFigure lib={d.lib!} composition={d.composition!} onPaint={painting ? d.paint : undefined} onBake={onBake} interactive />
        ) : (
          <div className="flex h-full items-center justify-center text-4xl text-muted" data-testid="design-loading">
            Getting the parts ready…
          </div>
        )}
      </div>
      <div className="mt-6 flex gap-3" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={d.tab === t.id}
            data-testid={`tab-${t.id}`}
            onClick={() => d.set({ tab: t.id })}
            className={cx('hit flex-1 rounded-tile py-5 font-display text-3xl font-semibold', d.tab === t.id ? 'bg-accent text-white shadow-soft' : 'bg-card text-ink')}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="no-scrollbar mt-6 flex-1 overflow-y-auto" data-testid={`panel-${d.tab}`}>
        {ready && d.tab === 'shape' && <ShapePanel />}
        {ready && d.tab === 'patterns' && <PatternsPanel />}
        {ready && d.tab === 'paint' && <PaintPanel />}
        {ready && d.tab === 'extras' && <ExtrasPanel />}
      </div>
      <div className="mt-6 flex items-center gap-6">
        {s.bespokeEnabled && (
          <Button variant="soft" onClick={() => s.go('bespoke')} data-testid="make-unique" disabled={!ready}>
            Make it unique
          </Button>
        )}
        <Button className="flex-1" onClick={() => s.go('name')} disabled={!ready} data-testid="to-name">
          Next: name it ›
        </Button>
      </div>
    </div>
  );
}

export function NameScreen() {
  const s = useSession();
  const d = useDesign();
  const name = d.composition?.pet_name ?? '';
  const [busy, setBusy] = useState(false);
  if (!d.composition) return null;
  const order = async () => {
    setBusy(true);
    try {
      await d.placeOrder(s.sessionId);
      if (!useDesign.getState().orderError) s.go('order');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex h-full flex-col px-16 pb-10 pt-24" data-testid="name">
      <Title sub="It goes on the base of your figurine.">What's their name?</Title>
      <TextDisplay value={name} placeholder="Biscuit" testId="pet-name" />
      {d.orderError && (
        <p className="mt-6 text-3xl font-semibold text-accent2" data-testid="order-error">
          {d.orderError}
        </p>
      )}
      <div className="mt-auto">
        <Keyboard value={name} onChange={d.setName} maxLength={24} onDone={() => void order()} doneLabel={busy ? 'Ordering…' : 'Order my figurine'} />
        <Button variant="ghost" className="mt-6" onClick={() => s.go('design')} data-testid="name-back">
          ‹ Back to design
        </Button>
      </div>
    </div>
  );
}

export function OrderScreen() {
  const s = useSession();
  const d = useDesign();
  const o = d.order;
  const refresh = useCallback(() => void useDesign.getState().refreshOrder(), []);
  useEffect(() => {
    if (!o || o.status === 'ready' || o.status === 'failed') return;
    const t = setInterval(refresh, 1000);
    return () => clearInterval(t);
  }, [o, refresh]);
  if (!o) return null;
  const ready = o.status === 'ready';
  return (
    <div className="flex h-full flex-col items-center px-16 pb-12 pt-24 text-center" data-testid="order">
      <Title sub={ready ? 'Show this ticket at the counter. Scan the code to keep a copy on your phone.' : (o.export?.message ?? 'Preparing your order')}>
        {ready ? `${o.pet_name || 'Your figurine'} is on the way!` : 'Placing your order…'}
      </Title>
      <div className="relative h-[820px] w-full overflow-hidden rounded-tile bg-card shadow-soft">
        {ready && o.previews.glb ? (
          <GlbFigure url={o.previews.glb} fallbackImage={o.previews.thumbnail} spin testId="order-figure" />
        ) : d.lib && d.composition ? (
          <LibraryFigure lib={d.lib} composition={d.composition} spin interactive={false} testId="order-preview" />
        ) : null}
      </div>
      {!ready && o.status !== 'failed' && (
        <div className="mt-8 h-6 w-full overflow-hidden rounded-full bg-line" data-testid="order-progress">
          <motion.div className="h-full bg-accent" animate={{ width: `${o.export?.pct ?? 5}%` }} />
        </div>
      )}
      {o.status === 'failed' && (
        <p className="mt-8 text-3xl font-semibold text-accent2" data-testid="order-failed">
          Something went wrong preparing the print. A member of staff can reprint ticket {o.ticket}.
        </p>
      )}
      <div className="mt-10 flex w-full items-center justify-between gap-10">
        <div className="rounded-tile bg-accent px-12 py-8 font-display text-5xl text-white" data-testid="order-ticket">
          Ticket <b>{o.ticket}</b>
        </div>
        {ready && o.result_url && (
          <div className="rounded-tile bg-white p-4" data-testid="order-qr">
            <QRCodeSVG value={o.result_url} size={200} level="M" />
          </div>
        )}
      </div>
      <Button className="mt-auto w-full" onClick={s.reset} data-testid="order-done">
        Done
      </Button>
    </div>
  );
}

/** "Make it unique" (KIOSK_BESPOKE): the composition goes to the studio as a bespoke job's starting spec, and the
 *  customer gets a ticket and a "we'll message you" promise, never a Generating screen. */
export function BespokeScreen() {
  const s = useSession();
  const [contact, setContact] = useState('');
  const [busy, setBusy] = useState(false);
  const send = async () => {
    setBusy(true);
    try {
      await s.requestBespoke(contact);
    } finally {
      setBusy(false);
    }
  };
  if (s.bespoke) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-10 px-16 text-center" data-testid="bespoke-accepted">
        <div className="text-9xl">💌</div>
        <Title sub={s.bespoke.message}>We're on it!</Title>
        <div className="rounded-tile bg-accent px-12 py-8 font-display text-5xl text-white" data-testid="bespoke-ticket">
          Ticket <b>{s.bespoke.ticket}</b>
        </div>
        <Button onClick={s.reset} data-testid="bespoke-done">
          Done
        </Button>
      </div>
    );
  }
  return (
    <div className="flex h-full flex-col px-16 pb-10 pt-24" data-testid="bespoke">
      <Title sub="Our studio sculpts a one-off figure from your design. It takes a while, so we'll message you when it's ready.">Make it unique</Title>
      <p className="mb-4 text-3xl text-muted">Phone or email (optional; staff can also look it up by ticket)</p>
      <TextDisplay value={contact} placeholder="07700 900123" testId="bespoke-contact" />
      {s.error && (
        <p className="mt-6 text-3xl font-semibold text-accent2" data-testid="bespoke-error">
          {s.error}
        </p>
      )}
      <div className="mt-auto">
        <Keyboard value={contact} onChange={setContact} maxLength={80} onDone={() => void send()} doneLabel={busy ? 'Sending…' : 'Send'} compact capitalize={false} contact />
        <Button variant="ghost" className="mt-6" onClick={() => s.go('design')} data-testid="bespoke-back">
          ‹ Back to design
        </Button>
      </div>
    </div>
  );
}

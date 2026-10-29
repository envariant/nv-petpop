// Screen 4: Build. One scrolling column of visual selectors (BRIEF Section 4 table) with the live 3D
// preview on the right. Every tap is a user override and is protected from the brief parser.
import { motion } from 'framer-motion';
import { useState } from 'react';
import tilesIndex from '@assets/tiles/index.json';
import type { PetSpec } from '@petpop/core';
import { PreviewFigure } from '@petpop/viewer';
import { Chip, Row, Section, Swatch, Tile, cx } from '@petpop/ui';
import { EYE_PALETTE, PALETTE, PALETTE_ORDER, assetUrl, getPath, label, nearestPalette } from '@petpop/core';
import { useSession } from '../store/session';
import { NavBar } from './Nav';

type Species = 'dog' | 'cat';
const tiles = tilesIndex as Record<Species, Record<string, string[]>>;
const ACC = ['collar', 'bandana', 'bow', 'hat', 'glasses'] as const;
const ACC_COLOURS = ['#DD3333', '#3366CC', '#2E9E5B', '#F2C230', '#E04A8A', '#1E1B1A'];
const ACC_ICON: Record<string, string> = { collar: '📿', bandana: '🧣', bow: '🎀', hat: '🎩', glasses: '👓' };
const MARK_LABEL: Record<string, string> = { white_blaze: 'Blaze', white_socks: 'Socks', white_chest: 'Chest', dark_mask: 'Mask', points: 'Points' };

function TileImg({ species, slot, value }: { species: Species; slot: string; value: string }) {
  return <img src={assetUrl(`assets/tiles/${species}/${slot}__${value}.png`)} alt="" className="h-28 w-28 object-contain" draggable={false} />;
}

export function useHighlight() {
  const highlights = useSession((s) => s.highlights);
  return (path: string) => highlights.some((h) => h === path || h.startsWith(`${path}.`));
}

function TileRow({ slot, values, cols }: { slot: string; values: string[]; cols?: number }) {
  const spec = useSession((s) => s.spec)!;
  const tap = useSession((s) => s.tap);
  const hl = useHighlight();
  const species = spec.species as Species;
  const current = getPath(spec, slot);
  return (
    <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${cols ?? values.length}, minmax(0, 1fr))` }}>
      {values.map((v) => (
        <Tile key={v} label={label(v === 'semi_erect' ? 'semi-erect' : v === 'long_thin' ? 'long thin' : v === 'saddle_with_white_chest' ? 'saddle' : v)} selected={current === v} highlight={current === v && hl(slot)} onClick={() => tap(slot, v)} testId={`tile-${slot}-${v}`}>
          <TileImg species={species} slot={slot} value={v} />
        </Tile>
      ))}
    </div>
  );
}

function ColourWheel({ onPick }: { onPick: (hex: string) => void }) {
  const pick = (e: React.PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    const hue = ((Math.atan2(y, x) * 180) / Math.PI + 450) % 360;
    const sat = Math.min(1, Math.hypot(x, y) * 2);
    const l = 0.62 - sat * 0.2;
    const a = sat * Math.min(l, 1 - l);
    const f = (n: number) => {
      const k = (n + hue / 30) % 12;
      return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))));
    };
    onPick(`#${[f(0), f(8), f(4)].map((v) => v.toString(16).padStart(2, '0')).join('')}`.toUpperCase());
  };
  return (
    <div
      data-testid="colour-wheel"
      onPointerDown={pick}
      className="h-72 w-72 rounded-full shadow-soft"
      style={{ background: 'radial-gradient(circle, #d8cfc6 0%, transparent 70%), conic-gradient(from 90deg, red, yellow, lime, cyan, blue, magenta, red)' }}
    />
  );
}

function Palette({ slot, optional }: { slot: 'colour.base' | 'colour.secondary'; optional?: boolean }) {
  const spec = useSession((s) => s.spec)!;
  const tap = useSession((s) => s.tap);
  const hl = useHighlight();
  const [wheel, setWheel] = useState(false);
  const current = getPath(spec, slot) as { name: string; hex: string } | undefined;
  const isCustom = current && !PALETTE_ORDER.some((n) => PALETTE[n].hex.toUpperCase() === current.hex.toUpperCase());
  return (
    <div>
      <div className="flex flex-wrap gap-4">
        {optional && (
          <button data-testid={`swatch-${slot}-none`} aria-pressed={!current} onClick={() => tap(slot, undefined)} className={cx('hit h-[84px] w-[84px] rounded-full border-4 border-dashed font-display text-xl', !current ? 'border-accent' : 'border-line')}>
            None
          </button>
        )}
        {PALETTE_ORDER.map((n) => (
          <Swatch key={n} hex={PALETTE[n].hex} label={label(n)} testId={`swatch-${slot}-${n}`} selected={current?.hex.toUpperCase() === PALETTE[n].hex.toUpperCase()} highlight={current?.name === n && hl(slot)} onClick={() => tap(slot, { name: n, hex: PALETTE[n].hex })} />
        ))}
        <button data-testid={`swatch-${slot}-custom`} aria-label="Custom colour" aria-pressed={!!isCustom} onClick={() => setWheel(!wheel)} className={cx('hit h-[84px] w-[84px] rounded-full border-4 shadow-soft', isCustom ? 'border-accent' : 'border-card')} style={{ background: isCustom ? current!.hex : 'conic-gradient(red, yellow, lime, cyan, blue, magenta, red)' }} />
      </div>
      {wheel && (
        <div className="mt-6 flex items-center gap-8">
          <ColourWheel onPick={(hex) => tap(slot, { name: nearestPalette(hex), hex })} />
          <Chip onClick={() => setWheel(false)}>Done</Chip>
        </div>
      )}
    </div>
  );
}

function Markings() {
  const spec = useSession((s) => s.spec)!;
  const tap = useSession((s) => s.tap);
  const hl = useHighlight();
  const marks = spec.colour.markings ?? [];
  return (
    <div className="mt-5 flex flex-wrap gap-3">
      {Object.keys(MARK_LABEL).map((m) => (
        <Chip key={m} testId={`chip-marking-${m}`} selected={marks.includes(m as never)} highlight={marks.includes(m as never) && hl('colour.markings')} onClick={() => tap('colour.markings', marks.includes(m as never) ? marks.filter((x) => x !== m) : [...marks, m])}>
          {MARK_LABEL[m]}
        </Chip>
      ))}
    </div>
  );
}

function Eyes() {
  const spec = useSession((s) => s.spec)!;
  const tap = useSession((s) => s.tap);
  const hl = useHighlight();
  const eyes = spec.eyes;
  const names = Object.keys(EYE_PALETTE);
  return (
    <div>
      <div className="flex flex-wrap items-center gap-4">
        {names.map((n) => (
          <Swatch key={n} hex={EYE_PALETTE[n].hex} label={`${label(n)} eyes`} testId={`swatch-eyes-${n}`} selected={eyes.colour === n} highlight={eyes.colour === n && hl('eyes')} onClick={() => tap('eyes', { ...eyes, colour: n, hex: EYE_PALETTE[n].hex })} />
        ))}
        <Chip testId="toggle-heterochromia" selected={eyes.heterochromia} onClick={() => tap('eyes', { ...eyes, heterochromia: !eyes.heterochromia, second_colour: eyes.second_colour ?? 'blue', second_hex: eyes.second_hex ?? EYE_PALETTE.blue.hex })}>
          Odd eyes
        </Chip>
      </div>
      {eyes.heterochromia && (
        <div className="mt-4 flex gap-4">
          <span className="self-center text-2xl text-muted">Second eye</span>
          {names.map((n) => (
            <Swatch key={n} size={64} hex={EYE_PALETTE[n].hex} label={`Second eye ${label(n)}`} selected={eyes.second_colour === n} onClick={() => tap('eyes', { ...eyes, second_colour: n, second_hex: EYE_PALETTE[n].hex })} />
          ))}
        </div>
      )}
    </div>
  );
}

function Accessories() {
  const spec = useSession((s) => s.spec)!;
  const tap = useSession((s) => s.tap);
  const hl = useHighlight();
  const list = spec.accessories ?? [];
  const toggle = (t: (typeof ACC)[number]) => {
    const has = list.some((a) => a.type === t);
    tap('accessories', has ? list.filter((a) => a.type !== t) : [...list, { type: t, colour_hex: ACC_COLOURS[0], colour_name: nearestPalette(ACC_COLOURS[0]), ...(t === 'collar' ? { tag: true } : {}) }]);
  };
  const recolour = (t: string, hex: string) => tap('accessories', list.map((a) => (a.type === t ? { ...a, colour_hex: hex, colour_name: nearestPalette(hex) } : a)));
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-3">
        {ACC.map((t) => (
          <Chip key={t} testId={`chip-acc-${t}`} selected={list.some((a) => a.type === t)} highlight={list.some((a) => a.type === t) && hl('accessories')} onClick={() => toggle(t)}>
            {ACC_ICON[t]} {label(t)}
          </Chip>
        ))}
      </div>
      {list.map((a) => (
        <div key={a.type} className="flex items-center gap-3">
          <span className="w-40 font-display text-2xl">{label(a.type)}</span>
          {ACC_COLOURS.map((hex) => (
            <Swatch key={hex} size={60} hex={hex} label={`${a.type} ${hex}`} selected={a.colour_hex === hex} onClick={() => recolour(a.type, hex)} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function BuildScreen() {
  const spec = useSession((s) => s.spec);
  const tap = useSession((s) => s.tap);
  const go = useSession((s) => s.go);
  const hl = useHighlight();
  if (!spec) return null;
  const species = spec.species as Species;
  const pick = (slot: string, values: string[]) => (
    <Row>
      {values.map((v) => (
        <Chip key={v} testId={`chip-${slot}-${v}`} selected={getPath(spec, slot) === v} highlight={getPath(spec, slot) === v && hl(slot)} onClick={() => tap(slot, v)}>
          {label(v)}
        </Chip>
      ))}
    </Row>
  );
  return (
    <div className="flex h-full flex-col">
      <div className="flex min-h-0 flex-1">
        <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto px-12 pb-10 pt-16" data-testid="build-scroll">
          <h1 className="font-display text-6xl font-semibold">Build {spec.breed.id === 'mixed' ? 'your pet' : `your ${spec.breed.label}`}</h1>
          <p className="mb-10 mt-2 text-2xl text-muted">We filled in the breed look. Tap anything to change it.</p>
          <Section title="Body size and build" testId="sel-body">
            <TileRow slot="body.size" values={tiles[species]['body.size']} />
            <div className="mt-4 flex flex-col gap-3">
              {pick('body.build', ['slim', 'standard', 'stocky'])}
              {pick('body.leg_length', ['short', 'medium', 'long'])}
            </div>
          </Section>
          <Section title="Coat length" testId="sel-coat">
            <TileRow slot="coat.length" values={tiles[species]['coat.length']} />
          </Section>
          <Section title="Main colour" testId="sel-base">
            <Palette slot="colour.base" />
          </Section>
          <Section title="Second colour" testId="sel-secondary">
            <Palette slot="colour.secondary" optional />
          </Section>
          <Section title="Pattern and markings" testId="sel-pattern">
            <TileRow slot="colour.pattern" values={tiles[species]['colour.pattern']} cols={4} />
            <Markings />
          </Section>
          <Section title="Ears" testId="sel-ears">
            <TileRow slot="ears.shape" values={tiles[species]['ears.shape']} cols={3} />
          </Section>
          <Section title="Tail" testId="sel-tail">
            <TileRow slot="tail.type" values={tiles[species]['tail.type']} cols={3} />
          </Section>
          <Section title="Muzzle" testId="sel-muzzle">
            <TileRow slot="head.muzzle_length" values={tiles[species]['head.muzzle_length']} />
          </Section>
          <Section title="Eyes" testId="sel-eyes">
            <Eyes />
          </Section>
          <Section title="Accessories" testId="sel-accessories">
            <Accessories />
          </Section>
        </div>
        <motion.aside className="relative w-[400px] shrink-0 border-l-4 border-line bg-card/60" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <div className="absolute inset-0">
            <PreviewFigure spec={spec as PetSpec} />
          </div>
          <span className="absolute left-6 top-6 rounded-full bg-ink/80 px-4 py-1 text-xl font-semibold uppercase tracking-wider text-paper">Preview</span>
        </motion.aside>
      </div>
      <NavBar back={() => go('breed')} next={() => go('brief')} nextLabel="Next" />
    </div>
  );
}

// Screens 1-3: Attract loop, Species, Breed.
import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useMemo, useState } from 'react';
import fixtureIndex from '@fixtures/pets/index.json';
import { KioskApi as Api } from '@petpop/core';
import type { Breed, Species } from '@petpop/core';
import { GlbFigure } from '@petpop/viewer';
import { Keyboard, TextDisplay } from '@petpop/ui';
import { Tile, Title } from '@petpop/ui';
import { useSession } from '../store/session';

const SHOWCASE = fixtureIndex.pets.slice(0, 6);

export function AttractScreen() {
  const start = useSession((s) => s.start);
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % SHOWCASE.length), 6000);
    return () => clearInterval(t);
  }, []);
  const pet = SHOWCASE[i];
  return (
    <button data-testid="attract" onClick={() => void start()} className="relative flex h-full w-full flex-col items-center justify-between px-16 pb-24 pt-28 text-left">
      <div className="text-center">
        <div className="font-display text-9xl font-semibold tracking-tight">
          Pet<span className="text-accent">Pop</span>
        </div>
        <p className="mt-6 text-4xl text-muted">Your pet, as a tiny collectible figure</p>
      </div>
      <div className="relative h-[1000px] w-full">
        <AnimatePresence mode="wait">
          <motion.div key={pet.id} className="absolute inset-0" initial={{ opacity: 0, scale: 0.94 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.94 }} transition={{ duration: 0.6 }}>
            <GlbFigure url={`/fixtures/${pet.id}/figure.glb`} fallbackImage={`/fixtures/${pet.id}/thumbnail.png`} spin />
          </motion.div>
        </AnimatePresence>
      </div>
      <p className="text-3xl text-muted" data-testid="attract-caption" aria-live="polite">
        {pet.pet_name} the {pet.breed.replace(/_/g, ' ')}
      </p>
      <div className="pulse rounded-full bg-accent px-16 py-8 font-display text-6xl font-semibold text-white shadow-soft">Tap to make yours</div>
    </button>
  );
}

export function SpeciesScreen() {
  const choose = useSession((s) => s.chooseSpecies);
  const tile = (sp: Species, emoji: string, label: string, colour: string) => (
    <motion.button
      whileTap={{ scale: 0.96 }}
      data-testid={`species-${sp}`}
      onClick={() => choose(sp)}
      className="hit flex flex-1 flex-col items-center justify-center rounded-tile shadow-soft"
      style={{ background: colour }}
    >
      <span className="text-[260px] leading-none" aria-hidden>
        {emoji}
      </span>
      <span className="mt-8 font-display text-7xl font-semibold text-white">{label}</span>
    </motion.button>
  );
  return (
    <div className="flex h-full flex-col px-16 pb-16 pt-20">
      <Title sub="Pick one to start.">Dog or cat?</Title>
      <div className="flex flex-1 flex-col gap-10">
        {tile('dog', '🐶', 'Dog', '#FF8A3D')}
        {tile('cat', '🐱', 'Cat', '#7A5CFF')}
      </div>
    </div>
  );
}

export function BreedScreen() {
  const species = useSession((s) => s.species) ?? 'dog';
  const choose = useSession((s) => s.chooseBreed);
  const [q, setQ] = useState('');
  const [items, setItems] = useState<Breed[]>([]);
  const [typing, setTyping] = useState(false);
  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      Api.breeds(species, q).then((r) => live && setItems(r.items)).catch(() => undefined);
    }, 120);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [species, q]);
  const silhouette = useMemo(() => (species === 'dog' ? '🐕' : '🐈'), [species]);
  return (
    <div className="flex h-full flex-col px-16 pb-10 pt-20">
      <Title sub="Search or tap. Not sure? Pick Mixed.">Which breed?</Title>
      <button className="mb-6 text-left" data-testid="breed-search" onClick={() => setTyping(true)}>
        <TextDisplay value={q} placeholder="🔍  Search breeds" />
      </button>
      <div className="no-scrollbar grid flex-1 auto-rows-[220px] grid-cols-3 gap-5 overflow-y-auto pb-6" data-testid="breed-grid">
        {items.map((b) => (
          <Tile key={b.id} label={b.label} testId={`breed-${b.id}`} onClick={() => choose(b)} className={b.id === 'mixed' ? 'border-dashed !border-line' : ''}>
            <span className="text-7xl" aria-hidden>
              {b.id === 'mixed' ? '❓' : silhouette}
            </span>
          </Tile>
        ))}
        {items.length === 0 && <p className="col-span-3 text-3xl text-muted">No breed matches “{q}”. Try Mixed / not sure.</p>}
      </div>
      {typing && <Keyboard value={q} onChange={setQ} maxLength={30} onDone={() => setTyping(false)} compact capitalize={false} />}
    </div>
  );
}

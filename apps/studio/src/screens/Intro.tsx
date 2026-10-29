// Generate workspace, steps 1-2: Species and Breed.
import { motion } from 'framer-motion';
import { useEffect, useMemo, useState } from 'react';
import { StudioApi as Api } from '@petpop/core';
import type { Breed, Species } from '@petpop/core';
import { Keyboard, TextDisplay } from '@petpop/ui';
import { Tile, Title } from '@petpop/ui';
import { useSession } from '../store/session';

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
      <Title sub="Pick the species for this figurine.">Dog or cat?</Title>
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

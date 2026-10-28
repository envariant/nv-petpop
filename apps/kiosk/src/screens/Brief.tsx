// Screens 5 and 6: Brief (free text parsed into the same PetSpec) and Name & generate.
import { useState } from 'react';
import { Api } from '../api/client';
import { Keyboard, TextDisplay } from '../components/Keyboard';
import { Button, Chip, Title } from '../components/ui';
import { label } from '../lib/spec';
import { useSession } from '../store/session';
import { NavBar } from './Nav';

const EXAMPLES = ['loves snacks', 'one ear that flops', 'chunky', 'fluffy tail', 'white socks', 'blue eyes', 'red collar', 'cheeky'];
const FIELD_LABEL: Record<string, string> = {
  'body.size': 'Size', 'body.build': 'Build', 'body.leg_length': 'Legs', 'coat.length': 'Coat length', 'coat.texture': 'Coat', 'colour.base': 'Main colour',
  'colour.secondary': 'Second colour', 'colour.pattern': 'Pattern', 'colour.markings': 'Markings', 'ears.shape': 'Ears', 'ears.size': 'Ear size', 'tail.type': 'Tail',
  'tail.length': 'Tail length', 'head.muzzle_length': 'Muzzle', eyes: 'Eyes', 'nose.colour': 'Nose', accessories: 'Accessories', personality: 'Personality',
  'breed.id': 'Breed', 'overrides.ears.asymmetry': 'Floppy ear',
};

export function changedLabels(paths: string[]): string[] {
  const out = new Set<string>();
  for (const p of paths) {
    const key = Object.keys(FIELD_LABEL).find((k) => p === k || p.startsWith(`${k}.`));
    if (key) out.add(FIELD_LABEL[key]);
  }
  return [...out];
}

export function BriefScreen() {
  const s = useSession();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const name = (s.spec as { pet_name?: string } | null)?.pet_name || (s.species === 'cat' ? 'your cat' : 'your dog');
  const read = async () => {
    if (!s.spec || !s.species) return;
    setBusy(true);
    setFailed(false);
    try {
      s.applyParse(await Api.parse(s.species, s.spec, s.briefText, s.tapped));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };
  const changed = changedLabels(s.highlights);
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 px-16 pt-20">
        <Title sub="Anything that makes them them. We'll match it to the swatches.">Tell us about {name}</Title>
        <TextDisplay value={s.briefText} placeholder="e.g. a chunky corgi with one floppy ear who loves snacks" testId="brief-text" lines={3} />
        <div className="my-6 flex flex-wrap gap-3">
          {EXAMPLES.map((e) => (
            <Chip key={e} testId={`example-${e}`} onClick={() => s.setBrief((s.briefText ? `${s.briefText.replace(/[ ,]+$/, '')}, ` : '') + e)}>
              + {e}
            </Chip>
          ))}
        </div>
        <div className="mb-6 flex items-center gap-6">
          <Button onClick={() => void read()} disabled={busy || !s.briefText.trim()} data-testid="brief-apply" variant="soft">
            {busy ? 'Reading…' : 'Use my words'}
          </Button>
          <div className="text-2xl" data-testid="brief-result" aria-live="polite">
            {failed && <span className="text-muted">We'll use your words for flavour only.</span>}
            {s.parse && s.parse.flavour_only && <span className="text-muted">We'll use your words for flavour only.</span>}
            {s.parse && !s.parse.flavour_only && changed.length > 0 && (
              <span>
                Updated: <b>{changed.join(', ')}</b>
              </span>
            )}
            {s.parse && s.parse.blocked && <span className="block text-muted">Some words were skipped.</span>}
          </div>
        </div>
        {s.parse && changed.length > 0 && (
          <button className="mb-4 text-2xl text-accent underline" data-testid="brief-review" onClick={() => s.go('build')}>
            See the changes on the swatches
          </button>
        )}
      </div>
      <div className="px-12 pb-4">
        <Keyboard value={s.briefText} onChange={s.setBrief} maxLength={500} />
      </div>
      <NavBar back={() => s.go('build')} next={() => s.go('name')} nextLabel={s.briefText.trim() && !s.parse ? 'Skip' : 'Next'} />
    </div>
  );
}

export function NameScreen() {
  const s = useSession();
  const spec = s.spec;
  if (!spec) return null;
  const petName = (spec as { pet_name?: string }).pet_name ?? '';
  const facts: [string, string][] = [
    ['Breed', spec.breed.label],
    ['Colour', `${label(spec.colour.base.name)}${spec.colour.secondary ? ` & ${label(spec.colour.secondary.name)}` : ''}, ${label(spec.colour.pattern)}`],
    ['Ears / tail', `${label(spec.ears.shape)} ears, ${label(spec.tail.type)} tail`],
    ['Eyes', label(spec.eyes.colour)],
    ['Accessories', spec.accessories.length ? spec.accessories.map((a) => label(a.type)).join(', ') : 'None'],
  ];
  if (spec.personality?.length) facts.push(['Personality', spec.personality.join(', ')]);
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 px-16 pt-20">
        <Title sub="This name goes on the figurine's page.">What's their name?</Title>
        <TextDisplay value={petName} placeholder="Pet name" testId="name-text" />
        <div className="mt-8 rounded-tile bg-card p-10 shadow-soft" data-testid="summary-card">
          <h2 className="mb-6 font-display text-5xl font-semibold">{petName || 'Your pet'}</h2>
          <dl className="grid grid-cols-[240px_1fr] gap-y-4 text-3xl">
            {facts.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted">{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </div>
        {s.error && (
          <p className="mt-6 text-3xl font-semibold text-accent2" data-testid="generate-error">
            {s.error}
          </p>
        )}
      </div>
      <div className="px-12 pb-4">
        <Keyboard value={petName} onChange={s.setName} maxLength={24} />
      </div>
      <NavBar
        back={() => s.go('brief')}
        next={() => void s.generate()}
        nextLabel="Generate"
        nextDisabled={!petName.trim() || s.generationsLeft <= 0}
        extra={<span className="text-2xl text-muted" data-testid="generations-left">{s.generationsLeft} of 3 left</span>}
      />
    </div>
  );
}

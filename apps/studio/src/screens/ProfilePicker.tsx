// "Run on": the GenAI profile a new job or batch uses (decision 113). Lists what the server offers
// (PETPOP_STUDIO_PROFILES, led by the default GENAI_PROFILE); a profile missing a key is shown but not selectable.
import { useEffect } from 'react';
import { Chip, Row, Section } from '@petpop/ui';
import { useProfiles } from '../store/profiles';

const TITLES: Record<string, string> = {
  mock: 'Mock (no GenAI)',
  'tripo-manual': 'Tripo, by hand',
  tripo: 'Tripo API',
  'mac-m4pro': 'Mac GenAI host',
  'nvidia-24gb': 'NVIDIA GenAI host',
};

export function ProfilePicker() {
  const { offered, choice, load, choose } = useProfiles();
  useEffect(() => {
    if (!offered) void load();
  }, [offered, load]);
  if (!offered) return null;
  const current = offered.items.find((p) => p.name === choice);
  return (
    <Section title="Run on" testId="profile-picker">
      <Row>
        {offered.items.map((p) => (
          <Chip key={p.name} selected={choice === p.name} onClick={() => p.ready && choose(p.name)} testId={`profile-${p.name}`}>
            {TITLES[p.name] ?? p.name}
            {p.name === offered.default ? ' (default)' : ''}
            {!p.ready ? ` · needs ${p.missing.join(', ')}` : ''}
          </Chip>
        ))}
      </Row>
      {current && (
        <p className="mt-3 text-2xl text-muted" data-testid="profile-description">
          {current.description}
        </p>
      )}
    </Section>
  );
}

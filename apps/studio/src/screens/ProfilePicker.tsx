// "Run on", "Pipeline" and "Quality" (decisions 113 to 115): the GenAI profile a new job or batch uses (what the
// server offers: PETPOP_STUDIO_PROFILES, led by the default GENAI_PROFILE), the profile's pipeline and its quality
// switches, with the API credits a figurine costs where the provider prices by credit. A profile missing a key is
// listed but not selectable.
import { useEffect } from 'react';
import { Chip, Row, Section } from '@petpop/ui';
import { current, estimate, useProfiles } from '../store/profiles';

const TITLES: Record<string, string> = {
  mock: 'Mock (no GenAI)',
  'tripo-manual': 'Tripo, by hand',
  tripo: 'Tripo API',
  'mac-m4pro': 'Mac GenAI host',
  'nvidia-24gb': 'NVIDIA GenAI host',
};

export function ProfilePicker() {
  const s = useProfiles();
  useEffect(() => {
    if (!s.offered) void s.load();
  }, [s.offered, s.load]);
  if (!s.offered) return null;
  const p = current(s);
  const credits = estimate(s);
  return (
    <div data-testid="profile-picker">
      <Section title="Run on">
        <Row>
          {s.offered.items.map((x) => (
            <Chip key={x.name} selected={s.choice === x.name} onClick={() => x.ready && s.choose(x.name)} testId={`profile-${x.name}`}>
              {TITLES[x.name] ?? x.name}
              {x.name === s.offered!.default ? ' (default)' : ''}
              {!x.ready ? ` · needs ${x.missing.join(', ')}` : ''}
            </Chip>
          ))}
        </Row>
        {p && (
          <p className="mt-3 text-2xl text-muted" data-testid="profile-description">
            {p.description}
          </p>
        )}
      </Section>
      {p && p.pipelines.length > 0 && (
        <Section title="Pipeline" testId="pipeline-picker">
          <Row>
            {p.pipelines.map((x) => (
              <Chip key={x.name} selected={s.pipeline === x.name} onClick={() => s.choosePipeline(x.name)} testId={`pipeline-${x.name}`}>
                {x.title}
                {x.credits != null ? ` · ${x.credits} cr` : ''}
              </Chip>
            ))}
          </Row>
          {p.pipelines.find((x) => x.name === s.pipeline)?.note && (
            <p className="mt-3 text-2xl text-muted" data-testid="pipeline-note">
              {p.pipelines.find((x) => x.name === s.pipeline)!.note}
            </p>
          )}
        </Section>
      )}
      {p && p.options.length > 0 && (
        <Section title="Quality" testId="option-picker">
          <Row>
            {p.options.map((o) => (
              <Chip key={o.name} selected={!!s.options[o.name]} onClick={() => s.toggle(o.name)} testId={`option-${o.name}`}>
                {o.title}
                {o.credits ? ` +${o.credits} cr` : ''}
              </Chip>
            ))}
          </Row>
          <ul className="mt-3 text-xl text-muted">
            {p.options.map((o) => (o.note ? <li key={o.name}>{`${o.title}: ${o.note}`}</li> : null))}
          </ul>
        </Section>
      )}
      {credits != null && (
        <p className="mb-6 text-2xl" data-testid="credit-estimate">
          About <b>{credits}</b> API credits (${(credits / 100).toFixed(2)}) per figurine
          {p?.name.endsWith('-manual') ? '; by hand you spend Tripo Studio credits instead' : ''}
        </p>
      )}
    </div>
  );
}

// Manual mode inbox (decision 111): each card is a request the pipeline would have sent the GenAI API, shown so the
// operator can run it in the vendor's own app (Tripo Studio): prompt and settings to copy, input files to download,
// step-by-step instructions, and an upload for the output, which resumes the job.
import { useEffect, useRef, useState } from 'react';
import type { ManualTask } from '@petpop/core';
import { Button, Chip, Row, Section, Title, cx } from '@petpop/ui';
import { useManual, type ManualFilter } from '../store/manual';

function Copy({ text, testId }: { text: string; testId: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      variant="soft"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        });
      }}
      data-testid={testId}
    >
      {done ? 'Copied' : 'Copy'}
    </Button>
  );
}

function TextBlock({ label, text, testId }: { label: string; text: string; testId: string }) {
  return (
    <Section title={label}>
      <div className="flex items-start gap-4">
        <p className="flex-1 select-all rounded-tile bg-card p-5 text-2xl leading-snug shadow-soft" data-testid={testId}>
          {text}
        </p>
        <Copy text={text} testId={`${testId}-copy`} />
      </div>
    </Section>
  );
}

function TaskCard({ t, selected, onClick }: { t: ManualTask; selected: boolean; onClick: () => void }) {
  return (
    <button
      className={cx('hit mb-3 flex w-full items-center justify-between rounded-tile p-5 text-left text-2xl shadow-soft', selected ? 'bg-accent text-white' : 'bg-card')}
      onClick={onClick}
      data-testid={`manual-task-${t.task_id}`}
    >
      <span>
        <b>{t.title}</b> · {t.pet_name ?? t.breed_label ?? t.species} · job {t.job_id}
      </span>
      <span className={cx('rounded-full px-4 py-1 font-display text-xl', t.status === 'pending' ? 'bg-accent2 text-white' : 'bg-line text-ink')}>{t.status}</span>
    </button>
  );
}

function SlotUpload({ t, slot }: { t: ManualTask; slot: string }) {
  const { busy, submit } = useManual();
  const [file, setFile] = useState<File | null>(null);
  const done = (t.filled ?? []).includes(slot);
  return (
    <div className="mb-3 flex items-center gap-4 rounded-tile bg-card p-4 text-2xl shadow-soft" data-testid={`manual-slot-${slot}`}>
      <b className="w-28 capitalize">{slot}</b>
      {done ? (
        <span className="flex-1 text-accent" data-testid={`manual-slot-${slot}-done`}>
          received ✓
        </span>
      ) : (
        <>
          <input type="file" accept={t.expects.accept.join(',')} className="flex-1" onChange={(e) => setFile(e.target.files?.[0] ?? null)} data-testid={`manual-file-${slot}`} />
          <Button disabled={!file || busy} onClick={() => file && void submit(file, slot)} data-testid={`manual-submit-${slot}`}>
            Send
          </Button>
        </>
      )}
    </div>
  );
}

function Detail({ t }: { t: ManualTask }) {
  const { busy, submit } = useManual();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  useEffect(() => setFile(null), [t.task_id]);
  return (
    <div data-testid="manual-detail">
      <Section title={`${t.vendor}: ${t.title}`}>
        <ol className="list-decimal pl-8 text-2xl leading-relaxed" data-testid="manual-steps">
          {t.instructions.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
      </Section>
      {t.prompt && <TextBlock label="Prompt" text={t.prompt} testId="manual-prompt" />}
      {t.negative_prompt && <TextBlock label="Negative prompt" text={t.negative_prompt} testId="manual-negative" />}
      {t.settings.length > 0 && (
        <Section title="Settings">
          <ul className="rounded-tile bg-card p-5 font-mono text-xl shadow-soft" data-testid="manual-settings">
            {t.settings.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </Section>
      )}
      {t.inputs.length > 0 && (
        <Section title="Files to upload to the vendor">
          <Row>
            {t.inputs.map((i) => (
              <a key={i.name} href={i.url} download={i.name} className="hit flex flex-col items-center gap-2 rounded-tile bg-card p-4 text-xl shadow-soft" data-testid={`manual-input-${i.name}`}>
                <img src={i.url} alt={i.name} className="h-40 w-40 rounded-2xl bg-paper object-contain" />
                {i.name} ↓
              </a>
            ))}
          </Row>
        </Section>
      )}
      <Section title="The API request this replaces">
        <details className="rounded-tile bg-card p-5 text-xl shadow-soft">
          <summary className="hit">
            {t.route} · {t.manifest}
          </summary>
          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-lg" data-testid="manual-request">
            {JSON.stringify(t.request, null, 1)}
          </pre>
          <Copy text={JSON.stringify(t.request, null, 1)} testId="manual-request-copy" />
        </details>
      </Section>
      {t.status === 'pending' && (t.expects.slots ?? []).length > 0 ? (
        <Section title={`Upload each view (${t.expects.accept.join(', ')}); the job continues once all ${(t.expects.slots ?? []).length} are in`} testId="manual-slots">
          {(t.expects.slots ?? []).map((slot) => (
            <SlotUpload key={slot} t={t} slot={slot} />
          ))}
        </Section>
      ) : t.status === 'pending' ? (
        <Section title={`Upload the ${t.expects.kind === 'model' ? '3D model' : 'image'} (${t.expects.accept.join(', ')})`}>
          <div className="flex items-center gap-6">
            <input
              ref={input}
              type="file"
              accept={t.expects.accept.join(',')}
              className="flex-1 text-2xl"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              data-testid="manual-file"
            />
            <Button
              disabled={!file || busy}
              onClick={() => {
                if (file) void submit(file).then((r) => r && input.current && (input.current.value = ''));
              }}
              data-testid="manual-submit"
            >
              {busy ? 'Uploading…' : 'Send to the job'}
            </Button>
          </div>
        </Section>
      ) : (
        <p className="text-2xl text-muted" data-testid="manual-submitted">
          Output received: {t.result_name}
        </p>
      )}
    </div>
  );
}

export function ManualScreen() {
  const m = useManual();
  useEffect(() => {
    void m.load();
    const t = setInterval(() => void useManual.getState().load(), 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [m.filter]);
  const selected = m.tasks.find((t) => t.task_id === m.selectedId) ?? null;
  return (
    <div className="no-scrollbar flex h-full flex-col overflow-y-auto px-12 pb-10 pt-24" data-testid="manual">
      <Title sub="Requests the pipeline would send the GenAI API. Run each in the vendor's app, then upload the output here.">
        Manual tasks ({m.pending} waiting)
      </Title>
      {(m.error || m.notice) && (
        <p className={cx('mb-4 text-2xl font-semibold', m.error ? 'text-accent2' : 'text-accent')} data-testid={m.error ? 'manual-error' : 'manual-notice'}>
          {m.error ?? m.notice}
        </p>
      )}
      <Row>
        {(['pending', 'submitted', 'all'] as ManualFilter[]).map((f) => (
          <Chip key={f} selected={m.filter === f} onClick={() => m.set({ filter: f })} testId={`manual-filter-${f}`}>
            {f}
          </Chip>
        ))}
      </Row>
      <Section title="Tasks" testId="manual-list">
        {m.tasks.length === 0 && <p className="text-2xl text-muted">Nothing waiting. Jobs on a manual profile stop here for you.</p>}
        {m.tasks.map((t) => (
          <TaskCard key={t.task_id} t={t} selected={t.task_id === m.selectedId} onClick={() => m.select(t.task_id)} />
        ))}
      </Section>
      {selected && <Detail t={selected} />}
    </div>
  );
}

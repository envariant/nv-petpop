// Screens 7 and 8 (Generating, Result) and the phone result page /r/:token.
import { AnimatePresence, motion } from 'framer-motion';
import { QRCodeSVG } from 'qrcode.react';
import { useEffect, useState } from 'react';
import { Api, subscribeJob } from '../api/client';
import type { ResultPage } from '../api/types';
import { GlbFigure } from '../components/Figure3D';
import { Button, Chip, Title } from '../components/ui';
import { useSession } from '../store/session';

const STAGES = [
  { id: 'A', label: 'Reading the description' },
  { id: 'B', label: 'Concept sketch' },
  { id: 'C', label: 'Four views' },
  { id: 'D', label: 'Sculpting' },
  { id: 'E', label: 'Fitting the figure' },
  { id: 'F', label: 'Painting and print prep' },
];
const ORDER = ['queued', 'A', 'control', 'B', 'C', 'D', 'E', 'F', 'done'];

export function GeneratingScreen() {
  const s = useSession();
  useEffect(() => {
    if (!s.jobId) return;
    return subscribeJob(s.jobId, s.onEvent, s.onJob);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.jobId]);
  const last = s.events[s.events.length - 1];
  const status = s.job?.status ?? last?.status ?? 'queued';
  const stage = last?.stage ?? s.job?.stage ?? 'queued';
  const pct = Math.max(last?.pct ?? 0, s.job?.pct ?? 0);
  const done = status === 'done' || status === 'fulfilled';
  const failed = status === 'failed';
  useEffect(() => {
    if (done && s.job) {
      const t = setTimeout(() => s.go('result'), 1200);
      return () => clearTimeout(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done, s.job]);
  const p = s.previews;
  const views = ['view_front', 'view_left', 'view_back', 'view_right'].filter((k) => p[k]);
  const name = (s.spec as { pet_name?: string } | null)?.pet_name ?? 'your pet';
  return (
    <div className="flex h-full flex-col px-16 pt-20" data-testid="generating" data-status={status}>
      <Title sub={failed ? undefined : 'This takes two to four minutes. Watch it come together.'}>{failed ? 'That one got stuck' : done ? `${name} is ready!` : `Making ${name}…`}</Title>
      {status === 'queued' && (
        <div className="mb-8 rounded-tile bg-card p-8 text-4xl shadow-soft" data-testid="queue-position">
          You're <b>#{last?.queue_position ?? s.job?.queue_position ?? 1}</b> in the queue. Another figurine is being made first.
        </div>
      )}
      <div className="mb-6 h-8 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <motion.div className="h-full bg-accent" animate={{ width: `${pct}%` }} transition={{ duration: 0.6 }} />
      </div>
      <p className="mb-8 text-3xl" data-testid="progress-message" aria-live="polite">
        {last?.message ?? 'Starting…'}
      </p>
      <div className="relative mb-8 flex-1 overflow-hidden rounded-tile bg-card shadow-soft" data-testid="preview-stage">
        <AnimatePresence mode="wait">
          {p.glb && done ? (
            <motion.div key="final" className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <GlbFigure url={p.glb} fallbackImage={p.thumbnail} />
            </motion.div>
          ) : p.shape ? (
            <motion.div key="shape" className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="preview-shape">
              <GlbFigure url={p.shape} />
              <span className="absolute bottom-6 left-6 rounded-full bg-ink/80 px-4 py-1 text-xl text-paper">Raw shape</span>
            </motion.div>
          ) : views.length ? (
            <motion.div key="views" className="absolute inset-0 grid grid-cols-2 gap-4 p-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="preview-views">
              {views.map((k) => (
                <img key={k} src={p[k]} alt={k.replace('_', ' ')} className="h-full w-full rounded-2xl bg-paper object-contain" />
              ))}
            </motion.div>
          ) : p.concept ? (
            <motion.img key="concept" src={p.concept} alt="concept" className="absolute inset-0 h-full w-full object-contain p-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="preview-concept" />
          ) : (
            <motion.div key="wait" className="absolute inset-0 flex items-center justify-center text-[200px]" animate={{ rotate: [0, 10, -10, 0] }} transition={{ repeat: Infinity, duration: 2 }}>
              {s.species === 'cat' ? '🐱' : '🐶'}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      <ol className="mb-10 grid grid-cols-3 gap-3 text-2xl">
        {STAGES.map((st) => {
          const reached = ORDER.indexOf(stage) > ORDER.indexOf(st.id) || done;
          const current = stage === st.id && !done;
          return (
            <li key={st.id} className={`rounded-2xl px-4 py-3 ${reached ? 'bg-accent/15 text-ink' : current ? 'bg-accent text-white' : 'bg-card text-muted'}`} data-testid={`stage-${st.id}`} data-state={reached ? 'done' : current ? 'current' : 'todo'}>
              {reached ? '✓ ' : ''}
              {st.label}
            </li>
          );
        })}
      </ol>
      {failed && (
        <div className="mb-12 flex items-center gap-6" data-testid="generate-failed">
          <p className="flex-1 text-3xl text-muted">{s.job?.error ?? 'Something went wrong.'} Staff have been told.</p>
          <Button onClick={() => s.go('build')} variant="soft">
            Back to Build
          </Button>
        </div>
      )}
    </div>
  );
}

export function ResultScreen() {
  const s = useSession();
  const [clay, setClay] = useState(false);
  const [sending, setSending] = useState(false);
  const job = s.job;
  if (!job) return null;
  const glb = job.previews.glb ?? job.artefacts.find((a) => a.kind === 'glb')?.url;
  const name = job.pet_name ?? 'Your pet';
  const send = async () => {
    setSending(true);
    try {
      await s.fulfil();
    } finally {
      setSending(false);
    }
  };
  return (
    <div className="flex h-full flex-col px-16 pt-20" data-testid="result">
      <Title sub={job.fallback !== 'none' ? 'We used our classic figure shape this time; the colours are all yours.' : 'Pinch to zoom, drag to turn.'}>Meet {name}!</Title>
      <div className="relative flex-1 overflow-hidden rounded-tile bg-card shadow-soft" data-testid="result-viewer">
        {glb && <GlbFigure url={glb} clay={clay} interactive fallbackImage={job.previews.thumbnail} />}
        <div className="absolute right-6 top-6 flex gap-2">
          <Chip selected={!clay} onClick={() => setClay(false)} testId="toggle-textured">
            Painted
          </Chip>
          <Chip selected={clay} onClick={() => setClay(true)} testId="toggle-clay">
            Clay
          </Chip>
        </div>
      </div>
      <div className="my-10 flex items-center gap-10">
        <div className="rounded-3xl bg-white p-5 shadow-soft" data-testid="result-qr">
          {job.result_url && <QRCodeSVG value={job.result_url} size={220} level="M" />}
        </div>
        <div className="flex flex-1 flex-col gap-5">
          <p className="text-3xl text-muted">Scan to open {name} on your phone.</p>
          {s.ticket ? (
            <div className="rounded-tile bg-accent p-6 font-display text-4xl text-white" data-testid="ticket">
              Sent to print! Ticket <b>{s.ticket}</b>
            </div>
          ) : (
            <Button onClick={() => void send()} disabled={sending} data-testid="send-to-print">
              {sending ? 'Sending…' : 'Send to print'}
            </Button>
          )}
        </div>
      </div>
      <div className="mb-12 flex justify-between">
        <Button variant="soft" onClick={s.tweak} disabled={s.generationsLeft <= 0} data-testid="tweak">
          Tweak ({s.generationsLeft} left)
        </Button>
        <Button variant="ghost" onClick={s.reset} data-testid="start-over">
          Start over
        </Button>
      </div>
    </div>
  );
}

export function PhoneResult({ token }: { token: string }) {
  const [page, setPage] = useState<ResultPage | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    Api.result(token).then(setPage).catch((e: { status?: number }) => setErr(e.status === 410 ? 'This link has expired.' : 'We could not find this figurine.'));
  }, [token]);
  return (
    <div className="kiosk flex min-h-full flex-col items-center px-6 py-10" data-theme="candy" data-testid="phone-result">
      <div className="font-display text-5xl font-semibold">
        Pet<span className="text-accent">Pop</span>
      </div>
      {err && <p className="mt-10 text-xl">{err}</p>}
      {page && (
        <>
          <h1 className="mt-6 font-display text-4xl">{page.pet_name ?? 'Your pet'}</h1>
          <p className="text-lg text-muted">{page.breed_label}</p>
          <div className="my-6 h-[60vh] w-full max-w-md rounded-[28px] bg-card shadow-soft">
            <GlbFigure url={page.glb_url} interactive fallbackImage={page.thumbnail_url ?? undefined} />
          </div>
          <a className="rounded-full bg-accent px-8 py-4 font-display text-2xl text-white" href={page.glb_url} download={`${page.pet_name ?? 'petpop'}.glb`}>
            Download 3D file
          </a>
          <p className="mt-4 text-sm text-muted">Link expires {new Date(page.expires_at).toLocaleDateString()}</p>
        </>
      )}
    </div>
  );
}

// Studio overlays: "Back in a moment" when the API drops, and the studio queue panel.
import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import { StudioApi as Api } from '@petpop/core';
import type { StaffQueue } from '@petpop/core';
import { Button } from '@petpop/ui';

const Backdrop = ({ children, testId }: { children: React.ReactNode; testId: string }) => (
  <motion.div data-testid={testId} className="absolute inset-0 z-40 flex items-center justify-center bg-ink/60 p-16" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
    {children}
  </motion.div>
);

/** Polls /health; when it fails the studio shows "Back in a moment" and keeps retrying. */
export function useOnline(): boolean {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    let live = true;
    let fails = 0;
    const check = async () => {
      try {
        await Api.health();
        fails = 0;
        if (live) setOnline(true);
      } catch {
        fails += 1;
        if (live && fails >= 2) setOnline(false);
      }
    };
    const t = setInterval(check, 2500);
    void check();
    return () => {
      live = false;
      clearInterval(t);
    };
  }, []);
  return online;
}

export function Offline() {
  return (
    <Backdrop testId="offline">
      <div className="w-full rounded-tile bg-paper p-16 text-center shadow-soft">
        <div className="mb-6 text-9xl">🛠️</div>
        <h2 className="font-display text-6xl font-semibold">Back in a moment</h2>
        <p className="mt-6 text-3xl text-muted">We're reconnecting. Your pet is safe.</p>
      </div>
    </Backdrop>
  );
}

/** The studio queue: what is running, what waits, the last 20 jobs with retry and reprint. */
export function QueuePanel({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState<StaffQueue | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = async () => {
    try {
      setQ(await Api.queue());
      setErr(null);
    } catch {
      setErr('Could not load the queue');
    }
  };
  useEffect(() => {
    void load();
  }, []);
  return (
    <Backdrop testId="staff-panel">
      <div className="max-h-full w-full overflow-y-auto rounded-tile bg-paper p-12 shadow-soft">
        <div className="mb-8 flex items-center justify-between">
          <h2 className="font-display text-5xl font-semibold">Studio queue</h2>
          <Button variant="soft" onClick={onClose} data-testid="staff-close">
            Close
          </Button>
        </div>
        {!q ? (
          <p className="text-2xl text-muted">{err ?? 'Loading…'}</p>
        ) : (
          <div className="text-2xl" data-testid="staff-queue">
            <p className="mb-4">
              Mode <b>{q.mode}</b> · GPU <b>{q.gpu.name}</b> · {q.gpu.temp_c ?? '–'} °C · running {q.running ? q.running.pet_name : 'nothing'} · {q.queued.length} queued
            </p>
            <table className="w-full text-left">
              <thead className="text-muted">
                <tr>
                  <th />
                  <th>Pet</th>
                  <th>By</th>
                  <th>Status</th>
                  <th>Fallback</th>
                  <th>Time</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {q.recent.map((j) => (
                  <tr key={j.job_id} className="border-t border-line">
                    <td>{j.thumbnail_url && <img src={j.thumbnail_url} alt="" className="h-16 w-16 object-contain" />}</td>
                    <td>{j.pet_name}</td>
                    <td>{j.kind === 'bespoke' ? `${j.requested_by} (bespoke)` : j.requested_by}</td>
                    <td>{j.status}</td>
                    <td>{j.fallback}</td>
                    <td>{j.total_ms ? `${Math.round(j.total_ms / 1000)} s` : '–'}</td>
                    <td className="flex gap-2 py-2">
                      <Button variant="soft" className="!px-4 !py-2 !text-xl" onClick={() => void Api.retry(j.job_id).then(() => load())}>
                        Retry
                      </Button>
                      {(j.status === 'done' || j.status === 'fulfilled') && (
                        <Button variant="soft" className="!px-4 !py-2 !text-xl" onClick={() => void Api.fulfil(j.job_id).then(() => load())}>
                          Reprint
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Backdrop>
  );
}

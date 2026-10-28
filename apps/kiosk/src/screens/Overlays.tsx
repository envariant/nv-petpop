// Kiosk behaviour: idle "Still there?" countdown, "Back in a moment" offline overlay, hidden staff panel.
import { motion } from 'framer-motion';
import { useEffect, useRef, useState } from 'react';
import { Api } from '../api/client';
import type { StaffQueue } from '../api/types';
import { Keyboard, TextDisplay } from '../components/Keyboard';
import { Button } from '../components/ui';
import { useSession } from '../store/session';

const Backdrop = ({ children, testId }: { children: React.ReactNode; testId: string }) => (
  <motion.div data-testid={testId} className="absolute inset-0 z-40 flex items-center justify-center bg-ink/60 p-16" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
    {children}
  </motion.div>
);

/** Idle timer: after idleSeconds without a touch (any screen but Attract) show the countdown, then wipe. */
export function useIdle(): { countdown: number | null; dismiss: () => void } {
  const screen = useSession((s) => s.screen);
  // ?idle=&countdown= override the session policy (seconds) for tests and demos.
  const params = new URLSearchParams(location.search);
  const policyIdle = useSession((s) => s.idleSeconds);
  const policyCountdown = useSession((s) => s.countdownSeconds);
  const idleSeconds = Number(params.get('idle') ?? policyIdle);
  const countdownSeconds = Number(params.get('countdown') ?? policyCountdown);
  const reset = useSession((s) => s.reset);
  const [countdown, setCountdown] = useState<number | null>(null);
  const last = useRef(Date.now());
  useEffect(() => {
    const touch = () => {
      last.current = Date.now();
    };
    window.addEventListener('pointerdown', touch, true);
    window.addEventListener('keydown', touch, true);
    return () => {
      window.removeEventListener('pointerdown', touch, true);
      window.removeEventListener('keydown', touch, true);
    };
  }, []);
  useEffect(() => {
    last.current = Date.now();
    setCountdown(null);
  }, [screen]);
  useEffect(() => {
    if (screen === 'attract' || screen === 'generating') return;
    const t = setInterval(() => {
      const idle = (Date.now() - last.current) / 1000;
      if (idle >= idleSeconds + countdownSeconds) {
        setCountdown(null);
        reset();
      } else if (idle >= idleSeconds) setCountdown(Math.ceil(idleSeconds + countdownSeconds - idle));
      else setCountdown(null);
    }, 200);
    return () => clearInterval(t);
  }, [screen, idleSeconds, countdownSeconds, reset]);
  return { countdown, dismiss: () => ((last.current = Date.now()), setCountdown(null)) };
}

export function StillThere({ seconds, onStay }: { seconds: number; onStay: () => void }) {
  return (
    <Backdrop testId="still-there">
      <div className="w-full rounded-tile bg-paper p-16 text-center shadow-soft">
        <h2 className="font-display text-7xl font-semibold">Still there?</h2>
        <p className="my-8 text-4xl text-muted">
          Starting over in <b data-testid="still-there-seconds">{seconds}</b> s
        </p>
        <Button onClick={onStay} data-testid="still-there-stay">
          I'm here!
        </Button>
      </div>
    </Backdrop>
  );
}

/** Polls /health; when it fails the kiosk shows "Back in a moment" and keeps retrying. */
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

/** Five taps in the top-right corner within 3 s opens the staff panel. */
export function useFiveTap(onOpen: () => void) {
  const taps = useRef<number[]>([]);
  return () => {
    const now = Date.now();
    taps.current = [...taps.current.filter((t) => now - t < 3000), now];
    if (taps.current.length >= 5) {
      taps.current = [];
      onOpen();
    }
  };
}

export function StaffPanel({ onClose }: { onClose: () => void }) {
  const [token, setToken] = useState(() => {
    try {
      return localStorage.getItem('pp-staff-token') ?? '';
    } catch {
      return '';
    }
  });
  const [q, setQ] = useState<StaffQueue | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = async (t = token) => {
    try {
      setQ(await Api.staffQueue(t));
      setErr(null);
      try {
        localStorage.setItem('pp-staff-token', t);
      } catch {
        /* storage may be blocked */
      }
    } catch {
      setErr('Token not accepted');
      setQ(null);
    }
  };
  useEffect(() => {
    if (token) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <Backdrop testId="staff-panel">
      <div className="max-h-full w-full overflow-y-auto rounded-tile bg-paper p-12 shadow-soft">
        <div className="mb-8 flex items-center justify-between">
          <h2 className="font-display text-5xl font-semibold">Staff</h2>
          <Button variant="soft" onClick={onClose} data-testid="staff-close">
            Close
          </Button>
        </div>
        {!q ? (
          <div>
            <TextDisplay value={token.replace(/./g, '•')} placeholder="Staff token" testId="staff-token" />
            {err && <p className="my-4 text-2xl text-accent2">{err}</p>}
            <div className="mt-6">
              <Keyboard value={token} onChange={setToken} onDone={() => void load()} doneLabel="Open" compact capitalize={false} />
            </div>
          </div>
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
                    <td>{j.status}</td>
                    <td>{j.fallback}</td>
                    <td>{j.total_ms ? `${Math.round(j.total_ms / 1000)} s` : '–'}</td>
                    <td className="flex gap-2 py-2">
                      <Button variant="soft" className="!px-4 !py-2 !text-xl" onClick={() => void Api.staffRetry(j.job_id, token).then(() => load())}>
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

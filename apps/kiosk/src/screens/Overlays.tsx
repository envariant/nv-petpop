// Kiosk behaviour: idle "Still there?" countdown, "Back in a moment" offline overlay, the five-tap ops panel.
import { motion } from 'framer-motion';
import { useEffect, useRef, useState } from 'react';
import { KioskApi as Api } from '@petpop/core';
import type { KioskOps } from '@petpop/core';
import { Keyboard, TextDisplay } from '@petpop/ui';
import { Button } from '@petpop/ui';
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
    if (screen === 'attract') return;
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

/** The five-tap ops panel (BRIEF Section 17): release version, health, reprint; no generation controls. */
export function StaffPanel({ onClose }: { onClose: () => void }) {
  const [pin, setPin] = useState(() => {
    try {
      return localStorage.getItem('pp-staff-token') ?? '';
    } catch {
      return '';
    }
  });
  const [ops, setOps] = useState<KioskOps | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = async (t = pin) => {
    try {
      setOps(await Api.ops(t));
      setErr(null);
      try {
        localStorage.setItem('pp-staff-token', t);
      } catch {
        /* storage may be blocked */
      }
    } catch {
      setErr('PIN not accepted');
      setOps(null);
    }
  };
  const [reprinted, setReprinted] = useState<string | null>(null);
  const reprint = async (id: string) => {
    try {
      await Api.reprint(pin, id);
      setReprinted(id);
    } catch {
      setErr('Reprint failed');
    }
  };
  useEffect(() => {
    if (pin) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <Backdrop testId="staff-panel">
      <div className="max-h-full w-full overflow-y-auto rounded-tile bg-paper p-12 shadow-soft">
        <div className="mb-8 flex items-center justify-between">
          <h2 className="font-display text-5xl font-semibold">Kiosk</h2>
          <Button variant="soft" onClick={onClose} data-testid="staff-close">
            Close
          </Button>
        </div>
        {!ops ? (
          <div>
            <TextDisplay value={pin.replace(/./g, '•')} placeholder="Staff PIN" testId="staff-token" />
            {err && <p className="my-4 text-2xl text-accent2">{err}</p>}
            <div className="mt-6">
              <Keyboard value={pin} onChange={setPin} onDone={() => void load()} doneLabel="Open" compact capitalize={false} />
            </div>
          </div>
        ) : (
          <dl className="grid grid-cols-2 gap-y-4 text-3xl" data-testid="staff-ops">
            <dt className="text-muted">Kiosk</dt>
            <dd>{ops.kiosk_id}</dd>
            <dt className="text-muted">Library release</dt>
            <dd data-testid="ops-release">{Object.values(ops.releases).join(', ') || 'none loaded'}</dd>
            <dt className="text-muted">API</dt>
            <dd>
              {ops.api_version} ({ops.mode})
            </dd>
            <dt className="text-muted">Exports</dt>
            <dd>
              {ops.exports_running} running · {ops.exports_queued} queued
            </dd>
            <dt className="text-muted">Make it unique</dt>
            <dd>{ops.bespoke_enabled ? 'on' : 'off'}</dd>
            <dt className="col-span-2 mt-6 font-display text-4xl font-semibold text-ink">Recent orders</dt>
            {ops.orders.length === 0 && <dd className="col-span-2 text-muted">No orders yet</dd>}
            {ops.orders.map((o) => (
              <dd key={o.composition_id} className="col-span-2 flex items-center justify-between gap-6" data-testid={`ops-order-${o.ticket}`}>
                <span>
                  <b>{o.ticket}</b> · {o.pet_name || 'unnamed'} · {o.status}
                </span>
                <Button variant="soft" disabled={o.status !== 'ready'} onClick={() => void reprint(o.composition_id)} data-testid={`reprint-${o.ticket}`}>
                  {reprinted === o.composition_id ? 'Sent ✓' : 'Reprint'}
                </Button>
              </dd>
            ))}
          </dl>
        )}
      </div>
    </Backdrop>
  );
}

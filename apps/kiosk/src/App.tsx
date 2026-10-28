// Kiosk shell: a fixed 1080x1920 portrait canvas scaled to the window, one screen at a time.
import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useState, type ReactNode } from 'react';
import { BuildScreen } from './screens/Build';
import { BriefScreen, NameScreen } from './screens/Brief';
import { AttractScreen, BreedScreen, SpeciesScreen } from './screens/Intro';
import { GeneratingScreen, PhoneResult, ResultScreen } from './screens/Outcome';
import { Offline, StaffPanel, StillThere, useFiveTap, useIdle, useOnline } from './screens/Overlays';
import { useSession, type Screen } from './store/session';

export const W = 1080;
export const H = 1920;

export function theme(): string {
  const t = new URLSearchParams(location.search).get('theme');
  return t === 'studio' || t === 'toybox' ? t : 'candy';
}

export function KioskFrame({ children, species, themeName }: { children: ReactNode; species?: string | null; themeName?: string }) {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const fit = () => setScale(Math.min(window.innerWidth / W, window.innerHeight / H));
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, []);
  return (
    <div className="fixed inset-0 bg-black" style={{ overflow: 'clip' }}>
      <div
        className="kiosk absolute left-1/2 top-1/2"
        data-theme={themeName ?? theme()}
        data-species={species ?? 'dog'}
        style={{ width: W, height: H, overflow: 'clip', transform: `translate(-50%, -50%) scale(${scale})`, transformOrigin: 'center' }}
      >
        {children}
      </div>
    </div>
  );
}

export const SCREENS: Record<Screen, () => JSX.Element | null> = {
  attract: AttractScreen,
  species: SpeciesScreen,
  breed: BreedScreen,
  build: BuildScreen,
  brief: BriefScreen,
  name: NameScreen,
  generating: GeneratingScreen,
  result: ResultScreen,
};

function Kiosk() {
  const screen = useSession((s) => s.screen);
  const species = useSession((s) => s.species);
  const reset = useSession((s) => s.reset);
  const { countdown, dismiss } = useIdle();
  const online = useOnline();
  const [staff, setStaff] = useState(false);
  const corner = useFiveTap(() => setStaff(true));
  const Current = SCREENS[screen];
  return (
    <KioskFrame species={species}>
      <AnimatePresence mode="wait">
        <motion.div key={screen} className="absolute inset-0" data-screen={screen} initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -40 }} transition={{ duration: 0.25 }}>
          <Current />
        </motion.div>
      </AnimatePresence>
      {screen !== 'attract' && screen !== 'generating' && screen !== 'result' && (
        <button aria-label="Start over" data-testid="home" onClick={reset} className="hit absolute left-8 top-6 z-30 rounded-full px-4 py-2 text-2xl text-muted">
          ✕ Start over
        </button>
      )}
      <button aria-label="Staff" data-testid="staff-corner" onClick={corner} className="absolute right-0 top-0 z-50 h-28 w-28 opacity-0" />
      <AnimatePresence>
        {countdown !== null && <StillThere key="idle" seconds={countdown} onStay={dismiss} />}
        {!online && <Offline key="offline" />}
        {staff && <StaffPanel key="staff" onClose={() => setStaff(false)} />}
      </AnimatePresence>
    </KioskFrame>
  );
}

export function App() {
  const path = location.pathname;
  if (path.startsWith('/r/')) return <PhoneResult token={decodeURIComponent(path.slice(3))} />;
  return <Kiosk />;
}

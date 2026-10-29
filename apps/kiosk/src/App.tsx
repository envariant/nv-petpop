// PetPop Kiosk (customers): library mode only (BRIEF Sections 16 and 17). A fixed 1080x1920 portrait canvas,
// one screen at a time; it never depends on the GenAI host.
import { AnimatePresence, motion } from 'framer-motion';
import { useState } from 'react';
import { KioskFrame } from '@petpop/ui';
import { BespokeScreen, DesignScreen } from './screens/Design';
import { AttractScreen, BreedScreen, SpeciesScreen } from './screens/Intro';
import { Offline, StaffPanel, StillThere, useFiveTap, useIdle, useOnline } from './screens/Overlays';
import { PhoneResult } from './screens/Phone';
import { useSession, type Screen } from './store/session';

export const SCREENS: Record<Screen, () => JSX.Element | null> = {
  attract: AttractScreen,
  species: SpeciesScreen,
  breed: BreedScreen,
  design: DesignScreen,
  bespoke: BespokeScreen,
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
      {screen !== 'attract' && (
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

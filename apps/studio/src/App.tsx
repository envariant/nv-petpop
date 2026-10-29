// PetPop Studio (staff): the Generate workspace behind a staff login, plus the studio queue. Same portrait frame
// and UI kit as the kiosk (@petpop/ui), so a figure looks the same in both apps.
import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import { KioskFrame } from '@petpop/ui';
import { BuildScreen } from './screens/Build';
import { GenerateScreen, LibraryScreen, ReleasesScreen, ReviewScreen } from './screens/Curate';
import { BriefScreen, NameScreen } from './screens/Brief';
import { BreedScreen, SpeciesScreen } from './screens/Intro';
import { LoginScreen } from './screens/Login';
import { GeneratingScreen, ResultScreen } from './screens/Outcome';
import { Offline, QueuePanel, useOnline } from './screens/Overlays';
import { useSession, type Screen } from './store/session';

export const SCREENS: Record<Screen, () => JSX.Element | null> = {
  generate: GenerateScreen,
  review: ReviewScreen,
  library: LibraryScreen,
  releases: ReleasesScreen,
  species: SpeciesScreen,
  breed: BreedScreen,
  build: BuildScreen,
  brief: BriefScreen,
  name: NameScreen,
  generating: GeneratingScreen,
  result: ResultScreen,
};

const AREAS: { screen: Screen; title: string }[] = [
  { screen: 'generate', title: 'Generate' },
  { screen: 'review', title: 'Review' },
  { screen: 'library', title: 'Library' },
  { screen: 'releases', title: 'Releases' },
];

export function StudioBar({ onQueue }: { onQueue: () => void }) {
  const user = useSession((s) => s.user);
  const logout = useSession((s) => s.logout);
  const screen = useSession((s) => s.screen);
  const go = useSession((s) => s.go);
  return (
    <div className="absolute inset-x-0 top-0 z-30 flex items-center justify-between px-8 py-4 text-2xl text-muted" data-testid="studio-bar">
      <div className="flex items-center gap-5">
        <button onClick={() => go('generate')} className="hit font-display" data-testid="home">
          Pet<span className="text-accent">Pop</span> Studio
        </button>
        {AREAS.map((a) => (
          <button key={a.screen} onClick={() => go(a.screen)} className={`hit ${screen === a.screen ? 'font-semibold text-ink' : ''}`} data-testid={`nav-${a.screen}`}>
            {a.title}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-6">
        <span data-testid="studio-user">
          {user?.username} ({user?.role})
        </span>
        <button className="hit underline" onClick={onQueue} data-testid="open-queue">
          Queue
        </button>
        <button className="hit underline" onClick={logout} data-testid="logout">
          Sign out
        </button>
      </div>
    </div>
  );
}

function Studio() {
  const user = useSession((s) => s.user);
  const screen = useSession((s) => s.screen);
  const species = useSession((s) => s.species);
  const restore = useSession((s) => s.restore);
  const online = useOnline();
  const [queue, setQueue] = useState(false);
  useEffect(() => {
    void restore();
  }, [restore]);
  const Current = SCREENS[screen];
  return (
    <KioskFrame species={species}>
      {!user ? (
        <LoginScreen />
      ) : (
        <>
          <AnimatePresence mode="wait">
            <motion.div key={screen} className="absolute inset-0" data-screen={screen} initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -40 }} transition={{ duration: 0.25 }}>
              <Current />
            </motion.div>
          </AnimatePresence>
          <StudioBar onQueue={() => setQueue(true)} />
        </>
      )}
      <AnimatePresence>
        {!online && <Offline key="offline" />}
        {queue && user && <QueuePanel key="queue" onClose={() => setQueue(false)} />}
      </AnimatePresence>
    </KioskFrame>
  );
}

export function App() {
  return <Studio />;
}

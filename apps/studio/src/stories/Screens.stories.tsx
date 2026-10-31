// One story per Studio screen and overlay, rendered in the portrait frame with fixture data.
import type { Decorator, Meta, StoryObj } from '@storybook/react';
import { useEffect, useState, type ReactNode } from 'react';
import { KioskFrame } from '@petpop/ui';
import { SCREENS, StudioBar } from '../App';
import { LoginScreen } from '../screens/Login';
import { Offline, QueuePanel } from '../screens/Overlays';
import { useSession, type Screen, type SessionState } from '../store/session';
import { useCurate, type CurateState } from '../store/curate';
import { useManual, type ManualState } from '../store/manual';
import { MANUAL_TASKS } from '../mocks/manual';
import { PROFILES } from '../mocks/handlers';
import { useProfiles } from '../store/profiles';
import { BATCH, CORGI, PATTERN_ITEM, RELEASES, SPEC, VIEW_PREVIEWS, job } from './fixtures';

const OPERATOR = { username: 'operator', role: 'operator' as const };

function Hydrate({ state, curate, manual, children }: { state: Partial<SessionState>; curate?: Partial<CurateState>; manual?: Partial<ManualState>; children: ReactNode }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    useSession.getState().reset();
    useSession.getState().hydrate({ user: OPERATOR, ...state });
    if (curate) useCurate.getState().set(curate);
    if (manual) useManual.getState().set(manual);
    useProfiles.getState().set({ offered: PROFILES as never, choice: 'tripo-manual', pipeline: 'multiview', options: { hd_texture: true, hd_geometry: false, quad: false } });
    setReady(true);
  }, [state, curate, manual]);
  return ready ? <>{children}</> : null;
}

const withFrame: Decorator = (Story, ctx) => (
  <div style={{ height: '100vh' }}>
    <KioskFrame species={useSession.getState().species ?? 'dog'} themeName={ctx.globals.theme as string}>
      <Story />
    </KioskFrame>
  </div>
);

function ScreenStory({ screen, state = {}, curate, manual }: { screen: Screen; state?: Partial<SessionState>; curate?: Partial<CurateState>; manual?: Partial<ManualState> }) {
  const Current = SCREENS[screen];
  return (
    <Hydrate state={{ screen, ...state }} curate={curate} manual={manual}>
      <Current />
      <StudioBar onQueue={() => undefined} />
    </Hydrate>
  );
}

const meta: Meta<typeof ScreenStory> = { title: 'Studio/Generate workspace', component: ScreenStory, decorators: [withFrame] };
export default meta;
type Story = StoryObj<typeof ScreenStory>;

const built = { species: 'dog' as const, breed: CORGI, spec: SPEC };

const ADMIN = { username: 'admin', role: 'admin' as const };
export const Generate: Story = { args: { screen: 'generate', curate: { breeds: ['pug', 'beagle'], variants: ['preset', 'big_ears'], seeds: 2, batches: [{ ...BATCH, figurines: [] }] } } };
export const Review: Story = { args: { screen: 'review', curate: { batch: BATCH } } };
export const Library: Story = { args: { screen: 'library', curate: { kind: 'pattern', items: [PATTERN_ITEM], selected: PATTERN_ITEM } } };
export const Releases: Story = { args: { screen: 'releases', state: { user: ADMIN }, curate: { releases: RELEASES } } };
export const Manual: Story = { args: { screen: 'manual', manual: { tasks: MANUAL_TASKS, pending: 3, selectedId: MANUAL_TASKS[1].task_id } } };
export const ManualViews: Story = { args: { screen: 'manual', manual: { tasks: MANUAL_TASKS, pending: 3, selectedId: MANUAL_TASKS[2].task_id } } };
export const Species: Story = { args: { screen: 'species' } };
export const Breed: Story = { args: { screen: 'breed', state: { species: 'dog' } } };
export const Build: Story = { args: { screen: 'build', state: built } };
export const BuildWithBriefHighlights: Story = { args: { screen: 'build', state: { ...built, highlights: ['ears.shape', 'body.build', 'colour.markings'] } } };
export const Brief: Story = { args: { screen: 'brief', state: { ...built, briefText: 'Biscuit is a chunky corgi with one ear that flops, loves snacks' } } };
export const BriefFlavourOnly: Story = {
  args: { screen: 'brief', state: { ...built, briefText: 'the best boy', parse: { patch: {}, changed_fields: [], personality: [], free_text_unmapped: 'best boy', parser: 'rules', llm_available: false, flavour_only: true, blocked: false, ms: 2 } } },
};
export const NameAndGenerate: Story = { args: { screen: 'name', state: built } };
export const GeneratingQueued: Story = { args: { screen: 'generating', state: { ...built, job: job('queued'), events: [{ job_id: 'j', status: 'queued', stage: 'queued', pct: 0, message: 'Waiting for the studio', queue_position: 2, preview_url: null, preview_kind: null }] } } };
export const GeneratingViews: Story = { args: { screen: 'generating', state: { ...built, job: job('running'), previews: VIEW_PREVIEWS, events: [{ job_id: 'j', status: 'running', stage: 'C', pct: 45, message: 'Four views ready', queue_position: 0, preview_url: null, preview_kind: null }] } } };
export const GeneratingFailed: Story = { args: { screen: 'generating', state: { ...built, job: job('failed'), previews: VIEW_PREVIEWS, events: [{ job_id: 'j', status: 'failed', stage: 'D', pct: 55, message: 'Stage D failed', queue_position: 0, preview_url: null, preview_kind: null }] } } };
export const Result: Story = { args: { screen: 'result', state: { ...built, jobId: 'j_story', job: job('done') } } };
export const ResultFallback: Story = { args: { screen: 'result', state: { ...built, jobId: 'j_story', job: job('done', { fallback: 'parametric' }) } } };
export const ResultSentToPrint: Story = { args: { screen: 'result', state: { ...built, jobId: 'j_story', job: job('fulfilled'), ticket: 'PP-4821' } } };

export const Login: StoryObj = { render: () => <LoginScreen /> };
export const LoginFailed: StoryObj = {
  render: () => {
    useSession.getState().hydrate({ loginError: 'Wrong username or password.' });
    return <LoginScreen />;
  },
};
export const QueueOverlay: StoryObj = { render: () => <QueuePanel onClose={() => undefined} /> };
export const OfflineOverlay: StoryObj = { render: () => <Offline /> };

// One story per Studio screen and overlay, rendered in the portrait frame with fixture data.
import type { Decorator, Meta, StoryObj } from '@storybook/react';
import { useEffect, useState, type ReactNode } from 'react';
import { KioskFrame } from '@petpop/ui';
import { SCREENS, StudioBar } from '../App';
import { LoginScreen } from '../screens/Login';
import { Offline, QueuePanel } from '../screens/Overlays';
import { useSession, type Screen, type SessionState } from '../store/session';
import { CORGI, SPEC, VIEW_PREVIEWS, job } from './fixtures';

const OPERATOR = { username: 'operator', role: 'operator' as const };

function Hydrate({ state, children }: { state: Partial<SessionState>; children: ReactNode }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    useSession.getState().reset();
    useSession.getState().hydrate({ user: OPERATOR, ...state });
    setReady(true);
  }, [state]);
  return ready ? <>{children}</> : null;
}

const withFrame: Decorator = (Story, ctx) => (
  <div style={{ height: '100vh' }}>
    <KioskFrame species={useSession.getState().species ?? 'dog'} themeName={ctx.globals.theme as string}>
      <Story />
    </KioskFrame>
  </div>
);

function ScreenStory({ screen, state = {} }: { screen: Screen; state?: Partial<SessionState> }) {
  const Current = SCREENS[screen];
  return (
    <Hydrate state={{ screen, ...state }}>
      <Current />
      <StudioBar onQueue={() => undefined} />
    </Hydrate>
  );
}

const meta: Meta<typeof ScreenStory> = { title: 'Studio/Generate workspace', component: ScreenStory, decorators: [withFrame] };
export default meta;
type Story = StoryObj<typeof ScreenStory>;

const built = { species: 'dog' as const, breed: CORGI, spec: SPEC };

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

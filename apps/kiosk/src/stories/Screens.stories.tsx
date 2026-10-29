// One story per kiosk screen and overlay, rendered in the 1080x1920 frame with fixture data.
import type { Decorator, Meta, StoryObj } from '@storybook/react';
import { useEffect, useState, type ReactNode } from 'react';
import { KioskFrame } from '@petpop/ui';
import { SCREENS } from '../App';
import { Offline, StaffPanel, StillThere } from '../screens/Overlays';
import { PhoneResult } from '../screens/Phone';
import { useSession, type Screen, type SessionState } from '../store/session';
import { CORGI, SPEC } from './fixtures';

function Hydrate({ state, children }: { state: Partial<SessionState>; children: ReactNode }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    useSession.getState().reset();
    useSession.getState().hydrate(state);
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
    </Hydrate>
  );
}

const meta: Meta<typeof ScreenStory> = { title: 'Kiosk/Screens', component: ScreenStory, decorators: [withFrame] };
export default meta;
type Story = StoryObj<typeof ScreenStory>;

const chosen = { species: 'dog' as const, breed: CORGI, spec: SPEC, sessionId: 's_story' };

export const Attract: Story = { args: { screen: 'attract' } };
export const Species: Story = { args: { screen: 'species' } };
export const Breed: Story = { args: { screen: 'breed', state: { species: 'dog' } } };
export const Design: Story = { args: { screen: 'design', state: chosen } };
export const DesignWithMakeItUnique: Story = { args: { screen: 'design', state: { ...chosen, bespokeEnabled: true } } };
export const Bespoke: Story = { args: { screen: 'bespoke', state: { ...chosen, bespokeEnabled: true } } };
export const BespokeAccepted: Story = {
  args: { screen: 'bespoke', state: { ...chosen, bespokeEnabled: true, bespoke: { request_id: 'j_story', ticket: 'PP-4821', message: "We'll message you when your one-off figurine is ready." } } },
};

export const StillThereOverlay: StoryObj = { render: () => <StillThere seconds={12} onStay={() => undefined} /> };
export const OfflineOverlay: StoryObj = { render: () => <Offline /> };
export const StaffPanelLocked: StoryObj = { render: () => <StaffPanel onClose={() => undefined} /> };
export const PhoneResultPage: StoryObj = { decorators: [(S) => <S />], render: () => <PhoneResult token="mock.demo" /> };

// One story per kiosk screen and overlay, rendered in the 1080x1920 frame with fixture data.
import type { Decorator, Meta, StoryObj } from '@storybook/react';
import { useEffect, useState, type ReactNode } from 'react';
import { KioskFrame } from '@petpop/ui';
import { SCREENS } from '../App';
import { Offline, StaffPanel, StillThere } from '../screens/Overlays';
import { PhoneResult } from '../screens/Phone';
import { useDesign, type DesignState } from '../store/design';
import { useSession, type Screen, type SessionState } from '../store/session';
import { CORGI, ORDER_READY, SPEC } from './fixtures';

/** Session state, plus (for the screens after Design) a composition begun from the library release via MSW. */
function Hydrate({ state, design, children }: { state: Partial<SessionState>; design?: Partial<DesignState>; children: ReactNode }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    void (async () => {
      useSession.getState().reset();
      useSession.getState().hydrate(state);
      if (design && state.breed) {
        await useDesign.getState().begin(state.breed);
        const c = useDesign.getState().composition;
        useDesign.getState().set({ ...design, composition: c && { ...c, pet_name: 'Biscuit' } });
      }
      setReady(true);
    })();
  }, [state, design]);
  return ready ? <>{children}</> : null;
}

const withFrame: Decorator = (Story, ctx) => (
  <div style={{ height: '100vh' }}>
    <KioskFrame species={useSession.getState().species ?? 'dog'} themeName={ctx.globals.theme as string}>
      <Story />
    </KioskFrame>
  </div>
);

function ScreenStory({ screen, state = {}, design }: { screen: Screen; state?: Partial<SessionState>; design?: Partial<DesignState> }) {
  const Current = SCREENS[screen];
  return (
    <Hydrate state={{ screen, ...state }} design={design}>
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
export const DesignMarkings: Story = { args: { screen: 'design', state: chosen, design: { tab: 'patterns' } } };
export const DesignPaint: Story = { args: { screen: 'design', state: chosen, design: { tab: 'paint' } } };
export const DesignExtras: Story = { args: { screen: 'design', state: chosen, design: { tab: 'extras' } } };
export const Name: Story = { args: { screen: 'name', state: chosen, design: {} } };
export const Order: Story = { args: { screen: 'order', state: chosen, design: { order: ORDER_READY } } };
export const DesignWithMakeItUnique: Story = { args: { screen: 'design', state: { ...chosen, bespokeEnabled: true } } };
export const Bespoke: Story = { args: { screen: 'bespoke', state: { ...chosen, bespokeEnabled: true } } };
export const BespokeAccepted: Story = {
  args: { screen: 'bespoke', state: { ...chosen, bespokeEnabled: true, bespoke: { request_id: 'j_story', ticket: 'PP-4821', message: "We'll message you when your one-off figurine is ready." } } },
};

export const StillThereOverlay: StoryObj = { render: () => <StillThere seconds={12} onStay={() => undefined} /> };
export const OfflineOverlay: StoryObj = { render: () => <Offline /> };
export const StaffPanelLocked: StoryObj = { render: () => <StaffPanel onClose={() => undefined} /> };
export const PhoneResultPage: StoryObj = { decorators: [(S) => <S />], render: () => <PhoneResult token="mock.demo" /> };

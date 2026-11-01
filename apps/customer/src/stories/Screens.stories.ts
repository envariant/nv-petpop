// One story per customer screen and overlay, with fixture data from the MSW handlers. The toolbar switches the
// visual direction and the mode (kiosk or app); the viewport menu has kiosk, phone, tablet and desktop sizes.
import type { Decorator, Meta, StoryObj } from '@storybook/vue3';
import { defineComponent, h, onMounted, ref, type Component, type PropType } from 'vue';
import { AppFrame } from '@petpop/ui-vue';
import { useDesign, type Tab } from '../stores/design';
import { useSession, type Screen } from '../stores/session';
import AttractScreen from '../screens/Attract.vue';
import SpeciesScreen from '../screens/Species.vue';
import BreedScreen from '../screens/Breed.vue';
import DesignScreen from '../screens/Design.vue';
import NameScreen from '../screens/Name.vue';
import OrderScreen from '../screens/Order.vue';
import BespokeScreen from '../screens/Bespoke.vue';
import StillThere from '../screens/StillThere.vue';
import Offline from '../screens/Offline.vue';
import StaffPanel from '../screens/StaffPanel.vue';
import PhoneResult from '../screens/PhoneResult.vue';
import { CORGI, ORDER_READY, SPEC } from './fixtures';

const SCREENS: Record<Screen, Component> = { attract: AttractScreen, species: SpeciesScreen, breed: BreedScreen, design: DesignScreen, name: NameScreen, order: OrderScreen, bespoke: BespokeScreen };

/** Session fixtures by name: story args stay primitive (Vue deep-traverses object args). */
const chosen = { species: 'dog' as const, breed: CORGI, spec: SPEC, sessionId: 's_story' };
const STATES = {
  none: {},
  dog: { species: 'dog' as const },
  chosen,
  bespoke: { ...chosen, bespokeEnabled: true },
  accepted: { ...chosen, bespokeEnabled: true, bespoke: { request_id: 'j_story', ticket: 'PP-4821', message: "We'll message you when your one-off figurine is ready." } },
};

/** Session state, plus (for the screens from Design on) a composition begun from the library release via MSW. */
const ScreenStory = defineComponent({
  name: 'ScreenStory',
  props: {
    screen: { type: String as PropType<Screen>, required: true },
    state: { type: String as PropType<keyof typeof STATES>, default: 'none' },
    tab: { type: String as PropType<Tab>, default: 'shape' },
    ordered: { type: Boolean, default: false },
  },
  setup(props) {
    const ready = ref(false);
    onMounted(async () => {
      const s = useSession();
      const d = useDesign();
      s.reset();
      Object.assign(s, STATES[props.state]);
      if (s.breed) {
        await d.begin(s.breed);
        d.setName('Biscuit');
        d.tab = props.tab;
        if (props.ordered) d.order = ORDER_READY;
      }
      s.screen = props.screen;
      ready.value = true;
    });
    return () => (ready.value ? h('div', { class: 'absolute inset-0', 'data-screen': props.screen }, [h(SCREENS[props.screen])]) : null);
  },
});

const withFrame: Decorator = (story, ctx) =>
  defineComponent({
    setup() {
      const inner = story(); // once: a new story component per render would remount it, and it resets the store
      const session = useSession();
      return () =>
        h('div', { style: 'height:100vh' }, [
          h(AppFrame, { species: session.species ?? 'dog', themeName: ctx.globals.theme as string }, () => [h('div', { class: 'relative h-full' }, [h(inner)])]),
        ]);
    },
  });

const meta: Meta<typeof ScreenStory> = { title: 'Customer/Screens', component: ScreenStory, decorators: [withFrame] };
export default meta;
type Story = StoryObj<typeof ScreenStory>;

export const Attract: Story = { args: { screen: 'attract' } };
export const Species: Story = { args: { screen: 'species' } };
export const Breed: Story = { args: { screen: 'breed', state: 'dog' } };
export const Design: Story = { args: { screen: 'design', state: 'chosen' } };
export const DesignMarkings: Story = { args: { screen: 'design', state: 'chosen', tab: 'patterns' } };
export const DesignPaint: Story = { args: { screen: 'design', state: 'chosen', tab: 'paint' } };
export const DesignExtras: Story = { args: { screen: 'design', state: 'chosen', tab: 'extras' } };
export const Name: Story = { args: { screen: 'name', state: 'chosen' } };
export const Order: Story = { args: { screen: 'order', state: 'chosen', ordered: true } };
export const DesignWithMakeItUnique: Story = { args: { screen: 'design', state: 'bespoke' } };
export const Bespoke: Story = { args: { screen: 'bespoke', state: 'bespoke' } };
export const BespokeAccepted: Story = { args: { screen: 'bespoke', state: 'accepted' } };

const show = (c: Component, props: Record<string, unknown> = {}) => () => defineComponent({ setup: () => () => h(c, props) });
export const StillThereOverlay: StoryObj = { render: show(StillThere, { seconds: 12 }) };
export const OfflineOverlay: StoryObj = { render: show(Offline) };
export const StaffPanelLocked: StoryObj = { render: show(StaffPanel) };
export const PhoneResultPage: StoryObj = { render: show(PhoneResult, { token: 'mock.demo' }) };

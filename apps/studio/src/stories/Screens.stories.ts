// One story per Studio screen and overlay, with the top bar and fixture data. Story args stay primitive (named
// fixtures): Vue deep-traverses object args.
import type { Decorator, Meta, StoryObj } from '@storybook/vue3';
import { defineComponent, h, onMounted, ref, type Component, type PropType } from 'vue';
import { AppFrame } from '@petpop/ui-vue';
import { setStaffToken, type ParseResponse, type ProgressEvent } from '@petpop/core';
import { SCREENS } from '../screens';
import StudioBar from '../components/StudioBar.vue';
import LoginScreen from '../screens/Login.vue';
import Offline from '../components/Offline.vue';
import QueuePanel from '../components/QueuePanel.vue';
import { useSession, type Screen } from '../stores/session';
import { useCurate } from '../stores/curate';
import { useManual } from '../stores/manual';
import { useProfiles } from '../stores/profiles';
import { MANUAL_TASKS } from '../mocks/manual';
import { PROFILES } from '../mocks/handlers';
import { BATCH, CORGI, PART_KIT, PART_KITS, PATTERN_ITEM, RELEASES, SPEC, VIEW_PREVIEWS, job } from './fixtures';
import { useParts } from '../stores/parts';

const OPERATOR = { username: 'operator', role: 'operator' as const };
const ADMIN = { username: 'admin', role: 'admin' as const };
const built = { species: 'dog' as const, breed: CORGI, spec: SPEC };
const ev = (status: string, stage: string, pct: number, message: string, queue_position = 0) =>
  [{ job_id: 'j', status, stage, pct, message, queue_position, preview_url: null, preview_kind: null }] as unknown as ProgressEvent[];
const FLAVOUR = { patch: {}, changed_fields: [], personality: [], free_text_unmapped: 'best boy', parser: 'rules', llm_available: false, flavour_only: true, blocked: false, ms: 2 } as unknown as ParseResponse;

/** Each fixture sets up the stores for one story. */
const FIXTURES: Record<string, () => void> = {
  none: () => undefined,
  batchBuilder: () => {
    const c = useCurate();
    c.breeds = ['pug', 'beagle'];
    c.variants = ['preset', 'big_ears'];
    c.seeds = 2;
    c.batches = [{ ...BATCH, figurines: [] }];
  },
  batch: () => (useCurate().batch = BATCH),
  library: () => {
    const c = useCurate();
    c.kind = 'pattern';
    c.items = [PATTERN_ITEM];
    c.selected = PATTERN_ITEM;
  },
  releases: () => {
    useSession().user = ADMIN;
    setStaffToken('mock.admin');
    useCurate().releases = RELEASES;
  },
  manual: () => Object.assign(useManual(), { tasks: MANUAL_TASKS, pending: 3, selectedId: MANUAL_TASKS[1].task_id }),
  manualViews: () => Object.assign(useManual(), { tasks: MANUAL_TASKS, pending: 3, selectedId: MANUAL_TASKS[2].task_id }),
  dog: () => (useSession().species = 'dog'),
  parts: () => (useParts().kits = PART_KITS),
  rigging: () => Object.assign(useParts(), { kit: JSON.parse(JSON.stringify(PART_KIT)), target: { type: 'slot', slot: 'front_left' }, view: 'assembled', poseId: 'curious' }),
  built: () => Object.assign(useSession(), built),
  highlights: () => Object.assign(useSession(), built, { highlights: ['ears.shape', 'body.build', 'colour.markings'] }),
  brief: () => Object.assign(useSession(), built, { briefText: 'Biscuit is a chunky corgi with one ear that flops, loves snacks' }),
  briefFlavour: () => Object.assign(useSession(), built, { briefText: 'the best boy', parse: FLAVOUR }),
  queued: () => Object.assign(useSession(), built, { job: job('queued'), events: ev('queued', 'queued', 0, 'Waiting for the studio', 2) }),
  views: () => Object.assign(useSession(), built, { job: job('running'), previews: VIEW_PREVIEWS, events: ev('running', 'C', 45, 'Four views ready') }),
  failed: () => Object.assign(useSession(), built, { job: job('failed'), previews: VIEW_PREVIEWS, events: ev('failed', 'D', 55, 'Stage D failed') }),
  result: () => Object.assign(useSession(), built, { jobId: 'j_story', job: job('done') }),
  resultFallback: () => Object.assign(useSession(), built, { jobId: 'j_story', job: job('done', { fallback: 'parametric' }) }),
  resultPrinted: () => Object.assign(useSession(), built, { jobId: 'j_story', job: job('fulfilled'), ticket: 'PP-4821' }),
};

const ScreenStory = defineComponent({
  name: 'ScreenStory',
  props: {
    screen: { type: String as PropType<Screen>, required: true },
    fixture: { type: String, default: 'none' },
  },
  setup(props) {
    const ready = ref(false);
    onMounted(() => {
      const s = useSession();
      s.clearFigure();
      s.user = OPERATOR;
      setStaffToken('mock.operator'); // the MSW handlers' staff token
      Object.assign(useProfiles(), { offered: PROFILES, choice: 'tripo-manual', pipeline: 'multiview', options: { hd_texture: true, hd_geometry: false, quad: false } });
      FIXTURES[props.fixture]();
      s.screen = props.screen;
      ready.value = true;
    });
    return () =>
      ready.value
        ? h('div', { class: 'flex h-full flex-col' }, [
          h(StudioBar),
          h('main', { class: 'relative min-h-0 flex-1' }, [h('div', { class: 'absolute inset-0', 'data-screen': props.screen }, [h(SCREENS[props.screen])])]),
        ])
        : null;
  },
});

const withFrame: Decorator = (story, ctx) =>
  defineComponent({
    setup() {
      const inner = story(); // once: a new story component per render would remount it, and it resets the stores
      const session = useSession();
      return () => h('div', { style: 'height:100vh' }, [h(AppFrame, { species: session.species ?? 'dog', themeName: ctx.globals.theme as string }, () => [h(inner)])]);
    },
  });

const meta: Meta<typeof ScreenStory> = { title: 'Studio/Screens', component: ScreenStory, decorators: [withFrame] };
export default meta;
type Story = StoryObj<typeof ScreenStory>;

export const Generate: Story = { args: { screen: 'generate', fixture: 'batchBuilder' } };
export const Review: Story = { args: { screen: 'review', fixture: 'batch' } };
export const Library: Story = { args: { screen: 'library', fixture: 'library' } };
export const Releases: Story = { args: { screen: 'releases', fixture: 'releases' } };
export const Manual: Story = { args: { screen: 'manual', fixture: 'manual' } };
export const ManualViews: Story = { args: { screen: 'manual', fixture: 'manualViews' } };
export const Parts: Story = { args: { screen: 'parts', fixture: 'parts' } };
export const Rigging: Story = { args: { screen: 'rigging', fixture: 'rigging' } };
export const Species: Story = { args: { screen: 'species' } };
export const Breed: Story = { args: { screen: 'breed', fixture: 'dog' } };
export const Build: Story = { args: { screen: 'build', fixture: 'built' } };
export const BuildWithBriefHighlights: Story = { args: { screen: 'build', fixture: 'highlights' } };
export const Brief: Story = { args: { screen: 'brief', fixture: 'brief' } };
export const BriefFlavourOnly: Story = { args: { screen: 'brief', fixture: 'briefFlavour' } };
export const NameAndGenerate: Story = { args: { screen: 'name', fixture: 'built' } };
export const GeneratingQueued: Story = { args: { screen: 'generating', fixture: 'queued' } };
export const GeneratingViews: Story = { args: { screen: 'generating', fixture: 'views' } };
export const GeneratingFailed: Story = { args: { screen: 'generating', fixture: 'failed' } };
export const Result: Story = { args: { screen: 'result', fixture: 'result' } };
export const ResultFallback: Story = { args: { screen: 'result', fixture: 'resultFallback' } };
export const ResultSentToPrint: Story = { args: { screen: 'result', fixture: 'resultPrinted' } };

const show = (c: Component, props: Record<string, unknown> = {}, before?: () => void) => () =>
  defineComponent({
    setup() {
      before?.();
      return () => h(c, props);
    },
  });
export const Login: StoryObj = { render: show(LoginScreen, {}, () => (useSession().user = null)) };
export const LoginFailed: StoryObj = { render: show(LoginScreen, {}, () => Object.assign(useSession(), { user: null, loginError: 'Wrong username or password.' })) };
export const QueueOverlay: StoryObj = { render: show(QueuePanel) };
export const OfflineOverlay: StoryObj = { render: show(Offline) };

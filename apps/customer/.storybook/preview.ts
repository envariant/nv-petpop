import type { Preview } from '@storybook/vue3';
import { setup } from '@storybook/vue3';
import { createPinia } from 'pinia';
import { setupWorker } from 'msw/browser';
import '@petpop/ui-vue/styles.css';
import { applyMode, mode } from '@petpop/ui-vue';
import { handlers } from '../src/mocks/handlers';

const pinia = createPinia();
setup((app) => {
  app.use(pinia);
});
applyMode();

let worker: Promise<unknown> | null = null;

const preview: Preview = {
  parameters: {
    layout: 'fullscreen',
    controls: { disable: true },
    actions: { disable: true },
    viewport: {
      viewports: {
        kiosk: { name: 'Kiosk 1080x1920', styles: { width: '540px', height: '960px' } },
        phone: { name: 'Phone', styles: { width: '390px', height: '844px' } },
        tablet: { name: 'Tablet landscape', styles: { width: '1180px', height: '820px' } },
        desktop: { name: 'Desktop', styles: { width: '1440px', height: '900px' } },
      },
    },
  },
  globalTypes: {
    theme: {
      description: 'Visual direction',
      defaultValue: 'candy',
      toolbar: { title: 'Direction', icon: 'paintbrush', items: ['candy', 'studio', 'toybox'], dynamicTitle: true },
    },
    mode: {
      description: 'Kiosk or app mode (decision 122)',
      defaultValue: mode,
      toolbar: { title: 'Mode', icon: 'mobile', items: ['app', 'kiosk'], dynamicTitle: true },
    },
  },
  decorators: [
    (story, ctx) => {
      // The mode is fixed per page load (as on a device): remember the choice and reload into it.
      const want = ctx.globals.mode as string;
      if (want !== mode) {
        try {
          localStorage.setItem('pp-mode', want);
        } catch {
          /* storage may be blocked */
        }
        location.reload();
      }
      return story();
    },
  ],
  loaders: [
    async () => {
      worker ??= setupWorker(...handlers).start({ onUnhandledRequest: 'bypass', quiet: true });
      await worker;
      return {};
    },
  ],
};
export default preview;

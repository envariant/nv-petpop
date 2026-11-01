import type { Preview } from '@storybook/vue3';
import { setup } from '@storybook/vue3';
import { createPinia } from 'pinia';
import { setupWorker } from 'msw/browser';
import '@petpop/ui-vue/styles.css';
import { applyMode } from '@petpop/ui-vue';
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
        desktop: { name: 'Desktop', styles: { width: '1440px', height: '900px' } },
        laptop: { name: 'Laptop', styles: { width: '1280px', height: '800px' } },
        tablet: { name: 'Tablet portrait', styles: { width: '820px', height: '1180px' } },
      },
    },
  },
  globalTypes: {
    theme: {
      description: 'Visual direction',
      defaultValue: 'candy',
      toolbar: { title: 'Direction', icon: 'paintbrush', items: ['candy', 'studio', 'toybox'], dynamicTitle: true },
    },
  },
  loaders: [
    async () => {
      worker ??= setupWorker(...handlers).start({ onUnhandledRequest: 'bypass', quiet: true });
      await worker;
      return {};
    },
  ],
};
export default preview;

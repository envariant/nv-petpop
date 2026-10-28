import type { Preview } from '@storybook/react';
import { setupWorker } from 'msw/browser';
import '../src/styles.css';
import { handlers } from '../src/mocks/handlers';

let worker: Promise<unknown> | null = null;

const preview: Preview = {
  parameters: { layout: 'fullscreen', controls: { disable: true }, actions: { disable: true } },
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

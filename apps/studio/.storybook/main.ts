import type { StorybookConfig } from '@storybook/vue3-vite';

const config: StorybookConfig = {
  stories: ['../src/**/*.stories.ts'],
  addons: ['@storybook/addon-essentials'],
  framework: { name: '@storybook/vue3-vite', options: {} },
  staticDirs: ['../public'],
  core: { disableTelemetry: true },
  viteFinal: (c) => (process.env.SB_NOMINIFY ? { ...c, build: { ...c.build, minify: false } } : c),
};
export default config;

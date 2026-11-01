import { createApp } from 'vue';
import { createPinia } from 'pinia';
import '@petpop/ui-vue/styles.css';
import { applyMode } from '@petpop/ui-vue';

async function boot() {
  applyMode();
  if (import.meta.env.VITE_MOCK === '1') {
    const { startMockWorker } = await import('./mocks/browser');
    await startMockWorker();
  }
  const { default: App } = await import('./App.vue');
  createApp(App).use(createPinia()).mount('#app');
}
void boot();

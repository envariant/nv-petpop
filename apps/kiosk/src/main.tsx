import React from 'react';
import ReactDOM from 'react-dom/client';
import '@petpop/ui/styles.css';

async function boot() {
  if (import.meta.env.VITE_MOCK === '1') {
    const { startMockWorker } = await import('./mocks/browser');
    await startMockWorker();
  }
  const { App } = await import('./App');
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}
void boot();

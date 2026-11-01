import { defineConfig, devices } from '@playwright/test';

// The Vue customer app (Vite, decision 122) against the standalone mock server; PP_BACKEND=real swaps in the real backend, and
// PP_GENAI_DOWN=1 points that backend's GenAI profile at hosts that do not answer (gate 7: the kiosk still sells).
const GENAI_DOWN = process.env.PP_GENAI_DOWN === '1'
  ? 'GENAI_PROFILE=mac-m4pro COMFY_URL=http://127.0.0.1:9 SHAPE_URL=http://127.0.0.1:9 OLLAMA_URL=http://127.0.0.1:9 GENAI_TOKEN=unreachable '
  : '';
const MOCK_PORT = 8013;
const WEB_PORT = 5183;
const ORIGIN = `http://127.0.0.1:${WEB_PORT}`;
// The app's mode is remembered in localStorage (decision 122): each project starts in its mode.
const inMode = (mode: 'kiosk' | 'app') => ({ cookies: [], origins: [{ origin: ORIGIN, localStorage: [{ name: 'pp-mode', value: mode }] }] });

export default defineConfig({
  testDir: 'tests', // e2e/ (gates 1 and 2) and gate7/ (gate 7)
  timeout: 90_000,
  expect: { timeout: 15_000 },
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: ORIGIN,
    hasTouch: true,
    launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] },
    trace: 'retain-on-failure',
  },
  // One kiosk (portrait touchscreen) and three app sizes: a phone, a tablet in landscape and a desktop.
  projects: [
    { name: 'kiosk', use: { ...devices['Pixel 7'], viewport: { width: 540, height: 960 }, isMobile: false, hasTouch: true, storageState: inMode('kiosk') } },
    { name: 'phone', testIgnore: /gate7/, use: { ...devices['Pixel 7'], viewport: { width: 390, height: 844 }, isMobile: false, hasTouch: true, storageState: inMode('app') } },
    { name: 'tablet', testIgnore: /gate7/, use: { viewport: { width: 1180, height: 820 }, hasTouch: true, storageState: inMode('app') } },
    { name: 'desktop', testIgnore: /gate7/, use: { viewport: { width: 1440, height: 900 }, hasTouch: true, storageState: inMode('app') } },
  ],
  webServer: [
    {
      // PP_BACKEND=real runs the same tests against the real backend (make dev mode, embedded worker).
      command: process.env.PP_BACKEND === 'real'
        ? `cd ../.. && rm -rf var/e2e && ${GENAI_DOWN}PYTHONPATH=.:mock-server:packages/core/python:packages/library/python PETPOP_VAR=var/e2e PETPOP_EMBED_WORKER=1 PETPOP_QUALITY=test PETPOP_MOCK_SPEED=0.02 PETPOP_STAFF_TOKEN=staffpin PETPOP_STUDIO_PASSWORD=petpop-dev KIOSK_BESPOKE=1 .venv/bin/python -m backend.api --port ${MOCK_PORT}`
        : `cd ../.. && PYTHONPATH=.:mock-server:packages/core/python:packages/library/python PETPOP_MOCK_SPEED=0.02 PETPOP_STAFF_TOKEN=staffpin PETPOP_STUDIO_PASSWORD=petpop-dev KIOSK_BESPOKE=1 .venv/bin/python -m mock_server --port ${MOCK_PORT}`,
      url: `http://127.0.0.1:${MOCK_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // PP_NATIVE=1 serves the pruned native bundle (npm run bundle:native) instead of the dev server: what a device runs.
      command: process.env.PP_NATIVE === '1'
        ? `VITE_API_TARGET=http://127.0.0.1:${MOCK_PORT} npx vite preview --outDir dist-native --port ${WEB_PORT} --strictPort`
        : `npm run -s sync-assets && VITE_API_TARGET=http://127.0.0.1:${MOCK_PORT} npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}/`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});

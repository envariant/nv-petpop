import { defineConfig, devices } from '@playwright/test';

// The SPA (Vite) talks to the standalone mock server, the only backend the front end uses in S1.
const MOCK_PORT = 8011;
const WEB_PORT = 5181;

export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    ...devices['Pixel 7'],
    viewport: { width: 540, height: 960 },
    hasTouch: true,
    isMobile: false,
    launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] },
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: `cd ../.. && PYTHONPATH=.:mock-server PETPOP_MOCK_SPEED=0.02 PETPOP_STAFF_TOKEN=staffpin .venv/bin/python -m mock_server --port ${MOCK_PORT}`,
      url: `http://127.0.0.1:${MOCK_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npm run -s sync-assets && VITE_API_TARGET=http://127.0.0.1:${MOCK_PORT} npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}/`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});

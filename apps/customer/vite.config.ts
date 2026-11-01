import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';

const apiTarget = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
  base: '/', // absolute: the phone page lives at /r/<token>; Capacitor serves the build at its origin's root too
  plugins: [vue()],
  resolve: {
    dedupe: ['vue', 'three'],
    alias: {
      '@data': fileURLToPath(new URL('../../data', import.meta.url)),
      '@fixtures': fileURLToPath(new URL('../../fixtures', import.meta.url)),
      '@mockscripts': fileURLToPath(new URL('../../mock-server/scripts', import.meta.url)),
      '@assets': fileURLToPath(new URL('../../assets', import.meta.url)),
    },
  },
  server: {
    port: 5175,
    host: '127.0.0.1',
    fs: { allow: ['../..'] },
    proxy: { '/api': { target: apiTarget, ws: true, changeOrigin: false } },
  },
  preview: { port: 7175, host: '127.0.0.1', proxy: { '/api': { target: apiTarget, ws: true } } },
  build: { outDir: 'dist', chunkSizeWarningLimit: 2000 },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
});

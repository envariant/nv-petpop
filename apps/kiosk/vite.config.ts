import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

const apiTarget = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@data': fileURLToPath(new URL('../../data', import.meta.url)),
      '@fixtures': fileURLToPath(new URL('../../fixtures', import.meta.url)),
      '@mockscripts': fileURLToPath(new URL('../../mock-server/scripts', import.meta.url)),
      '@assets': fileURLToPath(new URL('../../assets', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    host: '127.0.0.1',
    fs: { allow: ['../..'] },
    proxy: {
      '/api': { target: apiTarget, ws: true, changeOrigin: false },
    },
  },
  preview: { port: 4173, host: '127.0.0.1', proxy: { '/api': { target: apiTarget, ws: true } } },
  build: { outDir: 'dist', chunkSizeWarningLimit: 2000 },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
} as never);

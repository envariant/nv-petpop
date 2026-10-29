import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

const apiTarget = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
  base: '/studio/',
  plugins: [react()],
  resolve: {
    // One copy of React and three across the app and the workspace packages.
    dedupe: ['react', 'react-dom', 'three', '@react-three/fiber'],
    alias: {
      '@data': fileURLToPath(new URL('../../data', import.meta.url)),
      '@fixtures': fileURLToPath(new URL('../../fixtures', import.meta.url)),
      '@mockscripts': fileURLToPath(new URL('../../mock-server/scripts', import.meta.url)),
      '@assets': fileURLToPath(new URL('../../assets', import.meta.url)),
    },
  },
  server: {
    port: 5174,
    host: '127.0.0.1',
    fs: { allow: ['../..'] },
    proxy: {
      '/api': { target: apiTarget, ws: true, changeOrigin: false },
    },
  },
  preview: { port: 7174, host: '127.0.0.1', proxy: { '/api': { target: apiTarget, ws: true } } },
  build: { outDir: 'dist', chunkSizeWarningLimit: 2000 },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
} as never);

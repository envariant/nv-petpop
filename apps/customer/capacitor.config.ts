// Capacitor (decision 122): the same Vue build as an iOS and Android app. The API origin is baked in at build time
// (VITE_API_ORIGIN); the backend allows the Capacitor origins (backend/api/contract.py). A kiosk build sets
// VITE_MODE=kiosk and runs locked to the app (Android lock-task mode, iPad Guided Access).
import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: process.env.PETPOP_APP_ID ?? 'com.petpop.app',
  appName: 'PetPop',
  webDir: 'dist-native', // npm run bundle:native: the web build pruned to what a device needs
  backgroundColor: '#FFF7F0',
  ios: { contentInset: 'never' },
  android: { allowMixedContent: false },
};

export default config;

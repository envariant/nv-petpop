/// <reference types="vite/client" />
declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<object, object, unknown>;
  export default component;
}
interface ImportMetaEnv {
  readonly VITE_MOCK?: string;
  readonly VITE_MODE?: 'kiosk' | 'app';
}

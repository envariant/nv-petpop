import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue';
import { StudioApi } from '@petpop/core';

/** Polls /health; after two failures the studio shows "Back in a moment" and keeps retrying. */
export function useOnline(): Ref<boolean> {
  const online = ref(true);
  let fails = 0;
  let timer = 0;
  const check = async () => {
    try {
      await StudioApi.health();
      fails = 0;
      online.value = true;
    } catch {
      fails += 1;
      if (fails >= 2) online.value = false;
    }
  };
  onMounted(() => {
    void check();
    timer = window.setInterval(check, 2500);
  });
  onBeforeUnmount(() => clearInterval(timer));
  return online;
}

/** Run `f` now and every `ms` while the component is mounted. */
export function usePoll(f: () => unknown, ms: number): void {
  let timer = 0;
  onMounted(() => {
    void f();
    timer = window.setInterval(() => void f(), ms);
  });
  onBeforeUnmount(() => clearInterval(timer));
}

/** "Snake_case" vocabulary to words. */
export const words = (s: string) => s.replace(/_/g, ' ');

// Kiosk behaviour as composables: the idle countdown, the offline watch and the five-tap staff corner.
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue';
import { KioskApi } from '@petpop/core';
import { useSession } from './stores/session';

/** After idleSeconds without a touch (any screen but Attract) show the countdown, then wipe the session.
 *  ?idle=&countdown= override the session policy (seconds) for tests and demos. */
export function useIdle(enabled: boolean): { countdown: Ref<number | null>; dismiss: () => void } {
  const s = useSession();
  const params = new URLSearchParams(location.search);
  const countdown = ref<number | null>(null);
  let last = Date.now();
  const touch = () => (last = Date.now());
  let timer = 0;
  onMounted(() => {
    window.addEventListener('pointerdown', touch, true);
    window.addEventListener('keydown', touch, true);
    timer = window.setInterval(() => {
      if (!enabled || s.screen === 'attract') return;
      const idle = Number(params.get('idle') ?? s.idleSeconds);
      const cd = Number(params.get('countdown') ?? s.countdownSeconds);
      const t = (Date.now() - last) / 1000;
      if (t >= idle + cd) {
        countdown.value = null;
        s.reset();
      } else countdown.value = t >= idle ? Math.ceil(idle + cd - t) : null;
    }, 200);
  });
  watch(() => s.screen, () => {
    last = Date.now();
    countdown.value = null;
  });
  onBeforeUnmount(() => {
    window.removeEventListener('pointerdown', touch, true);
    window.removeEventListener('keydown', touch, true);
    clearInterval(timer);
  });
  return { countdown, dismiss: () => ((last = Date.now()), (countdown.value = null)) };
}

/** Polls /health; two misses in a row show "Back in a moment" until it answers again. */
export function useOnline(): Ref<boolean> {
  const online = ref(true);
  let fails = 0;
  let timer = 0;
  const check = async () => {
    try {
      await KioskApi.health();
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

/** Five taps within 3 s. */
export function useFiveTap(onOpen: () => void): () => void {
  let taps: number[] = [];
  return () => {
    const now = Date.now();
    taps = [...taps.filter((t) => now - t < 3000), now];
    if (taps.length >= 5) {
      taps = [];
      onOpen();
    }
  };
}

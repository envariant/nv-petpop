// Kiosk or app (decision 122). `kiosk`: fullscreen touch kiosk (on-screen keyboard, idle wipe, staff panel, sizes
// scaled to the screen). `app`: the store app and the browser (system keyboard, normal navigation).
// Order: ?mode=, then a remembered choice (a kiosk is set up once with ?mode=kiosk), then the build's VITE_MODE.
export type Mode = 'kiosk' | 'app';

const KEY = 'pp-mode';

export function detectMode(): Mode {
  // An app that has one mode only (Studio: staff at a desk) locks it at build time: VITE_MODE_LOCK.
  const locked = import.meta.env.VITE_MODE_LOCK;
  if (locked === 'kiosk' || locked === 'app') return locked;
  const q = new URLSearchParams(location.search).get('mode');
  if (q === 'kiosk' || q === 'app') {
    try {
      localStorage.setItem(KEY, q);
    } catch {
      /* storage may be blocked */
    }
    return q;
  }
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'kiosk' || saved === 'app') return saved;
  } catch {
    /* storage may be blocked */
  }
  return import.meta.env.VITE_MODE === 'kiosk' ? 'kiosk' : 'app';
}

export const mode: Mode = detectMode();
export const isKiosk = mode === 'kiosk';

/** Apply the mode to <html>, where it sets the type scale (frame.css). */
export function applyMode(): void {
  document.documentElement.dataset.mode = mode;
}

export function theme(): string {
  const t = new URLSearchParams(location.search).get('theme');
  return t === 'studio' || t === 'toybox' ? t : 'candy';
}

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ');

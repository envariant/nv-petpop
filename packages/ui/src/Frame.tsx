// The fixed 1080x1920 portrait canvas scaled to the window: the kiosk screen, and the Studio's working frame.
import { useEffect, useState, type ReactNode } from 'react';

export const W = 1080;
export const H = 1920;

export function theme(): string {
  const t = new URLSearchParams(location.search).get('theme');
  return t === 'studio' || t === 'toybox' ? t : 'candy';
}

export function KioskFrame({ children, species, themeName }: { children: ReactNode; species?: string | null; themeName?: string }) {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const fit = () => setScale(Math.min(window.innerWidth / W, window.innerHeight / H));
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, []);
  return (
    <div className="fixed inset-0 bg-black" style={{ overflow: 'clip' }}>
      <div
        className="kiosk absolute left-1/2 top-1/2"
        data-theme={themeName ?? theme()}
        data-species={species ?? 'dog'}
        style={{ width: W, height: H, overflow: 'clip', transform: `translate(-50%, -50%) scale(${scale})`, transformOrigin: 'center' }}
      >
        {children}
      </div>
    </div>
  );
}

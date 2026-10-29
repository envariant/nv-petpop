// Touch primitives: every control is a tile, swatch or chip with a >= 48 px hit area.
import { motion } from 'framer-motion';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ');

export function Button({ children, variant = 'primary', className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'soft' }) {
  return (
    <motion.button
      whileTap={{ scale: 0.96 }}
      className={cx(
        'hit rounded-tile px-10 py-6 font-display text-4xl font-semibold transition-colors disabled:opacity-40',
        variant === 'primary' && 'bg-accent text-white shadow-soft',
        variant === 'soft' && 'bg-card text-ink shadow-soft',
        variant === 'ghost' && 'bg-transparent text-muted',
        className,
      )}
      {...(rest as object)}
    >
      {children}
    </motion.button>
  );
}

export function Tile({ selected, highlight, onClick, children, label, testId, className }: { selected?: boolean; highlight?: boolean; onClick?: () => void; children?: ReactNode; label: string; testId?: string; className?: string }) {
  return (
    <motion.button
      whileTap={{ scale: 0.95 }}
      aria-pressed={selected}
      aria-label={label}
      data-testid={testId}
      onClick={onClick}
      className={cx(
        'hit flex flex-col items-center justify-center gap-2 rounded-tile border-4 bg-card p-3 shadow-soft transition-colors',
        selected ? 'border-accent' : 'border-transparent',
        highlight && 'ring-highlight',
        className,
      )}
    >
      {children}
      <span className="font-display text-2xl font-medium leading-tight">{label}</span>
    </motion.button>
  );
}

export function Swatch({ hex, selected, highlight, onClick, label, testId, size = 84 }: { hex: string; selected?: boolean; highlight?: boolean; onClick?: () => void; label: string; testId?: string; size?: number }) {
  return (
    <motion.button
      whileTap={{ scale: 0.9 }}
      aria-label={label}
      aria-pressed={selected}
      data-testid={testId}
      onClick={onClick}
      className={cx('hit shrink-0 rounded-full border-4 shadow-soft', selected ? 'border-accent' : 'border-card', highlight && 'ring-highlight')}
      style={{ width: size, height: size, background: hex }}
    />
  );
}

export function Chip({ selected, highlight, onClick, children, testId }: { selected?: boolean; highlight?: boolean; onClick?: () => void; children: ReactNode; testId?: string }) {
  return (
    <motion.button
      whileTap={{ scale: 0.95 }}
      aria-pressed={selected}
      data-testid={testId}
      onClick={onClick}
      className={cx('hit rounded-full border-4 px-7 py-3 font-display text-2xl', selected ? 'border-accent bg-accent text-white' : 'border-line bg-card text-ink', highlight && 'ring-highlight')}
    >
      {children}
    </motion.button>
  );
}

export function Section({ title, children, testId }: { title: string; children: ReactNode; testId?: string }) {
  return (
    <section className="mb-10" data-testid={testId}>
      <h3 className="mb-4 font-display text-3xl font-semibold">{title}</h3>
      {children}
    </section>
  );
}

export function Row({ children }: { children: ReactNode }) {
  return <div className="no-scrollbar flex gap-4 overflow-x-auto pb-2">{children}</div>;
}

export function Title({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <header className="mb-10">
      <h1 className="font-display text-7xl font-semibold leading-tight">{children}</h1>
      {sub && <p className="mt-3 text-3xl text-muted">{sub}</p>}
    </header>
  );
}

export { cx };

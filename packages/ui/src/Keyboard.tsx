// On-screen keyboard: the only way to type on the kiosk (breed search, pet name, brief, contact details).
import { motion } from 'framer-motion';
import { useState } from 'react';

const ROWS = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm'];

export function Keyboard({ value, onChange, maxLength = 500, onDone, doneLabel = 'Done', compact, capitalize = true, contact }: { value: string; onChange: (v: string) => void; maxLength?: number; onDone?: () => void; doneLabel?: string; compact?: boolean; capitalize?: boolean; contact?: boolean }) {
  const [shift, setShift] = useState(capitalize && value.length === 0);
  const press = (k: string) => {
    if (value.length >= maxLength) return;
    const ch = shift ? k.toUpperCase() : k;
    onChange(value + ch);
    setShift(false);
  };
  const key = (label: string, onClick: () => void, wide = 1, testId?: string) => (
    <motion.button
      key={label + wide}
      whileTap={{ scale: 0.9 }}
      data-testid={testId ?? `key-${label}`}
      onClick={onClick}
      className="hit rounded-2xl bg-card font-display text-3xl shadow-soft"
      style={{ flex: wide, height: compact ? 72 : 88 }}
    >
      {label}
    </motion.button>
  );
  return (
    <div className="select-none rounded-tile bg-line/60 p-4" data-testid="keyboard">
      {contact && (
        <div className="mb-3 flex gap-2">
          {'1234567890'.split('').map((k) => key(k, () => press(k), 1, `key-${k}`))}
          {key('@', () => press('@'), 1, 'key-at')}
          {key('+', () => press('+'), 1, 'key-plus')}
        </div>
      )}
      {ROWS.map((r, i) => (
        <div key={r} className="mb-3 flex gap-2" style={{ paddingLeft: i * 28, paddingRight: i * 28 }}>
          {r.split('').map((k) => key(shift ? k.toUpperCase() : k, () => press(k), 1, `key-${k}`))}
        </div>
      ))}
      <div className="flex gap-2">
        {key('⇧', () => setShift(!shift), 1.3, 'key-shift')}
        {key(',', () => press(','), 1, 'key-comma')}
        {key('space', () => press(' '), 5, 'key-space')}
        {key('.', () => press('.'), 1, 'key-dot')}
        {key('⌫', () => onChange(value.slice(0, -1)), 1.5, 'key-backspace')}
        {onDone && key(doneLabel, onDone, 2, 'key-done')}
      </div>
    </div>
  );
}

export function TextDisplay({ value, placeholder, testId, lines = 1 }: { value: string; placeholder: string; testId?: string; lines?: number }) {
  return (
    <div data-testid={testId} className="rounded-tile border-4 border-line bg-card px-8 py-5 text-4xl" style={{ minHeight: 40 + lines * 52 }}>
      {value ? <span>{value}</span> : <span className="text-muted">{placeholder}</span>}
      <span className="ml-1 inline-block h-10 w-1 animate-pulse bg-accent align-middle" />
    </div>
  );
}

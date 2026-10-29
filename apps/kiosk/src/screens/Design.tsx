// Design: where the customer assembles and paints the figurine from the library (BRIEF Section 16). The parts
// and pattern tools arrive with library mode (M7); until then it shows the breed's preset on the base mesh.
import { useState } from 'react';
import { PreviewFigure } from '@petpop/viewer';
import { Button, Keyboard, TextDisplay, Title } from '@petpop/ui';
import { useSession } from '../store/session';

export function DesignScreen() {
  const s = useSession();
  if (!s.spec || !s.breed) return null;
  return (
    <div className="flex h-full flex-col px-16 pb-12 pt-24" data-testid="design">
      <Title sub="Your figurine, live. Parts and pattern tools are coming next.">Design your {s.breed.label}</Title>
      <div className="relative flex-1 overflow-hidden rounded-tile bg-card shadow-soft" data-testid="design-preview">
        <PreviewFigure spec={s.spec} />
      </div>
      {s.bespokeEnabled && (
        <div className="mt-10 flex items-center justify-between gap-8 rounded-tile bg-card p-8 shadow-soft">
          <p className="flex-1 text-3xl text-muted">Want a one-off shape made just for your pet? Our studio can sculpt it.</p>
          <Button variant="soft" onClick={() => s.go('bespoke')} data-testid="make-unique">
            Make it unique
          </Button>
        </div>
      )}
    </div>
  );
}

/** "Make it unique" (KIOSK_BESPOKE): a studio job and a "we'll message you" promise, never a Generating screen. */
export function BespokeScreen() {
  const s = useSession();
  const [contact, setContact] = useState('');
  const [busy, setBusy] = useState(false);
  const send = async () => {
    setBusy(true);
    try {
      await s.requestBespoke(contact);
    } finally {
      setBusy(false);
    }
  };
  if (s.bespoke) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-10 px-16 text-center" data-testid="bespoke-accepted">
        <div className="text-9xl">💌</div>
        <Title sub={s.bespoke.message}>We're on it!</Title>
        <div className="rounded-tile bg-accent px-12 py-8 font-display text-5xl text-white" data-testid="bespoke-ticket">
          Ticket <b>{s.bespoke.ticket}</b>
        </div>
        <Button onClick={s.reset} data-testid="bespoke-done">
          Done
        </Button>
      </div>
    );
  }
  return (
    <div className="flex h-full flex-col px-16 pb-10 pt-24" data-testid="bespoke">
      <Title sub="Our studio sculpts a one-off figure from your design. It takes a while, so we'll message you when it's ready.">Make it unique</Title>
      <p className="mb-4 text-3xl text-muted">Phone or email (optional; staff can also look it up by ticket)</p>
      <TextDisplay value={contact} placeholder="07700 900123" testId="bespoke-contact" />
      {s.error && (
        <p className="mt-6 text-3xl font-semibold text-accent2" data-testid="bespoke-error">
          {s.error}
        </p>
      )}
      <div className="mt-auto">
        <Keyboard value={contact} onChange={setContact} maxLength={80} onDone={() => void send()} doneLabel={busy ? 'Sending…' : 'Send'} compact capitalize={false} contact />
        <Button variant="ghost" className="mt-6" onClick={() => s.go('design')} data-testid="bespoke-back">
          ‹ Back to design
        </Button>
      </div>
    </div>
  );
}

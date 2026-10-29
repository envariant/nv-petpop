import { Button } from '@petpop/ui';

export function NavBar({ back, next, nextLabel = 'Next', nextDisabled, extra }: { back?: () => void; next?: () => void; nextLabel?: string; nextDisabled?: boolean; extra?: React.ReactNode }) {
  return (
    <nav className="flex items-center justify-between gap-6 border-t-4 border-line bg-paper px-12 py-8">
      {back ? (
        <Button variant="soft" onClick={back} data-testid="nav-back">
          ‹ Back
        </Button>
      ) : (
        <span />
      )}
      {extra}
      {next && (
        <Button onClick={next} disabled={nextDisabled} data-testid="nav-next">
          {nextLabel} ›
        </Button>
      )}
    </nav>
  );
}

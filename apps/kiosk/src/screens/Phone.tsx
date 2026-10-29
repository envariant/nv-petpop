// The phone result page /r/:token, opened from the QR code (public, signed, expires in 7 days).
import { useEffect, useState } from 'react';
import { KioskApi } from '@petpop/core';
import type { ResultPage } from '@petpop/core';
import { GlbFigure } from '@petpop/viewer';

export function PhoneResult({ token }: { token: string }) {
  const [page, setPage] = useState<ResultPage | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    KioskApi.result(token).then(setPage).catch((e: { status?: number }) => setErr(e.status === 410 ? 'This link has expired.' : 'We could not find this figurine.'));
  }, [token]);
  return (
    <div className="kiosk flex min-h-full flex-col items-center px-6 py-10" data-theme="candy" data-testid="phone-result">
      <div className="font-display text-5xl font-semibold">
        Pet<span className="text-accent">Pop</span>
      </div>
      {err && <p className="mt-10 text-xl">{err}</p>}
      {page && (
        <>
          <h1 className="mt-6 font-display text-4xl">{page.pet_name ?? 'Your pet'}</h1>
          <p className="text-lg text-muted">{page.breed_label}</p>
          <div className="my-6 h-[60vh] w-full max-w-md rounded-[28px] bg-card shadow-soft">
            <GlbFigure url={page.glb_url} interactive fallbackImage={page.thumbnail_url ?? undefined} />
          </div>
          <a className="rounded-full bg-accent px-8 py-4 font-display text-2xl text-white" href={page.glb_url} download={`${page.pet_name ?? 'petpop'}.glb`}>
            Download 3D file
          </a>
          <p className="mt-4 text-sm text-muted">Link expires {new Date(page.expires_at).toLocaleDateString()}</p>
        </>
      )}
    </div>
  );
}

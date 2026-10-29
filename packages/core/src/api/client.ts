// Typed client generated from data/schema/openapi.json (npm run gen:client -w @petpop/core). One origin: each app
// only ever talks to its own API. KioskApi is the customer kiosk's surface (anonymous session); StudioApi is the
// staff app's (bearer token from POST /studio/auth/login). They share only the meta routes.
import createClient from 'openapi-fetch';
import type { paths } from './schema';
import type {
  Batch, BatchCreate, BatchList, ItemKind, ItemStatus, LibraryItem, LibraryItemList, LibraryItemPatch, ReleaseInfo, ReleaseList,
  ReviewDecision,
  BespokeAccepted, BreedList, CompositionBody, CompositionStatus, ExportAccepted, FulfilResponse, Job, JobCreated, KioskOps,
  KioskOrder, LibraryFamilies, LibraryParts, LibraryPatterns, LibraryRelease, ParseResponse, PetSpec, ProgressEvent, ResultPage, Session,
  Species, StaffQueue, StaffToken, StaffUser,
} from './types';

export const api = createClient<paths>({ baseUrl: typeof window !== 'undefined' ? window.location.origin : 'http://localhost' });

export class ApiFailure extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === 'string' ? detail : `API error ${status}`);
  }
}

function unwrap<T>(r: { data?: T; error?: unknown; response: Response }): T {
  if (r.data === undefined || r.error !== undefined) {
    const detail = (r.error as { detail?: unknown } | undefined)?.detail ?? r.error;
    throw new ApiFailure(r.response.status, detail);
  }
  return r.data;
}

export const MetaApi = {
  health: async () => unwrap(await api.GET('/api/v1/health')),
  result: async (token: string): Promise<ResultPage> => unwrap(await api.GET('/api/v1/r/{token}', { params: { path: { token } } })),
};

export const KioskApi = {
  ...MetaApi,
  createSession: async (kioskId = 'kiosk-1'): Promise<Session> =>
    unwrap(await api.POST('/api/v1/kiosk/sessions', { body: { kiosk_id: kioskId } })),
  breeds: async (species: Species, q?: string): Promise<BreedList> =>
    unwrap(await api.GET('/api/v1/kiosk/breeds', { params: { query: { species, q: q || undefined } } })),
  ops: async (pin: string): Promise<KioskOps> => unwrap(await api.GET('/api/v1/kiosk/ops', { headers: { 'X-Staff-Token': pin } } as never)),
  reprint: async (pin: string, compositionId: string): Promise<KioskOrder> =>
    unwrap(await api.POST('/api/v1/kiosk/ops/orders/{composition_id}/reprint', { params: { path: { composition_id: compositionId } }, headers: { 'X-Staff-Token': pin } } as never)),
  // library mode: the active release and the composition, the order record
  libraryRelease: async (species: Species): Promise<LibraryRelease> =>
    unwrap(await api.GET('/api/v1/kiosk/library/{species}', { params: { path: { species } } })),
  libraryFamilies: async (species: Species): Promise<LibraryFamilies> =>
    unwrap(await api.GET('/api/v1/kiosk/library/{species}/families', { params: { path: { species } } })),
  libraryParts: async (species: Species, region?: string): Promise<LibraryParts> =>
    unwrap(await api.GET('/api/v1/kiosk/library/{species}/parts', { params: { path: { species }, query: { region: region as never } } })),
  libraryPatterns: async (species: Species): Promise<LibraryPatterns> =>
    unwrap(await api.GET('/api/v1/kiosk/library/{species}/patterns', { params: { path: { species } } })),
  createComposition: async (sessionId: string, composition: CompositionBody): Promise<CompositionStatus> =>
    unwrap(await api.POST('/api/v1/kiosk/compositions', { body: { session_id: sessionId, composition } })),
  composition: async (compositionId: string): Promise<CompositionStatus> =>
    unwrap(await api.GET('/api/v1/kiosk/compositions/{composition_id}', { params: { path: { composition_id: compositionId } } })),
  exportComposition: async (compositionId: string): Promise<ExportAccepted> =>
    unwrap(await api.POST('/api/v1/kiosk/compositions/{composition_id}/export', { params: { path: { composition_id: compositionId } } })),
  bespoke: async (compositionId: string, contact?: string): Promise<BespokeAccepted> =>
    unwrap(await api.POST('/api/v1/kiosk/compositions/{composition_id}/bespoke', { params: { path: { composition_id: compositionId } }, body: { contact: contact || null } })),
};

// ------------------------------------------------------------------ studio: bearer token
let staffToken: string | null = null;
export function setStaffToken(token: string | null): void {
  staffToken = token;
}
export function getStaffToken(): string | null {
  return staffToken;
}
const auth = () => ({ headers: staffToken ? { Authorization: `Bearer ${staffToken}` } : {} }) as never;

export const StudioApi = {
  ...MetaApi,
  login: async (username: string, password: string): Promise<StaffToken> =>
    unwrap(await api.POST('/api/v1/studio/auth/login', { body: { username, password } })),
  me: async (): Promise<StaffUser> => unwrap(await api.GET('/api/v1/studio/auth/me', auth())),
  breeds: async (species: Species, q?: string): Promise<BreedList> =>
    unwrap(await api.GET('/api/v1/studio/breeds', { params: { query: { species, q: q || undefined } }, ...(auth() as object) })),
  parse: async (species: Species, current: PetSpec, text: string, tapped: string[]): Promise<ParseResponse> =>
    unwrap(await api.POST('/api/v1/studio/spec/parse', { body: { species, current_spec: current, text, tapped_fields: tapped }, ...(auth() as object) })),
  createJob: async (spec: PetSpec): Promise<JobCreated> => unwrap(await api.POST('/api/v1/studio/jobs', { body: { spec }, ...(auth() as object) })),
  job: async (id: string): Promise<Job> => unwrap(await api.GET('/api/v1/studio/jobs/{job_id}', { params: { path: { job_id: id } }, ...(auth() as object) })),
  tweak: async (id: string, patch: Record<string, unknown>): Promise<JobCreated> =>
    unwrap(await api.POST('/api/v1/studio/jobs/{job_id}/tweak', { params: { path: { job_id: id } }, body: { patch }, ...(auth() as object) })),
  fulfil: async (id: string): Promise<FulfilResponse> =>
    unwrap(await api.POST('/api/v1/studio/jobs/{job_id}/fulfil', { params: { path: { job_id: id } }, ...(auth() as object) })),
  queue: async (): Promise<StaffQueue> => unwrap(await api.GET('/api/v1/studio/queue', auth())),
  retry: async (id: string): Promise<JobCreated> =>
    unwrap(await api.POST('/api/v1/studio/jobs/{job_id}/retry', { params: { path: { job_id: id } }, ...(auth() as object) })),
  // library curation (M8)
  createBatch: async (body: BatchCreate): Promise<Batch> => unwrap(await api.POST('/api/v1/studio/batches', { body, ...(auth() as object) })),
  batches: async (): Promise<BatchList> => unwrap(await api.GET('/api/v1/studio/batches', auth())),
  batch: async (id: string): Promise<Batch> =>
    unwrap(await api.GET('/api/v1/studio/batches/{batch_id}', { params: { path: { batch_id: id } }, ...(auth() as object) })),
  review: async (id: string, decisions: ReviewDecision[]): Promise<Batch> =>
    unwrap(await api.POST('/api/v1/studio/batches/{batch_id}/review', { params: { path: { batch_id: id } }, body: { decisions }, ...(auth() as object) })),
  libraryItems: async (species: Species, kind?: ItemKind, status?: ItemStatus): Promise<LibraryItemList> =>
    unwrap(await api.GET('/api/v1/studio/library/{species}', { params: { path: { species }, query: { kind, status } }, ...(auth() as object) })),
  editItem: async (species: Species, kind: ItemKind, id: string, patch: LibraryItemPatch): Promise<LibraryItem> =>
    unwrap(await api.PATCH('/api/v1/studio/library/{species}/{kind}/{item_id}', { params: { path: { species, kind, item_id: id } }, body: patch, ...(auth() as object) })),
  publishItem: async (species: Species, kind: ItemKind, id: string): Promise<LibraryItem> =>
    unwrap(await api.POST('/api/v1/studio/library/{species}/{kind}/{item_id}/publish', { params: { path: { species, kind, item_id: id } }, ...(auth() as object) })),
  unpublishItem: async (species: Species, kind: ItemKind, id: string): Promise<LibraryItem> =>
    unwrap(await api.POST('/api/v1/studio/library/{species}/{kind}/{item_id}/unpublish', { params: { path: { species, kind, item_id: id } }, ...(auth() as object) })),
  releases: async (): Promise<ReleaseList> => unwrap(await api.GET('/api/v1/studio/releases', auth())),
  createRelease: async (species: Species): Promise<ReleaseInfo> =>
    unwrap(await api.POST('/api/v1/studio/releases', { body: { species }, ...(auth() as object) })),
};

export function eventsUrl(jobId: string): string {
  const { protocol, host } = window.location;
  return `${protocol === 'https:' ? 'wss' : 'ws'}://${host}/api/v1/studio/jobs/${jobId}/events?token=${encodeURIComponent(staffToken ?? '')}`;
}

/** Subscribe to a studio job's progress: WebSocket first, polling GET /studio/jobs/{id} as the fallback. Returns unsubscribe. */
export function subscribeJob(jobId: string, onEvent: (e: ProgressEvent) => void, onJob?: (j: Job) => void): () => void {
  let closed = false;
  let ws: WebSocket | null = null;
  let poll: ReturnType<typeof setInterval> | null = null;
  const terminal = new Set(['done', 'failed', 'fulfilled']);
  const startPolling = () => {
    if (poll || closed) return;
    poll = setInterval(async () => {
      try {
        const j = await StudioApi.job(jobId);
        onJob?.(j);
        onEvent({ job_id: j.job_id, status: j.status, stage: j.stage, pct: j.pct, message: j.message, queue_position: j.queue_position, preview_url: null, preview_kind: null });
        if (terminal.has(j.status) && poll) clearInterval(poll);
      } catch {
        /* offline overlay handles it */
      }
    }, 1000);
  };
  try {
    ws = new WebSocket(eventsUrl(jobId));
    ws.onmessage = (m) => {
      const ev = JSON.parse(m.data as string) as ProgressEvent;
      onEvent(ev);
      if (terminal.has(ev.status)) StudioApi.job(jobId).then((j) => onJob?.(j)).catch(() => undefined);
    };
    ws.onerror = () => startPolling();
    ws.onclose = (e) => {
      if (!closed && e.code !== 1000) startPolling();
    };
  } catch {
    startPolling();
  }
  return () => {
    closed = true;
    ws?.close();
    if (poll) clearInterval(poll);
  };
}

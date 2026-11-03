// Typed client generated from data/schema/openapi.json (npm run gen:client -w @petpop/core). One origin: each app
// only ever talks to its own API. KioskApi is the customer kiosk's surface (anonymous session); StudioApi is the
// staff app's (bearer token from POST /studio/auth/login). They share only the meta routes.
import createClient from 'openapi-fetch';
import type { paths } from './schema';
import type {
  GenaiProfiles, ManualTask, ManualTaskList,
  Batch, BatchCreate, BatchList, ItemKind, ItemStatus, LibraryItem, LibraryItemList, LibraryItemPatch, ReleaseInfo, ReleaseList,
  ReviewDecision,
  BespokeAccepted, BreedList, CompositionBody, CompositionStatus, ExportAccepted, FulfilResponse, Job, JobCreated, KioskOps,
  KioskOrder, LibraryFamilies, Payment, PaymentMethod, Account, AccountOrders, AccountSession, AuthConfig, Channel, CodeSent,
  OrderContact, Provider, PartKit, PartKitList, PartKitSetup, PartRigPatch, PartUploadResult, LibraryParts, LibraryPatterns, LibraryRelease, ParseResponse, PetSpec, ProgressEvent, ResultPage, Session,
  Species, StaffQueue, StaffToken, StaffUser,
} from './types';

/** Where the API is: the page's own origin, or VITE_API_ORIGIN when the app runs elsewhere (its Capacitor shell,
 *  decision 122). */
export const API_ORIGIN: string =
  (import.meta.env.VITE_API_ORIGIN as string | undefined) || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost');

/** An API path the server returned (library files, previews, signed artefacts) as a URL the app can fetch. */
export function apiUrl(path: string): string {
  return /^[a-z][a-z0-9+.-]*:/i.test(path) ? path : new URL(path, API_ORIGIN).toString();
}

export const api = createClient<paths>({ baseUrl: API_ORIGIN });

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
  /** Place the order. A guest gives a contact; a signed-in account (setAccountToken) may use its own. */
  exportComposition: async (compositionId: string, contact?: OrderContact | null): Promise<ExportAccepted> =>
    unwrap(await api.POST('/api/v1/kiosk/compositions/{composition_id}/export', {
      params: { path: { composition_id: compositionId } }, body: { contact: contact ?? null }, ...accountAuth(),
    })),
  orderReady: async (pin: string, compositionId: string): Promise<KioskOrder> =>
    unwrap(await api.POST('/api/v1/kiosk/ops/orders/{composition_id}/ready', { params: { path: { composition_id: compositionId } }, headers: { 'X-Staff-Token': pin } } as never)),
  bespoke: async (compositionId: string, contact?: string): Promise<BespokeAccepted> =>
    unwrap(await api.POST('/api/v1/kiosk/compositions/{composition_id}/bespoke', { params: { path: { composition_id: compositionId } }, body: { contact: contact || null } })),
  // Payment for an order (decision 125): start (or restart) one, poll it, and, with the fake provider, simulate it.
  createPayment: async (compositionId: string, method: PaymentMethod): Promise<Payment> =>
    unwrap(await api.POST('/api/v1/kiosk/compositions/{composition_id}/payment', { params: { path: { composition_id: compositionId } }, body: { method } })),
  payment: async (compositionId: string): Promise<Payment> =>
    unwrap(await api.GET('/api/v1/kiosk/compositions/{composition_id}/payment', { params: { path: { composition_id: compositionId } } })),
  simulatePayment: async (compositionId: string): Promise<Payment> =>
    unwrap(await api.POST('/api/v1/kiosk/compositions/{composition_id}/payment/simulate', { params: { path: { composition_id: compositionId } } })),
};

// ------------------------------------------------------------------ studio: bearer token
// ---------------------------------------------------------------------------- customer accounts (decision 126)
let accountToken: string | null = null;
/** The signed-in customer's bearer token (or null): sent with the account routes and when placing an order. */
export function setAccountToken(token: string | null): void {
  accountToken = token;
}
export function getAccountToken(): string | null {
  return accountToken;
}
const accountAuth = (): { headers: Record<string, string> } => ({ headers: accountToken ? { Authorization: `Bearer ${accountToken}` } : {} });

export const AccountApi = {
  config: async (): Promise<AuthConfig> => unwrap(await api.GET('/api/v1/account/config')),
  sendCode: async (channel: Channel, to: string): Promise<CodeSent> => unwrap(await api.POST('/api/v1/account/code', { body: { channel, to } })),
  verify: async (channel: Channel, to: string, code: string, name?: string): Promise<AccountSession> =>
    unwrap(await api.POST('/api/v1/account/verify', { body: { channel, to, code, name: name || null } })),
  provider: async (provider: Provider, idToken: string, nonce?: string, name?: string): Promise<AccountSession> =>
    unwrap(await api.POST('/api/v1/account/oauth/{provider}', { params: { path: { provider } }, body: { id_token: idToken, nonce: nonce || null, name: name || null } })),
  me: async (): Promise<Account> => unwrap(await api.GET('/api/v1/account/me', accountAuth())),
  rename: async (name: string): Promise<Account> => unwrap(await api.PATCH('/api/v1/account/me', { body: { name }, ...accountAuth() })),
  addContact: async (channel: Channel, to: string, code: string): Promise<Account> =>
    unwrap(await api.POST('/api/v1/account/me/contact', { body: { channel, to, code, name: null }, ...accountAuth() })),
  removeContact: async (channel: Channel): Promise<Account> =>
    unwrap(await api.DELETE('/api/v1/account/me/contact/{channel}', { params: { path: { channel } }, ...accountAuth() })),
  link: async (provider: Provider, idToken: string, nonce?: string): Promise<Account> =>
    unwrap(await api.POST('/api/v1/account/me/providers/{provider}', { params: { path: { provider } }, body: { id_token: idToken, nonce: nonce || null, name: null }, ...accountAuth() })),
  unlink: async (provider: Provider): Promise<Account> =>
    unwrap(await api.DELETE('/api/v1/account/me/providers/{provider}', { params: { path: { provider } }, ...accountAuth() })),
  orders: async (): Promise<AccountOrders> => unwrap(await api.GET('/api/v1/account/me/orders', accountAuth())),
  addDevice: async (token: string, platform: 'ios' | 'android' | 'web') =>
    unwrap(await api.POST('/api/v1/account/me/devices', { body: { token, platform }, ...accountAuth() })),
  removeDevice: async (token: string) => {
    const r = await api.DELETE('/api/v1/account/me/devices', { params: { query: { token } }, ...accountAuth() });
    if (!r.response.ok) throw new ApiFailure(r.response.status, (r.error as { detail?: unknown } | undefined)?.detail);
  },
  signOut: async () => {
    await api.POST('/api/v1/account/sign-out', accountAuth());
  },
  remove: async () => {
    const r = await api.DELETE('/api/v1/account/me', accountAuth());
    if (!r.response.ok) throw new ApiFailure(r.response.status, (r.error as { detail?: unknown } | undefined)?.detail);
  },
};

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
  createJob: async (spec: PetSpec, genaiProfile?: string | null, pipeline?: string | null, options?: Record<string, boolean> | null): Promise<JobCreated> =>
    unwrap(await api.POST('/api/v1/studio/jobs', { body: { spec, genai_profile: genaiProfile || null, pipeline: pipeline || null, options: options ?? null }, ...(auth() as object) })),
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
  // the part library (decision 127): kits of parts, rigged in the workbench and committed
  partKits: async (species: Species): Promise<PartKitList> =>
    unwrap(await api.GET('/api/v1/studio/parts/{species}', { params: { path: { species } }, ...(auth() as object) })),
  /** scale (default on) fits each part to its breed's size guess; off for parts already in proportion. */
  uploadParts: async (species: Species, files: File[], breedId?: string, scale = true): Promise<PartUploadResult> => {
    const form = new FormData();
    for (const f of files) form.append('files', f, f.name);
    const params = new URLSearchParams();
    if (breedId) params.set('breed_id', breedId);
    if (!scale) params.set('scale', 'false');
    const q = params.toString() ? `?${params}` : '';
    const r = await fetch(apiUrl(`/api/v1/studio/parts/${species}/upload${q}`), { method: 'POST', body: form, headers: staffToken ? { Authorization: `Bearer ${staffToken}` } : {} });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new ApiFailure(r.status, (body as { detail?: unknown }).detail ?? body);
    return body as PartUploadResult;
  },
  partKit: async (species: Species, breedId: string): Promise<PartKit> =>
    unwrap(await api.GET('/api/v1/studio/parts/{species}/{breed_id}', { params: { path: { species, breed_id: breedId } }, ...(auth() as object) })),
  editPartRig: async (species: Species, breedId: string, partId: string, patch: PartRigPatch): Promise<PartKit> =>
    unwrap(await api.PATCH('/api/v1/studio/parts/{species}/{breed_id}/parts/{part_id}', { params: { path: { species, breed_id: breedId, part_id: partId } }, body: patch, ...(auth() as object) })),
  reguessPart: async (species: Species, breedId: string, partId: string): Promise<PartKit> =>
    unwrap(await api.POST('/api/v1/studio/parts/{species}/{breed_id}/parts/{part_id}/guess', { params: { path: { species, breed_id: breedId, part_id: partId } }, ...(auth() as object) })),
  deletePart: async (species: Species, breedId: string, partId: string): Promise<PartKit> =>
    unwrap(await api.DELETE('/api/v1/studio/parts/{species}/{breed_id}/parts/{part_id}', { params: { path: { species, breed_id: breedId, part_id: partId } }, ...(auth() as object) })),
  partKitSetup: async (species: Species, breedId: string, body: PartKitSetup): Promise<PartKit> =>
    unwrap(await api.PUT('/api/v1/studio/parts/{species}/{breed_id}/setup', { params: { path: { species, breed_id: breedId } }, body, ...(auth() as object) })),
  commitPartKit: async (species: Species, breedId: string): Promise<PartKit> =>
    unwrap(await api.POST('/api/v1/studio/parts/{species}/{breed_id}/commit', { params: { path: { species, breed_id: breedId } }, ...(auth() as object) })),
  createRelease: async (species: Species): Promise<ReleaseInfo> =>
    unwrap(await api.POST('/api/v1/studio/releases', { body: { species }, ...(auth() as object) })),
  // per-job GenAI profiles (decision 113): what Studio may run a job on, and the server default
  profiles: async (): Promise<GenaiProfiles> => unwrap(await api.GET('/api/v1/studio/profiles', auth())),
  // manual mode (decision 111): run a provider request in the vendor's app, upload its output
  manualTasks: async (status: 'pending' | 'submitted' | 'all' = 'pending'): Promise<ManualTaskList> =>
    unwrap(await api.GET('/api/v1/studio/manual', { params: { query: { status } }, ...(auth() as object) })),
  manualTask: async (taskId: string): Promise<ManualTask> =>
    unwrap(await api.GET('/api/v1/studio/manual/{task_id}', { params: { path: { task_id: taskId } }, ...(auth() as object) })),
  submitManual: async (taskId: string, file: Blob, filename: string, slot?: string): Promise<ManualTask> => {
    const form = new FormData();
    form.append('file', file, filename);
    const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
    const query = slot ? `?slot=${encodeURIComponent(slot)}` : '';
    const r = await fetch(`${origin}/api/v1/studio/manual/${encodeURIComponent(taskId)}/result${query}`, {
      method: 'POST',
      body: form,
      headers: staffToken ? { Authorization: `Bearer ${staffToken}` } : {},
    });
    const body = (await r.json().catch(() => ({}))) as { detail?: unknown };
    if (!r.ok) throw new ApiFailure(r.status, body.detail ?? body);
    return body as ManualTask;
  },
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

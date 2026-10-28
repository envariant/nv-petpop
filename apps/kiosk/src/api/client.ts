// Typed client generated from data/schema/openapi.json (npm run gen:client). One origin: the kiosk only
// ever talks to its own API.
import createClient from 'openapi-fetch';
import type { paths } from './schema';
import type { BreedList, FulfilResponse, Job, JobCreated, ParseResponse, PetSpec, ProgressEvent, ResultPage, Session, Species, StaffQueue } from './types';

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

export const Api = {
  health: async () => unwrap(await api.GET('/api/v1/health')),
  createSession: async (kioskId = 'kiosk-1'): Promise<Session> => unwrap(await api.POST('/api/v1/sessions', { body: { kiosk_id: kioskId } })),
  breeds: async (species: Species, q?: string): Promise<BreedList> =>
    unwrap(await api.GET('/api/v1/breeds', { params: { query: { species, q: q || undefined } } })),
  parse: async (species: Species, current: PetSpec, text: string, tapped: string[]): Promise<ParseResponse> =>
    unwrap(await api.POST('/api/v1/spec/parse', { body: { species, current_spec: current, text, tapped_fields: tapped } })),
  createJob: async (sessionId: string, spec: PetSpec): Promise<JobCreated> =>
    unwrap(await api.POST('/api/v1/jobs', { body: { session_id: sessionId, spec } })),
  job: async (id: string): Promise<Job> => unwrap(await api.GET('/api/v1/jobs/{job_id}', { params: { path: { job_id: id } } })),
  tweak: async (id: string, sessionId: string, patch: Record<string, unknown>): Promise<JobCreated> =>
    unwrap(await api.POST('/api/v1/jobs/{job_id}/tweak', { params: { path: { job_id: id } }, body: { session_id: sessionId, patch } })),
  fulfil: async (id: string): Promise<FulfilResponse> => unwrap(await api.POST('/api/v1/jobs/{job_id}/fulfil', { params: { path: { job_id: id } } })),
  result: async (token: string): Promise<ResultPage> => unwrap(await api.GET('/api/v1/r/{token}', { params: { path: { token } } })),
  staffQueue: async (token: string): Promise<StaffQueue> =>
    unwrap(await api.GET('/api/v1/staff/queue', { headers: { 'X-Staff-Token': token } } as never)),
  staffRetry: async (id: string, token: string): Promise<JobCreated> =>
    unwrap(await api.POST('/api/v1/staff/jobs/{job_id}/retry', { params: { path: { job_id: id } }, headers: { 'X-Staff-Token': token } } as never)),
};

export function eventsUrl(jobId: string): string {
  const { protocol, host } = window.location;
  return `${protocol === 'https:' ? 'wss' : 'ws'}://${host}/api/v1/jobs/${jobId}/events`;
}

/** Subscribe to job progress: WebSocket first, polling GET /jobs/{id} as the fallback. Returns unsubscribe. */
export function subscribeJob(jobId: string, onEvent: (e: ProgressEvent) => void, onJob?: (j: Job) => void): () => void {
  let closed = false;
  let ws: WebSocket | null = null;
  let poll: ReturnType<typeof setInterval> | null = null;
  const terminal = new Set(['done', 'failed', 'fulfilled']);
  const startPolling = () => {
    if (poll || closed) return;
    poll = setInterval(async () => {
      try {
        const j = await Api.job(jobId);
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
      if (terminal.has(ev.status)) Api.job(jobId).then((j) => onJob?.(j)).catch(() => undefined);
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

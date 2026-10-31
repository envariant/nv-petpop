// Manual mode (decision 111): provider requests the operator runs in the vendor's own app (Tripo Studio). The inbox
// lists them; uploading an output resumes its job.
import { create } from 'zustand';
import { ApiFailure, StudioApi } from '@petpop/core';
import type { ManualTask } from '@petpop/core';

export type ManualFilter = 'pending' | 'submitted' | 'all';

export interface ManualState {
  tasks: ManualTask[];
  pending: number;
  filter: ManualFilter;
  selectedId: string | null;
  busy: boolean;
  error: string | null;
  notice: string | null;
  set: (p: Partial<ManualState>) => void;
  load: () => Promise<void>;
  select: (id: string | null) => void;
  submit: (file: File, slot?: string) => Promise<ManualTask | null>;
}

const message = (e: unknown) =>
  e instanceof ApiFailure ? (typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail)) : 'Something went wrong.';

export const useManual = create<ManualState>((set, get) => ({
  tasks: [],
  pending: 0,
  filter: 'pending',
  selectedId: null,
  busy: false,
  error: null,
  notice: null,
  set: (p) => set(p),
  load: async () => {
    try {
      const r = await StudioApi.manualTasks(get().filter);
      const keep = r.items.some((t) => t.task_id === get().selectedId);
      set({ tasks: r.items, pending: r.pending, selectedId: keep ? get().selectedId : (r.items[0]?.task_id ?? null) });
    } catch {
      /* the offline overlay handles a dropped API */
    }
  },
  select: (id) => set({ selectedId: id, error: null, notice: null }),
  submit: async (file, slot) => {
    const id = get().selectedId;
    if (!id) return null;
    set({ busy: true, error: null, notice: null });
    try {
      const t = await StudioApi.submitManual(id, file, file.name, slot);
      const left = (t.expects.slots ?? []).filter((x) => !(t.filled ?? []).includes(x));
      set({ notice: left.length ? `${slot} view received; still to come: ${left.join(', ')}.` : `${t.title}: ${file.name} received, the job carries on.` });
      await get().load();
      return t;
    } catch (e) {
      set({ error: message(e) });
      return null;
    } finally {
      set({ busy: false });
    }
  },
}));

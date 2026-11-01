// Manual mode (decision 111): provider requests the operator runs in the vendor's own app (Tripo Studio). The inbox
// lists them; uploading an output resumes its job.
import { defineStore } from 'pinia';
import { ref } from 'vue';
import { ApiFailure, StudioApi } from '@petpop/core';
import type { ManualTask } from '@petpop/core';

export type ManualFilter = 'pending' | 'submitted' | 'all';

const message = (e: unknown) =>
  e instanceof ApiFailure ? (typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail)) : 'Something went wrong.';

export const useManual = defineStore('manual', () => {
  const tasks = ref<ManualTask[]>([]);
  const pending = ref(0);
  const filter = ref<ManualFilter>('pending');
  const selectedId = ref<string | null>(null);
  const busy = ref(false);
  const error = ref<string | null>(null);
  const notice = ref<string | null>(null);

  async function load() {
    try {
      const r = await StudioApi.manualTasks(filter.value);
      const keep = r.items.some((t) => t.task_id === selectedId.value);
      tasks.value = r.items;
      pending.value = r.pending;
      if (!keep) selectedId.value = r.items[0]?.task_id ?? null;
    } catch {
      /* the offline overlay handles a dropped API */
    }
  }
  function select(id: string | null) {
    selectedId.value = id;
    error.value = null;
    notice.value = null;
  }
  async function submit(file: File, slot?: string): Promise<ManualTask | null> {
    const id = selectedId.value;
    if (!id) return null;
    busy.value = true;
    error.value = null;
    notice.value = null;
    try {
      const t = await StudioApi.submitManual(id, file, file.name, slot);
      const left = (t.expects.slots ?? []).filter((x) => !(t.filled ?? []).includes(x));
      notice.value = left.length ? `${slot} view received; still to come: ${left.join(', ')}.` : `${t.title}: ${file.name} received, the job carries on.`;
      await load();
      return t;
    } catch (e) {
      error.value = message(e);
      return null;
    } finally {
      busy.value = false;
    }
  }
  return { tasks, pending, filter, selectedId, busy, error, notice, load, select, submit };
});

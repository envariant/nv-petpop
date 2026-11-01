// Per-job GenAI choices (decisions 113 to 115): the profile ("Run on"), its pipeline (single view or multiview) and
// its quality switches, shared by the batch builder and the one-off figurine flow. The kiosk never chooses: its jobs
// use the server default. The credit estimate is the provider's API price per figurine, where it prices by credit.
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { StudioApi } from '@petpop/core';
import type { GenaiProfileInfo, GenaiProfiles } from '@petpop/core';

export const useProfiles = defineStore('profiles', () => {
  const offered = ref<GenaiProfiles | null>(null);
  const choice = ref<string | null>(null);
  const pipeline = ref<string | null>(null);
  const options = ref<Record<string, boolean>>({});

  const current = computed<GenaiProfileInfo | null>(() => offered.value?.items.find((p) => p.name === choice.value) ?? null);
  /** API credits per figurine for the current choices, or null when the profile does not price by credit. */
  const estimate = computed<number | null>(() => {
    const p = current.value;
    const pipe = p?.pipelines.find((x) => x.name === pipeline.value);
    if (!p || pipe?.credits == null) return null;
    return pipe.credits + p.options.reduce((sum, o) => sum + (options.value[o.name] ? (o.credits ?? 0) : 0), 0);
  });

  function defaults(p: GenaiProfileInfo | null) {
    pipeline.value = p?.pipelines.find((x) => x.default)?.name ?? null;
    options.value = Object.fromEntries((p?.options ?? []).map((o) => [o.name, o.default]));
  }
  async function load() {
    try {
      const o = await StudioApi.profiles();
      const keep = o.items.some((p) => p.name === choice.value && p.ready);
      offered.value = o;
      if (!keep) {
        choice.value = o.default;
        defaults(o.items.find((p) => p.name === o.default) ?? null);
      }
    } catch {
      /* the offline overlay handles a dropped API; jobs then use the server default */
    }
  }
  function choose(name: string) {
    choice.value = name;
    defaults(offered.value?.items.find((p) => p.name === name) ?? null);
  }
  function choosePipeline(name: string) {
    pipeline.value = name;
  }
  function toggle(option: string) {
    options.value = { ...options.value, [option]: !options.value[option] };
  }
  return { offered, choice, pipeline, options, current, estimate, load, choose, choosePipeline, toggle };
});

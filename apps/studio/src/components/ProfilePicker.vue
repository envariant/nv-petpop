<script setup lang="ts">
// "Run on", "Pipeline" and "Quality" (decisions 113 to 115): the GenAI profile a new job or batch uses (what the
// server offers: PETPOP_STUDIO_PROFILES, led by the default GENAI_PROFILE), the profile's pipeline and its quality
// switches, with the API credits a figurine costs where the provider prices by credit. A profile missing a key is
// listed but not selectable.
import { computed, onMounted } from 'vue';
import { Chip, PRow, PSection } from '@petpop/ui-vue';
import { useProfiles } from '../stores/profiles';
const s = useProfiles();
onMounted(() => !s.offered && void s.load());
const TITLES: Record<string, string> = {
  mock: 'Mock (no GenAI)', 'tripo-manual': 'Tripo, by hand', tripo: 'Tripo API', 'mac-m4pro': 'Mac GenAI host', 'nvidia-24gb': 'NVIDIA GenAI host',
};
const pipeNote = computed(() => s.current?.pipelines.find((x) => x.name === s.pipeline)?.note);
</script>

<template>
  <div v-if="s.offered" data-testid="profile-picker">
    <PSection title="Run on">
      <PRow>
        <Chip v-for="x in s.offered.items" :key="x.name" :selected="s.choice === x.name" :test-id="`profile-${x.name}`" @click="x.ready && s.choose(x.name)">
          {{ TITLES[x.name] ?? x.name }}{{ x.name === s.offered.default ? ' (default)' : '' }}{{ !x.ready ? ` · needs ${x.missing.join(', ')}` : '' }}
        </Chip>
      </PRow>
      <p v-if="s.current" class="mt-2 text-base text-muted" data-testid="profile-description">{{ s.current.description }}</p>
    </PSection>
    <PSection v-if="s.current && s.current.pipelines.length" title="Pipeline" test-id="pipeline-picker">
      <PRow>
        <Chip v-for="x in s.current.pipelines" :key="x.name" :selected="s.pipeline === x.name" :test-id="`pipeline-${x.name}`" @click="s.choosePipeline(x.name)">
          {{ x.title }}{{ x.credits != null ? ` · ${x.credits} cr` : '' }}
        </Chip>
      </PRow>
      <p v-if="pipeNote" class="mt-2 text-base text-muted" data-testid="pipeline-note">{{ pipeNote }}</p>
    </PSection>
    <PSection v-if="s.current && s.current.options.length" title="Quality" test-id="option-picker">
      <PRow>
        <Chip v-for="o in s.current.options" :key="o.name" :selected="!!s.options[o.name]" :test-id="`option-${o.name}`" @click="s.toggle(o.name)">
          {{ o.title }}{{ o.credits ? ` +${o.credits} cr` : '' }}
        </Chip>
      </PRow>
      <ul class="mt-2 text-sm text-muted md:text-base">
        <template v-for="o in s.current.options" :key="o.name"><li v-if="o.note">{{ o.title }}: {{ o.note }}</li></template>
      </ul>
    </PSection>
    <p v-if="s.estimate != null" class="mb-6 text-base md:text-lg" data-testid="credit-estimate">
      About <b>{{ s.estimate }}</b> API credits (${{ (s.estimate / 100).toFixed(2) }}) per figurine{{ s.current?.name.endsWith('-manual') ? '; by hand you spend Tripo Studio credits instead' : '' }}
    </p>
  </div>
</template>

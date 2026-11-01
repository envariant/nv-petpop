<script setup lang="ts">
// One manual task: the steps, the prompt and settings to copy, the input files, the API request it replaces, and the
// upload (one file, or one per view for a multiview task) that resumes the job.
import { ref, watch } from 'vue';
import type { ManualTask } from '@petpop/core';
import { PButton, PRow, PSection } from '@petpop/ui-vue';
import { useManual } from '../../stores/manual';
import CopyButton from './CopyButton.vue';
import SlotUpload from './SlotUpload.vue';
import TextBlock from './TextBlock.vue';
const props = defineProps<{ t: ManualTask }>();
const m = useManual();
const input = ref<HTMLInputElement | null>(null);
const file = ref<File | null>(null);
watch(() => props.t.task_id, () => (file.value = null));
async function send() {
  if (!file.value) return;
  if ((await m.submit(file.value)) && input.value) input.value.value = '';
}
</script>

<template>
  <div data-testid="manual-detail">
    <PSection :title="`${t.vendor}: ${t.title}`">
      <ol class="list-decimal pl-6 text-base leading-relaxed md:text-lg" data-testid="manual-steps"><li v-for="st in t.instructions" :key="st">{{ st }}</li></ol>
    </PSection>
    <TextBlock v-if="t.prompt" title="Prompt" :text="t.prompt" test-id="manual-prompt" />
    <TextBlock v-if="t.negative_prompt" title="Negative prompt" :text="t.negative_prompt" test-id="manual-negative" />
    <PSection v-if="t.settings.length" title="Settings">
      <ul class="rounded-tile bg-card p-4 font-mono text-sm shadow-soft md:text-base" data-testid="manual-settings"><li v-for="st in t.settings" :key="st">{{ st }}</li></ul>
    </PSection>
    <PSection v-if="t.inputs.length" title="Files to upload to the vendor">
      <PRow>
        <a v-for="i in t.inputs" :key="i.name" :href="i.url" :download="i.name" class="hit flex flex-col items-center gap-1 rounded-tile bg-card p-3 text-sm shadow-soft" :data-testid="`manual-input-${i.name}`">
          <img :src="i.url" :alt="i.name" class="h-28 w-28 rounded-2xl bg-paper object-contain" />{{ i.name }} ↓
        </a>
      </PRow>
    </PSection>
    <PSection title="The API request this replaces">
      <details class="rounded-tile bg-card p-4 text-sm shadow-soft md:text-base">
        <summary class="hit">{{ t.route }} · {{ t.manifest }}</summary>
        <pre class="mt-2 overflow-x-auto whitespace-pre-wrap text-sm" data-testid="manual-request">{{ JSON.stringify(t.request, null, 1) }}</pre>
        <CopyButton :text="JSON.stringify(t.request, null, 1)" test-id="manual-request-copy" />
      </details>
    </PSection>
    <PSection v-if="t.status === 'pending' && (t.expects.slots ?? []).length"
      :title="`Upload each view (${t.expects.accept.join(', ')}); the job continues once all ${(t.expects.slots ?? []).length} are in`" test-id="manual-slots">
      <SlotUpload v-for="slot in t.expects.slots ?? []" :key="slot" :t="t" :slot="slot" />
    </PSection>
    <PSection v-else-if="t.status === 'pending'" :title="`Upload the ${t.expects.kind === 'model' ? '3D model' : 'image'} (${t.expects.accept.join(', ')})`">
      <div class="flex flex-wrap items-center gap-4">
        <input ref="input" type="file" :accept="t.expects.accept.join(',')" class="min-w-0 flex-1 text-base" data-testid="manual-file"
          @change="file = ($event.target as HTMLInputElement).files?.[0] ?? null" />
        <PButton :disabled="!file || m.busy" test-id="manual-submit" @click="send">{{ m.busy ? 'Uploading…' : 'Send to the job' }}</PButton>
      </div>
    </PSection>
    <p v-else class="text-base text-muted md:text-lg" data-testid="manual-submitted">Output received: {{ t.result_name }}</p>
  </div>
</template>

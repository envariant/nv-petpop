<script setup lang="ts">
import { computed } from 'vue';
import { Chip, PRow } from '@petpop/ui-vue';
import { useSession } from '../../stores/session';
import { MARK_LABEL, useHighlight } from './vocab';
const s = useSession();
const hl = useHighlight();
const marks = computed<string[]>(() => (s.spec?.colour.markings ?? []) as string[]);
const toggle = (m: string) => s.tap('colour.markings', marks.value.includes(m) ? marks.value.filter((x) => x !== m) : [...marks.value, m]);
</script>

<template>
  <div class="mt-3">
    <PRow>
      <Chip v-for="(title, m) in MARK_LABEL" :key="m" :test-id="`chip-marking-${m}`" :selected="marks.includes(m)" :highlight="marks.includes(m) && hl('colour.markings')" @click="toggle(m)">
        {{ title }}
      </Chip>
    </PRow>
  </div>
</template>

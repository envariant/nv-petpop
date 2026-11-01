<script setup lang="ts">
import { label } from '@petpop/core';
import { Chip, PRow } from '@petpop/ui-vue';
import { useSession } from '../../stores/session';
import { useHighlight, useValue } from './vocab';
defineProps<{ path: string; values: string[] }>();
const s = useSession();
const hl = useHighlight();
const value = useValue();
</script>

<template>
  <PRow>
    <Chip v-for="v in values" :key="v" :test-id="`chip-${path}-${v}`" :selected="value(path) === v" :highlight="value(path) === v && hl(path)" @click="s.tap(path, v)">
      {{ label(v) }}
    </Chip>
  </PRow>
</template>

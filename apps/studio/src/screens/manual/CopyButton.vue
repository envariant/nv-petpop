<script setup lang="ts">
import { ref } from 'vue';
import { PButton } from '@petpop/ui-vue';
const props = defineProps<{ text: string; testId: string }>();
const done = ref(false);
function copy() {
  void navigator.clipboard?.writeText(props.text).then(() => {
    done.value = true;
    setTimeout(() => (done.value = false), 1500);
  });
}
</script>

<template>
  <PButton variant="soft" :test-id="testId" @click="copy">{{ done ? 'Copied' : 'Copy' }}</PButton>
</template>

<script setup lang="ts">
// A text or number field that keeps what is being typed: the value from the store only replaces it when nothing is
// being edited, so a save's answer landing mid-typing (another edit's) never wipes the user's text. `commit` fires on
// change (Enter or leaving the field) with what was typed.
import { ref, watch } from 'vue';

const props = defineProps<{ value: string | number | null | undefined }>();
const emit = defineEmits<{ commit: [value: string] }>();
const show = (v: string | number | null | undefined) => (v == null ? '' : String(v));
const text = ref(show(props.value));
let editing = false;
watch(() => props.value, (v) => {
  if (!editing) text.value = show(v);
});
function changed() {
  editing = false;
  emit('commit', text.value);
}
function left() {
  editing = false;
  text.value = show(props.value);
}
</script>

<template>
  <input v-model="text" @input="editing = true" @change="changed" @blur="left" />
</template>

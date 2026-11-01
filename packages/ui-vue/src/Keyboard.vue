<script setup lang="ts">
// The on-screen keyboard (kiosk mode only): breed search, pet name, contact details, the staff PIN.
import { ref } from 'vue';
const props = withDefaults(defineProps<{ modelValue: string; maxLength?: number; doneLabel?: string; showDone?: boolean; compact?: boolean; capitalize?: boolean; contact?: boolean }>(),
  { maxLength: 500, doneLabel: 'Done', showDone: true, capitalize: true });
const emit = defineEmits<{ 'update:modelValue': [string]; done: [] }>();
const ROWS = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm'];
const shift = ref(props.capitalize && props.modelValue.length === 0);
function press(k: string) {
  if (props.modelValue.length >= props.maxLength) return;
  emit('update:modelValue', props.modelValue + (shift.value ? k.toUpperCase() : k));
  shift.value = false;
}
const keyClass = 'press hit flex-1 rounded-xl bg-card font-display text-lg shadow-soft md:text-xl';
const tests: Record<string, string> = { ' ': 'key-space', ',': 'key-comma', '.': 'key-dot', '@': 'key-at', '+': 'key-plus' };
</script>

<template>
  <div class="select-none rounded-tile bg-line/60 p-2" data-testid="keyboard">
    <div v-if="contact" class="mb-2 flex gap-1">
      <button v-for="k in '1234567890@+'.split('')" :key="k" :data-testid="tests[k] ?? `key-${k}`" :class="keyClass" :style="{ height: compact ? '2.6rem' : '3rem' }" @click="press(k)">{{ k }}</button>
    </div>
    <div v-for="(r, i) in ROWS" :key="r" class="mb-2 flex gap-1" :style="{ paddingLeft: `${i * 1.2}rem`, paddingRight: `${i * 1.2}rem` }">
      <button v-for="k in r.split('')" :key="k" :data-testid="`key-${k}`" :class="keyClass" :style="{ height: compact ? '2.6rem' : '3rem' }" @click="press(k)">{{ shift ? k.toUpperCase() : k }}</button>
    </div>
    <div class="flex gap-1">
      <button data-testid="key-shift" :class="keyClass" style="flex: 1.3; height: 3rem" @click="shift = !shift">⇧</button>
      <button data-testid="key-comma" :class="keyClass" style="height: 3rem" @click="press(',')">,</button>
      <button data-testid="key-space" :class="keyClass" style="flex: 5; height: 3rem" @click="press(' ')">space</button>
      <button data-testid="key-dot" :class="keyClass" style="height: 3rem" @click="press('.')">.</button>
      <button data-testid="key-backspace" :class="keyClass" style="flex: 1.5; height: 3rem" @click="emit('update:modelValue', modelValue.slice(0, -1))">⌫</button>
      <button v-if="showDone" data-testid="key-done" :class="keyClass" style="flex: 2; height: 3rem" @click="emit('done')">{{ doneLabel }}</button>
    </div>
  </div>
</template>

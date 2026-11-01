<script setup lang="ts">
// A text field that fits the mode: the system keyboard in the app, a display over the on-screen keyboard on a kiosk.
import { isKiosk } from './mode';
import Keyboard from './Keyboard.vue';
import TextDisplay from './TextDisplay.vue';
withDefaults(defineProps<{ modelValue: string; placeholder: string; testId?: string; maxLength?: number; doneLabel?: string; keyboard?: boolean;
  compact?: boolean; capitalize?: boolean; contact?: boolean; inputType?: string; mask?: boolean }>(), { maxLength: 500, doneLabel: 'Done', keyboard: true, inputType: 'text', capitalize: true });
const emit = defineEmits<{ 'update:modelValue': [string]; done: []; focus: [] }>();
</script>

<template>
  <div v-if="isKiosk" class="flex flex-col gap-3">
    <button class="text-left" :data-testid="testId ? `${testId}-field` : undefined" @click="emit('focus')">
      <TextDisplay :value="mask ? modelValue.replace(/./g, '•') : modelValue" :placeholder="placeholder" :test-id="testId" />
    </button>
    <Keyboard v-if="keyboard" :model-value="modelValue" :max-length="maxLength" :done-label="doneLabel" :compact="compact" :capitalize="capitalize" :contact="contact"
      @update:model-value="emit('update:modelValue', $event)" @done="emit('done')" />
  </div>
  <form v-else class="flex flex-col gap-3 sm:flex-row" @submit.prevent="emit('done')">
    <input
      :value="modelValue" :type="mask ? 'password' : inputType" :placeholder="placeholder" :maxlength="maxLength" :data-testid="testId"
      :autocapitalize="capitalize ? 'words' : 'none'" autocomplete="off"
      class="min-w-0 flex-1 rounded-tile border-4 border-line bg-card px-4 py-3 text-lg text-ink outline-none focus:border-accent md:text-xl"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)" @focus="emit('focus')"
    />
    <button v-if="keyboard" type="submit" data-testid="key-done" class="press hit rounded-tile bg-accent px-6 py-3 font-display text-lg font-semibold text-white shadow-soft md:text-xl">{{ doneLabel }}</button>
  </form>
</template>

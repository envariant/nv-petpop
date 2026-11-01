<script setup lang="ts">
import { PButton } from '@petpop/ui-vue';
import Backdrop from './Backdrop.vue';
defineProps<{ seconds: number }>();
defineEmits<{ stay: [] }>();
</script>

<template>
  <Backdrop test-id="still-there">
    <div class="text-center">
      <h2 class="font-display text-4xl font-semibold md:text-5xl">Still there?</h2>
      <p class="my-4 text-xl text-muted md:text-2xl">Starting over in <b data-testid="still-there-seconds">{{ seconds }}</b> s</p>
      <PButton test-id="still-there-stay" @click="$emit('stay')">I'm here!</PButton>
    </div>
  </Backdrop>
</template>

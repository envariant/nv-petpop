<script setup lang="ts">
import QRCode from 'qrcode';
import { ref, watchEffect } from 'vue';
const props = withDefaults(defineProps<{ value: string; size?: number }>(), { size: 200 });
const svg = ref('');
watchEffect(async () => {
  svg.value = await QRCode.toString(props.value, { type: 'svg', errorCorrectionLevel: 'M', margin: 0, width: props.size });
});
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- generated locally from our own result URL -->
  <div class="leading-none" :style="{ width: `${size}px`, height: `${size}px` }" v-html="svg" />
</template>

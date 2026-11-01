<script setup lang="ts">
import Backdrop from './Backdrop.vue';
</script>

<template>
  <Backdrop test-id="offline">
    <div class="w-full max-w-lg rounded-tile bg-paper p-10 text-center shadow-soft">
      <div class="mb-4 text-6xl">🛠️</div>
      <h2 class="font-display text-3xl font-semibold md:text-4xl">Back in a moment</h2>
      <p class="mt-4 text-lg text-muted">We're reconnecting. Your work is safe.</p>
    </div>
  </Backdrop>
</template>

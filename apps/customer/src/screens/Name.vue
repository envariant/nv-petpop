<script setup lang="ts">
import { computed, ref } from 'vue';
import { PButton, PTitle, TextEntry } from '@petpop/ui-vue';
import { useDesign } from '../stores/design';
import { useSession } from '../stores/session';
const s = useSession();
const d = useDesign();
const name = computed({ get: () => d.composition?.pet_name ?? '', set: (v: string) => d.setName(v) });
const busy = ref(false);
async function order() {
  if (busy.value) return;
  busy.value = true;
  try {
    await d.placeOrder(s.sessionId);
    if (!d.orderError) s.go('order');
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div v-if="d.composition" class="mx-auto flex h-full max-w-3xl flex-col px-4 pb-4 pt-2 md:px-8" data-testid="name">
    <PTitle sub="It goes on the base of your figurine.">What's their name?</PTitle>
    <TextEntry v-model="name" placeholder="Biscuit" test-id="pet-name" :max-length="24" :done-label="busy ? 'Ordering…' : 'Order my figurine'" class="landscape:md:mt-4" @done="order" />
    <p v-if="d.orderError" class="mt-4 text-lg font-semibold text-accent2" data-testid="order-error">{{ d.orderError }}</p>
    <PButton variant="ghost" class="mt-auto self-start" test-id="name-back" @click="s.go('design')">‹ Back to design</PButton>
  </div>
</template>

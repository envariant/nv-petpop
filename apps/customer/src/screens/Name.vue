<script setup lang="ts">
import { computed } from 'vue';
import { PButton, PTitle, TextEntry } from '@petpop/ui-vue';
import { useDesign } from '../stores/design';
import { useSession } from '../stores/session';
const s = useSession();
const d = useDesign();
const name = computed({ get: () => d.active?.pet_name ?? '', set: (v: string) => d.setName(v) });
const next = () => name.value.trim() && s.go('contact'); // checkout: how we reach the customer (decision 126)
</script>

<template>
  <div v-if="d.active" class="mx-auto flex h-full max-w-3xl flex-col px-4 pb-4 pt-2 md:px-8" data-testid="name">
    <PTitle sub="It goes on the base of your figurine.">What's their name?</PTitle>
    <TextEntry v-model="name" placeholder="Biscuit" test-id="pet-name" :max-length="24" :done-label="'Next: how we reach you'" class="landscape:md:mt-4" @done="next" />
    <PButton variant="ghost" class="mt-auto self-start" test-id="name-back" @click="s.go('design')">‹ Back to design</PButton>
  </div>
</template>

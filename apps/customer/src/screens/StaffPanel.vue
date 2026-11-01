<script setup lang="ts">
// The five-tap ops panel on a kiosk (BRIEF Section 17): release version, health, reprint; no generation controls.
import { onMounted, ref } from 'vue';
import { KioskApi } from '@petpop/core';
import type { KioskOps } from '@petpop/core';
import { PButton, TextEntry } from '@petpop/ui-vue';
import Backdrop from './Backdrop.vue';
defineEmits<{ close: [] }>();
const stored = (() => {
  try {
    return localStorage.getItem('pp-staff-token') ?? '';
  } catch {
    return '';
  }
})();
const pin = ref(stored);
const ops = ref<KioskOps | null>(null);
const err = ref<string | null>(null);
const reprinted = ref<string | null>(null);
async function load() {
  try {
    ops.value = await KioskApi.ops(pin.value);
    err.value = null;
    try {
      localStorage.setItem('pp-staff-token', pin.value);
    } catch {
      /* storage may be blocked */
    }
  } catch {
    err.value = 'PIN not accepted';
    ops.value = null;
  }
}
async function reprint(id: string) {
  try {
    await KioskApi.reprint(pin.value, id);
    reprinted.value = id;
  } catch {
    err.value = 'Reprint failed';
  }
}
onMounted(() => pin.value && void load());
</script>

<template>
  <Backdrop test-id="staff-panel">
    <div class="mb-6 flex items-center justify-between">
      <h2 class="font-display text-3xl font-semibold md:text-4xl">Kiosk</h2>
      <PButton variant="soft" test-id="staff-close" @click="$emit('close')">Close</PButton>
    </div>
    <div v-if="!ops">
      <TextEntry v-model="pin" placeholder="Staff PIN" test-id="staff-token" mask done-label="Open" compact :capitalize="false" @done="load" />
      <p v-if="err" class="my-3 text-lg text-accent2">{{ err }}</p>
    </div>
    <dl v-else class="grid grid-cols-2 gap-y-2 text-lg md:text-xl" data-testid="staff-ops">
      <dt class="text-muted">Kiosk</dt><dd>{{ ops.kiosk_id }}</dd>
      <dt class="text-muted">Library release</dt><dd data-testid="ops-release">{{ Object.values(ops.releases).join(', ') || 'none loaded' }}</dd>
      <dt class="text-muted">API</dt><dd>{{ ops.api_version }} ({{ ops.mode }})</dd>
      <dt class="text-muted">Exports</dt><dd>{{ ops.exports_running }} running · {{ ops.exports_queued }} queued</dd>
      <dt class="text-muted">Make it unique</dt><dd>{{ ops.bespoke_enabled ? 'on' : 'off' }}</dd>
      <dt class="col-span-2 mt-4 font-display text-2xl font-semibold text-ink">Recent orders</dt>
      <dd v-if="ops.orders.length === 0" class="col-span-2 text-muted">No orders yet</dd>
      <dd v-for="o in ops.orders" :key="o.composition_id" class="col-span-2 flex items-center justify-between gap-4" :data-testid="`ops-order-${o.ticket}`">
        <span><b>{{ o.ticket }}</b> · {{ o.pet_name || 'unnamed' }} · {{ o.status }}</span>
        <PButton variant="soft" :disabled="o.status !== 'ready'" :test-id="`reprint-${o.ticket}`" @click="reprint(o.composition_id)">{{ reprinted === o.composition_id ? 'Sent ✓' : 'Reprint' }}</PButton>
      </dd>
    </dl>
  </Backdrop>
</template>

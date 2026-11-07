<script setup lang="ts">
// The order: Stage F runs at once; with payments on (decision 125) the customer pays first, by PayNow (a QR their
// banking app scans) or by card (HitPay's checkout: opened in the app, a QR to scan on a kiosk), then gets the ticket
// and the result QR. With payments off the shop takes payment at the counter.
import { computed, onBeforeUnmount, watch } from 'vue';
import { apiUrl } from '@petpop/core';
import { Chip, FigureView, GlbView, KitFigureView, PButton, PTitle, QrCode, isKiosk } from '@petpop/ui-vue';
import { useDesign } from '../stores/design';
import { useSession } from '../stores/session';
const s = useSession();
const d = useDesign();
const o = computed(() => d.order);
const ready = computed(() => o.value?.status === 'ready');
const p = computed(() => o.value?.payment ?? null);
const needsPay = computed(() => !!s.payment && p.value?.status !== 'paid');
// what this order costs: its own quote (the figurine and its priced extras, decision 137), else the session's price
const price = computed(() => (d.order?.quote ? `S$${d.order.quote.total.amount}` : s.payment && `S$${s.payment.price.amount}`));
const busy = computed(() => (o.value && o.value.status !== 'ready' && o.value.status !== 'failed') || p.value?.status === 'pending');
let t = 0;
watch(busy, (b) => {
  clearInterval(t);
  if (b) t = window.setInterval(() => void d.refreshOrder(), 1500);
}, { immediate: true });
onBeforeUnmount(() => clearInterval(t));
const openCheckout = () => p.value?.checkout_url && window.open(p.value.checkout_url, '_blank', 'noopener');
const title = computed(() => {
  if (needsPay.value) return 'Pay to confirm your order';
  return ready.value ? `${o.value?.pet_name || 'Your figurine'} is on the way!` : 'Placing your order…';
});
const sub = computed(() => {
  if (needsPay.value) return `${price.value} · PayNow or card. We start preparing it now.`;
  return ready.value ? 'Show this ticket at the counter. Scan the code to keep a copy on your phone.' : (o.value?.export?.message ?? 'Preparing your order');
});
</script>

<template>
  <div v-if="o" class="flex h-full flex-col items-center gap-4 px-4 pb-4 pt-2 text-center md:px-8 landscape:md:flex-row landscape:md:items-stretch landscape:md:text-left" data-testid="order">
    <div class="relative h-[38%] min-h-[12rem] w-full shrink-0 overflow-hidden rounded-tile bg-card shadow-soft landscape:md:h-full landscape:md:flex-1">
      <GlbView v-if="ready && o.previews.glb" :url="apiUrl(o.previews.glb)" :fallback-image="o.previews.thumbnail ? apiUrl(o.previews.thumbnail) : undefined" spin test-id="order-figure" />
      <KitFigureView v-else-if="d.kitMode && d.kit && d.kitComposition" :manifest="d.kitManifest()" :kit="d.kit" :composition="d.kitComposition"
        :url="d.fileUrl" spin :interactive="false" test-id="order-preview" />
      <FigureView v-else-if="d.lib && d.composition" :lib="d.lib" :composition="d.composition" spin :interactive="false" test-id="order-preview" />
    </div>
    <div class="no-scrollbar flex w-full min-h-0 flex-1 flex-col items-center gap-4 overflow-y-auto landscape:md:w-[min(42%,30rem)] landscape:md:flex-none landscape:md:items-start landscape:md:justify-center">
      <PTitle :sub="sub">{{ title }}</PTitle>
      <div v-if="!ready && o.status !== 'failed'" class="h-3 w-full shrink-0 overflow-hidden rounded-full bg-line" data-testid="order-progress">
        <div class="h-full bg-accent transition-all" :style="{ width: `${o.export?.pct ?? 5}%` }" />
      </div>
      <p v-if="o.status === 'failed'" class="text-lg font-semibold text-accent2" data-testid="order-failed">
        Something went wrong preparing the print. A member of staff can reprint ticket {{ o.ticket }}.
      </p>

      <!-- payment (decision 125) -->
      <section v-if="needsPay" class="flex w-full flex-col items-center gap-3 landscape:md:items-start" data-testid="order-pay">
        <div class="flex gap-2">
          <Chip :selected="p?.method === 'paynow' && p.status === 'pending'" test-id="pay-paynow" @click="d.pay('paynow')">PayNow</Chip>
          <Chip :selected="p?.method === 'card' && p.status === 'pending'" test-id="pay-card" @click="d.pay('card')">Card</Chip>
        </div>
        <template v-if="p?.status === 'pending'">
          <div v-if="p.method === 'paynow' && p.qr" class="flex flex-col items-center gap-2 landscape:md:items-start">
            <div class="rounded-tile bg-white p-3" data-testid="pay-qr"><QrCode :value="p.qr" :size="180" /></div>
            <p class="text-base text-muted">Scan with your banking app (PayNow).<span v-if="!isKiosk" class="md:hidden"> On this phone: screenshot it and open it in your banking app.</span></p>
          </div>
          <div v-else-if="p.method === 'card' && p.checkout_url" class="flex flex-col items-center gap-2 landscape:md:items-start">
            <template v-if="isKiosk">
              <div class="rounded-tile bg-white p-3" data-testid="pay-card-qr"><QrCode :value="p.checkout_url" :size="160" /></div>
              <p class="text-base text-muted">Scan to pay by card on your phone.</p>
            </template>
            <PButton v-else test-id="pay-card-open" @click="openCheckout">Pay {{ price }} by card</PButton>
          </div>
          <p class="text-sm text-muted" data-testid="pay-waiting">Waiting for the payment…</p>
          <PButton v-if="p.provider === 'fake'" variant="soft" test-id="pay-simulate" @click="d.simulatePay()">Simulate payment (test)</PButton>
        </template>
        <p v-else-if="p && p.status !== 'paid'" class="text-base text-accent2" data-testid="pay-retry">That payment did not go through. Choose a way to pay again.</p>
        <p v-if="d.payError" class="text-base font-semibold text-accent2" data-testid="pay-error">{{ d.payError }}</p>
      </section>

      <div v-else class="flex w-full flex-wrap items-center justify-center gap-4 landscape:md:justify-start">
        <div class="rounded-tile bg-accent px-6 py-3 font-display text-2xl text-white md:text-3xl" data-testid="order-ticket">Ticket <b>{{ o.ticket }}</b></div>
        <div v-if="ready && o.result_url" class="rounded-tile bg-white p-3" data-testid="order-qr"><QrCode :value="o.result_url" :size="140" /></div>
      </div>
      <PButton class="mt-auto w-full shrink-0" :variant="needsPay ? 'ghost' : 'primary'" test-id="order-done" @click="s.reset()">{{ needsPay ? 'Cancel' : 'Done' }}</PButton>
    </div>
  </div>
</template>

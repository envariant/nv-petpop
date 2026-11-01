<script setup lang="ts">
// PetPop customer app (decision 122): library mode, one screen at a time, responsive from phones to desktops and
// kiosks. Kiosk mode adds the idle wipe and the five-tap staff panel. It never depends on the GenAI host.
import { ref } from 'vue';
import { AppFrame, isKiosk } from '@petpop/ui-vue';
import { useFiveTap, useIdle, useOnline } from './composables';
import { useSession } from './stores/session';
import Attract from './screens/Attract.vue';
import Species from './screens/Species.vue';
import BreedScreen from './screens/Breed.vue';
import Design from './screens/Design.vue';
import NameScreen from './screens/Name.vue';
import Order from './screens/Order.vue';
import Bespoke from './screens/Bespoke.vue';
import StillThere from './screens/StillThere.vue';
import Offline from './screens/Offline.vue';
import StaffPanel from './screens/StaffPanel.vue';
import PhoneResult from './screens/PhoneResult.vue';

const s = useSession();
const screens = { attract: Attract, species: Species, breed: BreedScreen, design: Design, name: NameScreen, order: Order, bespoke: Bespoke };
const resultToken = location.pathname.startsWith('/r/') ? decodeURIComponent(location.pathname.slice(3)) : null;
const { countdown, dismiss } = useIdle(isKiosk);
const online = useOnline();
const staff = ref(false);
const corner = useFiveTap(() => (staff.value = true));
</script>

<template>
  <PhoneResult v-if="resultToken" :token="resultToken" />
  <AppFrame v-else :species="s.species">
    <div class="flex h-full flex-col">
      <header v-if="s.screen !== 'attract'" class="flex shrink-0 items-center justify-between px-4 pt-2 md:px-8 md:pt-4">
        <button aria-label="Start over" data-testid="home" class="hit rounded-full px-3 py-1 text-base text-muted md:text-lg" @click="s.reset()">✕ Start over</button>
        <span class="font-display text-xl font-semibold md:text-2xl">Pet<span class="text-accent">Pop</span></span>
      </header>
      <main class="relative min-h-0 flex-1">
        <Transition name="screen" mode="out-in">
          <div :key="s.screen" class="absolute inset-0" :data-screen="s.screen">
            <component :is="screens[s.screen]" />
          </div>
        </Transition>
      </main>
    </div>
    <button v-if="isKiosk" aria-label="Staff" data-testid="staff-corner" class="absolute right-0 top-0 z-50 h-20 w-20 opacity-0" @click="corner" />
    <Transition name="fade">
      <StillThere v-if="countdown !== null" :seconds="countdown" @stay="dismiss" />
    </Transition>
    <Transition name="fade">
      <Offline v-if="!online" />
    </Transition>
    <Transition name="fade">
      <StaffPanel v-if="staff" @close="staff = false" />
    </Transition>
  </AppFrame>
</template>

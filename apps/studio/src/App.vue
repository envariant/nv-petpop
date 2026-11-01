<script setup lang="ts">
// PetPop Studio (staff, decision 122): the curation workspace and the one-off figurine flow behind a staff login.
// Desktop first: a top bar, screens that use the width, the system keyboard; it still works on a tablet.
import { onMounted, ref } from 'vue';
import { AppFrame } from '@petpop/ui-vue';
import { useOnline } from './composables';
import { SCREENS } from './screens';
import { useSession } from './stores/session';
import StudioBar from './components/StudioBar.vue';
import Login from './screens/Login.vue';
import Offline from './components/Offline.vue';
import QueuePanel from './components/QueuePanel.vue';

const s = useSession();
const online = useOnline();
const queue = ref(false);
onMounted(() => void s.restore());
</script>

<template>
  <AppFrame :species="s.species">
    <Login v-if="!s.user" />
    <div v-else class="flex h-full flex-col">
      <StudioBar @queue="queue = true" />
      <main class="relative min-h-0 flex-1">
        <Transition name="screen" mode="out-in">
          <div :key="s.screen" class="absolute inset-0" :data-screen="s.screen">
            <component :is="SCREENS[s.screen]" />
          </div>
        </Transition>
      </main>
    </div>
    <Transition name="fade">
      <Offline v-if="!online" />
    </Transition>
    <Transition name="fade">
      <QueuePanel v-if="queue && s.user" @close="queue = false" />
    </Transition>
  </AppFrame>
</template>

<script setup lang="ts">
// The top bar: the areas, the manual-task count, the signed-in user, the queue and sign out. On a narrow screen the
// account links wrap to a second row and the areas scroll sideways.
import { cx } from '@petpop/ui-vue';
import { usePoll } from '../composables';
import { useManual } from '../stores/manual';
import { useSession, type Screen } from '../stores/session';
defineEmits<{ queue: [] }>();
const s = useSession();
const m = useManual();
usePoll(() => m.load(), 15000);
const AREAS: { screen: Screen; title: string }[] = [
  { screen: 'generate', title: 'Generate' },
  { screen: 'review', title: 'Review' },
  { screen: 'library', title: 'Library' },
  { screen: 'parts', title: 'Parts' },
  { screen: 'releases', title: 'Releases' },
  { screen: 'manual', title: 'Manual' },
];
</script>

<template>
  <header class="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b-2 border-line bg-paper px-4 py-3 text-base text-muted md:gap-x-6 md:px-8 md:text-lg" data-testid="studio-bar">
    <button class="hit shrink-0 font-display text-xl text-ink md:text-2xl" data-testid="home" @click="s.go('generate')">
      Pet<span class="text-accent">Pop</span> Studio
    </button>
    <nav class="no-scrollbar flex min-w-0 items-center gap-1 overflow-x-auto md:gap-2">
      <button v-for="a in AREAS" :key="a.screen" :data-testid="`nav-${a.screen}`"
        :class="cx('hit rounded-full px-3 py-1', s.screen === a.screen && 'bg-card font-semibold text-ink shadow-soft')" @click="s.go(a.screen)">
        {{ a.title }}
        <span v-if="a.screen === 'manual' && m.pending > 0" class="ml-1 rounded-full bg-accent2 px-2 text-sm text-white" data-testid="manual-pending">{{ m.pending }}</span>
      </button>
    </nav>
    <div class="ml-auto flex shrink-0 items-center gap-4">
      <span data-testid="studio-user">{{ s.user?.username }} ({{ s.user?.role }})</span>
      <button class="hit underline" data-testid="open-queue" @click="$emit('queue')">Queue</button>
      <button class="hit underline" data-testid="logout" @click="s.logout()">Sign out</button>
    </div>
  </header>
</template>

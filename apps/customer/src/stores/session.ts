// One visitor's session (Pinia). reset() wipes everything (idle, Start over, Done). The customer app talks only to
// the /kiosk routes and never depends on the GenAI host (BRIEF Section 17). The design itself is stores/design.ts.
import { defineStore } from 'pinia';
import { ref } from 'vue';
import { ApiFailure, KioskApi, randomSeed, specFromBreed } from '@petpop/core';
import type { BespokeAccepted, Breed, CompositionBody, PetSpec, Species } from '@petpop/core';
import { useDesign } from './design';

export type Screen = 'attract' | 'species' | 'breed' | 'design' | 'name' | 'order' | 'bespoke';

export const useSession = defineStore('session', () => {
  const screen = ref<Screen>('attract');
  const sessionId = ref<string | null>(null);
  const idleSeconds = ref(90);
  const countdownSeconds = ref(15);
  const bespokeEnabled = ref(false);
  const species = ref<Species | null>(null);
  const breed = ref<Breed | null>(null);
  const spec = ref<PetSpec | null>(null);
  const bespoke = ref<BespokeAccepted | null>(null);
  const error = ref<string | null>(null);

  function go(s: Screen) {
    screen.value = s;
    error.value = null;
  }
  function clear() {
    sessionId.value = null;
    species.value = null;
    breed.value = null;
    spec.value = null;
    bespoke.value = null;
    error.value = null;
  }
  async function start() {
    clear();
    screen.value = 'species';
    try {
      const s = await KioskApi.createSession();
      sessionId.value = s.session_id;
      idleSeconds.value = s.idle_policy.idle_seconds;
      countdownSeconds.value = s.idle_policy.countdown_seconds;
      bespokeEnabled.value = s.bespoke_enabled;
    } catch {
      /* the offline overlay retries */
    }
  }
  function chooseSpecies(s: Species) {
    species.value = s;
    breed.value = null;
    spec.value = null;
    screen.value = 'breed';
  }
  function chooseBreed(b: Breed) {
    breed.value = b;
    spec.value = specFromBreed(species.value!, b, randomSeed());
    screen.value = 'design';
  }
  async function requestBespoke(contact: string) {
    const composition = useDesign().composition;
    if (!sessionId.value || !composition) return;
    error.value = null;
    try {
      // The design goes to the studio as the bespoke job's starting point (BRIEF Section 17).
      const created = await KioskApi.createComposition(sessionId.value, composition as CompositionBody);
      bespoke.value = await KioskApi.bespoke(created.composition_id, contact.trim() || undefined);
    } catch (e) {
      error.value = e instanceof ApiFailure && e.status === 409 ? String(e.detail) : 'Something went wrong. Please ask a member of staff.';
    }
  }
  function reset() {
    useDesign().reset();
    clear();
    screen.value = 'attract';
  }
  return { screen, sessionId, idleSeconds, countdownSeconds, bespokeEnabled, species, breed, spec, bespoke, error, go, start, chooseSpecies, chooseBreed, requestBespoke, reset };
});

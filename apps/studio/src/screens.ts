// Every Studio screen by name (App.vue and the stories render from this map).
import type { Component } from 'vue';
import type { Screen } from './stores/session';
import Generate from './screens/Generate.vue';
import Review from './screens/Review.vue';
import Library from './screens/Library.vue';
import Releases from './screens/Releases.vue';
import Manual from './screens/Manual.vue';
import Species from './screens/Species.vue';
import Breed from './screens/Breed.vue';
import Build from './screens/Build.vue';
import Brief from './screens/Brief.vue';
import NameScreen from './screens/Name.vue';
import Generating from './screens/Generating.vue';
import Result from './screens/Result.vue';

export const SCREENS: Record<Screen, Component> = {
  generate: Generate, review: Review, library: Library, releases: Releases, manual: Manual,
  species: Species, breed: Breed, build: Build, brief: Brief, name: NameScreen, generating: Generating, result: Result,
};

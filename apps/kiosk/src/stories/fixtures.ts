// Story and test data built from the fixture pack (fixtures/pets/biscuit).
import biscuit from '@fixtures/pets/biscuit/spec.json';
import type { Breed, PetSpec } from '@petpop/core';
import dogs from '@data/breeds/dog.json';

export const SPEC = biscuit as unknown as PetSpec;
export const CORGI = (dogs.breeds as unknown as Breed[]).find((b) => b.id === 'corgi_pembroke')!;

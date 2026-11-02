// Story and test data built from the fixture pack (fixtures/pets/biscuit).
import biscuit from '@fixtures/pets/biscuit/spec.json';
import type { Breed, CompositionStatus, PetSpec } from '@petpop/core';
import dogs from '@data/breeds/dog.json';

export const SPEC = biscuit as unknown as PetSpec;
export const CORGI = (dogs.breeds as unknown as Breed[]).find((b) => b.id === 'corgi_pembroke')!;

/** A finished library order (the Order screen once Stage F is done), with the fixture pack's figurine. */
export const ORDER_READY = {
  composition_id: 'c_story', session_id: 's_story', status: 'ready', pet_name: 'Biscuit', species: 'dog', release_version: 'release-dog-1',
  created_at: '2026-10-29T10:00:00Z', ticket: 'PP-4821', result_url: 'http://kiosk.local/r/c_story.0.mock',
  export: { job_id: 'j_story', status: 'done', stage: 'done', pct: 100, message: 'Your figurine is ready' },
  artefacts: [], previews: { glb: '/fixtures/biscuit/figure.glb', thumbnail: '/fixtures/biscuit/thumbnail.png' }, error: null, composition: {},
} as unknown as CompositionStatus;

/** A signed-in customer (decision 126): email and Google. */
export const ACCOUNT = { account_id: 'a_story', name: 'Sam', email: 'sam@example.com', phone: null, providers: ['google' as const], created_at: '2026-11-01T09:00:00Z' };

/** The same order, exported but waiting for its PayNow payment (decision 125). */
export const PAY_OFFER = { price: { amount: '39.00', currency: 'SGD' as const }, methods: ['paynow', 'card'] as ('paynow' | 'card')[], provider: 'fake' as const };
export const ORDER_PAYING = {
  ...ORDER_READY, result_url: null,
  payment: { payment_id: 'p_story', composition_id: 'c_story', method: 'paynow', status: 'pending', price: PAY_OFFER.price, provider: 'fake',
    qr: '00020101021226370009SG.PAYNOW010120213201234567A0301104081999123152040000530370254053900.005802SG5907PETPOP 6009Singapore6304ABCD',
    checkout_url: null, created_at: '2026-11-02T10:00:00Z', expires_at: '2026-11-02T10:15:00Z', paid_at: null },
} as unknown as CompositionStatus;

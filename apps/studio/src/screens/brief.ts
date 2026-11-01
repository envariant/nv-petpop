const FIELD_LABEL: Record<string, string> = {
  'body.size': 'Size', 'body.build': 'Build', 'body.leg_length': 'Legs', 'coat.length': 'Coat length', 'coat.texture': 'Coat', 'colour.base': 'Main colour',
  'colour.secondary': 'Second colour', 'colour.pattern': 'Pattern', 'colour.markings': 'Markings', 'ears.shape': 'Ears', 'ears.size': 'Ear size', 'tail.type': 'Tail',
  'tail.length': 'Tail length', 'head.muzzle_length': 'Muzzle', eyes: 'Eyes', 'nose.colour': 'Nose', accessories: 'Accessories', personality: 'Personality',
  'breed.id': 'Breed', 'overrides.ears.asymmetry': 'Floppy ear',
};

/** The selector names for the spec paths the brief changed. */
export function changedLabels(paths: string[]): string[] {
  const out = new Set<string>();
  for (const p of paths) {
    const key = Object.keys(FIELD_LABEL).find((k) => p === k || p.startsWith(`${k}.`));
    if (key) out.add(FIELD_LABEL[key]);
  }
  return [...out];
}

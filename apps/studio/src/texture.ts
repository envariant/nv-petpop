// The words a breed's default texture uses (decision 131): the patterns and markings of the breed database
// (data/breeds/dog_pebbles_simple.json, preset.colour; texture.test.ts checks every one is here). Others may be typed:
// a pattern or a marking is a name the per-part masks are made for.
export const PATTERNS = ['solid', 'bicolour', 'tricolour', 'saddle_with_white_chest', 'merle', 'sable', 'spotted', 'tuxedo'];
export const MARKINGS = ['white_chest', 'white_blaze', 'white_socks', 'dark_mask', 'points'];
export const words = (x: string) => x.replace(/_/g, ' ');
/** A typed name as the texture stores it: lower case, words joined by underscores. */
export const slug = (x: string) => x.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40);

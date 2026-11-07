# Part kits: authoring, rigging and composing breeds from parts (decisions 127 to 131)

A breed is a **kit** of five parts, put together at joints:

| Kind | Instances | Joint | Moves |
| --- | --- | --- | --- |
| torso | 1 | six attachment points (head, front left, front right, hind left, hind right, tail) | none |
| head | 1 | pivot + axis | yaw, pitch and roll, within the head's limits |
| front leg | 2 | pivot + axis | twist about the socket axis: 0, 120 or 240 degrees |
| hind leg | 2 | pivot + axis | twist about the socket axis: 0, 120 or 240 degrees |
| tail | 1 | pivot + axis | none |

**The shared library and the breed's head (decision 130).** Torsos, legs and tails are shared by every breed: a library
of variants named by the breed database's part types (torso `long_low`, `standard`, ...; front leg `paw`, `boot`, ...;
hind leg `bean`, `hock`, ... and the sitting `sitting_fold`; tail `bob`, `plume`, ...), each rigged once. Each breed
brings its own **head**, with its own texture template (decision 129). A breed's kit:

- **allows** some shared variants per kind: the ones customers may choose on it. It starts with its own part types in
  the breed database (the corgi: `long_low`, `paw`, `bean` and `sitting_fold`, `bob`), its defaults; you offer more in
  the workbench. Head variants are not a customer choice.
- **stretches** each shared part per axis to its proportions (a corgi's `paw` is shorter than a dane's): first the
  size guess (decision 128), adjustable in the workbench. A variant the breed's row names fills the breed's guessed
  size; any other keeps its own shape at the breed's scale.
- has a **default texture**: its colours, pattern and markings (`preset.colour` in the breed database).
- may still have parts of its own (`<breed>__torso.glb`, ...), which win over the shared ones of the same variant.
- has **torso presets** per torso variant (decision 131): the customers' shape choices. The first is the default
  (the variant's stretch, no offsets); others ("Stocky", "Long", ...) each have their own stretch and **socket
  offsets**, a move (mm) and a turn (degrees about x, then y, then z) of any torso socket for this breed. Customers
  choose a torso variant and one of its presets.
- has its own **head variants** (`<breed>__head.glb`, `<breed>__head__<variant>.glb`); the default is the curator's
  choice in the workbench. Head variants are not a customer choice.

**Which parts each breed uses** lives in the per-breed parts file, `data/breeds/dog_breed_parts.json`, not in the
breed database (which describes bodies). Per breed and kind: the variants it offers and its default; per variant its
stretch (null: the size guess); per torso variant its presets; the sitting variant; the default texture. Studio
starts each breed's kit from its entry, and the workbench takes it from there. `make breed-parts` adds entries for new
breeds in the database (from their part types) and never touches existing ones, so the file is yours to edit:

```json
"corgi_pembroke": {"parts": {
  "torso": {"default": "long_low", "offer": {"long_low": {"presets": [
    {"preset_id": "default", "label": "Standard", "stretch": null, "sockets": {}},
    {"preset_id": "stocky", "label": "Stocky", "stretch": [1.2, 1.0, 0.9],
     "sockets": {"hind_left": {"translate": [1, 0, -2], "rotate": [0, 0, 8]}, "hind_right": {"translate": [-1, 0, -2], "rotate": [0, 0, -8]}}}]}}},
  "front_leg": {"default": "paw", "offer": {"paw": {"stretch": null}}}, ...},
 "sitting": "sitting_fold", "texture": {...}}
```

**Poses** are named sets of joint settings (each leg's twist, the head's angles) and may swap variants in: the
breed database sits every breed, so once `sitting_fold` is in the library a breed gets a **sitting** pose (the hind
legs folded) as its default. Each breed has an allowed list.

## 1. The parts

Names: `shared__<kind>__<variant>.glb` for the shared library (e.g. `shared__torso__long_low.glb`,
`shared__fore_leg__paw.glb`, `shared__hind_leg_sitting__sitting_fold.glb`), `<breed>__head.glb` for a breed's head.

Two ways in:

- **Exported one at a time** (the usual way, decision 128): each part generated on its own from the breed database's
  prompts (`data/breeds/dog_pebbles_simple.json`), so each comes at its own scale about its own origin and nothing in
  the files says how they fit. Studio and the draft script (section 1a) fit each part to its breed's **size guess**
  (`data/breeds/<species>_part_sizes.json`, `scripts/guess_part_sizes.py`), centre it, stand the torso on the floor
  (y = 0) and guess every joint from shape. Legs are taken as the pet's **left** legs, as the prompts ask.
- **Split in place** from one figure (the proxy kits, or a figure you model whole): the parts are in proportion and
  where they belong, so turn the scaling off ("Scale to size guess" in Studio, `--keep-scale` in the script). Studio
  then finds the joints where each part meets the torso (open cuts help), and mirrors a leg supplied on the right.

For both:

- Frame: export glTF (`.glb`), **+Y up, the pet facing +Z**, its own left on +X. (The draft script's `--front` turns
  exports that face another way.) Split-in-place parts are in **millimetres** (about 60 to 90 mm tall).
- Legs: the pet's **left** front leg and left hind leg; the right ones are their mirror.
- UVs (`uv_layout`, decision 129): every **head** has its **breed's own texture template**, and with it its own
  masks (blaze, mask, spots, ...): `dog-corgi_pembroke-head-1`. A breed's head variants share it. The torso, legs and
  tail each follow one layout shared across breeds and variants (`dog-torso-1`, ...), so their markings are painted
  once per pattern.
- File names: `<breed_id>__<kind>[__<variant>].glb`, where kind is `head`, `torso`, `front_leg`, `hind_leg` or `tail`
  and variant is lower case (`default` when absent). Example: `corgi_pembroke__torso__stocky.glb`. The breed
  database's names work too: `fore_leg` is the front leg, `hind_leg_sitting` the hind leg's `sitting` variant.
  `fixtures/parts/<species>/mixed__*.glb` are proxy kits cut from the templates (`scripts/make_proxy_parts.py`).

## 1a. The draft (a script, before Studio)

    make draft-parts FILES=~/exports/corgi OUT=var/drafts/corgi_pembroke [ARGS="--shared ~/exports/shared --front -x --fuse"]

`scripts/draft_parts.py` guesses how a breed's exported parts fit together and composes the draft figure, so you see
the whole breed before touching the workbench. It runs Studio's own part library on a throwaway database, so it
guesses exactly what an upload would: the fitted parts (`<out>/store/parts/`, textures kept), a draft kit
(`<breed>.draft-kit.json`, kit-2, its problems listed) and the figure in each pose, and once per other allowed variant
(`<breed>__draft*.glb`, `.stl`). Give it the breed's head and the shared library (`--files`, `--shared`). Every leg variant is slid along its axis to stand on the
floor, so the folded sitting leg and the standing one both reach it. The sizes come from the breed's size guess:
torso proportions and width from its prompt ("about twice as long as it is tall ... moderately full from side to
side"), leg proportions from theirs ("barely taller than it is wide"), leg thickness from the build, head size from
the size class (small breeds get bigger heads) with the muzzle and ears, tail length from the preset; the whole
figure scaled to the mandrel's 90 mm height, or 120 mm nose to tail for long, low breeds. They are guesses: final
authoring starts from the draft. Upload the same exports to Studio (Parts), rig, commit, then compose with your own
edits (section 3).

## 2. Rigging in Studio (the workbench)

1. **Parts**, upload the breed's GLBs (several at once). Studio reads the names, fits each part to the breed's size
   guess (unless "Scale to size guess" is off), keeps legs as left legs, and makes its first guess at every joint:
   for parts exported one at a time, from each part's shape and the torso's, with every leg standing on the floor; for
   parts split in place, where each part touches the torso (refined to the open cut's centre), the axis from there
   into the part, and the torso's six attachment points from the default parts. Each guess shows its method and a
   confidence; the upload's notes say what was scaled or mirrored.
2. Open the breed: the assembled figure in a 3D viewport. Select a joint (a part's pivot or a torso attachment) and
   drag it; switch the gizmo to rotate to turn its axis, and set the twist. **Symmetry** (on by default) mirrors an edit
   to a left slot onto the right one and keeps the head and tail slots on the centre line.
3. **Variants**: per kind, preview one (⧉ marks the shared library), make it the default, offer it to customers on
   this breed, and set its **stretch** (side to side, up, front to back; "size guess" puts the guess back). For the
   torso, its **shapes** (presets): preview one, add one (a copy of the one shown), rename or remove it; the stretch
   shown is the preset's. Select a torso socket: with a shared torso, or any shape but the default, the gizmo and the
   numbers set this breed's **socket offset** for that shape (move and turn), mirrored by symmetry; otherwise they
   edit the torso's own socket. A shared
   part's joints are the same for every breed: edit them from any breed's workbench (or the "Shared parts" kit) and
   every breed's kit has changes to commit.
   The breed's **default texture** is edited below it: colour A, and optionally B and C (a swatch and a name each;
   C is for tricolour patterns), the pattern, and the markings (remove one by tapping it; add one of the database's,
   or type another: it is stored lower case with underscores, the name its masks are made for). Each change is saved
   as you make it.
4. Head limits, and the **poses**: each leg's twist (0, 1 or 2 thirds), the head's angles, and any variant the pose
   swaps in (sitting: the hind leg `sitting_fold`); mark the default.
5. **Commit**: Studio checks the kit (every kind present with a default, every joint set, poses within limits and
   their variants in the kit) and saves it as the breed's next kit version (`data/schema/part_kit.schema.json`, kit-2:
   the allowed parts only, each with its stretch, the texture). The shared library is committed with each breed.

## 3. Composing in Blender (the final mesh step)

`scripts/compose_parts.py` consumes a committed kit and a composition (which variant per kind, which pose) and builds
the figure: each part stretched to the breed and placed at its joint, the right legs mirrored, then joined and stood
on the floor (a breed's stretch moves its feet; the plan's matrices include the move); `--fuse` voxel-remeshes it into one
watertight surface (no walls inside the joints); `--modify edits.py` runs your `modify(obj, job)` on the joined figure
in Blender, the last authoring step (joint fillets, sculpted blends, decimation). It writes `<breed>__<pose>.glb`, the
print `.stl` and a `.plan.json` recording which part went where with which matrix.

```bash
make compose-parts KIT=var/artefacts/kits/dog/corgi_pembroke/kit-3.json FILES=var/artefacts ARGS="--all-poses --fuse"
```
```bash
python scripts/compose_parts.py --kit kit-3.json --files ~/kits/corgi --out out/ --variants torso=stocky --pose sitting --modify my_edits.py
```

`--preset stocky` composes a torso shape other than the default. `--files` is the store root (Studio's keys) or a
folder of your own GLBs named as in section 1. Blender's `bpy`
(`PETPOP_BPY_PYTHON`) does the work when it is there; without it a trimesh stand-in composes (no voxel fuse, no
`--modify`).

## The maths

`packages/library/python/petpop_library/parts.py` (Python) and `packages/scene/src/parts.ts` (the apps) are twins.
A joint's frame is (axis, ref, axis x ref): ref is the world front (+Z) projected off the axis (world up when the axis
points nearly front or back), turned by the twist. A part goes onto its slot by putting its pivot on the attachment
and its frame onto the attachment's frame; the pose then turns it about the attachment's frame (legs about the axis;
the head by yaw about ref, pitch about axis x ref, roll about the axis). A right leg uses the mirrored part, joint and
twist, so a symmetric pose has the same index on both sides. A stretch `s` scales the part's mesh, pivot and axis
(the axis as a direction drawn on the mesh: `s * axis`, renormalised) before it is placed, and the torso's stretch its
attachments likewise; the workbench shows the stretched figure and saves edits in the parts' own coordinates. A
preset's socket offset then acts on the stretched socket: the position moves by `translate`, and the socket's whole
frame turns by `R = Rz Ry Rx` (`rotate`, degrees; three.js Euler order 'ZYX') about it, which turns its axis and
sets its twist. The mirror slot's offset is the mirror image: `translate` x negated, `rotate` y and z negated.

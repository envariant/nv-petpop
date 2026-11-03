# Part kits: authoring, rigging and composing breeds from parts (decision 127)

A breed is a **kit** of five parts, put together at joints:

| Kind | Instances | Joint | Moves |
| --- | --- | --- | --- |
| torso | 1 | six attachment points (head, front left, front right, hind left, hind right, tail) | none |
| head | 1 | pivot + axis | yaw, pitch and roll, within the head's limits |
| front leg | 2 | pivot + axis | twist about the socket axis: 0, 120 or 240 degrees |
| hind leg | 2 | pivot + axis | twist about the socket axis: 0, 120 or 240 degrees |
| tail | 1 | pivot + axis | none |

Each kind can have **variants** per breed. Customers choose the torso variant (the figure's shape) and, where a breed
has them, leg and tail variants; head variants are not a customer choice. Customers choose among their own breed's
parts only. **Poses** are named sets of joint settings (each leg's twist, the head's angles); each breed has an
allowed list, one to start with.

## 1. The parts

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
- UVs: each kind follows its shared texture layout (`uv_layout`), so markings painted once work on every breed and
  variant. Heads may get a per-breed layout later if one shared layout proves too tight.
- File names: `<breed_id>__<kind>[__<variant>].glb`, where kind is `head`, `torso`, `front_leg`, `hind_leg` or `tail`
  and variant is lower case (`default` when absent). Example: `corgi_pembroke__torso__stocky.glb`. The breed
  database's names work too: `fore_leg` is the front leg, `hind_leg_sitting` the hind leg's `sitting` variant.
  `fixtures/parts/<species>/mixed__*.glb` are proxy kits cut from the templates (`scripts/make_proxy_parts.py`).

## 1a. The draft (a script, before Studio)

    make draft-parts FILES=~/exports/corgi OUT=var/drafts/corgi_pembroke [ARGS="--front -x --fuse"]

`scripts/draft_parts.py` guesses how a breed's exported parts fit together and composes the draft figure, so you see
the whole breed before touching the workbench: the fitted parts (`<out>/parts/`, textures kept), a draft kit
(`<breed>.draft-kit.json`, the first guess at every joint) and the figure standing, once with the default variants
and once per other variant (`<breed>__draft*.glb`, `.stl`). Every leg variant is slid along its axis to stand on the
floor, so the folded sitting leg and the standing one both reach it. The sizes come from the breed's size guess:
torso proportions and width from its prompt ("about twice as long as it is tall ... moderately full from side to
side"), leg proportions from theirs ("barely taller than it is wide"), leg thickness from the build, head size from
the size class (small breeds get bigger heads) with the muzzle and ears, tail length from the preset; the whole
figure scaled to the mandrel's 90 mm height, or 120 mm nose to tail for long, low breeds. They are guesses: final
authoring starts from the draft. Upload `<out>/parts/` to Studio with "Scale to size guess" off (they are fitted
already) or the original exports with it on (the same result), rig, commit, then compose with your own edits
(section 3).

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
3. Head limits, and the **poses**: each leg's twist (0, 1 or 2 thirds) and the head's angles; mark the default.
4. **Commit**: Studio checks the kit (every kind present with a default, every joint set, poses within limits) and
   saves it as the breed's next kit version (`data/schema/part_kit.schema.json`).

## 3. Composing in Blender (the final mesh step)

`scripts/compose_parts.py` consumes a committed kit and a composition (which variant per kind, which pose) and builds
the figure: each part placed at its joint, the right legs mirrored, then joined; `--fuse` voxel-remeshes it into one
watertight surface (no walls inside the joints); `--modify edits.py` runs your `modify(obj, job)` on the joined figure
in Blender, the last authoring step (joint fillets, sculpted blends, decimation). It writes `<breed>__<pose>.glb`, the
print `.stl` and a `.plan.json` recording which part went where with which matrix.

```bash
make compose-parts KIT=var/artefacts/kits/dog/corgi_pembroke/kit-3.json FILES=var/artefacts ARGS="--all-poses --fuse"
```
```bash
python scripts/compose_parts.py --kit kit-3.json --files ~/kits/corgi --out out/ --variants torso=stocky --pose sitting --modify my_edits.py
```

`--files` is the store root (Studio's keys) or a folder of your own GLBs named as in section 1. Blender's `bpy`
(`PETPOP_BPY_PYTHON`) does the work when it is there; without it a trimesh stand-in composes (no voxel fuse, no
`--modify`).

## The maths

`packages/library/python/petpop_library/parts.py` (Python) and `packages/scene/src/parts.ts` (the apps) are twins.
A joint's frame is (axis, ref, axis x ref): ref is the world front (+Z) projected off the axis (world up when the axis
points nearly front or back), turned by the twist. A part goes onto its slot by putting its pivot on the attachment
and its frame onto the attachment's frame; the pose then turns it about the attachment's frame (legs about the axis;
the head by yaw about ref, pitch about axis x ref, roll about the axis). A right leg uses the mirrored part, joint and
twist, so a symmetric pose has the same index on both sides.

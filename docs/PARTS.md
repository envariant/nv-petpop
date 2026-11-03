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

## 1. Authoring the parts (you, in Blender)

- Model the figure whole, then split it into the five parts **in place** (do not move them apart): Studio finds the
  joints where each part meets the torso. Leaving the cuts open helps the first guess; closed parts work too.
- Frame: export glTF (`.glb`), **+Y up, the pet facing +Z**, its own left on +X, in **millimetres** (the figurine's
  real size, about 60 to 90 mm tall).
- Legs: supply the pet's **left** front leg and left hind leg; the right ones are their mirror. (A right leg is
  mirrored on import.)
- UVs: each kind follows its shared texture layout (`uv_layout`), so markings painted once work on every breed and
  variant. Heads may get a per-breed layout later if one shared layout proves too tight.
- File names: `<breed_id>__<kind>[__<variant>].glb`, where kind is `head`, `torso`, `front_leg`, `hind_leg` or `tail`
  and variant is lower case (`default` when absent). Example: `corgi_pembroke__torso__stocky.glb`.
  `fixtures/parts/<species>/mixed__*.glb` are proxy kits cut from the templates (`scripts/make_proxy_parts.py`).

## 2. Rigging in Studio (the workbench)

1. **Parts**, upload the breed's GLBs (several at once). Studio reads the names, keeps legs as left legs, and makes
   its first guess at every joint: where each part touches the torso (refined to the open cut's centre), the axis from
   there into the part, and the torso's six attachment points from the default parts. Each guess shows its method and
   a confidence.
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

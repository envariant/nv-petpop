# ComfyUI workflows (S3)

One API-format workflow JSON per stage, exported from the ComfyUI editor and committed with a
`meta.version` bump (never hand-edit node ids). The worker fills `PrimitiveNode`s **by title**, so each
workflow must expose these titled inputs and titled outputs:

| File | Stage | Titled inputs | Titled outputs |
| --- | --- | --- | --- |
| `01_concept_front.json` | B | `positive`, `negative`, `seed`, `depth_image`, `init_image` | `concept` |
| `02_views_ipadapter.json` | C | `concept_image`, `seed`, `negative`, `depth_{front,left,back,right}`, `positive_{front,left,back,right}` | `view_{front,left,back,right}` |
| `02b_views_mvadapter.json` | C (alt) | same as above | same as above |
| `03_shape_hy2mv.json` | D | `view_{front,left,back,right}`, `seed` | `shape` (GLB) |
| `03b_shape_hy21_single.json` | D (fallback) | `view_front`, `seed` | `shape` (GLB) |
| `04_texture_hy_paint.json` | F (texture) | `view_{front,left,back,right}`, `mesh_obj`, `resolution` | `albedo` |

Add `"meta": {"version": "1"}` at the top level of each exported file. The adapters live in
`backend/worker/backends/real/comfy.py`; model weights are pinned in `models.yaml` and fetched with
`make models`. None of these files exist yet: they are created on the GPU host in S3.

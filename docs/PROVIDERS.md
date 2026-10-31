# GenAI providers: commercial APIs behind profiles and manifests

Since decision 108 the GenAI stages can run on a commercial API instead of a GenAI host of our own. Nothing about
the product changes: the kiosk still never calls GenAI, a library release is still built on the base mesh's fixed
topology and UV layout, and Stages E and F still run in the VM. What changes is where Stages B and D come from.

## Three layers

| Layer | File | Says |
| --- | --- | --- |
| GenAI profile | `config/genai/<profile>.yaml` (schema `data/schema/genai-profile.schema.json`) | which provider serves which stage, with which models and options; timeouts; texture backend |
| Provider manifest | `config/providers/<manifest>.yaml` (schema `data/schema/provider-manifest.schema.json`) | one vendor API's wire format: auth, JSON envelope, upload, task polling, field names per capability, how private generation and commercial rights are obtained |
| Provider class | `backend/worker/providers/` | `ManifestProvider` executes any manifest; `TaskClient` (base.py) holds the HTTP rules |

The stages call the same adapter interfaces as before (`ImageBackend.concept`, `ShapeBackend.multiview` /
`single_view`, `TextureBackend.paint`); `backend/worker/backends/real/api.py` turns those calls into provider
capabilities:

| Capability | Stage | Returns |
| --- | --- | --- |
| `text_to_image(prompt, negative, params)` | B concept | PNG (JPEG and WebP are converted) |
| `image_to_model(image, params, seed)` | D shape (profile `shape.views: [front]`) | textured GLB |
| `multiview_to_model(views, params, seed)` | D shape (four views) | textured GLB |
| `image_to_multiview(image, params, seed)` | C views (multiview pipeline) | four PNGs (front, left, back, right) |
| `balance()` | `scripts/genai_check.py` | credits left |

## The `tripo` profile (Tripo3D apiv3)

```
concept (Tripo text-to-image) -> border-key matte (local) -> [no Stage C] -> Tripo image-to-model (textured)
  -> texture-keeping normalisation -> Stage E labels Tripo's mesh to the segmentation schema -> Stage F keeps
     Tripo's texture in Tripo's UVs (the figurine is Tripo's mesh itself, decision 116)
```

- Stage C is skipped (`image.views: none`): the shape comes from the concept alone, which stays truest to it
  (decision 107) and spends fewest credits. `shape.views: [front, left, back, right]` plus a views source would
  switch Stage D to multiview-to-model.
- Stage F's `transfer` texture keeps the provider's own texture image in the provider's own UVs: Stage E stores it as
  `provider_albedo.png` and the figurine mesh keeps Tripo's UVs, so nothing is resampled and nothing can ghost
  (decisions 108 and 116). A provider mesh without a texture image takes its colour by nearest surface point
  (pipelines/blender/transfer_texture.py).
- Each stage's manifest entry notes the provider task id and the credits it consumed; the job manifest records the
  provider manifest and version (`genai.models["provider.tripo"]`).

## Pipelines, quality switches and cost (decisions 114, 115)

Studio picks per job: the profile ("Run on"), its pipeline and its quality switches; each job records all three.

| Tripo pipeline | Stages | API credits per figurine |
| --- | --- | --- |
| Single view (default) | text-to-image -> image-to-3D (textured) | 35 |
| Multiview | text-to-image -> image-to-multiview -> multiview-to-3D (textured) | 45 |

| Switch | Default | Add-on | Note |
| --- | --- | --- | --- |
| HD texture | on | +10 | the figurine's texture as Tripo made it |
| HD geometry | off | +20 | reaches the print: the figurine is Tripo's mesh (decision 116) |
| Quad mesh | off | +5 | reaches the figurine's mesh (the print is re-meshed for watertightness either way) |

Prices from developers.tripo3d.ai/en/pricing on 2026-10-31 (1 credit = $0.01; image models other than the default
cost more). In manual mode the same requests run in Tripo Studio on its own credits.

## Credentials, cost and rights

- The key is read from the environment variable the profile names (`TRIPO_API_KEY`); it is never logged or
  committed. In a cloud session, add it in the environment settings (Network secrets or an environment
  variable); a new session picks it up. `python scripts/genai_check.py` with `GENAI_PROFILE=tripo` shows the
  balance.
- A task-creating POST is never retried after an ambiguous failure, so a dropped connection cannot spend credits
  twice; polls and downloads retry with back-off. A task still running at a stage deadline keeps running at the
  vendor and is charged.
- Private generation and commercial use: `licence` in the manifest records how the vendor grants them. Tripo grants
  both per account plan (subscribers' models are private with full commercial rights); no per-request flag is
  documented in its SDK 1.0.0. If a vendor has one, `create_extras` puts it on every generation request.

## Manual mode

`GENAI_PROFILE=tripo-manual` builds exactly these requests but hands each one to the operator in PetPop Studio
(Manual) instead of sending it; the job waits until the output is uploaded (docs/MANUAL-MODE.md, decision 111).
A provider entry with `kind: manual` does this for any manifest; a capability's optional `manual` block holds the
vendor app's steps the inbox shows.

## Swapping to an equivalent API

1. Write `config/providers/<vendor>-<api>.yaml` from its docs: routes, the field paths of the upload token, task
   id, status, progress, credits, errors and result URLs, and the request fields per capability (`body`, `rename`,
   `seeds`). `tests/unit/test_provider_manifests.py` shows an API with entirely different names working from its
   manifest alone.
2. Add a profile (copy `config/genai/tripo.yaml`), pointing `providers.<name>` at the manifest and the key's
   environment variable, and choose the models and options in `image.params` / `shape.params`.
3. `GENAI_PROFILE=<profile> python scripts/genai_check.py`, then one job.

Only an API a manifest cannot describe (results that are not URLs, synchronous answers, streaming) needs a class
in `backend/worker/providers/` registered in `KINDS`.

## Building your own GenAI API later

Implement any wire format a manifest can describe and write its manifest; the simplest is Tripo's shape:
`POST /files` (multipart) -> token; `POST /<capability>` (JSON) -> task id; `GET /tasks/{id}` -> status, output
URLs, credits; signed result URLs. The pipeline, profiles and tests then treat it like any vendor.

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
| `balance()` | `scripts/genai_check.py` | credits left |

## The `tripo` profile (Tripo3D apiv3)

```
concept (Tripo text-to-image) -> border-key matte (local) -> [no Stage C] -> Tripo image-to-model (textured)
  -> texture-keeping normalisation -> Stage E wrap onto the base mesh -> Stage F: texture TRANSFER onto the base UVs
```

- Stage C is skipped (`image.views: none`): the shape comes from the concept alone, which stays truest to it
  (decision 107) and spends fewest credits. `shape.views: [front, left, back, right]` plus a views source would
  switch Stage D to multiview-to-model.
- Stage F's `transfer` texture (pipelines/blender/transfer_texture.py) gives each texel of the base UV layout the
  colour of the nearest point of the provider's own textured surface. Unlike projecting views onto the wrapped
  mesh, nothing can ghost (decision 108).
- Each stage's manifest entry notes the provider task id and the credits it consumed; the job manifest records the
  provider manifest and version (`genai.models["provider.tripo"]`).

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

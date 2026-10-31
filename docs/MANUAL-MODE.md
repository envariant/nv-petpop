# Manual mode: Tripo by hand, through PetPop Studio

Decision 111. Tripo Studio credits do not apply to the Tripo API, so until API credits are worth spending, the
pipeline runs on the **`tripo-manual`** profile: every request it would have sent Tripo's API is shown to you in
PetPop Studio instead. You run it in Tripo Studio (your credits, private generation, commercial use), download
the output, and upload it back; the job then carries on exactly as it would have with the API. Switching to the
API later is `GENAI_PROFILE=tripo`: same manifest (`config/providers/tripo-v3.yaml`), models and options.

## What happens to a job

```
A parse -> control -> B concept: WAITS (you: Tripo text to image -> upload the image)
                   -> C skipped -> D shape: WAITS (you: Tripo image to 3D on the matted concept -> upload the GLB)
                   -> E labels the uploaded mesh to the schema -> F keeps its texture, print files -> done (and curation, for a batch)
```

- While it waits, the job's status is `waiting` (Studio shows "This figurine is waiting for you"); nothing runs.
- Uploading the output re-queues the job, which resumes from its stored stages; the provider hands your file back
  as if the API had returned it, with a synthetic task record (`manual-<request>`, no credits) in the stage notes.
- The multiview pipeline (decision 114) adds a step after the concept: Tripo image to multiview, uploaded as four
  images, one per slot (front, left, back, right; left is the pet's own left side). The job continues once all four
  are in, then waits for the 3D model from those views (Tripo multiview to 3D).
- Quality switches chosen for the job (HD texture, HD geometry, quad) appear in the task's settings to match.
- If the silhouette check in Stage D rejects your model, the pipeline asks once more (a new request with the next
  seed); if that fails too, the parametric base mesh ships, as on any profile.

## Running it

1. Offer it in Studio: `PETPOP_STUDIO_PROFILES=tripo-manual` in `.env` (or make it the default with
   `GENAI_PROFILE=tripo-manual`), then `make dev` (docs/LOCAL.md). No key needed. Each job or batch then picks
   "Run on" in Studio (decision 113).
2. PetPop Studio (http://127.0.0.1:5174/studio/ with `make dev`): sign in as operator.
3. Make figurines as usual: **Generate** for a batch (breeds x variants x seeds, which builds the library) or
   **One-off figurine** for a single one.
4. Open **Manual** (the tab shows how many requests wait). For each task:
   - the steps for Tripo Studio, the prompt and negative prompt (Copy buttons), the settings to match, and the
     input files to download (the matted concept for image to 3D);
   - "The API request this replaces": the exact JSON body, route and manifest version;
   - choose the output file and **Send to the job**. Images: PNG, JPG or WebP. Models: GLB with its texture.
5. Batch figurines then appear in **Review** as they finish; accept parts, publish in **Library**, cut a
   **Release** for the kiosk, all as before.

## Checks on an upload

An image must decode; a model must be a binary glTF (`.glb`) with faces and a real extent. Draco-compressed GLBs
are decoded (DracoPy); meshopt-compressed ones are refused with a hint to export without mesh compression. A task
takes one output; a wrong upload after submission means re-running the job (Queue, Retry).

## Where things are

- Requests and outputs: the job's store under `jobs/<job_id>/manual/<request_id>/` (`request.json`, input files,
  `result`); the inbox reads `manual_tasks` in the database.
- API: `GET /api/v1/studio/manual`, `GET /api/v1/studio/manual/{task_id}`,
  `POST /api/v1/studio/manual/{task_id}/result` (multipart `file`); API 3.2.0.
- Without the UI: `GENAI_PROFILE=tripo-manual python scripts/run_job.py --breed beagle --seed 1` prints the
  request and where to put the output; run it again to resume.
- `make mock` / `VITE_MOCK=1` serve two demo tasks (a concept request and a 3D request) to try the inbox.

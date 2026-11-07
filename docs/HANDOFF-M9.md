# Handoff M9: seeding the library through Studio

M9 fills the kiosk's library with real figurines: every breed preset gets a family on a mesh generated for it, and
every marking has a pattern layer (BRIEF Section 16, gate 9). Since decision 116 each curated figurine is a mesh of
its own, labelled to the species segmentation schema; breeds that should look alike share one mesh and are
labelled so. Generation runs on Tripo, through the API (`tripo`) or by hand in Tripo Studio (`tripo-manual`,
docs/MANUAL-MODE.md). This document is the staff routine; docs/HANDOFF-TRIPO.md covers the first Tripo jobs.

## Before you start

- `make dev` (docs/LOCAL.md) with `PETPOP_STUDIO_PROFILES=tripo,tripo-manual` in `.env`; for the API, `TRIPO_API_KEY`
  as well. Sign in to Studio (http://127.0.0.1:5174/studio/) as a curator; an admin cuts releases.
- One bespoke job per species first (HANDOFF-TRIPO, first steps), and look at its `parts.png` and landmarks: if
  Stage E labels Tripo's meshes badly, curation will reject everything, so fix that before spending a batch.
- Budget (Tripo's pricing, decision 114): single view 35 credits a figurine, multiview 45, plus HD texture 10
  (on by default), HD geometry 20 and quad 5. A 60-breed dog pass on single view with HD texture is about 2,700
  credits; in manual mode Tripo Studio's own credits apply instead.

## The routine, per batch

1. **Generate**: pick the species, 5 to 10 breeds, the preset variant, one seed (two for hero breeds); "Run on"
   `tripo` (or `tripo-manual`), pipeline and quality switches. The credit estimate shows per figurine.
2. In manual mode, work through **Manual**: each request shows the prompt, settings and inputs for Tripo Studio;
   upload what Tripo makes (decision 111).
3. **Review**: each finished figurine is one candidate, "Family on its own mesh", with its turntable and mesh QC
   (parts labelled, watertight print, triangle count). Auto-rejected ones say why (no generated mesh, labelling
   failed, a leaky print or thin walls). Accept the good ones (**Accept N that passed QC**), reject the rest,
   star heroes.
4. **Publish** the accepted families (per candidate, or **Publish N accepted**).
5. **Share meshes where breeds look alike**: in **Library**, Families, open a family and add breed ids (comma
   separated). Every breed on a family shares its mesh, and the kiosk tells customers "Same figure shape as ...";
   the editor's "Mesh m_... shared with ..." line lists breeds on other families built on the same mesh. Prefer a breed's own mesh when it has a distinct silhouette (ears,
   muzzle, tail); share only close look-alikes, or to fill gaps while their own figurine is pending.
6. **Release** (admin): Releases, **Publish a dog release** (or cat). The bundle lands in the kiosk's release inbox
   (`PETPOP_RELEASE_INBOX`, default `var/releases/inbox`) and the kiosk switches to it within 30 s.
7. **Check coverage**: `python scripts/library_coverage.py dog` (or the bundle path) lists the breeds covered (as
   part kits, or on a generated mesh), those still only on the proxy template or with nothing, the shared meshes, any
   kit whose default texture names a marking none of its parts has a mask for, and (for breeds on whole-figure
   meshes) any marking without a pattern layer. It exits 0 when coverage is complete; `--json file` keeps the report.

Re-runs: a rejected figurine can be generated again (another seed, or multiview for a tricky silhouette) in the
next batch; a published family can be edited (name, tags, breeds), which starts its next version, and unpublished.

## Patterns

The ten pattern layers come with the proxy release and fit every mesh (they are rasterised per mesh from the
segmentation). A textured figurine starts with no extra layers: its texture already carries its coat, and the base
colour tints it (decision 119). Edit a layer's default colour and coverage in Library, Patterns, if a coat reads
wrong on the new meshes.

## Gate 9

`make gate-9` (decision 140) checks:

- **Coverage**: `scripts/library_coverage.py` for dog and cat on the releases Studio published (var/releases/inbox).
  Until there are any, it prints SKIPPED.
- **The walkthrough from attract to a paid order in under 3 minutes**: a whole figure, and a figure of parts with a
  shape, a marking, a spot and an extra. Both are timed against the real backend.
- **70 % breed recognisability**: the final manual pass, in three steps:
  1. `python scripts/recognisability.py sheet` picks 20 library figurines from the newest releases: every kit in its
     default design, rendered as the print paints it, and families on generated meshes. It writes
     `var/gate9/sheet.html`, each figurine with four breed names, one right; the key stays in `var/gate9/key.json`.
  2. Open the sheet on a phone or tablet and hand it to people who do not know the breeds. Each person ends with
     "Finish and save my answers", which downloads their answers.
  3. `python scripts/recognisability.py record answers-*.json` scores them and writes
     `docs/gate9/recognisability.json`. Commit it.

  Until a result is recorded, the gate prints SKIPPED; below 70 % it fails. Record the result in docs/PROGRESS.md
  (Track B3).

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
   separated). Every breed on a family shares its mesh; the editor shows "Mesh m_... shared with ..." and the kiosk
   tells customers "Same figure shape as ...". Prefer a breed's own mesh when it has a distinct silhouette (ears,
   muzzle, tail); share only close look-alikes, or to fill gaps while their own figurine is pending.
6. **Release** (admin): Releases, **Publish a dog release** (or cat). The bundle lands in the kiosk's release inbox
   (`PETPOP_RELEASE_INBOX`, default `var/releases/inbox`) and the kiosk switches to it within 30 s.
7. **Check coverage**: `python scripts/library_coverage.py dog` (or the bundle path) lists the breeds on a
   generated mesh, those still only on the proxy template or without a family, the shared meshes, and any marking
   without a pattern layer. It exits 0 when coverage is complete.

Re-runs: a rejected figurine can be generated again (another seed, or multiview for a tricky silhouette) in the
next batch; a published family can be edited (name, tags, breeds), which starts its next version, and unpublished.

## Patterns

The ten pattern layers come with the proxy release and fit every mesh (they are rasterised per mesh from the
segmentation). A textured figurine starts with no extra layers: its texture already carries its coat, and the base
colour tints it (decision 119). Edit a layer's default colour and coverage in Library, Patterns, if a coat reads
wrong on the new meshes.

## Gate 9

Coverage (`scripts/library_coverage.py` exits 0 for dog and cat), then the kiosk walkthrough from attract to order
in under 3 minutes (`make gate-7` runs it), and 70 % breed recognisability: show 20 library figurines to people who
do not know the breed and count the right answers. Record the result in docs/PROGRESS.md (Track B3).

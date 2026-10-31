# PetPop: working rules for Claude Code

Read docs/BRIEF.md first; it is the spec. Section 13 gives the order of work: S0, S1, S2, M2.5, then S3 on
the Mac profile and S7 (the library track, Section 16) in parallel in this session.
Never install model stacks (torch, ComfyUI, Hunyuan3D) in a cloud session: GenAI stages run on a remote
host chosen by GENAI_PROFILE, and the Mac host is set up by Nishant from the scripts in mac/.

Profiles: GENAI_PROFILE=mock is the default everywhere. The worker never names a model or host; adapters
read config/genai/<profile>.yaml. GENAI_PROFILE=tripo runs the GenAI stages on the Tripo3D API (docs/PROVIDERS.md):
a vendor's wire format is a manifest in config/providers/, its key an environment variable, never committed;
GENAI_PROFILE=tripo-manual hands the same requests to the operator in Studio (docs/MANUAL-MODE.md). Current state
and next steps: docs/HANDOFF-TRIPO.md. Running locally: docs/LOCAL.md. Gates 3 to 6 and 8 print "SKIPPED (needs a GenAI host)" on the mock profile.
Commands: make dev (API + worker + SPA), make mock (standalone mock server), make test, make gate-N, make regress.

Loop: take the next unchecked item in docs/PROGRESS.md, implement it, run make test, run the milestone's
gate, commit with a conventional message, tick the item, continue. Do not stop to ask questions. Where the
brief is silent, choose the simplest option that satisfies the gate, record it in docs/DECISIONS.md, continue.

Git: work on branch poc and push after every green gate. Open one PR per milestone against main, then keep
working on poc without waiting for review.

Ownership: never hand-edit assets/base/ or the generated workflow JSONs in pipelines/comfy/ (regenerate them
with scripts/make_comfy_workflows.py); generate proxies by script. The base mesh is frozen before M9.
Contract: data/schema/openapi.json is the source of truth; change it only with a version bump that updates
mock-server, the TypeScript client and the backend in the same commit. manifest.schema.json is the contract
every GenAI adapter must satisfy, on every profile. A composition JSON is the only input to a library export.
Front end: every screen has a Storybook story and a Playwright test; gate-1 is the Playwright walkthrough.

Do not: download model weights, add paid services (other than the GenAI API providers Nishant chooses, decision
108), or commit secrets.

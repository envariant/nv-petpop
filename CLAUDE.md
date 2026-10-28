# PetPop: working rules for Claude Code

Read docs/BRIEF.md first; it is the spec. Section 13 gives the order of work: S0, then S1, then S2, then M2.5.
GenAI runs only on a remote GenAI host (Section 13, "GenAI profiles"). Never install or run GenAI models in a
cloud session. S3 drives a remote host only after Nishant has set its tunnel URLs and token in the environment.

Profile: GENAI_PROFILE selects config/genai/<profile>.yaml (mock, the default; mac-m4pro; nvidia-24gb). The
profile alone names models, hosts, quality, residency, timeouts and expected timings; the worker never does.
Gates 3 to 6 print "SKIPPED (needs a GenAI host)" on the mock profile.
Commands: make dev (API + worker + SPA), make mock (standalone mock server), make test, make gate-N, make regress,
make up / make smoke-stack (Compose stack), make workflows (regenerate ComfyUI JSONs), make -C mac ... (Mac host).

Loop: take the next unchecked item in docs/PROGRESS.md, implement it, run make test, run the milestone's
gate, commit with a conventional message, tick the item, continue. Do not stop to ask questions. Where the
brief is silent, choose the simplest option that satisfies the gate, record it in docs/DECISIONS.md, continue.

Git: work on branch poc and push after every green gate. Open one PR per milestone against main, then keep
working on poc without waiting for review.

Ownership: never hand-edit assets/base/ or the node ids in pipelines/comfy/*.json; generate proxies and the
workflows by script (scripts/make_proxy_base.py, scripts/make_comfy_workflows.py). Model ids and pins live in
config/genai/*.yaml and pipelines/comfy/models.yaml; sha256 pins are written only by scripts/models.py --pin.
Contract: data/schema/openapi.json is the source of truth; change it only with a version bump that updates
mock-server, the TypeScript client and the backend in the same commit.
Front end: every screen has a Storybook story and a Playwright test; gate-1 is the Playwright walkthrough.

Do not: install torch or ComfyUI or download model weights in a cloud session, add paid services, or commit
secrets (GENAI_TOKEN, .env, var/).

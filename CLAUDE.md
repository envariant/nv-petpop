# PetPop: working rules for Claude Code

Read docs/BRIEF.md first; it is the spec. Section 13 gives the order of work: S0, then S1, then S2.
Never start GPU work (milestones M3 to M5) in a cloud session.

Mode: PETPOP_MODE=mock is the default everywhere. Gates 3 to 5 print "SKIPPED (needs GPU)" in mock mode.
Commands: make dev (API + worker + SPA), make mock (standalone mock server), make test, make gate-N, make regress.

Loop: take the next unchecked item in docs/PROGRESS.md, implement it, run make test, run the milestone's
gate, commit with a conventional message, tick the item, continue. Do not stop to ask questions. Where the
brief is silent, choose the simplest option that satisfies the gate, record it in docs/DECISIONS.md, continue.

Git: work on branch poc and push after every green gate. Open one PR per milestone against main, then keep
working on poc without waiting for review.

Ownership: never hand-edit assets/base/ or the node ids in pipelines/comfy/*.json; generate proxies by script.
Contract: data/schema/openapi.json is the source of truth; change it only with a version bump that updates
mock-server, the TypeScript client and the backend in the same commit.
Front end: every screen has a Storybook story and a Playwright test; gate-1 is the Playwright walkthrough.

Do not: install torch or ComfyUI, download model weights, add paid services, or commit secrets.

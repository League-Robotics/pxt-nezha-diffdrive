---
id: "010"
title: "Build checkpoint: full build, flashable hex"
status: open
use-cases: []
depends-on: ["001", "002", "003", "004", "005", "006", "007", "008", "009"]
github-issue: ""
issue: ""
# completes_issue: Controls whether linked issues are archived when this ticket
# is moved to done. Default: true (archive when all referencing tickets are done).
# Set to false (scalar) to suppress archival for ALL linked issues on this ticket.
# Set to a mapping {filename.md: false} to suppress archival per issue filename.
# Use false for tickets that partially address a multi-sprint umbrella issue.
completes_issue: true
# exception: Written by a lower agent when it cannot proceed (see architecture §exception-protocol).
# exception:
#   thrown_by: "programmer"          # "programmer" | "sprint-planner"
#   thrown_at: "2026-05-07T14:23:00Z"
#   attempted: |
#     Description of what was attempted before giving up.
#   conflict: "architecture-update.md §3 — reason the agent is blocked"
#   surface: "internal"              # "user-visible" | "internal"
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint: full build, flashable hex

## Description

Standing convention: the last ticket in every sprint is a build checkpoint
that runs the real `pxt build` / `tools/make_deploy.py` pipeline and
confirms a flashable hex comes out the other end, closing the gap between
"597 host tests pass" and "this actually builds for the target." It's the
gate that would have caught issues the host-only test suite structurally
cannot see -- exactly the kind of blind spot this sprint's own thesis is
about (see `no-lint-or-typecheck-gate.md` and
`host-harness-masks-include-path-errors.md`, both addressed earlier in
this sprint but still only host-side gates; the actual cloud/CODAL compile
is the one check nothing else in this sprint substitutes for).

**Depends on tickets 001-009** -- this ticket must run last, after every
other change in the sprint, since its whole job is confirming the combined
result of all nine still builds. In particular:
- Ticket 008 adds a `typescript` dev dependency and possibly touches
  `package.json` -- confirm `pxt build`'s own dependency resolution still
  works cleanly alongside it.
- Ticket 009 is the ticket most likely to have left something broken (by
  design -- it's the one ticket expected to surface latent include
  problems). If ticket 009 corrected any `#include` paths, this checkpoint
  is the first real confirmation those corrections are actually right,
  since the host harness's own test (even the new mechanical gate) is
  still not the real compiler.
- Tickets 001-006 are docs/comments only and shouldn't affect the build,
  but this ticket is also the final confirmation that no doc edit
  accidentally clipped a code fence or similar into a source file.

## What to do

1. Run the full host test suite first (`uv run pytest`) and confirm it's
   green -- this is the pre-condition, not the checkpoint itself.
2. Run the real build pipeline exactly as prior sprints' build-checkpoint
   tickets have (e.g. sprint 010's
   `clasi/sprints/done/010-.../tickets/done/007-build-checkpoint-...md`,
   the clearest prior example on record): `tools/make_deploy.py` for the
   primary codal-microbit-v2 (V2) target, and again with `--testrig` for
   the second scratch path. `make_deploy.py`'s own triage
   (`classify_attempt()`) distinguishes a real compile diagnostic
   (hard failure, no retry) from the known benign shapes (legacy V1
   `bbc-microbit-classic-gcc` hex-merge failure; nondeterministic
   `TS9283`/`TS9043`/`TS9200` packaging aborts, retried once
   automatically) -- trust that triage rather than re-deriving it.
3. Confirm a flashable hex is produced with no errors for the V2 target
   (record the hex filename and byte size, as prior build-checkpoint
   tickets have).
4. If the build fails, the failure is diagnostic information about
   tickets 001-009, not a new bug to silently patch around -- report which
   prior ticket's change is implicated and coordinate the fix back into
   that ticket's scope (most likely candidate: ticket 009's include-path
   changes, or ticket 008's `package.json` dependency addition) rather
   than making an ad hoc fix in this ticket that isn't traceable to a
   ticket with acceptance criteria covering it.
5. Do not flash a real robot for this checkpoint unless the project's
   standing convention already does so for a docs/tooling sprint -- check
   what prior "build checkpoint" tickets in this repo actually verified
   (build success and hex output, vs. an on-hardware smoke test). This
   sprint changes no firmware behavior, so a hardware flash is unlikely to
   be a meaningful additional check, but follow the established convention
   rather than deciding unilaterally.

## Acceptance Criteria

- [ ] Full host suite (`uv run pytest`) passes.
- [ ] `ruff check tools tests` passes clean (ticket 007's gate).
- [ ] `tsc --noEmit` passes (ticket 008's gate).
- [ ] `clasi design validate` returns `ok: true` (ticket 001's gate).
- [ ] The real build pipeline (`tools/make_deploy.py` or equivalent)
      completes and produces a flashable hex with no errors.
- [ ] If the build surfaces a failure traceable to a specific ticket
      001-009, that failure is fixed within the scope of the responsible
      ticket (reopened if already closed) rather than patched ad hoc here.
- [ ] All of this sprint's success criteria from `sprint.md` are satisfied
      (design validate green, no stale `travelCalib`, S10 truthful, S12-S16
      removed, zero stale paths pinned by test, archaeology budget test in
      place, ruff clean, TypeScript decision executed, harness matches
      real build).

## Testing

- **Existing tests to run**: the full suite -- `uv run pytest` -- plus
  `ruff check tools tests` and `tsc --noEmit` as the two new gates this
  sprint added.
- **New tests to write**: none -- this ticket verifies existing gates and
  the real build, it doesn't add new pytest coverage of its own.
- **Verification command**: `uv run pytest && ruff check tools tests &&
  npx tsc --noEmit && clasi design validate && python tools/make_deploy.py
  && python tools/make_deploy.py --testrig`.

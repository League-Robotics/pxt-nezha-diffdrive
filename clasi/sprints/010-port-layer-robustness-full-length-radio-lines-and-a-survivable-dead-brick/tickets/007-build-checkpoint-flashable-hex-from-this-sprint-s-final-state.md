---
id: "007"
title: "Build checkpoint: flashable hex from this sprint's final state"
status: open
use-cases: []
depends-on: ['001', '002', '003', '004', '005', '006']
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

# Build checkpoint: flashable hex from this sprint's final state

## Description

Standing per-sprint convention (`src/DESIGN.md` §11/§14, sprint 008): a
green host suite is not evidence of target viability, since
`tests/host/` compiles at `-std=c++20` while both real embedded targets
compile at `-std=c++11`, and several of this sprint's own touched files
(`radio_transport.{h,cpp}`, `nezha_port.{h,cpp}`, `shims.cpp`) sit
entirely outside the `-std=c++11` syntax gate's four-file coverage —
invisible to every host test by construction. This sprint touches
build-eligible source (all six preceding tickets do), so it requires
this mandatory, always-last ticket per the standing convention, ordered
after and depending on every other ticket in the sprint.

Always run in the foreground per `.claude/rules/source-code.md`, never
backgrounded.

## Acceptance Criteria

- [ ] `tools/make_deploy.py` runs against this sprint's final state and
      produces a flashable hex for the codal-microbit-v2 (V2) target.
- [ ] `make_deploy.py`'s triage (sprint 008) correctly classifies the
      build attempt: a real `.cpp` compile diagnostic is treated as a
      hard failure (no retry); the two documented benign abort shapes
      (legacy V1 `bbc-microbit-classic-gcc` hex-merge failure;
      nondeterministic `TS9283`/`TS9043`/`TS9200` packaging abort) are
      retried once automatically.
- [ ] If the build fails on a real compile diagnostic, the diagnostic is
      resolved (fixing the offending ticket's change) before this ticket
      is marked done — a build-checkpoint failure blocks the sprint,
      exactly as sprint 008's own convention intends.
- [ ] Full `tests/host` suite passes (this is the sprint-level test run
      `close_sprint` gates on, per `.claude/rules/source-code.md`: run
      once per sprint here, not per ticket).
- [ ] `-std=c++11 -fsyntax-only` gate
      (`tests/host/test_cxx11_syntax_gate.py`) passes for the four
      covered files plus any extracted-header siblings this sprint added
      (none expected — this sprint adds no new host-portable header).

## Implementation Plan

**Approach.** Run the existing tooling; this ticket writes no new
production code.

**Files to modify:** none in `src/`. Possibly `tools/make_deploy.py`
only if this sprint's build surfaces a new benign-abort shape not yet
covered by its triage — unlikely, but the ticket should note if so
rather than silently working around it.

**C++11 gate coverage.** This ticket is the one place the gap between
"the syntax gate passes" and "the target actually links" gets closed —
see `src/DESIGN.md` §11 for the full distinction. It is not a substitute
for the syntax gate, and the syntax gate is not a substitute for it.

**Testing plan.**
- `uv run pytest` (or this project's equivalent host-suite entry point)
  for the full `tests/host` suite.
- `tools/make_deploy.py`'s own build-and-triage run.

**Documentation updates.** Record the resulting hex/build confirmation
in this ticket; update `docs/design/design.md`'s per-sprint convention
note only if this sprint's build surfaces something the convention
doesn't already describe (unlikely).

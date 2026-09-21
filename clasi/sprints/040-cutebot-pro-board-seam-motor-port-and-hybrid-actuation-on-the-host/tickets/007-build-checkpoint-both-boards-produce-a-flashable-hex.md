---
id: '007'
title: 'Build checkpoint: both boards produce a flashable hex'
status: open
use-cases: ["SUC-001", "SUC-005"]
depends-on: ["005", "006"]
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint: both boards produce a flashable hex

## Description

Depends on ticket 005 (the board bake must exist to select
`cutebot-pro`) and ticket 006 (confirms the hybrid stack already proves
out on the host simulator before spending a real build on it). This is
the mandatory, always-last build-checkpoint ticket
`docs/design/design.md`'s "Host-vs-target language standard" section
establishes as a standing convention for every sprint that touches
build-eligible source (`-std=c++20` host tests passing is not evidence
the code compiles for the real `-std=c++11` target — the confirmed
historical instance is a struct with default member initializers that
is not a C++11 aggregate).

- Run `tools/make_deploy.py` for a Nezha-fleet robot (no
  `firmware_bake.board` key) and confirm the resulting hex matches the
  pre-sprint build (byte-identical or, if the deploy pipeline embeds a
  timestamp/build id that legitimately differs, identical modulo that
  documented difference only).
- Run `tools/make_deploy.py` for the Cutebot fleet entry ticket 005
  created (`firmware_bake.board: "cutebot-pro"`) and confirm a
  flashable hex results — `build()`'s own triage-aware retry (sprint
  008's convention) handles the two known benign abort shapes
  automatically; a real `.cpp` compile failure is not retried and is
  this ticket's actual find.
- Confirm both hexes meet the existing `MIN_HEX_SIZE_BYTES` sanity
  floor (`tools/make_deploy.py:276`) — a suspiciously small hex is the
  documented signature of a truncated/incomplete build that otherwise
  exits clean.
- No firmware is flashed to any physical board in this sprint (both
  boards remain build-only artifacts here); Sprint 041 does the real
  flash.

## Acceptance Criteria

- [ ] `tools/make_deploy.py` produces `built/binary.hex` for a
      Nezha-fleet robot with no `firmware_bake.board` key, matching
      pre-sprint output.
- [ ] `tools/make_deploy.py` produces `built/binary.hex` for the
      Cutebot fleet entry (`firmware_bake.board: "cutebot-pro"`) with
      no compile errors.
- [ ] Both hexes meet `MIN_HEX_SIZE_BYTES`.
- [ ] Any benign build-abort retry that fires is logged as such
      (triage output distinguishes it from a real failure), per
      sprint 008's existing convention.
- [ ] Full host suite (`uv run pytest`) is green at this ticket's
      completion, confirming no earlier ticket's acceptance criteria
      regressed.

## Testing

- **Existing tests to run**: full `uv run pytest`; this ticket's own
  verification is real builds, not new pytest coverage.
- **New tests to write**: none required — this is a build/deploy
  checkpoint, not a unit-test ticket. If a gap is found, the fix
  belongs in the ticket whose module has the gap, not here.
- **Verification command**: two real `tools/make_deploy.py` runs (one
  per board), plus `uv run pytest` for the full suite.

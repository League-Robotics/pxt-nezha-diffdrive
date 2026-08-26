---
id: "003"
title: "Hardware ABI verification for sim.ts changes"
status: open
use-cases: [SUC-001, SUC-002, SUC-003]
depends-on: ["002"]
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

# Hardware ABI verification for sim.ts changes

## Description

Confirm on real hardware that ticket 002's `sim.ts` changes (TS
parameter types, added TS bodies, changed simulator divisor constant)
did not touch the native shim ABI. All three changes are TS-only by
construction — the C++ signatures in `shims.cpp`/`protocol.cpp` and the
kernel/motion-engine math in `motion_engine.h` are untouched — but
sprint.md's own Success Criteria requires this confirmed, not assumed;
this ticket is that confirmation, kept separate from ticket 002 because
it needs physical hardware and a build+flash session rather than a
browser.

The `int32`->`number` half of this was already spot-checked during
triage (tovez, commanded 200 mm `RUN:go` landed at 200.3 mm on a patched
build) — this ticket re-runs that check against the actual ticket-002
diff (which also includes the empty-body and divisor fixes the triage
spot-check didn't cover) rather than relying on the pre-verification
alone.

No linked issue: this ticket verifies work already tracked against the
three issues linked to ticket 002; it does not implement a new one.

## Acceptance Criteria

- [ ] A hex built from the post-ticket-002 tree (`pxt build`, per ticket
      001's doc) flashes successfully via `mbdeploy`.
- [ ] A commanded move (e.g. `RUN:go`, per the scaffold in ticket 001's
      doc) lands within the same tolerance pre-sprint firmware achieved
      (reference: 200 mm commanded -> 200.3 mm actual, from the issue's
      own pre-verification).
- [ ] No behavior change is observed on hardware attributable to the
      `sim.ts` edits — hardware only ever runs the C++ shim bodies, so
      this is a regression check, not a new-behavior check.
- [ ] Which robot was used, and its channel/relay path, is recorded in
      the ticket's own notes on completion (vevov via zavaz relay,
      channel 4; or tovez via USB only — per this sprint's hardware
      constraints, `getez` is not connected, so tovez cannot be used for
      anything requiring the radio path).

## Implementation Plan

**Approach**: Build the extension after ticket 002's changes land
(`pxt build` per ticket 001's documented flow, not MakeCode's Download),
flash to tovez (USB, bench stand — sufficient for a distance-verification
move; see `.claude/rules/playfield-testing.md` for why bench-stand
moves are fine for `RUN:go`-style distance checks but not for anything
needing real floor motion) via `mbdeploy`, and run the same `RUN:go`
verb the issue's own pre-verification used. Confirm the reported
distance matches within tolerance.

**Files to create/modify**: None — this ticket is verification-only, no
source changes. If a regression is found, it is a defect in ticket 002's
change and gets fixed there (reopen 002, or throw an exception per this
sprint's exception protocol if the conflict is architectural).

**Testing plan**: One hardware run as described above. No `pytest`
coverage applies (this is a live hardware check, not a host test); no
change to `uv run pytest`'s 718-test baseline is expected from this
ticket.

**Documentation updates**: None beyond recording the verification run's
robot/channel/result in the ticket itself on completion.

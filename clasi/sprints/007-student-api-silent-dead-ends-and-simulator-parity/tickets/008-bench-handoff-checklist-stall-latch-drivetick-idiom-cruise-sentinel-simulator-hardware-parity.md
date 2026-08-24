---
id: "008"
title: "Bench-handoff checklist: stall latch, driveTick idiom, cruise sentinel, simulator/hardware parity"
status: open
use-cases:
- SUC-001
- SUC-002
- SUC-003
- SUC-004
depends-on:
- '001'
- '002'
- '003'
- '004'
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

# Bench-handoff checklist: stall latch, driveTick idiom, cruise sentinel, simulator/hardware parity

## Description

Tickets 001-004 fix four behaviors whose acceptance criteria are all
satisfiable without a robot (shape-mirror host tests, wire-level test
doubles, code review, PXT builds — see each ticket's own "C++11 Gate
Coverage" section for exactly what is and isn't proven without
hardware). None of that is a substitute for actually flashing a real
robot and confirming the fixes hold under `shims.cpp`'s real
`Rig`/kernel composition, which no host test reaches. This ticket is a
**consolidated bench session** — one hardware sitting covering all
four fixes, following the precedent set by sprint 004's ticket 005 and
sprint 006's ticket 006 (bench-checkpoint tickets whose acceptance
criteria are the checklist being filled out truthfully, not a
sprint-closing gate). **This ticket does not block `close_sprint`** —
the sprint can close with this checklist run later, same as its
precedents.

Explicitly **not** covered here: issue 5's `rotationalSlip` setter
(ticket 005) is a chassis-calibration knob whose real-world effect is
inherently an open-ended re-calibration exercise for whichever
non-reference chassis eventually needs it, not a sprint-scoped
bench-verification item — its host tests (validation, wire round-trip)
are the actual gate for this sprint. Issue 6's Minors (tickets 006/007)
have no runtime behavior to verify on hardware at all.

## Acceptance Criteria (the checklist)

- [ ] **Stall latch (ticket 001).** On a real robot: command a drive
      into an obstacle (or hold both wheels) for >500 ms under a live
      Drive/Move command. Confirm `is stalled` reports `true` and the
      robot does not respond to further Drive/Move blocks. Place
      `clear stall latch`. Confirm the very next Drive/Move command
      takes effect normally, with no power cycle. Separately, confirm
      `clear emergency stop` does NOT clear a stall latch (latch
      independence).
- [ ] **`driveTick()` continuous-drive idiom (ticket 002).** Flash a
      test program using the exact documented idiom
      (`setWheelSpeeds(...)` / `driveTwist(...)` followed by
      `while (diffDrive.driveTick()) { ... }`). Confirm the robot
      actually keeps driving (not just twitching and stopping within
      ~150 ms as it did before this sprint). Confirm a position-mode
      `move()`/`goTo()` still completes and stops normally (no
      regression to blocking moves).
- [ ] **Cruise==0 sentinel (ticket 003).** Send `WHEELS_X <d> <d> 0
      <t>#<id>` (or the equivalent on `MOVE_X`/`GO_TO_R`/`GO_TO_W`)
      over the wire from a bench host. Confirm the robot moves at the
      configured default speed (~150 mm/s, or whatever `default_cruise`
      is set to) — not a full-duty lunge.
- [ ] **Simulator/hardware turn-rate parity (ticket 004).** Run the
      exact same `setWheelSpeeds(-15, 15)` (or similar) program in
      both the browser simulator and on hardware; confirm the turn
      rate is now comparable between the two (previously the sim
      turned 10× slower). Confirm `emergencyStop()` on hardware still
      behaves as documented (unchanged by this sprint) — this item is
      about the SIMULATOR now matching hardware, not a hardware
      behavior change.
- [ ] Record the actual robot/chassis used (e.g. vevov) and the date
      of this bench session in the ticket's own notes when closing it,
      matching sprint 004/006's precedent for bench-checkpoint tickets.

## C++11 Gate Coverage

Not applicable in the usual sense — this ticket exercises the real,
flashed, target-compiled firmware directly; there is no host-test
component. This ticket exists specifically to cover what tickets
001-004's host-testable acceptance criteria explicitly could not.

## Testing

- **Existing tests to run**: none (hardware-only ticket).
- **New tests to write**: none (a checklist, not automated test code).
- **Verification command**: none — manual bench session, checklist
  completion is the verification.

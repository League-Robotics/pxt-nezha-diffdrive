---
id: '003'
title: Binary motion verbs (MOVE, WHEELS, STOP, ESTOP)
status: done
use-cases:
- SUC-002
depends-on:
- '001'
- '002'
github-issue: ''
issue: implement-simple-protocol-v5.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Binary motion verbs (MOVE, WHEELS, STOP, ESTOP)

## Description

Implement the four binary motion command arms — `MOVE`, `WHEELS`,
`STOP`, `ESTOP` — using ticket 001's COBS+CRC codec and ticket 002's
established verb-registration pattern. Each binary payload uses a
locally-defined encoding sized to this project's actual capability
surface (not the firmware's protobuf schema) — see sprint.md's Design
Rationale for why. Reference: protocol-v5.md §3, §3.1, §3.2.

## Acceptance Criteria

- [x] `MOVE`, `WHEELS`, `STOP`, `ESTOP` registered in the verb registry
      as binary verbs.
- [x] `MOVE` accepts a velocity variant (twist or wheels) + one stop
      condition (time/distance/angle) + timeout + `replace` + `id`, per
      spec §4's semantic fields (locally encoded — see sprint.md
      Design Rationale, not protobuf-derived). Distance/angle-stop
      moves dispatch onto the existing move engine
      (`startMove`/`updateMove`-equivalent in `shims.cpp`). The
      TIME-stop-condition variant needs one new capability —
      time-bounded continuous drive — added to `shims.cpp`, layered
      over existing drive primitives the same way the move engine
      already layers a lease/deadline over `kernel.drive()`.
- [x] Every `MOVE` is treated as immediate/preemptive regardless of the
      `replace` flag's value (sprint.md Open Question 3 — this
      extension's move engine has no command queue to enqueue behind).
- [x] `WHEELS` applies a per-wheel velocity pair via the existing
      wheel-speed primitive (`setWheels`-equivalent), held for a
      REQUIRED duration, then auto-neutralizes — new duration-bound
      behavior added in `shims.cpp` on top of the existing primitive,
      not a kernel change.
- [x] `STOP` maps to the existing normal-stop primitive
      (`stopAll`-equivalent).
- [x] `ESTOP` maps to the existing emergency-stop primitive
      (`estopAll`-equivalent) and bypasses normal write-shaping the
      same way the `emergency stop` block does.
- [x] No command outcome (ack/ok/err) is sent for any of these four
      verbs — fire-and-forget, per sprint.md Open Question 1 (this
      sprint's TLM carries no ack field).
- [x] A malformed or undecodable binary body for any of these four
      verbs does not crash or hang the protocol loop, and no motion is
      commanded from a bad decode.
- [x] No changes to `diffdrive.h`/`diffdrive.cpp` (vendored kernel).

## Implementation Plan

**Approach**: Extend `shims.cpp` with the smallest additive surface
needed — a duration-bound wheel-speed helper (for `WHEELS`) and a
time-bounded drive helper (for `MOVE`'s TIME stop condition) — both
layered over the existing `kernel.drive()`/`kernel.neutral()` calls,
mirroring the existing move engine's own lease/deadline pattern
(`startMove`'s `moveDeadline`). Register the four verbs' handlers in
the Protocol/Comms module from tickets 001/002.

**Files to create/modify**: `shims.cpp` (additive helpers), the
Protocol/Comms module (handlers).

**Testing plan**: Desk-check each handler's mapping against the
existing block-level behavior it should approximate (e.g., `WHEELS`'
duration-bound behavior is comparable to what a MakeCode program could
already do with `setWheelSpeeds` + `basic.pause` + `stop`). The
browser simulator does not exercise the protocol layer (it is
C++-only, reached over serial, not through the TS shim boundary), so
simulator-level verification does not apply here. Hardware bench
verification is deferred to the stakeholder via `mbdeploy`/"zetuv"
(`test-on-microbit-zetuv-via-mbdeploy.md`).

**Documentation updates**: None beyond code comments.

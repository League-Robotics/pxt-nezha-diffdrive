---
id: 028
title: Single executor, honest encoder velocity, and a frame-zeroing verb
status: roadmap
branch: sprint/028-single-executor-honest-encoder-velocity-and-a-frame-zeroing-verb
use-cases: []
issues:
- single-executor-for-command-dispatch.md
- frozen-encoder-read-becomes-a-phantom-zero-velocity-and-the-pid-overreacts.md
- no-wire-verb-reaches-rebaseposition-so-tours-cannot-zero-their-frame.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 028: Single executor, honest encoder velocity, and a frame-zeroing verb

## Goals

Three independent, small-to-medium firmware fixes that share no code but
do share a prerequisite: none of them should start until sprint 027 (one
serial producer — the UART-wedge fix) has landed and been
hardware-confirmed, since two of the three touch the same protocol fiber
027 is repairing.

1. **The full executor inversion** carried out of sprint 026, and
   confirmed still worth doing by the 2026-09-02 triage note in
   `clasi/issues/single-executor-for-command-dispatch.md`: collapse the
   remaining two execution models (`RUN:` motion on a forked MessageBus
   fiber, wire motion on the protocol fiber) into one, so the I2C
   bus-discipline invariant is structural rather than a convention three
   call sites must each remember. This is the piece the triage explicitly
   separated from 027's single-serial-producer piece — not
   host-testable, budget 2-3 bench sessions, and it can wait for a
   reliably reachable board.
2. **Hold, don't zero** on a frozen encoder read
   (`clasi/issues/frozen-encoder-read-becomes-a-phantom-zero-velocity-and-the-pid-overreacts.md`):
   stop a failed I2C read from manufacturing a phantom zero-velocity
   sample that makes the velocity PID lunge toward the rail. Measured on
   gopiv, 7-45 occurrences per tour, clustered tightly on the frozen
   reads. Host-testable via `tests/host/motion_engine_shim.cpp`'s
   existing `meMotorArmPosition`/`meArmSettleProfile` scripting.
3. **A sequenced wire verb that reaches `rebasePosition()`**
   (`clasi/issues/no-wire-verb-reaches-rebaseposition-so-tours-cannot-zero-their-frame.md`):
   let a radio-driven tour zero its own pose/heading frame at leg 1
   instead of starting in whatever boot-anchored odometry frame the robot
   has accumulated. The issue's triage note suggests adding a sequenced
   `ESTOP` clear verb in the same ticket, since the existing
   `RUN:clearestop` is cleartext-only — flag as a candidate, not a
   commitment, pending detail planning's read of the wire grammar (owned
   cross-repo by radio-robot-lib's `protocol.md`).

## Problem

Three defects, unrelated in cause, share only that fixing any of them
touches the protocol fiber or the kernel-adjacent motion/platform layer
that sprint 027 is also working in:

- Command dispatch still runs on three coexisting fiber models instead
  of one deliberate one (sprint 026's item 3, deferred).
- A failed encoder I2C read is silently reinterpreted as "wheel
  stopped," not "read failed," even though the kernel already counts the
  failure (`i2cf`) — so the velocity PID sees a fabricated ~300 mm/s
  error and slams duty toward the rail.
- No wire verb reaches the kernel's existing `rebasePosition()`, so every
  radio-driven tour starts in an arbitrary accumulated heading and every
  chart needs host-side rotation to line up; on chassis with no OTOS
  (e.g. tigez), zeroing at tour start is the *only* mechanism for an
  absolute heading reference.

## Solution

Detail planning decides ticket count and sequencing per issue, but the
shape of each fix is already scoped by its issue:

1. Executor inversion: split `Protocol::run()` into a non-blocking
   service call plus a loop that services the wire, dispatches one queued
   RUN job, and ticks or sleeps; invert the tour's own tick loop onto
   that fiber via a service hook rather than moving the tick into
   TypeScript (explicitly not the superseded from-TypeScript-obligation
   design — see the issue's own "Superseded" section). This is the same
   shape sprint 026 already designed and partially specified before
   deferring it; detail planning should reuse that record rather than
   re-deriving it.
2. Frozen-encoder fix: the issue's own preference order is hold-the-
   previous-velocity first, range-gate against sprint 025's constant-`a`
   accel/decel bounds second. `src/core/diffdrive.{h,cpp}` is vendored
   and has been kept byte-identical through prior sprints; detail
   planning must decide explicitly whether this fix lives entirely in
   the platform/motion layer or requires touching the kernel, and record
   that as a scope decision rather than discovering it mid-ticket.
3. Frame-zeroing verb: add a sequenced wire verb (`SET pose 0 0 0` or a
   dedicated `REBASE`, per the issue's fix shape) that calls
   `rebasePosition()`. Wire grammar is shared cross-repo with
   radio-robot-lib's `protocol.md` — detail planning must account for
   that coordination before picking a final verb name/shape.

## Success Criteria

- Executor inversion: exactly one execution model remains for
  engine-facing motion (the protocol fiber); `RUN:abort` still stops a
  running job with no queue delay; a wire motion request arriving
  mid-job is arbitrated, not silently overwritten. Verified on hardware
  only — no host-test substitute exists for this piece.
- Frozen-encoder fix: a host test proves commanded duty does not step
  toward the rail on the tick following a frozen read or the tick after;
  a hardware re-run of `captures/gopiv-profile-sweep-20260901/tight_tour.py`
  on gopiv shows no speed excursion following an `i2cf` increment.
- Frame-zeroing verb: a tour issuing the new verb at leg 1 produces an
  axis-aligned odometry frame with no host-side rotation needed to read
  the chart; verified on both an OTOS-equipped chassis and tigez (no
  OTOS, wheel-encoder-only heading).
- `uv run pytest` passes throughout each ticket's scoped run, and in full
  at `close_sprint`.

## Scope

### In Scope

- The full executor inversion (protocol fiber split, `motionOwner_`
  arbitration, tour tick-loop inversion via service hook), per sprint
  026's already-specified design.
- The frozen-encoder-read fix in the motion/platform layer (or the
  kernel, if detail planning finds that unavoidable — to be stated
  explicitly, not silently).
- One new sequenced wire verb reaching `rebasePosition()`.
- Detail planning's judgment call on whether a sequenced `ESTOP` clear
  verb rides along in the same ticket as the frame-zeroing verb.

### Out of Scope

- Sprint 027's single-serial-producer fix (the UART wedge) — a hard
  prerequisite, not part of this sprint's own work.
- The genuine upstream CODAL fixes for anything FPU- or fiber-related —
  vendored toolchain, out of bounds, as already decided in sprint 026.
- Fixing the I2C failures themselves (loose connector, bus timing) — the
  frozen-encoder fix only stops a failed read from injecting a phantom
  velocity; it does not reduce how often reads fail.
- `first-i2c-command-can-wedge-the-program-with-no-recovery` and
  `i2c-fault-count-climbs-on-idle-bus` — related I2C issues the
  2026-09-02 triage placed in the next round after this one, not this
  sprint.
- `ensure-is-not-reentrant-two-rigs-can-be-constructed` — adjacent to the
  executor work but explicitly independent and not fixed by it, per the
  issue's own "Related" note.

## Test Strategy

(Describe the overall testing approach for this sprint: what types of tests,
what areas need coverage, any integration or system-level testing needed.)

## Architecture

(Architecture for this sprint's change, sized to the change — a
one-paragraph note for a trivial sprint, a fuller write-up with
component/data-model detail for a substantial one. May read "N/A —
trivial" when the change has no architectural impact.)

### Architecture Overview

(High-level structure and component relationships, if applicable.)

### Design Rationale

(Significant decisions with alternatives considered and reasoning, if
applicable.)

### Migration Concerns

(Data migration, backward compatibility, deployment sequencing — or
"None" if not applicable.)

## Use Cases

(Use cases sized to the change — may read "N/A — trivial" for small
sprints that don't warrant new or updated use cases.)

### SUC-001: (Title)
Parent: UC-XXX

- **Actor**: (Who)
- **Preconditions**: (What must be true before)
- **Main Flow**:
  1. (Step)
- **Postconditions**: (What is true after)
- **Acceptance Criteria**:
  - [ ] (Criterion)

## GitHub Issues

(GitHub issues linked to this sprint's tickets. Format: `owner/repo#N`.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [ ] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [ ] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|

Tickets execute serially in the order listed.

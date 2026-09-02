---
id: '002'
title: Sequenced SET rebase (and SET estop_clear) verbs reach the kernel
status: open
use-cases:
- SUC-003
depends-on: []
github-issue: ''
issue: no-wire-verb-reaches-rebaseposition-so-tours-cannot-zero-their-frame.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sequenced SET rebase (and SET estop_clear) verbs reach the kernel

## Description

No wire verb reaches the kernel's existing `rebasePosition()`, so
every radio-driven tour starts in whatever boot-anchored odometry
frame the robot has accumulated, and every chart needs host-side
rotation to line up. On chassis with no OTOS (e.g. tigez), zeroing at
tour start is the *only* mechanism for an absolute heading reference.

**Wire-grammar decision (binding — see sprint 028's `design/DESIGN.md`
§5 overlay for the full reasoning): add a write-triggered `SET`
pseudo-field, `rebase` — NOT a new top-level wire verb.**
`radio-robot-lib/docs/design/protocol.md` §7 states the library
"stores no configuration" and owns only the generic `GET`/`SET`
mechanism; field names under it are project-local
(`src/comms/wire_adapter.cpp`'s own `kFields` table), so this needs no
`protocol.md` change and no cross-repo grammar coordination. This is
the exact shape sprint 007's `stall_clear` (ordinal 17) already
established for "a write-triggered action wearing a config-field's
clothes." A dedicated new top-level verb (the issue's other candidate)
would instead require extending `WireHandler::kCommandTable` (a
drift-tested, currently-18-entry table) and coordinating with
radio-robot-lib — deliberately avoided.

The issue's triage note also flags a sequenced `ESTOP` clear verb as a
candidate, since the existing `RUN:clearestop` is cleartext-only. This
ticket accepts that candidate using the identical mechanism: `SET
estop_clear 1` calling `kernel.estopClear()`. It rides in this same
ticket because it is the same pattern, not a second new concept — if
implementation finds a reason it doesn't belong here, say so in this
ticket rather than silently dropping it.

## Acceptance Criteria

- [ ] `kFields` (`src/comms/wire_adapter.cpp`) gains `rebase` (ordinal
      32) backed by `kernel.rebasePosition()`, and `estop_clear`
      (ordinal 33) backed by `kernel.estopClear()` — both
      write-triggered, matching `stall_clear`'s existing shape exactly
      (a write of any nonzero value triggers the action; the GET side
      is a defined, stated readback convenience or an explicit refusal
      — pick one and document it, do not leave it ambiguous).
- [ ] `SET rebase 1 #<id>` and `SET estop_clear 1 #<id>` are sequenced
      (participate in the mandatory `#<id>` ack/nack reliability
      layer) — this falls out for free from reusing the existing `SET`
      verb path, but must be confirmed by a host test, not assumed.
- [ ] On an OTOS-equipped chassis, the `rebase` handler also re-seeds
      the OTOS pose source (mirroring `seedPose()`'s existing "write
      both pose sources" contract, `src/DESIGN.md` §7) so the two pose
      sources stay agreed at the zero point — do not leave the OTOS
      silently un-zeroed while the encoder frame resets.
- [ ] Both new fields are refused (an error response, not silent
      ignoring) while a motion obligation or RUN job is live — the
      same commandable-state gate other state-changing SET actions
      already check; zeroing the frame or clearing e-stop mid-move
      would corrupt in-flight position-error math.
- [ ] Host test proves `SET rebase 1` reaches `kernel.rebasePosition()`
      via the existing forward-declared `shims.cpp` seam
      (`WireMockAdapter`-style, matching how `stall_clear` is tested
      today).
- [ ] Host test proves `SET estop_clear 1` reaches
      `kernel.estopClear()`, distinctly sequenced from unsequenced
      `ESTOP` itself (`wire_handler.cpp`'s existing unsequenced-verb
      interception must NOT apply to this SET field).
- [ ] `radio-robot-lib/docs/design/protocol.md` is confirmed
      unchanged by this ticket (no PR needed there) — record that
      confirmation in this ticket's own notes, not asserted silently.
- [ ] Hardware acceptance: a tour issuing `SET rebase 1` at leg 1
      produces an axis-aligned odometry chart with no host-side
      rotation needed, verified on an OTOS-equipped chassis AND on
      tigez (no OTOS), against camera ground truth
      (`.claude/rules/playfield-testing.md`).

## Implementation Plan

**Approach.** Follow `stall_clear`'s existing pattern end to end:
`kFields` entry → `WireAdapter`'s SET dispatch → a forward-declared
`shims.cpp` free function → the kernel call. Two new ordinals (32, 33)
after the current highest (`profile_exit`, 31) — confirm this is still
the highest ordinal at implementation time, in case another sprint's
ticket landed a field in between.

**Files to modify.**
- `src/comms/wire_adapter.cpp` — `kFields` table, SET dispatch for the
  two new ordinals, the commandable-state refusal gate.
- `src/shims.cpp` — new forward-declared free functions calling
  `kernel.rebasePosition()` / `kernel.estopClear()` (the latter likely
  already has a caller path via `estopClear()` — check before adding a
  duplicate).
- OTOS re-seed path: locate the existing `seedPose()` call site and
  reuse it, do not duplicate its "write both" logic.
- `tests/host/` — new test file or extension of the existing
  `wire_adapter`/`WireMockAdapter` test suite.

**Testing plan.** Host tests as listed above, scoped to the wire
adapter/SET-field test files. Hardware acceptance per sprint.md's
Success Criteria, with a MEASURED citation naming the capture and
board for both the OTOS-equipped chassis and tigez runs.

**Documentation updates.** None beyond this ticket and the sprint's
`design/DESIGN.md`/`design/design.md` overlays (already written during
planning).

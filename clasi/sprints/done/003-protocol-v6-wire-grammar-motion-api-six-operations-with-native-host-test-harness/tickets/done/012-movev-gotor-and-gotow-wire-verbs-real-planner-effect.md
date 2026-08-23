---
id: '012'
title: 'moveV, goToR, and goToW wire verbs: real planner effect'
status: done
use-cases:
- SUC-001
- SUC-003
depends-on:
- '007'
- '010'
- '011'
github-issue: ''
issue:
- implement-protocol-v6-wire-grammar-and-reliability.md
- implement-motion-api-six-operations.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# moveV, goToR, and goToW wire verbs: real planner effect

## Description

Replace `WireAdapter::onMoveV`/`onGoToR`/`onGoToW`'s `kUnknown` stub
bodies with real dispatch onto `MotionEngine::moveV`/`goToR`/`goToW`
(tickets 007/010), completing all six motion verbs' real effect. After
this ticket, `WireAdapter` answers every one of the six motion verbs
for real — `DiffDriveAdapter`-style "no planner" `kUnknown` no longer
applies to this project at all (unlike the reference `radio-robot-lib`,
whose own `DiffDriveAdapter` deliberately keeps five of six unimplemented
— this project's motion issue explicitly requires ALL six to work).

## Acceptance Criteria

- [x] `MOVE_V <v_x> <omega> <duration> #<id>` dispatches to
      `MotionEngine::moveV`; wire-level golden vectors updated from
      `kUnknown` to real-effect.
- [x] `GO_TO_R <x> <y> <speed> <arrive> <timeout> #<id>` dispatches to
      `MotionEngine::goToR`.
- [x] `GO_TO_W <x> <y> <speed> <arrive> <timeout> #<id>` dispatches to
      `MotionEngine::goToW`, using whatever concrete `PoseSource` the
      hardware composition wires in (unaffected by this ticket, which
      is host-test-only — the host test path uses `FakePoseSource`).
- [x] The milliradian↔radian conversion for `omega` follows the exact
      same seam-and-test pattern ticket 011 established for `rotation`.
- [x] End-to-end wire-to-`FakeMotor`/`FakePoseSource` tests exist for
      all three verbs, matching ticket 011's "not just engine-level
      unit tests" requirement.
- [x] `wire_adapter.h`'s header comment's "documented `kUnknown`" list
      is now empty (or removed entirely) — every one of the six motion
      verbs has real effect.
- [x] `lastDone()`/`lastDoneReason()` are revisited: if any of the
      three newly-wired verbs gives `MotionEngine` a genuine completion
      event, decide (and document) whether `WireAdapter` should report
      it, or whether it remains `0`/`kNone` for now (matching the
      reference's own honest "no completion event on this adapter"
      posture) — this is a real decision this ticket must make
      explicitly, not leave ambiguous.

## Implementation Plan

**Approach**: Same pattern as ticket 011: forward decoded, converted
arguments from `WireAdapter` to the corresponding `MotionEngine`
method, via the same lazy-singleton reference.

**Files to modify**: `src/wire_adapter.h`/`.cpp` (replace the remaining
three stub bodies).

**Files to create**: none (extends existing test files).

**Testing plan**: Extend `tests/host/test_wire_motion_verbs.py` and
`tests/host/test_motion_engine_gotow.py` with wire-level end-to-end
assertions for the three verbs.

**Documentation updates**: Update `wire_adapter.h`'s header comment;
if the `lastDone` decision (Acceptance Criteria's last bullet) changes
current behavior, document the decision and rationale inline.

**Testing**

- **Existing tests to run**: `uv run pytest tests/host/`.
- **New tests to write**: extensions per Acceptance Criteria above.
- **Verification command**: `uv run pytest tests/host/`

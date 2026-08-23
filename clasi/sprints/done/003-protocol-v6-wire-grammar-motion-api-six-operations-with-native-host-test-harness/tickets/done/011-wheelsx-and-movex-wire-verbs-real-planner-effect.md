---
id: '011'
title: 'wheelsX and moveX wire verbs: real planner effect'
status: done
use-cases:
- SUC-001
- SUC-003
depends-on:
- '004'
- '006'
- '007'
github-issue: ''
issue:
- implement-protocol-v6-wire-grammar-and-reliability.md
- implement-motion-api-six-operations.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# wheelsX and moveX wire verbs: real planner effect

## Description

Replace `WireAdapter::onWheelsX`/`onMoveX`'s `kUnknown` stub bodies
(ticket 004) with real dispatch onto `MotionEngine::wheelsX`/`moveX`
(tickets 006/007), converting the wire's milliradian-integer rotation
field to the engine's float-radian (or whatever unit `motion_engine`
settled on internally) at this ONE seam — the binding, per
`motion-api.md` §9.1's "degrees at the API, milliradian integers on the
wire... the conversion lives in the binding, in one place." This is the
first of two "give a planner real effect" tickets (ticketing
requirement 4's second half); it covers the two verbs whose engine
methods land first (tickets 006/007), so it can start without waiting
for `goToW`'s `PoseSource` work (ticket 010).

## Acceptance Criteria

- [x] `WHEELS_X <left> <right> <cruise> <timeout> #<id>` dispatches to
      `MotionEngine::wheelsX` and returns `Result::kOk` on success;
      wire-level golden vectors are updated from ticket 004's
      `kUnknown`-expecting vectors to real-effect vectors.
- [x] `MOVE_X <distance> <rotation> <cruise> <timeout> #<id>` dispatches
      to `MotionEngine::moveX`, with the milliradian→radian (or
      engine-native unit) conversion happening in `wire_adapter.cpp`
      only — `motion_engine` itself has no wire-unit awareness.
  - [x] The conversion is tested in both directions (a positive wire
        `rotation` value produces the same physical turn direction as
        the corresponding block-API degree value) so a future unit
        mismatch fails a test.
- [x] A range/merits rejection path exists for at least one plausible
      out-of-range input per verb (e.g. a `cruise` of 0 defaulting to
      the configured default per `motion-api.md` §1.1, or an
      obviously-invalid combination) returning `Result::kRange`/
      `kBadArg` as appropriate — not silently accepted.
- [x] The full wire-to-`FakeMotor` path is tested end to end: a
      `WHEELS_X`/`MOVE_X` line fed into `WireHandler` produces the
      expected sequence of `FakeMotor::setDuty()` calls, not just that
      `MotionEngine`'s own unit tests pass in isolation.
- [x] `onWheelsX`/`onMoveX` no longer appear in the "documented
      `kUnknown`" list in `wire_adapter.h`'s header comment (updated to
      reflect only the remaining not-yet-wired verbs).

## Implementation Plan

**Approach**: `WireAdapter` gains a reference to the same
`MotionEngine` singleton `shims.cpp` uses (per sprint.md's
lazy-singleton Design Rationale) and forwards decoded, converted
arguments to it. The conversion helper (mrad↔rad or whatever
`motion_engine`'s native unit is) is a small, private, well-tested
function in `wire_adapter.cpp`.

**Files to modify**: `src/wire_adapter.h`/`.cpp` (replace two stub
bodies with real dispatch + the unit-conversion helper).

**Files to create**: none (extends existing test files from tickets
004/006/007).

**Testing plan**: Extend `tests/host/test_wire_motion_verbs.py` with
real-effect assertions replacing the `kUnknown`-expecting cases for
these two verbs; extend `tests/host/test_motion_engine_reductions.py`
if a wire-specific edge case surfaces that the engine-level tests did
not already cover.

**Documentation updates**: Update `wire_adapter.h`'s header comment's
list of which verbs are real vs. `kUnknown`.

**Testing**

- **Existing tests to run**: `uv run pytest tests/host/`.
- **New tests to write**: extensions to
  `tests/host/test_wire_motion_verbs.py` per Acceptance Criteria.
- **Verification command**: `uv run pytest tests/host/`

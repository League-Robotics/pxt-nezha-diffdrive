---
id: '004'
title: 'Six motion verbs: wire decode and dispatch (WireAdapter, WHEELS_V real, five
  kUnknown)'
status: done
use-cases:
- SUC-001
- SUC-002
depends-on:
- '003'
github-issue: ''
issue:
- implement-protocol-v6-wire-grammar-and-reliability.md
- implement-motion-api-six-operations.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Six motion verbs: wire decode and dispatch (WireAdapter, WHEELS_V real, five kUnknown)

## Description

Introduce `src/wire_adapter.h`/`.cpp` — the concrete Adapter behind
`wire_handler` (this project's analogue of `radio-robot-lib`'s
`DiffDriveAdapter`) — and add decode/execute pairs for all six motion
verbs (`WHEELS_X`, `WHEELS_V`, `MOVE_X`, `MOVE_V`, `GO_TO_R`, `GO_TO_W`)
to `wire_handler`'s command table, plus `STOP`'s optional `now` token
and `WHEELS`→`WHEELS_V`'s rename. This ticket is wire-decode-and-dispatch
ONLY: `WHEELS_V` gets real effect (it maps directly onto the existing
`setWheelsTimed`/`driveTwistTimed`-equivalent primitive that already
works today), and the other five motion verbs answer `Result::kUnknown`
— an honest, documented "this adapter has no planner yet" result,
matching `protocol.md` §9.10 item 1's own precedent for exactly this
situation. `STOP`/`ESTOP`/`GET`/`SET`/`RUN`/identity/status are wired
for real (calling straight through to existing `stopAll`/`estopAll`
equivalents and a small GET/SET field-name table replacing the old
`CONFIG`/`SET_FIELD`/`GET_CONFIG` verbs). Per ticketing requirement 4,
this proves the wire layer end to end BEFORE any planner exists.

## Acceptance Criteria

- [x] `WireAdapter` implements every pure-virtual method the wire
      handler's Adapter contract requires (identity, status, `onGet`/
      `onSet`/`fieldCount`/`fieldName`, `onTlm`, `onWheelsV`,
      `onWheelsX`/`onMoveX`/`onMoveV`/`onGoToR`/`onGoToW` (all five
      return `kUnknown`), `onStop(immediate, id)`, `onEstop`, `onRun`,
      `lastDone`/`lastDoneReason` (return `0`/`kNone` — no planner yet
      to complete anything)).
- [x] Golden wire vectors exist for all six motion verbs' decode arity
      (correct field count/types) AND their degenerate/malformed arity
      (wrong field count, an unparseable numeric field) — the latter
      must NACK per ticket 003's decode-failure rule, not silently
      dispatch.
- [x] `WHEELS_V`'s real effect is verified against the `FakeMotor`
      (ticket 001's harness): commanded left/right map to the correct
      velocity/twist and lease.
- [x] The five not-yet-wired verbs each produce `ack <id> ...` followed
      by `err 1 #<id>` (`ERR_UNKNOWN`) — a merits rejection, NOT a
      decode failure, since the line itself decoded fine.
- [x] `STOP #<id>` and `STOP now #<id>` both decode correctly; the `now`
      token is accepted as the literal string `now` only — anything
      else in that position is a decode failure.
- [x] `GET`/`SET` address the same `Rig`/`Config` fields the old
      `ConfigField` enum named, one field per `SET` line (the old
      multi-pair `CONFIG` batch verb is not reintroduced — flagged in
      sprint.md's Migration Concerns).
- [x] `TLM` emits v6's self-describing `thdr`/`t` frame shape (not the
      old `TLM:<x>:<y>:<heading>` cleartext line).
- [x] `WHEELS` does not appear anywhere in the new verb table —
      `WHEELS_V` is the only spelling.
- [x] `src/wire_adapter.{h,cpp}` are added to `pxt.json`'s `files`
      array.

## Implementation Plan

**Approach**: `WireAdapter` holds a reference/pointer it does not yet
have anywhere to point (the motion engine doesn't exist until ticket
006) — for THIS ticket, its six motion-verb methods are self-contained:
`onWheelsV` calls straight through to the existing hardware-facing
`setWheelsTimed`/`driveTwistTimed`-equivalent forward declarations
(same same-package-forward-declaration convention `protocol.cpp`
already uses to reach `shims.cpp`), and the other five simply `return
Result::kUnknown;` with a comment citing the precedent. This keeps this
ticket decoupled from ticket 006's motion-engine extraction — ticket
011/012 will replace the five stub bodies once `motion_engine` exists.

**Files to create**:
- `src/wire_adapter.h`/`.cpp` — the concrete Adapter.
- `tests/host/wire_motion_verb_shim.cpp`, `test_wire_motion_verbs.py`
  — golden vectors + arity/degenerate-input tests for the six verbs.

**Files to modify**: `src/wire_handler.{h,cpp}` (motion verb command
table rows), `pxt.json` (`files`).

**Testing plan**: Host-only; no hardware/PXT build exercised by this
ticket (that is ticket 005).

**Documentation updates**: `wire_adapter.h`'s header comment states
which five verbs are `kUnknown` and why, exactly the way
`diffdrive_adapter.h` documents the same posture for its own five
unimplemented verbs — so a future reader does not mistake it for an
oversight.

**Testing**

- **Existing tests to run**: `uv run pytest tests/host/` (everything
  from tickets 001-003).
- **New tests to write**: `tests/host/test_wire_motion_verbs.py` per
  Acceptance Criteria above.
- **Verification command**: `uv run pytest tests/host/`

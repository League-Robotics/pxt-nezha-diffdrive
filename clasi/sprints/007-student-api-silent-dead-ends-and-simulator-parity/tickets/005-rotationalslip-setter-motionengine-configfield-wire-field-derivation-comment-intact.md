---
id: '005'
title: 'rotationalSlip setter: MotionEngine + ConfigField/wire field, derivation comment
  intact'
status: in-progress
use-cases:
- SUC-005
depends-on: []
github-issue: ''
issue: rotational-slip-not-tunable.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# rotationalSlip setter: MotionEngine + ConfigField/wire field, derivation comment intact

## Description

`docs/design/design.md`'s Geometry doctrine is explicit: never adjust
`trackWidth` to make a turn land; all rotational-scrub correction
lives in `rotationalSlip`, measured per chassis against camera truth.
But `rotationalSlip_` (`motion_engine.h:399`, `= 0.952f`) is
getter-only — "Read-only for now: no caller in this codebase has ever
needed to set it at runtime" — absent from `setGeometry()`, absent
from `kFields`, no block. The doctrine names the correct knob; nothing
can turn it. The only turn-affecting knob reachable from any surface
is `set track width`, which the same doctrine explicitly forbids using
for this purpose (code review R-14/API-06, CONFIRMED).

**The 0.952 constant's derivation comment is load-bearing — do not
lose it.** `verify-comments.md`'s CHALLENGE on this exact field: a
prior comment-audit rewrite stated "six 180° pivots turned 164-166°
physical → slip 0.952," but 164-166/180 ≈ 0.915, not 0.952 — the
dropped middle of the derivation (ratio 0.915 → effective track must
be 120.0 mm → slip = 114.2/120.0 = 0.952) is the only bridge from the
measurement to the constant. Reproducing 0.915 from the same
experiment and "fixing" the constant to match is exactly the failure
this comment must prevent. Confirm the current in-tree comment
(`motion_engine.h`, above `rotationalSlip_`) states the full chain
(0.915 ratio → 120.0 mm effective track → 0.952 slip) before touching
the field — restore it if the short form is what's actually in the
file today.

## Implementation Plan

1. Add `void setRotationalSlip(float slip) { if (slip > 0.0f)
   rotationalSlip_ = slip; }` to `MotionEngine` (`motion_engine.h`),
   immediately after the existing `rotationalSlip()` getter — same
   `>0` silent-ignore validation style as `setTrackWidth()`/
   `setTravelCalib()`. Leave the derivation comment on `rotationalSlip_`
   exactly where it is (or restore the full chain per above); do not
   move it away from the field.
2. Add `RotationalSlip = 16` to `main.ts`'s `ConfigField` enum (`//%
   block="rotational slip"`). **No dedicated block** — reachable
   through the existing generic `set config %field to %value` block,
   same tier as `PID kp`/`stall demand`/12 other kernel fields (see
   Design Rationale). `trackWidth`/`travelCalib` keep their dedicated
   blocks; this one-time chassis-calibration constant does not need
   one.
3. Add `{"rotational_slip", 16}` to `wire_adapter.cpp`'s `kFields`.
4. `shims.cpp`: `setKernelValue()` case 16:
   `r.engine.setRotationalSlip(v);` (the switch already has `Rig& r`
   in scope; no signature change). `getConfigValue()` case 16:
   `v = r.engine.rotationalSlip();`.
5. `docs/design/specification.md` §4.8 gains the `RotationalSlip`/16
   row. `docs/design/usecases.md` UC-013 gains a third calibration
   step (rotational slip, same `>0`-silently-ignored error flow as the
   existing two). Direct edits on the sprint branch — neither file is
   part of this project's canonical design-doc-overlay set.

## Design Rationale

**Why the generic `ConfigField` escape hatch, not a dedicated "set
turn slip" block:** the issue's own remedy offers both ("a third
`setGeometry` path... or a dedicated advanced block"). This is a
one-time calibration constant for a teacher/builder setting up a
non-reference kit (UC-013's actor), not a value tuned as routinely as
`trackWidth`/`travelCalib` — which chose the dedicated-block route
precisely because they ARE the common case. The review's own text
accepts "at minimum... `ConfigField`" as sufficient, and this sprint
is already extending that same mechanism for `default_cruise`/
`stall_clear` (tickets 003/001) — adding a third entry to an
already-extended table is lower-risk than adding a fourth
dedicated-block code path in the same sprint.

## Acceptance Criteria

- [x] `MotionEngine::setRotationalSlip(float)` exists, validates `>0`,
      silently ignores invalid values (prior value retained) —
      matching `setTrackWidth()`/`setTravelCalib()`'s own tested
      behavior.
- [x] The derivation comment on `rotationalSlip_` states the full
      0.915 → 120.0 mm → 0.952 chain (not just the top-line
      measurement) after this ticket, whether or not it already did
      before.
- [x] `rotational_slip` is settable/gettable via `SET`/`GET` and via
      the generic `set config` block; no new dedicated block is
      added.
- [x] A host test constructs a `MotionEngine`, calls
      `setRotationalSlip()` with a valid value, confirms
      `rotationalSlip()`/`effectiveTrackWidth()` reflect it; calls it
      with `0` and a negative value, confirms both are silently
      ignored (prior value retained) — mirroring the existing
      `setTrackWidth`/`setTravelCalib` test pattern in
      `tests/host/test_motion_engine_primitives.py` or wherever those
      are currently tested.
- [x] A host test exercises the wire path: `SET rotational_slip
      <value>` then `GET rotational_slip` round-trips against a
      `WireAdapter`+`MotionEngine` fixture.
- [x] `docs/design/specification.md` §4.8 and `docs/design/usecases.md`
      UC-013 updated per the Implementation Plan.
- [x] Full existing host suite passes.

## C++11 Gate Coverage

- **Inside the gate**: `motion_engine.h` (the new setter — fully
  host-testable, no `pxt.h` dependency) and `wire_adapter.cpp`/`.h`
  (the new `kFields` row). This ticket's core logic is almost entirely
  host-testable, unusually so for this sprint.
- **Outside the gate**: `shims.cpp`'s two new switch-case bodies (one
  line each, calling the now-tested `MotionEngine` setter/getter) and
  `main.ts`'s `ConfigField` entry — no host-test coverage of either.
  Evidence for those two: code review (each is a one-line forward to
  already-tested logic) plus a PXT build. No robot is required.

## Testing

- **Existing tests to run**: whichever `tests/host/` file currently
  covers `MotionEngine::setTrackWidth()`/`setTravelCalib()` (locate
  before editing) plus `tests/host/test_wire_motion_verbs.py`.
- **New tests to write**: `setRotationalSlip()` validation test;
  `rotational_slip` wire GET/SET round-trip test.
- **Verification command**: `pytest tests/host/ -k "rotational_slip or motion_engine"`
  plus a full `pytest tests/host/` run before marking this ticket done.

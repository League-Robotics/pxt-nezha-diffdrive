---
id: "011"
title: "Host-compile shims.cpp and test the estimator wiring behaviourally"
status: open
use-cases: [SUC-001, SUC-004]
depends-on: ['005', '006']
github-issue: ""
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Host-compile shims.cpp and test the estimator wiring behaviourally

## Description

Stakeholder direction (2026-10-28): compile `src/shims.cpp` on the host.
This reverses the sprint 034 ticket 011 decision that lists it as a
translation unit nothing on the host compiles (`tests/DESIGN.md`,
enforced by `test_pxt_bound_exclusion_is_current.py`).

Why: ticket 004 put the estimator wiring in `shims.cpp`, and only text
pins cover it today (`test_estimator_wiring_source_pin.py`, 11 pins).
That wiring is the boot probe in `ensure()`, the `idleSense()` 10 Hz
idle read and its gates, the every-4th-tick sampling in `tickDrive()`,
and `reprime()` after `seedPose`/rebase. Bias learning at rest depends
on all of it. Tickets 007/008 add more wiring in the same file.

Feasibility, checked 2026-10-28 on the sprint branch at 98dd16b:
- With a 25-line stub `pxt.h`, `shims.cpp` compiles on the host with
  0 errors under `-std=c++11 -DDIFFDRIVE_HOST_BUILD`. The stub covers
  `ManagedString`, `pxt::String`/`StringData` with `getUTF8Size`,
  `MSTR`, `Action`, `incr`/`decr`, `runAction0`, `mkString`,
  `create_fiber`, `fiber_sleep`, `system_timer_current_time_us` and
  `uBit.serial.send`. A reference copy is in the team-lead scratchpad:
  `/private/tmp/claude-501/-Volumes-Proj-proj-robot-projects-nezha-robot-template/d39ff5a8-3f73-4f66-b00a-eb2e08125542/scratchpad/pxtstub/pxt.h`.
- The object leaves 55 undefined `diffDrive` symbols:
  - `MotionEngine` methods, already host-built for `motion_engine_shim`;
  - `board*` functions (`board_nezha.cpp` already compiles under
    `DIFFDRIVE_HOST_BUILD`, or fake them);
  - `OtosPort` methods (`begin`, `setPose`, `setOffset`,
    `calibrateImu`, …);
  - `protocol*` functions.

Do:
- Add a host stub `pxt.h` under `tests/host/` (only the names
  `shims.cpp` and its includes actually use) and a host build recipe
  for `shims.cpp`, following the existing shim-recipe conventions in
  `tests/host/DESIGN.md`.
- Link against the real portable code wherever it already host-builds.
  Fake the OTOS at the I2C level if practical, so the real
  `otos_port.cpp` probe and `begin()` run. Otherwise fake `OtosPort`'s
  methods and record why. Fake the protocol functions and a
  controllable clock.
- Replace the text pins in `test_estimator_wiring_source_pin.py` with
  behavioural tests wherever execution is now possible; keep a pin only
  where it still can't run, and say why. At minimum test:
  - `ensure()`: OTOS present gives Optical, absent gives EncodersOnly,
    with no user-program call needed;
  - `idleSense()`: reads at about 10 Hz when idle, skips while a
    move/job/block owns the motion, while the bus guard is held, and
    within 150 ms of a fiber tick; does nothing in EncodersOnly;
  - `tickDrive()`: samples the sensors every 4th tick;
  - `seedPose`/rebase plus `reprime()`: no heading step;
  - an idle-period integration: a simulated OTOS with a 50 deg/h bias
    sits idle for several minutes, and the estimator's `biasRate()`
    converges, with the TLM `bias` column, through the real
    `diagValue`, matching.
- Update `tests/DESIGN.md` (the exclusion table and the decision note),
  `tests/host/DESIGN.md` and `test_pxt_bound_exclusion_is_current.py`
  so the guard reflects that `shims.cpp` is now host-compiled. The
  other pxt-bound files stay excluded unless they come along for free.
- The target build must stay unchanged: no behaviour change in
  `shims.cpp` beyond what testability strictly needs, and the hex
  still builds.

## Acceptance Criteria

- [ ] `shims.cpp` compiles and links on the host in the test build
- [ ] Behavioural tests cover the probe, the idle-read cadence and
      gates, the drive sampling, the reprime and the idle bias
      convergence
- [ ] Ticket 004's text pins are replaced, or justified where kept
- [ ] Exclusion table, its guard test and the host-test DESIGN docs
      updated
- [ ] Hex builds via `tools/make_deploy.py`; `uv run pytest tests/host` green

## Testing

- **Existing tests to run**: `uv run pytest tests/host`, `tests/tools/test_tlm.py`
- **New tests to write**: see above
- **Verification command**: `uv run pytest tests/host`

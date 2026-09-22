---
id: '006'
title: 'sim_tour.py --board cutebot-pro: a hybrid tour that closes on the host'
status: done
use-cases:
- SUC-003
- SUC-005
depends-on:
- '004'
- '005'
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# sim_tour.py --board cutebot-pro: a hybrid tour that closes on the host

## Description

Depends on ticket 004 (the full hybrid stack — port, tap, policy, sim
onboard loop — must exist) and ticket 005 (the `--board` selection
needs to reach `sim_tour.py` the same way it reaches
`make_deploy.py`, and this ticket may reuse `_inject_board()`'s naming).
This is the sprint's headline proof point per its own Success Criteria:
a hybrid tour that closes on the host, before any board is touched.

Per `docs/design/cutebot-pro-support.md` §7 and §9:

- Extend `tests/host/sim_tour.py` with a `--board cutebot-pro` option
  (alongside its existing implicit Nezha default), composing the
  simulated `CutebotDevice`/`sim_cutebot_bus.h` in place of the
  existing simulated Nezha bus for the tour's `Rig`-equivalent
  construction.
- Run the existing tour shape (or the smallest existing named tour
  `sim_tour.py` already supports) at `onboard_pid` 0, 1, and 2 in turn,
  scored the same way the Nezha host tour already is (closure — the
  tour returns to its start pose within the existing pass bar).
- `onboard_pid 0` is the control case (pure PWM, proving ticket 002's
  work end-to-end through a real move sequence, not just unit tests);
  `onboard_pid` 1 and 2 are the hybrid cases this sprint exists to
  prove — the tour must close at all three, since a failure specific to
  1 or 2 would point at the policy or the sim onboard loop rather than
  the port.

## Acceptance Criteria

- [x] `sim_tour.py --board cutebot-pro` runs to completion (no crash,
      no host-side exception) at `onboard_pid` 0, 1, and 2.
- [x] The tour closes (returns to within the existing host-sim pass
      bar of its start pose) at all three `onboard_pid` values.
- [x] `sim_tour.py`'s existing `--board`-less invocation (Nezha)
      remains unchanged in behavior and output.
- [x] A CI-runnable form of this exists (a `test_*.py` wrapper calling
      `sim_tour.py`'s underlying function directly, not only a
      documented manual command) so `uv run pytest` covers it, per this
      sprint's "every acceptance criterion is host-verifiable" hard
      constraint.

## Testing

- **Existing tests to run**: full `uv run pytest`; the existing Nezha
  `sim_tour.py` invocation/test to confirm no shared-code regression.
- **New tests to write**: a pytest wrapper (e.g.
  `test_sim_tour_cutebot.py`) invoking `sim_tour.py --board
  cutebot-pro` at each `onboard_pid` value and asserting closure.
- **Verification command**: `uv run pytest tests/host/test_sim_tour_cutebot.py`,
  then full `uv run pytest`.

## Completion Notes

**Files added.** `tests/host/sim_cutebot_robot_shim.cpp` -- a whole-
stack `extern "C"` shim, the Cutebot analogue of `sim_robot_shim.cpp`
foretold by `cutebot_port_shim.cpp`'s own header comment ("a future
ticket ... builds that separately, the way sim_tour.py sits beside
sim_robot_shim.cpp today"): a real `CutebotDevice`/`CutebotMotorPort`
pair + `CutebotTapAdapter` (installed on `MotionEngine` via
`setWheelCommandTap()`, mirroring `board_cutebot.cpp`'s own
`CutebotBoard` composition) over a simulated 0x10 slave
(`sim_cutebot_bus.h`), under the real `DifferentialDrive` kernel,
`MotionEngine` and `Odometry`. Ground truth pose is integrated from the
ports' own reported positions (already side/sign-corrected), the same
choice `sim_robot_shim.cpp` settled on. Handoff counting exploits one
property of `sim_cutebot_bus.h`: its `onboardActive()` flips exactly
when a shipped frame's TYPE changes (a `0x10` write always clears it, a
`0x80` write always sets it), so watching it once per control cycle
counts engage/release transitions with no separate hook into the
policy. `tests/host/test_sim_tour_cutebot.py` -- 13 tests: no-crash +
finite pose at every `onboard_pid`; closure under
`CUTEBOT_CLOSURE_PASS_MM` at every mode; mode 0 ships zero `0x80`
frames on every leg; modes 1 and 2 ship at least one `0x80` frame on
every leg whose cruise is >= the floor and exactly zero on every leg
below it (per-move frame deltas, not just the tour-wide total); the
tour ends on PWM with both simulated wheels at exactly zero velocity
and zero applied duty at every mode; and the Nezha `--board`-less path
is unchanged (`parse_args([])` defaults to `board="nezha"`, and
`build()`/`run_square()` -- the exact functions
`test_sim_profile_tracking.py` already imports and calls -- still
produce the same shape of result after this ticket's `build()` ->
`_compile_lib()` refactor).

**Files modified.** `tests/host/sim_tour.py`: `import argparse`;
`build()` and the new `build_cutebot()` now share one `_compile_lib()`
helper (same recipe, parameterized by source list/lib name/prebuilt-env
var) -- `build()`'s own name, signature, output filename
(`libsimrobot.so`) and `SIMROBOT_LIB` escape-hatch message are
byte-identical to before, so `test_sim_profile_tracking.py` and every
other existing importer sees no difference; `_CUTEBOT_SOURCES` (the
new shim + `cutebot_port.cpp` + `cutebot_actuation_policy.cpp` +
`diffdrive.cpp` + `motion_engine.cpp` + `velocity_shaper.cpp`) and
`build_cutebot()` (its own `SIMCUTEBOT_LIB` escape hatch, for parity
with `build()`'s); `_bind_cutebot()` (the `sc*` ctypes surface, kept
separate from `_bind()` rather than merged, since the two shims are
different translation units with different symbols); `SimCutebotRobot`
(the `SimRobot` analogue -- its own docstring is explicit that EVERY
default is a placeholder, since no Cutebot Pro has been fitted, unlike
`SimRobot`'s tovez-measured firmware defaults; it has no port-shaping
constructor argument at all, matching `cutebot_port.h`'s "minimal
shaping, deliberately" note); `CUTEBOT_SQUARE` (same NE->NW->SW->SE->NE
route as `SQUARE`, DIFFERENT cruises -- 250 mm/s legs, 100 mm/s pivots
-- chosen so the tour straddles the default 200 mm/s `onboard_floor` on
both sides at once: legs are eligible for a hybrid handoff, pivots
(both wheels share one magnitude) never are); `CUTEBOT_CLOSURE_PASS_MM`
(reuses `test_sim_profile_tracking.py`'s own `closure < 160.0` bound
for a Nezha `SQUARE` tour on this same sim tier, rather than inventing
a fresh number, per this ticket's own "justify the tolerance from the
Nezha sim's own numbers" instruction); `run_cutebot_square()` (drives
`CUTEBOT_SQUARE` at one `onboard_pid`, returns closure/heading plus the
hybrid counters this ticket asks for, including per-move `onboard_frames`/
`pwm_frames` deltas so a test can localize a shipped frame to a
specific leg); `main()` is now a thin dispatcher, `main_nezha()` is the
OLD `main()` body verbatim (renamed only), `main_cutebot()` and
`parse_args()` are new. `tests/DESIGN.md`, `tests/host/DESIGN.md`,
`tests/host/README.md`: documented the new shim and, for
`tests/host/DESIGN.md`/`README.md`, `sim_robot_shim.cpp` itself, which
had no entry in either file before this ticket despite already
existing.

**MEASURED this session** (`uv run python tests/host/sim_tour.py
--board cutebot-pro`, and directly via `run_cutebot_square()`):

| onboard_pid | closure | net heading | 0x10 shipped | 0x80 shipped | handoffs (engage+release) | final frame |
|---|---|---|---|---|---|---|
| 0 | 118.9 mm | +12.63 deg | 1049 | 0 | 0 | PWM |
| 1 | 57.2 mm | +11.11 deg | 435 | 3272 | 8 (4 engage, 4 release) | PWM |
| 2 | 58.1 mm | +12.63 deg | 456 | 3260 | 8 (4 engage, 4 release) | PWM |

All three close well inside the 160 mm pass bar. Per-leg frame deltas
(all three modes) confirm the eligibility split exactly: each of the
four 250 mm/s straight legs ships >0 `0x80` frames at `onboard_pid`
1/2 and 0 at `onboard_pid` 0; each of the four 100 mm/s pivots ships
exactly 0 `0x80` frames at every mode. The hybrid modes closing TIGHTER
than pure PWM on this particular plant is a property of this
unfitted model, not a claim about real hardware -- see
`SimCutebotRobot`'s own UNVERIFIED-plant docstring.

**What this does NOT prove.** Same caveat every prior ticket in this
sprint states: `tau`/`breakaway_mm_s`/`full_duty_mm_s` are placeholders
copied from `SimRobot`'s own Nezha placeholders (themselves NOT
measured on tovez), and the firmware-shape defaults are kept equal to
`SimRobot`'s tovez bake purely for desk comparability, not because a
Cutebot Pro is expected to match tovez's tuning. This proves MECHANISM
(the hybrid policy hands off on an eligible leg, never on an
ineligible one, and a tour survives three full handoff cycles per
mode and still closes) -- never a value for a real board. The
up-handoff/down-handoff hazards (design doc S3.D) remain sprint 041
bench probes; nothing here touches hardware.

**Full-suite result.** `uv run pytest tests/host tests/tools -q
--ignore=tests/tools/test_field_dance_accel_bake.py` -- **2294
passed**, MEASURED this session (up from ticket 005's own 2281; this
ticket's 13 new tests account for the difference exactly). No existing
test's assertions changed.

**Not attempted / left for later.** A real Cutebot Pro build/flash
checkpoint (ticket 007); the design-doc overlay for
`src/platform/DESIGN.md`/`src/DESIGN.md`/`design.md`'s layer table
(ticket 008); anything the bench (sprint 041) has to measure --
whether either hybrid policy is worth keeping, the handoff hazards,
and real geometry/sign bakes.

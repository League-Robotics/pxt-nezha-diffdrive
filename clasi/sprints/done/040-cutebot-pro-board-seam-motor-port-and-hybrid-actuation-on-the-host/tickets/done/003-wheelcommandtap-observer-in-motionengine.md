---
id: '003'
title: WheelCommandTap observer in MotionEngine
status: done
use-cases:
- SUC-003
depends-on:
- '001'
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# WheelCommandTap observer in MotionEngine

## Description

Independent of the Cutebot port itself — this ticket lives entirely in
`motion/`, which this repo owns outright, and touches no I2C or board
code. It only needs ticket 001's seam merged so its own host tests run
against the post-seam tree; it does not need `CutebotMotorPort` to
exist.

Per `docs/design/cutebot-pro-support.md` §3.D ("Where the velocity
setpoint comes from") and §7:

- Add `src/motion/wheel_command_tap.h`: a small, host-portable observer
  interface, e.g. `WheelCommandTap` with `onDrive(float leftMmS, float
  rightMmS)` and `onNeutral()` — no I2C, no board knowledge, no
  dependency beyond libc, matching the layering `heading_wrap.h`/
  `encoder_glitch_armor.h`/`bus_guard.h` already establish for small
  host-portable helpers (`src/DESIGN.md` §1's layer table).
- `MotionEngine` gains one optional (nullable) `WheelCommandTap*`
  member, settable via a new accessor. When set, `MotionEngine`
  notifies it with the shaped `(left, right)` mm/s **alongside**, not
  instead of, every `kernel_.drive()` call
  (`src/motion/motion_engine.cpp:368` for a segment, `:406` for a
  hold — both read during architecture planning and confirmed current)
  and with `onNeutral()` alongside every `kernel_.neutral()` call this
  method makes (the wrong-way/stall/estop/expired abort branch above
  line 368, and the analogous stall/expired branches for the
  continuous-hold path around line 386-395). Audit `motion_engine.cpp`
  for any OTHER `kernel_.neutral()` site this ticket's own read of
  lines 320-413 may not have caught (e.g. inside `endMove()` or a
  pivot-then-straight transition) and notify there too — the whole
  point of a dedicated host test (below) is to make a missed site a
  test failure, not a silent gap.
- When no tap is set (every existing caller, until ticket 002/004's
  `CutebotDevice` registers one), behaviour is **byte-identical** to
  before this ticket — a null check before each notify, zero-cost when
  unset.

## Acceptance Criteria

- [x] `WheelCommandTap` compiles host-portable (no `pxt.h`, no board
      dependency) and is exercised with zero I2C or kernel-port fakes
      in the link, the same isolation `Odometry`/`VelocityShaper` tests
      already achieve.
- [x] Every `kernel_.drive()` call site in `motion_engine.cpp` notifies
      the tap with the identical `(left, right)` mm/s values passed to
      `kernel_.drive()` (verified by a test double, not by inspection
      alone).
- [x] Every `kernel_.neutral()` call site in `motion_engine.cpp`
      notifies the tap's `onNeutral()`.
- [x] With no tap registered, `MotionEngine`'s behaviour and the full
      existing host suite (particularly
      `tests/host/test_motion_engine_*.py`) are unchanged.

## Testing

- **Existing tests to run**: full `uv run pytest`, especially every
  `test_motion_engine_*.py` file, to confirm the tap is a strict
  addition with the tap unset.
- **New tests to write**: `test_wheel_command_tap.py` — a fake tap
  recording every `onDrive`/`onNeutral` call, driven through
  `MotionEngine::wheelsV`/`wheelsX`/`moveX`/`moveV`/`goToR`/`goToW` and
  every abort path (wrong-way, stall, e-stop, deadline expiry), proving
  the tap sees exactly the values the kernel receives and a
  neutral notification on every path that calls `kernel_.neutral()`.
- **Verification command**:
  `uv run pytest tests/host/test_wheel_command_tap.py`, then full
  `uv run pytest`.

## Completion Notes

**The tap interface (verbatim, `src/motion/wheel_command_tap.h`)**,
the exact signature ticket 004's `CutebotDevice`/`CutebotActuationPolicy`
will consume:

```cpp
namespace diffDrive {

class WheelCommandTap {
 public:
  virtual ~WheelCommandTap() = default;

  virtual void onDrive(float left,   // [mm/s]
                       float right,  // [mm/s]
                       VelocityShaper::Phase phase) = 0;

  virtual void onNeutral() = 0;
};

}  // namespace diffDrive
```

`VelocityShaper::Phase` (`src/motion/velocity_shaper.h`, nested in
`VelocityShaper`, so referenced as `VelocityShaper::Phase`):
`enum class Phase : uint8_t { kAccel, kCruise, kBrake };` — a new
member of `VelocityShaper::Step` (`Step{vCmd, arriving, phase}`),
derived in `VelocityShaper::advance()` itself, not fed back into
`v_`/`a_`/`vCmd`/`arriving` (zero shaping-behavior change).

`MotionEngine` gains `void setWheelCommandTap(WheelCommandTap*)` and
`WheelCommandTap* wheelCommandTap() const` (both public,
`motion_engine.h`), plus a private, non-owning `WheelCommandTap* tap_ =
nullptr;` and two private notify wrappers (`notifyDrive(left, right,
phase)` / `notifyNeutral()`), each a single null check.

**Phase derivation** (`velocity_shaper.cpp`, alongside the existing
brake-budget computation, no shaping behavior touched): a new local
`brakeLimited` bool is set to `vBrake < target` in the `remain >= 0`
branch (the SAME `vBrake` the existing code already computes to bound
`vGoal`) and left `false` for a continuous hold (`remain < 0`, no
brake budget at all). After the tick's final `vNext` is settled (post
rate/jerk-limit and the legacy-floor bump), phase is:
`kBrake` if `brakeLimited`; else `kAccel` if `vNext + epsilon < vGoal`
(still ramping toward the goal); else `kCruise` (holding at the goal).
`kPhaseEpsilon = 1e-3f` mm/s absorbs float roundoff from the
`sqrt`/`copysign` arithmetic upstream, not a tuning knob. Consequence
proven by `test_wheel_command_tap.py`: a move whose target is never
reachable within its remaining distance is `brakeLimited` from tick 1
onward (`vBrake` monotonically shrinks with `remain`), so it is
`kBrake` (or `kAccel`, on a tick where `vBrake` briefly exceeds the
still-ramping `vNext`) for its entire life and never reports `kCruise`
— the "no plateau" requirement — while a long move ramps
`kAccel` -> holds `kCruise` -> and finishes `kBrake` once `vBrake`
drops below `target`.

**Call sites** — every `kernel_.drive()`/`kernel_.neutral()` call in
`motion_engine.cpp` was audited (not just the two drive sites and the
combined segment-abort branch the ticket text named): 2 `drive()`
sites (segment tick, hold tick) and 13 `neutral()` sites
(`beginSegment()`'s zero-magnitude early return; the segment's
combined wrong-way/stall/estop/expired abort; the segment's arrival
branch, including its lag-settling repeat; the segment's refused-drive
branch; the hold's own stallHalted branch; the hold's own expiry
branch; the hold's own refused-drive branch; `endMove()`'s guarded
neutral; `firePulseAndSettle()`'s hard-zero; `beginNudge()`'s
zero-magnitude early return; and `serviceNudge()`'s estopped,
converged, and expired-or-budget-exhausted branches) — every one now
has a `notifyDrive()`/`notifyNeutral()` call immediately beside it,
each a literal 1:1 pairing with the `kernel_.drive()`/`kernel_.neutral()`
call it sits next to (not a summarized/collapsed notification), so a
future edit that adds a new drive/neutral site without a matching
notify call is a plain source diff away from being caught by eye, and
`test_wheel_command_tap.py` exercises 11 of the 15 sites directly (the
3 `serviceNudge()` early-return branches share one identical code
shape — `kernel_.neutral(); notifyNeutral(); nudge_.active = false;
return false;` — and only the convergence one is exercised; the other
two are the same shape, untested separately, a documented, deliberate
scope trim, not a gap in the source itself).

**`onDrive()`'s `(left, right)` are `velocity - twist` / `velocity +
twist`** applied to the SAME `(velocity, twist)` mm/s (pre-`countsPerMm()`
scaling) each call site is about to hand `kernel_.drive()` — the
identical decomposition `src/core/diffdrive.cpp`'s `rawLeft`/`rawRight`
apply internally in counts/s, confirmed against
`test_motion_engine_primitives.py`'s own pin of that convention. Proven
independently in `test_wheel_command_tap.py` by reconstructing each
wheel's actual applied mm/s from `motor_last_staged_duty(side) * fdv /
cpm` (the kernel's own staged output under a pure-feedforward
config), never from a second copy of `MotionEngine`'s own arithmetic.

**No units in identifiers**: `onDrive()`'s parameters are plain
`left`/`right` with trailing `// [mm/s]` comments, not `leftMmS`/
`rightMmS` — caught by this project's own
`test_no_unit_suffixed_identifiers_outside_core_and_allowlist` gate
during this ticket's own verification pass and fixed before commit.

**Files added**: `src/motion/wheel_command_tap.h`
(`WheelCommandTap`); `tests/host/wheel_command_tap_syntax_check.cpp`
(the C++11 syntax-gate translation unit a pure-virtual-only header
needs, mirroring `motion_limits_syntax_check.cpp`);
`tests/host/test_wheel_command_tap.py` (18 tests: no-tap-installed
inertness; `onDrive()` matching the kernel's own staged duty for a
segment tick and a hold tick; `onNeutral()` on arrival, deadline
expiry, e-stop, a refused drive (segment and hold, separately), wrong-way,
hold-stall, hold-expiry, `endMove()`/cancel (both the active and the
no-op case), the zero-magnitude `beginSegment()`/`beginNudge()`
sites, `pulseWheels()`'s hard-zero, and nudge convergence; and the two
phase tests above).

**Files modified**: `src/motion/velocity_shaper.h` (`Phase` enum,
`Step` gains a `phase` field); `src/motion/velocity_shaper.cpp`
(phase derivation, see above); `src/motion/motion_engine.h` (`#include
"wheel_command_tap.h"`, the tap accessor pair, the `tap_` member, the
two notify wrappers); `src/motion/motion_engine.cpp` (a
`notifyDrive()`/`notifyNeutral()` call beside every
`kernel_.drive()`/`kernel_.neutral()` call, and the one settling-branch
`Step{0.0f, true}` aggregate literal extended to `Step{0.0f, true,
VelocityShaper::Phase::kBrake}`); `pxt.json` (`files` gains
`src/motion/wheel_command_tap.h`); `tests/host/test_cxx11_syntax_gate.py`
(`_CXX11_PORTABLE_SOURCES` gains the new syntax-check translation
unit); `tests/host/motion_engine_shim.cpp` (`FakeWheelCommandTap`,
a `tap` member on `Handle`, and the `meTapInstall`/`meTapUninstall`/
`meTapClear`/`meTapRecordCount`/`meTapRecordKind`/`meTapRecordLeft`/
`meTapRecordRight`/`meTapRecordPhase` exports); `tests/host/conftest.py`
(their ctypes bindings in `_bind_motion_lib()`); `src/DESIGN.md` §3 and
`src/motion/DESIGN.md` (the new optional collaborator, documented).

**Zero behavior change with no tap installed**: every one of this
directory's other test files sharing the same compiled shim (twenty-
five-plus files behind the `motion_lib` fixture) never calls
`meTapInstall()` and passed unmodified; the one file that DID need a
one-line change was `motion_engine.cpp`'s own `Step{0.0f, true}`
literal, which needed a third field only because `Step` itself grew
one — no shaping value, branch, or return changed.

**Full scoped suite**: `uv run pytest tests/host tests/tools -q
--ignore=tests/tools/test_field_dance_accel_bake.py` — **2190 passed**
(the ignored file needs a live AprilCam daemon; pre-existing/unrelated,
per tickets 001/002's own notes on it).

**Not attempted / left for ticket 004**: wiring the tap into
`CutebotDevice`/`board_cutebot.cpp` (the `0x80` path this ticket's own
description calls "the seam left for the 0x80 path"); the
`CutebotActuationPolicy` that consumes `Phase`.

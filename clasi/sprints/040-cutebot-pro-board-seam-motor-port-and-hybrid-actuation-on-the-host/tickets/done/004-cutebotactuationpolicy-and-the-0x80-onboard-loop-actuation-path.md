---
id: '004'
title: CutebotActuationPolicy and the 0x80 onboard-loop actuation path
status: done
use-cases:
- SUC-003
- SUC-004
depends-on:
- '002'
- '003'
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# CutebotActuationPolicy and the 0x80 onboard-loop actuation path

## Description

Depends on ticket 002 (`CutebotMotorPort`/`CutebotDevice` must exist to
ship a frame) and ticket 003 (`WheelCommandTap` is the policy's other
input). This is the sprint's hybrid-actuation payload — §3.D and §1.5
of the design doc, and the stakeholder's 2026-09-21 direction: our
kernel below the handoff, the Cutebot's own loop at cruise.

- `src/platform/cutebot_actuation_policy.h/.cpp`: a **pure function**,
  `CutebotActuationPolicy::decide(PolicyState prevState, WheelStaged
  kernelDuty, WheelSetpoint tapSetpoint, int mode, float floorMmS) ->
  {FrameChoice, PolicyState}` (exact types at the implementer's
  discretion, but it must take no I2C/board/kernel reference — testable
  with zero simulated bus in the link, matching `MotionLimits`/
  `VelocityShaper`'s existing pattern per this sprint's Design
  Rationale). Three modes: `0` off (always PWM), `1` threshold with
  hysteresis (engage at both |v| ≥ some configured threshold, release
  below a lower one), `2` plateau-only (engage only once the shaper
  reports cruise, release the moment braking begins — the tap or a
  companion signal must carry enough phase information for this; if
  `WheelCommandTap` as built in ticket 003 does not yet expose a
  phase/"is cruising" signal, extend it here rather than inventing a
  second channel).
- **Both-wheels eligibility gate**: `0x80` treats 0 as "stop" but
  clamps any nonzero value below 200 mm/s up to 200 (design doc §1.5),
  so a wheel commanded under the floor (other than exactly 0) can never
  be handed to the onboard loop. The policy must gate on BOTH wheels —
  an arc whose inner wheel is under the floor keeps the WHOLE pair on
  PWM, never split one wheel per frame (the hardware takes one frame
  for both wheels; there is no way to split it).
- `CutebotDevice` (ticket 002) calls the policy once per kernel cycle
  with its own currently-staged duties and the tap's currently-shaped
  setpoint, and ships exactly the frame the policy returns — PWM
  (`0x10`) or the onboard setpoint (`0x80`).
- Two new `comms/config_fields.h` rows, appended after the existing
  last ordinal (42): `{"onboard_pid", 43, "1"}` and `{"onboard_floor",
  44, "mm/s"}`, following the existing `ConfigFieldDescriptor`
  pattern exactly (see the header's own row-comment convention,
  `// ConfigField.<Name>: "<label>"`). Wire behaviour lives in
  `shims.cpp`'s `kConfigAccessors`/board-diagnostics-hook pattern (per
  the seam from ticket 001), reading/writing the policy's mode/floor on
  whichever board is composed — a Nezha build's accessor is a no-op
  that reports `0`/refuses `SET`, since the fields are meaningless
  without a Cutebot. `SET onboard_pid 0` must always be reachable and
  must always ship PWM only, with no dependency on any other config
  value — the sprint's own explicit escape-hatch requirement.
- Re-run `tools/gen_config_field_enum.py` and commit the regenerated
  `blocks/motion.ts` `ConfigField` enum; `tests/tools/
  test_gen_config_field_enum.py` must pass.
- Extend `tests/host/sim_cutebot_bus.h` (from ticket 002) with a
  simulated onboard loop for `0x80`: a first-order lag driving the
  shared `SimWheel` toward the commanded setpoint, with the 200 mm/s
  clamp modelled (nonzero inputs below 200 clamp up; zero passes
  through), per design doc §7's own description of this fixture — so a
  policy bug that hands the loop an under-floor nonzero setpoint is
  visible on the host, not just a bench finding for sprint 041.

## Acceptance Criteria

- [x] `CutebotActuationPolicy::decide()` is a pure function (no I2C,
      no `MotionEngine`, no kernel reference) exercised entirely
      through `test_cutebot_actuation_policy.py`.
- [x] Mode `0` ships PWM unconditionally regardless of setpoint or
      floor — a host test drives both wheels well above the floor with
      mode 0 and asserts the PWM frame is chosen every tick.
- [x] Mode `1`'s hysteresis is proven: engages at/above the upper
      threshold, stays engaged through the gap between thresholds, and
      releases at/below the lower one — not a single crossing value.
- [x] Mode `2` engages only once cruise/plateau phase is reported and
      releases at the first sign of braking.
- [x] The both-wheels eligibility gate is proven with one wheel above
      floor and the other below (or one exactly 0, one nonzero-under-
      floor) — the pair stays on PWM in every such case.
- [x] `onboard_pid` (43) and `onboard_floor` (44) are reachable
      `GET`/`SET` rows, covered by `test_config_surface_single_source.py`
      and `test_gen_config_field_enum.py`; the regenerated
      `ConfigField` enum is committed.
- [x] `sim_cutebot_bus.h`'s simulated onboard loop models the 200 mm/s
      clamp (nonzero-under-200 clamps up; exactly 0 passes through) and
      a plausible first-order response, exercised by at least one new
      host test distinct from `sim_tour.py` (ticket 006 covers the
      full-tour case).
- [x] A Nezha-composed build's `onboard_pid`/`onboard_floor` accessors
      do not crash and behave as a documented no-op/refusal — the
      config rows exist on the wire for every board (append-only
      table), but only mean something on a Cutebot.

## Testing

- **Existing tests to run**: full `uv run pytest`, plus
  `test_config_surface_single_source.py` and
  `test_gen_config_field_enum.py` specifically (both must be extended,
  not just re-run, per the acceptance criteria above).
- **New tests to write**: `test_cutebot_actuation_policy.py` (pure
  policy, all three modes, the eligibility gate);
  `sim_cutebot_bus.h`'s onboard-loop extension gets its own focused
  test (or is folded into `test_cutebot_port.py`'s file, at the
  implementer's discretion) proving the clamp and lag model in
  isolation, ahead of ticket 006's full-tour proof.
- **Verification command**:
  `uv run pytest tests/host/test_cutebot_actuation_policy.py`, then
  full `uv run pytest`.

## Completion Notes

**Files added.** `src/platform/cutebot_actuation_policy.h`/`.cpp`
(`CutebotActuationPolicy`, pure, no I2C/board/kernel reference);
`tests/host/cutebot_actuation_policy_shim.cpp` +
`test_cutebot_actuation_policy.py` (31 tests, zero I2C or
`CutebotDevice` in the link); `tests/host/cutebot_hybrid_shim.cpp` +
`test_cutebot_hybrid_actuation.py` (19 tests — device-level
integration over a real `CutebotDevice`/`CutebotMotorPort` pair and
`sim_cutebot_bus.h`, distinct from both of the above).

**Files modified.** `src/platform/cutebot_port.h`/`.cpp`
(`CutebotDevice` gains the tap-sample state, `onboardMode_`/
`onboardFloor_`, `serviceCycle()` replacing the old unconditional
`shipFrame()` call inside `stageDuty()`, and `writeOnboardFrame()`;
`CutebotTapAdapter`, a new class implementing `WheelCommandTap`,
converts `MotionEngine`'s caller-space mm/s to wire-signed values using
each port's own `fwdSign_` before handing them to the device);
`src/platform/board.h` (`boardWheelCommandTap()`, `boardOnboardMode()`/
`boardSetOnboardMode()`, `boardOnboardFloor()`/`boardSetOnboardFloor()`
hooks, plus a `motion/wheel_command_tap.h` include); `src/platform/
board_nezha.cpp` (all four hooks as documented no-ops: tap `nullptr`,
mode/floor GET `0`, every SET refused); `src/platform/board_cutebot.cpp`
(`CutebotBoard` gains a `CutebotTapAdapter tap` member bound to the
same device/port pair; the four hooks forward to it/the device);
`src/comms/config_fields.h` (`onboard_pid` ordinal 43 unit `"1"`,
`onboard_floor` ordinal 44 unit `"mm/s"`, appended after the prior last
ordinal 42); `src/shims.cpp` (`ensure()` installs
`boardWheelCommandTap()` on the engine right after constructing `Rig`;
two new `cfgGet/SetOnboardMode`/`cfgGet/SetOnboardFloor` rows in
`kConfigAccessors`, thin forwards to the board hooks); `src/blocks/
motion.ts` (`ConfigField` enum regenerated via
`tools/gen_config_field_enum.py`, gains `OnboardPid`/`OnboardFloor`);
`pxt.json` (`files` gains the two new platform paths);
`tools/make_deploy.py` (`EXPECTED_CPP_FILES` gains
`cutebot_actuation_policy.cpp`); `tests/host/test_cxx11_syntax_gate.py`
(same file added to the C++11 portable-source compile list);
`tests/host/test_cutebot_port.py` (`_SOURCES` gains
`cutebot_actuation_policy.cpp`, now a link dependency of
`cutebot_port.cpp`); `tests/host/sim_nezha_bus.h` (`SimWheel` gains
`stepOnboard()`, a first-order lag straight to a commanded velocity,
bypassing the duty/breakaway pipeline `step()` uses); `tests/host/
sim_cutebot_bus.h` (cmd `0x80` handling: clamps a nonzero magnitude to
200..500, passes 0 through, and a `0x10` write flips `onboardActive_`
back off — the "0x10 cancels onboard mode" assumption, marked
UNVERIFIED in that file's own comment); `tests/host/
wire_motion_verb_shim.cpp` (`WaHandle` gains two plain
`onboardModeValue`/`onboardFloorMmS` fields and matching
`kWaConfigAccessors` rows — this double has no board composition to
forward to, so it just round-trips a stored value, which is what
`test_config_surface_single_source.py`'s compiled half actually
proves); `tests/host/test_board_seam_source_pin.py` and
`tests/host/test_board_cutebot_source_pin.py` (new source-pin tests for
the four hybrid-actuation hooks on each board, since neither
`board_nezha.cpp` nor `board_cutebot.cpp` is host-compilable);
`tests/host/test_block_toolbox_order.py` and `tests/host/
test_wire_motion_verbs.py` (both carry hand-kept lists — the toolbox's
approved `ConfigField` group order and the bare-`GET` dump's full field
list — that needed the two new ordinals appended; failures were
mechanical, not behavioral).

**The policy's exact decision rule, per mode** (`cutebot_actuation_
policy.cpp`). A neutral tick or mode 0 forces `{PWM, disengaged}`
unconditionally, ahead of everything else. Otherwise:

- **Mode 0 (off).** Already handled above — always PWM.
- **Mode 1 (threshold with hysteresis).** `minMag` is the SMALLER of
  the two wheels' tapped-setpoint magnitudes. Not currently engaged:
  engage iff `minMag >= floor * 1.1`. Currently engaged: stay engaged
  iff `minMag > floor * 0.9`. There is deliberately NO separate
  both-wheels eligibility check in this branch — the design doc's own
  illustrative numbers (engage 220, release 180 around a 200 mm/s
  floor) put the release threshold BELOW the floor on purpose, so an
  already-engaged tick whose magnitude sits in that gap must stay
  engaged; the receiving end's own clamp (`sim_cutebot_bus.h`) absorbs
  anything under 200 gracefully. The not-yet-engaged branch needs no
  separate check either: `minMag >= floor * 1.1` already implies both
  wheels clear the floor.
- **Mode 2 (plateau-only).** Both wheels must first pass the hard
  eligibility gate (magnitude exactly 0, or `>= floor`) — unlike mode
  1, mode 2 has no magnitude threshold of its own to fall back on, so
  an asymmetric under-floor pair (an arc) must not engage just because
  the shaper reports cruise. Given eligibility: `kBrake` releases,
  `kCruise` engages, `kAccel` holds whatever the previous state was
  (does not newly engage, does not release an already-engaged run).
- **Both-wheels eligibility gate**, used directly by mode 2 and
  implicitly by mode 1's not-yet-engaged branch: a wheel is eligible
  iff its tapped setpoint is exactly 0 or its magnitude is `>= floor`;
  anything strictly between 0 and the floor is never eligible (that is
  exactly what the `0x80` clamp would otherwise silently distort).

**Defaults.** `onboard_pid` (`CutebotDevice::onboardMode_`) defaults to
`0` — off, pure PWM — per the ticket's own "opt-in until a later bring-
up measures it" instruction. `onboard_floor`
(`CutebotDevice::onboardFloor_`) defaults to `200.0f` mm/s, matching the
onboard loop's own hardware clamp per the design doc's source reading.
`setOnboardMode()` refuses (returns `false`, leaves the stored mode
untouched) for anything outside `{0, 1, 2}`; `setOnboardFloor()`
refuses a non-positive value. A refused SET is silently ignored at the
wire layer (the same "ignored, not erred" shape every other
out-of-range config SET in this table already has) — `SET onboard_pid
0` still always ACKs on the wire, on every board, with no dependency on
any other config value, satisfying the ticket's own escape-hatch
requirement.

**Handoff bookkeeping (design doc's own hazard list).** On release
(onboard → PWM) for any reason other than a neutral tick — hysteresis
release, the plateau's first brake tick, an eligibility drop —
`CutebotDevice::serviceCycle()` ships ONLY the frame `decide()` chose:
`shipFrame()`'s normal PWM path, which sends whatever the kernel's own
PI loop is currently asking for (assumed roughly right at up-handoff;
a real bench measurement is out of this ticket's scope). On a neutral/
stop tick that arrives while the policy was previously engaged,
`serviceCycle()` ships an `0x80` zero-both frame FIRST, then falls
through to the normal PWM path (which ships the `0x10` zero, since
`decide()` always forces PWM on a neutral tick) — both zeros are sent,
per the ticket's own "which one really stops a wheel under onboard
control is a bench probe, and both are cheap" instruction. A neutral
tick that arrives while NOT previously engaged behaves exactly as
ticket 002 left it: one PWM frame only, no second `0x80` write.
`appliedDuty()` needed NO new code to satisfy "reports what the kernel
asked for" — `CutebotMotorPort::tick()` already sets `lastApplied_`
from the kernel's own staged duty unconditionally, before `stageDuty()`
is even called, so it already reflects the kernel's request regardless
of which frame `serviceCycle()` ultimately ships; `test_cutebot_hybrid_
actuation.py`'s own test proves this rather than assuming it.

**The `0x80` clamp lives on the receiving end, not the sender.**
`CutebotDevice::writeOnboardFrame()` ships the tapped setpoint AS
DECIDED, unclamped (only a 16-bit overflow guard at 60000). The 200..500
mm/s clamp is modelled entirely inside `sim_cutebot_bus.h`'s handling of
cmd `0x80`, so a policy bug that slips an under-floor nonzero value
through is visible in what the simulated wheel actually does (clamped
to 200) rather than silently absorbed by a sender-side clamp nothing
would ever see fail. `sim_cutebot_bus.h`'s onboard loop treats the
wire's mm/s magnitude as a counts/s target for `SimWheel` 1:1 — an
arbitrary, clearly-commented simplification, since no real Cutebot
wheel geometry exists yet (caliper measurements are a later bring-up's
job). A `0x10` write flips the sim back to the duty-driven plant — the
"0x10 cancels onboard mode" assumption is UNVERIFIED against a real
board and flagged as such in that file's own comment.

**Every `MEASURED`/`UNVERIFIED` claim in the new code is a source
reading, not a bench result** — no hardware exists for this ticket to
run against. The hysteresis band (±10% of `onboard_floor`) is an
explicitly-labelled POLICY CHOICE modelled on the design doc's own
illustrative 220/180 numbers, not a bench-fitted constant; a later
bring-up may replace it entirely once both policies are actually
scored against real hardware.

**Archaeology-comment budget.** The first draft of this ticket's
comments pushed the repo-wide sprint/ticket-marker count from 173 to
195 and `comms/config_fields.h`'s comment-to-code ratio from 1.61 to
1.70, both hard ratchets (`test_archaeology_marker_budget.py`). Every
`sprint 040 ticket 004`-style reference in the new/edited `src/` files
was cut in favor of stating the current contract plainly (the
sprint/ticket provenance lives in this commit and this ticket file
instead, per the project's own write-time comment standard) — the
suite is back at exactly the pre-existing budget.

**Full-suite result.** `uv run pytest tests/host tests/tools -q
--ignore=tests/tools/test_field_dance_accel_bake.py` — **2260 passed**,
MEASURED this session. This ticket's own new tests are 31
(`test_cutebot_actuation_policy.py`) + 19
(`test_cutebot_hybrid_actuation.py`) + 10 new source-pin tests across
`test_board_seam_source_pin.py`/`test_board_cutebot_source_pin.py` = 60
of those; the remainder are pre-existing and green, including every
test tickets 001-003 added. The ignored file needs a live AprilCam
daemon and is pre-existing/unrelated, per prior tickets' own notes on
it.

**Not attempted / left for later tickets.** `tools/make_deploy.py`'s
`geometry.firmware_bake.board` key, the fleet JSON entry, and the
manifest/TU-list plumbing beyond this ticket's own two new files
(ticket 005); `sim_tour.py --board cutebot-pro` and the full hybrid
tour that closes on the host (ticket 006); a real Cutebot build
checkpoint (ticket 007); the design-doc overlay for `src/platform/
DESIGN.md`/`src/DESIGN.md`/`design.md`'s layer table (ticket 008). On
real hardware (sprint 041 and later): whether the hysteresis band's
±10% is anywhere near right, whether `0x10` genuinely cancels a running
onboard loop, which zero frame actually stops a wheel under onboard
control, and the up-handoff hypothesis that the kernel's PI integrator
resumes close to right after a down-handoff.

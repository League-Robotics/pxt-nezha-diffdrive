# Simulated pivot ringing analysis

Date: 2026-09-06. Model: tovez defaults in `tests/host/sim_tour.py`.
No hardware connected or measured. Plant lag, breakaway and maximum speed
are hypothetical, not fitted to tovez. No firmware or test source changes.

## Evidence and reproduction

The following tables transcribe the successful terminal output from this
analysis session. This document is the retained artifact for those results.
The requested command was run from the repository root:

```sh
ulimit -u 4000; uv run --with matplotlib python tests/host/sim_tour.py
```

Additional parameter-only experiments loaded that module with `runpy.run_path`,
built a fresh library with `_bind(build())`, and called `run_square(lib, **params)`.
All used the default plant and 16 settle ticks. Peak speeds are right-wheel
encoder speeds; headings include the fixed post-move settling interval.

| Overrides | Closure [mm] | Net heading [deg] | First leg peak [mm/s] | First pivot peak [mm/s] | First pivot [deg] |
|---|---:|---:|---:|---:|---:|
| None | 156.19 | +15.52 | 167.4 | 137.9 | 93.96 |
| `twist_hold_gain=0` | 12.35 | -1.56 | 167.4 | 124.7 | 89.39 |
| `ki=0` | 11.81 | +1.03 | 121.5 | 114.9 | 90.15 |
| Both gains zero | 8.70 | +0.27 | 121.5 | 82.1 | 89.81 |
| `reversal_dwell=0` | 33.35 | +3.31 | 167.4 | 137.9 | 90.42 |
| `ki=0, reversal_dwell=0` | 11.81 | +1.03 | 121.5 | 114.9 | 90.15 |
| `full_duty_velocity=676*10/0.7878` | 15.64 | -1.37 | 196.9 | 157.6 | 89.54 |
| Matched full-duty velocity, both gains zero | 15.63 | +0.99 | 151.0 | 101.8 | 89.73 |

Baseline first-pivot trace excerpt, time relative to the first recorded pivot
sample. Duty signs below are robot-side, not raw motor-port signs.

| Time [s] | Left speed [mm/s] | Right speed [mm/s] | Right duty | Left duty | Heading [deg] | Engine active |
|---:|---:|---:|---:|---:|---:|---:|
| 0.816 | -95.19 | +95.19 | +0.03 | -0.03 | 75.40 | 1 |
| 0.840 | -85.35 | +85.35 | 0 | 0 | 77.38 | 1 |
| 0.936 | -39.39 | +42.67 | 0 | 0 | 82.51 | 1 |
| 0.960 | -36.11 | +36.11 | -0.08 | +0.08 | 83.35 | 1 |
| 1.008 | -9.85 | +9.85 | -0.07 | +0.07 | 84.07 | 1 |
| 1.152 | +16.41 | -16.41 | -0.03 | +0.03 | 82.55 | 1 |
| 1.176 | +16.41 | -16.41 | 0 | 0 | 82.17 | 1 |
| 1.296 | +6.57 | -6.57 | +0.15 | -0.16 | 80.95 | 1 |
| 1.392 | -59.09 | +59.09 | +0.19 | -0.19 | 84.26 | 0 |
| 1.416 | -68.93 | +68.93 | 0 | 0 | 85.86 | 0 |
| 1.776 | -6.57 | +3.28 | 0 | 0 | 93.96 | 0 |

Baseline first-pivot startup samples through 0.31 s were identical with
reversal dwell enabled and disabled. Disabling either twist hold or wheel I
removed the wrong-direction wheel-speed excursion after startup and before
engine completion. Disabling dwell alone left a small reverse excursion.

## 1. Feedback changes the profile after it has been shaped

Source reading: `src/core/diffdrive.cpp`, `controlStep()` and `fastPid()`.

The engine sends shaped body velocity/twist to the kernel. Twist hold computes
an integrated commanded-twist position reference and adds proportional
position-error trim to the wheel targets. Its cap is full motor authority
minus the previous target magnitude, not the segment cruise or acceleration
limit. Then each wheel integrates its already-trimmed target into another
position reference and adds `ki * posError` to the duty-producing command.

This creates interacting outer twist-position and inner wheel-position
corrections around a lagged plant. The run uses `twistHoldGain=4`, `ki=6`,
`kp=0`, and `kaff=0`. Neither correction must respect the shaper's cruise,
acceleration, jerk, or requested direction. They can increase the initial
overshoot, subtract enough duty to reverse, and subsequently demand forward
motion again. This is not the old positive-feedback bug that integrated trim
into the twist reference: that specific bug is already corrected here.

Hypothesis tested: the combination of twist hold and wheel I drives the large
reverse excursion. Disabling either independently removes it in this model;
disabling twist hold does not remove the straight-leg speed overshoot.
Removing wheel I does remove that overshoot, but leaves substantial steady
underspeed with the current feedforward calibration. These are discriminating
experiments, not recommended production gain settings.

## 2. Reversal dwell amplifies the braking/restart excursion

Source reading: `src/platform/nezha_port.cpp`, `writeShapedDuty()`.

The 100 ms dwell intercepts any duty-sign change, including controller-generated
braking. The position references continue progressing while the port writes
zero: a fresh encoder sample does not imply the requested duty was delivered.
The default kernel `posErrMax` is zero (unclamped); an I-output clamp alone
does not bound its stored position backlog. Twist trim is likewise not
conditioned on delivered actuator authority.

The observed zero intervals at 0.840-0.936 s and 1.176-1.272 s occur inside the
pivot, before the reverse and forward bursts respectively. In this plotted
run, the 384 ms inter-move pause already satisfies startup reversal dwell.
The chart/module comments attributing this trace primarily to one wheel's
delayed startup therefore do not explain the actual reproduced trace.

Do not remove the dwell as a hardware fix: its source documents an encoder
wedge protection purpose. The controller needs to account for unavailable
actuator authority, rather than integrate through it unaware.

## 3. Arrival is a predicted coast, not a rest-state completion

Source reading: `src/motion/velocity_shaper.cpp` and
`src/motion/motion_engine.cpp`, `service()`.

Arrival uses `remain <= vNext*dt + vAct*lag + stopDistance`. On that condition
the engine stages neutral and returns inactive. It does not require low
wheel velocity or acceleration. Neutral lands on the next kernel step.
The baseline declares completion at 84.26 degrees with wheels near +/-59
mm/s; the next sample is near +/-69 mm/s, followed by coast to 93.96 degrees.
A single lag-distance estimate cannot guarantee endpoint accuracy while
feedback and dwell are producing this nonmonotonic actuation.

Short inter-move gaps also matter: the original script's two-tick-gap run
closes at 106.6 mm and -10.76 degrees; with twist hold disabled it closes at
271.1 mm and -29.47 degrees. Thus better closure with a long pause is not proof
of a correct start/stop/handoff contract. `settleToRest()` exists, but this
simulator uses a fixed tick count, and `service()` itself reports inactive
before rest.

## 4. This is not an end-to-end jerk-limited trajectory

Source reading: `src/motion/motion_limits.h` defaults jerk to zero;
`tests/host/sim_robot_shim.cpp::srSetLimits()` never sets jerk. The plotted run
therefore has acceleration limiting only, even before downstream feedback.

The shaper applies its speed floor AFTER acceleration/jerk limiting. At 24 ms
the configured acceleration permits a 9.6 mm/s first increment, but a straight
starts at 70 mm/s and a pivot at about 20.7 mm/s. These deliberate reference
steps cannot meet the requested acceleration/jerk contract. Similarly, the
arrival-to-neutral transition bypasses a smooth terminal ramp.

There is also a separate jerk-branch defect visible in source: after computing
a jerk-limited `vNext`, it executes `if (vNext > vGoal) vNext = vGoal`.
For a descending goal this can snap immediately to that goal, undoing the
rate limits. Braking distance also uses `sqrt(2*decel*usable)`, without a
jerk-dependent stopping-distance plan. These cannot cause this jerk-disabled
trace, but simply enabling jerk will not establish the requested guarantee.
UNVERIFIED executable descending-goal probe: the attempted follow-up could
not spawn Python because of the machine's process limit, despite `ulimit`.

## 5. Test and simulator qualifications

Executed `uv run pytest tests/host/test_velocity_shaper.py -q`: 33 passed.
Its startup test explicitly requires the floor step. Its jerk test disables
the floor and tests acceleration toward a constant target, not descending
goals, terminal stopping, or the downstream closed-loop motor stack.

The model's feedforward expects 10795 counts/s at full duty, whereas the plant
provides `676*10/0.7878`, about 8581 counts/s. That deliberate/unfitted mismatch
requires persistent correction. Matching it changes the transient substantially;
with both feedback gains retained it actually increases the speed peaks.
Endpoint closure alone is therefore an inadequate acceptance metric.

Also, `sim_robot_shim.cpp::srTick()` computes ground-gain-adjusted plant
positions but discards them and integrates the port's encoder positions for
the chart pose. This is not independent ground truth, and its ground-gain
injection currently does not reach the plotted trajectory. It does not explain
the default symmetric run's ringing, but limits claims about physical accuracy.

## Recommended next work

1. Add regression checks on the full motor-port simulation for no physical
   reverse excursion, peak speed, acceleration/jerk, endpoint error and
   rest-state handoff. Plot planned speed, trimmed target, I correction,
   requested/applied duty and completion state together.
2. Make feedback/anti-windup aware of applied actuator authority and reversal
   dwell; design the twist and wheel loops together rather than tuning them
   independently. Preserve the hardware protection dwell.
3. Establish one coherent trajectory contract including jerk-aware braking,
   physically justified breakaway handling, and terminal velocity/acceleration.
   Do not enforce a discontinuous minimum trajectory speed to compensate for
   actuator stiction without explicitly accounting for that compromise.
4. Validate with fitted motor dynamics and then camera-truthed hardware runs.

Resolution: cause isolated by source inspection and parameter ablation; no
production fix attempted. Full project suite not run because source/tests
were not changed. Existing simulator edits were left intact.

## Implementation follow-up: host validated, bench tour captured

The stakeholder subsequently authorized implementation and explicitly allowed
a local vendored-kernel change, with upstream synchronization deferred.

Added `tests/host/test_sim_profile_tracking.py`. All three tests failed on
the unchanged baseline: reverse pivot excursion, cruise overshoot, and
square closure. This confirms the tests detect the reported behavior.

The completed host change separates the wheel position references from twist
trim and filters both position and twist references using the configured
response lag. The shaper now rounds descending targets without snapping to
them, budgets jerk-dependent braking, and lets jerk-enabled startup ramp
through the reference floor. Lagged segments remain active until two fresh
encoder samples report low speed with zero applied duty. Zero-lag segments
retain their previous completion contract.

The initial validation interruption was traced to recursive Copilot CLI
processes and resolved with stakeholder authorization. The focused full-stack
tests now cover reverse excursion, cruise overshoot, closure, pivot error,
and completion without an external settling gap, at jerk 0 and 800.

HOST TESTED 2026-09-06, no hardware board involved:
`captures/vevov-motion-20260906/regression.log`
(`uv run pytest -q --maxfail=1`) records 1877 passed in 80.08 seconds.
The behavioral checks are in
`tests/host/test_sim_profile_tracking.py` and
`tests/host/test_velocity_shaper.py`.

The host model remains unfitted. This is not a claim of physically bounded
motor jerk or playfield accuracy. `final-simulation.log` records the final
jerk-800 model result: 17.0 mm closure, -1.67 degrees net heading error.

MEASURED Vevov 2026-09-06, `captures/vevov-motion-20260906/tour.log`,
`tour_pose.csv`, `tour_tlm.csv`, and `provenance.json` in that directory:
the farm-stand wheels tour completed with OTOS off, 31.06 mm encoder
closure and -4.35 degrees heading residual. No telemetry frames were
dropped. The firmware's `i2cf` diagnostic rose to 45; its cause remains
unresolved. See that directory's `notes.md` for the firmware hash,
configuration, bench-only limitations, and separate hardware graph.
---
status: pending
---

# Trajectory shaping: constant-acceleration profiles + speed chosen by distance

## Description

Leg accuracy collapses as commanded speed rises, and the move engine has no
term for deceleration anywhere in it.

MEASURED 2026-08-31, `captures/fleet-tours-speed-20260831.json` (vevov + tigez,
100 cm orange-dot legs, camera-scored):

| commanded cruise | peak reached | speed still moving when the move ended | mean leg miss |
|---|---|---|---|
| 200 mm/s | ~230 | 38–70 mm/s | 2.0–2.1 cm |
| 400 mm/s | ~440 | **~400 mm/s** | 3.6–4.1 cm |

At 400 mm/s the robot **never decelerates at all** — it runs at full cruise and
the move simply ends. A telemetry frame at that speed covers 2.9 cm, so the
stop lands wherever momentum puts it.

Stakeholder goal (2026-09-01): a longer, controllable ramp-down; independent
control of acceleration and deceleration; and a default cruise chosen by the
distance of the move, so a move never asks for a stop it cannot make.
Priority: accuracy over speed.

## Cause

Deceleration is a *distance-proportional taper* over a **fixed** window
(`src/motion/motion_engine.cpp:361-398`):

```cpp
const float axisScale = remain / distTaper_;   // distTaper_ = 400 counts ≈ 31.5 mm
if (axisScale < scale) scale = axisScale;
```

Because the window is a fixed distance, the deceleration it *demands* rises as
the square of speed (`a = v²/distTaper`), while the control loop stays at 24 ms
(`src/shims.cpp:225`):

| cruise | implied decel | time in the window |
|---|---|---|
| 100 mm/s | 320 mm/s² | 315 ms (achievable) |
| 200 mm/s | 1 270 mm/s² | 157 ms (marginal) |
| 400 mm/s | **5 080 mm/s²** | **79 ms — under 4 control ticks** |

This is not a tuning problem: the profile asks for a deceleration the robot
cannot produce, and there is no `a_decel` term in the codebase to bound it.

Acceleration has the mirror-image defect — it is **time**-based, not
acceleration-based (`motion_engine.cpp:402-408`, `rampMs_` = 400 ms rising from
0.25·cruise), so effective accel is `1.875 × cruise` and silently scales with
whatever cruise is passed. Accel and decel are two different kinds of quantity,
unified only by `min()`; neither is expressed in mm/s².

Contributing: an undocumented `0.25f` first-tick literal
(`motion_engine.cpp:171,183`) acts as a third floor that bypasses `turnFloor_`
and starts every segment with a step discontinuity.

## Proposed fix

Both requirements reduce to one equation. Constant deceleration `a` means
braking distance `d = v²/(2a)`, so the speed permissible with `remain` left is
`v = √(2·a·remain)`.

**1. Deceleration — constant-`a` solve** (`motion_engine.cpp:356-398`). Replace
`remain / distTaper_` with a braking-speed solve in engineering units: convert
`remain` to mm via `countsPerMm()` (`motion_engine.h:239`), compute
`v_allow = sqrt(2 · aDecelMmS2_ · remain_mm)`, command `scale = v_allow / cruise`,
still min-combined with the accel term and floored so every existing guard
(floors, margins, wrong-way, deadline) keeps working. The braking window then
auto-scales with speed (≈29 mm at 200 mm/s, ≈114 mm at 400 mm/s, at 700 mm/s²)
instead of being frozen at 31.5 mm. Retain `distTaper_`/`yawTaper_` as a window
ceiling.

**2. Acceleration — true mm/s² ramp.** Replace the `elapsed/rampMs_` fraction
with a velocity integrator, `v_cmd ≤ v_prev + aAccelMmS2_ · dt`, giving the two
slopes independent control. Fix the `0.25f` first-tick literal while here.

**3. Speed chosen by distance.** `cruise == 0` already means "use the default"
on the wire (`src/comms/wire_adapter.cpp:397-399`), so this needs **no wire
arity change and no new verb** — only a change to what the sentinel resolves to
(today a flat 150 mm/s, `src/shims.cpp:165`):

```
v_default(D) = min( vMaxMmS_, sqrt(2 · aDecelMmS2_ · brakeFrac_ · D) )
```

`brakeFrac_` caps the share of the leg spent braking (accuracy-first ⇒ ~0.35–0.4).
`vMaxMmS_` is the global ceiling; measurement points at 200–250 mm/s, since
200 mm/s produced the best closure this rig has recorded (tigez 0.22 cm,
2026-08-31) while 400 mm/s doubled the miss. **Constants come from the bench
sweep below, not from a guess.** An explicit `cruise` on the wire always wins.

**4. Legacy mode.** With `aAccel == 0 && aDecel == 0` the engine must follow
today's code path bit-for-bit, so the feature ships inert and the pinned
regression tests (`tests/host/test_motion_engine_deadline_boundary.py`,
`test_regression_yaw_taper_pure_turn.py`) keep passing unmodified.

**5. Make the profile wire-settable.** The five shaping knobs (`distTaper_`,
`yawTaper_`, `distFloor_`, `turnFloor_`, `rampMs_`) are reachable only from
TypeScript — none is in `kFields[]` (`wire_adapter.cpp:103-144`) — so every
profile experiment currently costs a reflash. Add the new terms (`accel`,
`decel`, `v_max`, `brake_frac`) plus those five as SET/GET fields at ordinals
19+, following the `pivot_overrun` precedent (`git show b99294f --name-only`):

- `src/blocks/motion.ts:16-55` — `ConfigField` enum member (ordinal source of truth)
- `src/comms/wire_adapter.cpp:103-143` — `kFields[]` row; the trailing
  `// ConfigField.Name` comment is load-bearing, a drift test parses it
- `src/shims.cpp:949-999` and `:1013-1047` — `setKernelValue`/`getConfigValue`
  cases (both required; a drift test asserts every ordinal has both)
- `src/motion/motion_engine.h:561-567` — field plus setter/getter with validation
- `tests/host/wire_motion_verb_shim.cpp:279-380` — the hand-mirrored test double
- `tests/host/motion_engine_shim.cpp:341-353` — `meSetX()` export for engine tests
- `tests/host/test_block_toolbox_order.py:134-143` — hardcoded enum baseline
- `docs/design/specification.md:207-228` — §4.8 table (already stale at ordinal 17)

Constraints: `//%` shims are capped at 4 params (5 crashes PXT with TS9200,
`shims.cpp:1099-1110`), so pair the new setters as `setTaperWindows` does; and
`src/core/diffdrive.{h,cpp}` is vendored byte-identical from radio-robot and must
not be touched — all shaping belongs in `motion_engine`.

## Verification

**Tier 1 — host simulation, no hardware.** `uv run pytest`. The harness already
drives the engine tick-by-tick and records: `_drive_to_completion()` at
`tests/host/test_motion_engine_deadline_boundary.py:317-351`, sampling
`meOutVelocityLeft/Right`. New tests assert: decel measured in mm/s² is constant
across cruise 100/200/400/600; accel and decel are independently settable and
observed; `v_default(D)` is monotonic in D and never exceeds what the leg can
brake from; and legacy mode reproduces today's profile bit-for-bit.

**Tier 2 — bench, lossless.** With a robot on USB (farm node), sweep
distance × cruise and capture `TLM FULL` at 20 Hz off the USB tap (0.0% frame
loss, versus ~25% over radio — see
`clasi/issues/radio-telemetry-loss-is-wifi-interference-at-the-relay-site.md`).
Fit actual accel/decel per run; this is the source of the real constants. Decode
via `tools/tlm.py` — `vl`/`vr` are already mm/s, `dutl`/`dutr` are percent×100.

**Tier 3 — field.** Re-run the orange-dot tour at the tuned defaults and compare
leg misses against the 2026-08-31 baseline (200 mm/s: 2.0 cm; 400 mm/s:
3.6–4.1 cm). Success is 400 mm/s matching or beating the old 200 mm/s accuracy.

## Related

- `reports/tovez-taper-stall-20260829.md` — already recommended "a wider
  `distTaper_` would let the wheel track the reference"; this generalizes that
  fix rather than re-tuning one constant. Also the origin of the `vMin` 70 mm/s
  floor (`shims.cpp:200-211`), raised because the old taper let the position
  I-term brake a wheel into a stall it could not restart. A longer, gentler
  ramp-down should reduce that risk, but **the Tier-2 sweep must explicitly
  re-check for the end-of-leg stiction bump** under the new profile.
- `reports/gopiv-speed-floor-70-20260829.md` — speed-floor measurement.
- `reports/fleet-tours-20260831.md` — the tours this issue's numbers come from.
- `clasi/issues/goto-under-closed-profile-terminates-legs-early.md` — open, and
  directly implicates ramp shaping (legs abort under `closedLoopProfile()`'s
  180 ms ramp but never under the 400 ms open profile). Worth resolving together.

---
id: 009
title: 'Lag-aware braking and arrival: plan against measured wheel speed, add the
  lag limit, prove it on the lagged host model'
status: in-progress
use-cases:
- SUC-001
- SUC-003
depends-on:
- '004'
github-issue: ''
issue: pivot-end-predictive-termination-and-yaw-floor.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Lag-aware braking and arrival: plan against measured wheel speed, add the lag limit, prove it on the lagged host model

## Description

**Hardware finding.** Ticket 007's first bench run on tovez
(2026-09-04, `captures/bench-acceptance-029-20260904/`) found 90°
pivots at cruise 100 ending +13…+56° long in the robot's own odometry,
against the ideal-wheel probe's ±0.5° prediction
(`docs/design/motion-profile-unification.md` §6.3, "Plan against the
measured speed, and model the lag"). Two isolated single-pivot probes
that same session read +110.08° and +123.32° actual rotation on a
commanded +90° (camera-truthed, `evidence-pivot90-01.log`,
`evidence-pivot90-full-telemetry.log`); the session's own working
hypothesis was a kernel/fiber wedge (frozen telemetry columns), and a
follow-up diagnostic session (`captures/bench-acceptance-029-20260904-diag/notes.md`)
re-ranked that against two alternative explanations without new
hardware evidence. Design §6.3's own "+13…+56°" figure is the one this
ticket is chartered against — the design amendment below is the fix,
independent of which of the three hypotheses eventually explains the
20260904 telemetry anomaly, because it closes a real modeling gap
either way.

**The mechanism.** `VelocityShaper::advance()` (design §6.1,
`src/motion/velocity_shaper.cpp`) currently plans its braking distance
and its arrival predicate against `vPrev` — the shaper's own last
*commanded* speed — not what the wheel is actually doing. A real
drivetrain's wheel follows a command change about `lag` seconds late
(first-order response), so it keeps covering ground at the old,
higher, actual speed for that long after the shaper thinks it has
already started slowing down. A constant-decel plan braking from
cruise is sensitive to this in proportion to speed — MEASURED against
this sprint's engine as first landed, on the lagged host model
(`docs/code-review/2026-09-02/raw/stiction_probe.cpp` /
`.out`): ideal wheels land within ±0.1° at every cruise, but a 150 ms
lag with 70 mm/s breakaway stiction reaches **+26.1°** at cruise 200
(design §6.3's table, cruises 40/100/200). The *retired* legacy taper
was not exposed to this failure mode because it crawled the last
degrees at a fixed floor speed regardless of lag; the new
constant-decel braking plan brakes from cruise, so lag error scales
with how fast the pivot was going when braking began — exactly the
qualitative shape (bigger overshoot at higher cruise) design §6.3's
table and the hardware run both show.

**The design amendment** (`docs/design/motion-profile-unification.md`,
already written, this ticket implements it):
- §4.1: `MotionLimits` gains `lag` `// [s]` — drivetrain response lag,
  0 until measured, "positive-or-zero, else keep" setter (0 is a valid
  "unknown/no lag" value, same validation style as `jerk`/`omegaMax`).
- §6.1 steps 0, 1, 5: a new step 0 reads the kernel's *measured*
  dominant-axis speed (`vAct`) instead of the shaper's own `v_prev`
  when it is available; the braking plan (step 1) subtracts
  `vAct*(dt + lag)` from what remains instead of `vPrev*dt`; the
  arrival predicate (step 5) is `remain <= vAct*(dt + lag) +
  stopDistance` instead of `remain <= vNext*dt + stopDistance`.
- §6.3: names the mechanism and the fix — plan and predict against the
  measured speed, and model the lag explicitly rather than assuming
  the wheel already did what was commanded.
- §10.2: `lag` becomes the *first* of the three §10.2 bench
  measurements (fit a `WHEELS_V` step response as first-order,
  50-150 ms expected), landing before `stop_distance` (which must be
  measured with `lag` already set, since `stopDistance` is defined as
  only the speed-*independent* remainder once the lag term is
  accounted for separately).

## Acceptance Criteria

- [ ] `MotionLimits::lag` `// [s]` field added
      (`src/motion/motion_limits.h`), default `0.0f`, with a
      "non-negative, else keep" `setLag()` setter (same validation
      shape as `setOmegaFloor()`/`setJerk()` — 0 is a legitimate value,
      not "unset").
- [ ] `lag` exposed on the wire as ordinal **37** (the next free
      ordinal after `arrive_yaw`'s 36) in `src/comms/wire_adapter.cpp`'s
      `kFields[]`, and as the matching `ConfigField` entry in
      `src/blocks/motion.ts`, following the same thin-forward pattern
      `omega_floor`/`arrive_dist`/`arrive_yaw` already establish.
- [ ] `tools/make_deploy.py`'s `_GEOMETRY_BAKE_RES`/`_GEOMETRY_BAKE_FILES`
      gain a `lag_s` entry (regex on `float lag = `, targeting
      `motion_limits.h`, the same file `stop_distance_mm` already
      targets) so `firmware_bake.lag_s` bakes the same way
      `stop_distance_mm` does — opt-in, byte-identical build when a
      robot config carries no `lag_s` block.
- [ ] `VelocityShaper::advance()` (`src/motion/velocity_shaper.{h,cpp}`)
      takes one new trailing parameter carrying the kernel's measured
      dominant-axis speed (`float measured`, `// [mm/s]`, `-1.0f`
      meaning "unknown, use the shaper's own last command" — the
      sentinel design §6.1 step 0 describes), and both the braking
      plan (step 1) and the arrival predicate (step 5) use
      `vAct*(dt + lim.lag)` in place of the current `vPrev*dt` /
      `vNext*dt` exactly as design §6.1 now reads.
- [ ] `MotionEngine::service()` (`src/motion/motion_engine.cpp`) passes
      the kernel's measured dominant-axis speed on the segment's
      dominant axis to every `shaper_.advance()` call: for a distance
      segment, `0.5f*(out.velocityLeft + out.velocityRight)/cpm`
      (`// [mm/s]`); for a pure-turn segment, the half-differential
      `0.5f*(out.velocityRight - out.velocityLeft)/cpm` converted the
      same way `omegaFloorAsWheelSpeed()` already treats a pure-turn
      dominant axis; for the continuous hold (`wheelsV`), pass `-1.0f`
      (no single dominant axis to measure against a slewing target —
      the sentinel case).
- [ ] `tests/host/test_velocity_shaper.py` gains lag cases: a nonzero
      `measured` argument that differs from the shaper's own `v_prev`
      changes the braking-plan and arrival results in the direction
      design §6.1 predicts (planning against a higher `vAct` than
      `vPrev` brakes earlier / declares arrival sooner); `measured =
      -1` reproduces today's `vPrev`-only behavior exactly (regression
      guard — no behavior change for a caller that does not yet supply
      a measured speed).
- [ ] `tests/host/test_profile_probe.py` gains a lagged-wheel model
      ported from `docs/code-review/2026-09-02/raw/stiction_probe.cpp`
      (first-order response with time constant `tauS` = 0.08 and
      0.15 s, breakaway stiction 70 mm/s) and asserts 90° pivots at
      cruise 40/100/200 land within the 1.0° arrival window when
      `MotionLimits::lag` is set to the model's own `tauS` — i.e. the
      fix closes the gap the unfixed model shows in design §6.3's
      table, on the SAME lagged model, not just on ideal wheels.
      Ideal-wheel (`lag = 0`) results are unchanged (still ±0.5°, the
      existing ticket-003 assertion). Design §6.3's table is
      re-measured with the fix landed and the new numbers recorded in
      this ticket's own session notes before it is moved to done
      (`.claude/rules/measurement-citations.md` — a host-model run is
      MEASURED against the model, not against hardware; label it as
      such).
- [ ] `src/DESIGN.md` §3 gains a `lag` field-comment entry in the same
      style `travelCalib`/`trackWidth`/`rotationalSlip` already carry
      (default, units, "0 until measured", pointer to design §10.2).
- [ ] `docs/design/specification.md`'s constants table gains a `lag`
      row.
- [ ] Every new identifier (`lag`, `setLag`, `vAct`, `measured`, the
      wire name `lag`, the bake key `lag_s`) is bare with its unit in a
      trailing `// [unit]` comment on the declaration, per
      `.claude/rules/no-units-in-identifiers.md` — no `LagS`/`LagMs`
      suffix anywhere.
- [ ] Scoped run `uv run pytest tests/host/ -q --deselect
      tests/host/test_typescript_typecheck.py::test_tsc_noemit_is_clean`
      is green (`.claude/rules/source-code.md` — this ticket's own
      scoped subset; the full suite runs once at `close_sprint`).

## Implementation Plan

**Approach**: Add `lag` to `MotionLimits` first (isolated,
host-portable, no caller changes needed yet), then thread the measured
speed through `VelocityShaper::advance()`'s new trailing parameter,
then wire `MotionEngine::service()` to supply it from the kernel's
`Output` on both the distance and pure-turn dominant axes (and `-1.0f`
for the continuous hold), then extend the config descriptor surface
(wire ordinal, block field, bake key) so `lag` is settable and
bakeable the same way every other `MotionLimits` field already is,
then port the lagged-wheel model into the host probe test and confirm
the fix closes the gap design §6.3's table shows on the unfixed model.
This mirrors ticket 002's own layering (limits object, then shaper
math, then engine wiring) so each step is independently host-testable
before the next depends on it.

**Files to create/modify**:
- `src/motion/motion_limits.h` — `lag` field, `setLag()`.
- `src/motion/velocity_shaper.h` / `.cpp` — new `measured` parameter on
  `advance()`; `vAct` computation (step 0); braking plan and arrival
  predicate updated to use `vAct*(dt + lim.lag)`.
- `src/motion/motion_engine.cpp` — both `shaper_.advance()` call sites
  (segment path and continuous-hold path) pass the measured speed.
- `src/comms/wire_adapter.cpp` — `kFields[]` gains `{"lag", 37}`.
- `src/blocks/motion.ts` — `ConfigField` gains the matching entry.
- `src/shims.cpp` — the config descriptor's ordinal↔field switch gains
  case 37 (thin forward to `MotionLimits::setLag()`/`lag`), following
  the existing cases for ordinals 34-36.
- `tools/make_deploy.py` — `_GEOMETRY_BAKE_RES`/`_GEOMETRY_BAKE_FILES`
  gain `lag_s` (targets `motion_limits.h`, regex on `float lag = `).
- `tests/host/test_velocity_shaper.py` — lag cases (see acceptance
  criteria).
- `tests/host/test_profile_probe.py` — lagged-wheel model ported from
  `docs/code-review/2026-09-02/raw/stiction_probe.cpp`; pivot-at-cruise
  assertions with `lag` set.
- `src/DESIGN.md` §3, `docs/design/specification.md` (constants table)
  — `lag` field documentation.

**Testing plan**: Host-only — this ticket does not need a robot. Run
the scoped subset (`tests/host/`, per `.claude/rules/source-code.md` —
ticket-level runs stay scoped, the full suite runs once at
`close_sprint`) after each layering step above, then the new
lagged-model assertions in `test_profile_probe.py` last, since they
depend on every earlier step landing.

**Documentation updates**: `src/DESIGN.md` §3 (real-file edit, per
sprint.md's note on this sprint's `seed_sprint_design_overlay` slug
collision — `src/DESIGN.md` is not overlay-mediated this sprint, so
this edit must land in the real file directly, not through the
overlay) and `docs/design/specification.md`'s constants table.

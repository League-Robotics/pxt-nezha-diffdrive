---
status: pending
---

# Measure vevov's true full-duty velocity

## Description

`fullDutyVelocity = 10795 counts/s` (`src/shims.cpp` ensure(), the tovez
bake) is the feedforward gain for the entire velocity servo:
`duty = v_cmd / fullDutyVelocity`, and with `kp = 0` in the same bake it
carries essentially 100% of every commanded speed. The value has never
been measured on vevov — no capture artifact in this repo backs it
(UNVERIFIED per `.claude/rules/measurement-citations.md`), and the max
wheel speed in any existing capture is 175 mm/s (cruise-limited, never
saturated). At vevov's current travel calib (0.7122 mm/deg, baked
2026-08-28 after the wheel change) the constant claims ~769 mm/s
full-duty; the stakeholder estimates ~600 mm/s is closer to reality.

## Cause

The constant was inherited fleet-wide from tovez's
`boot_calibration.cpp` bake. The 2026-08-28 per-robot geometry bake
(`make_deploy.py _inject_geometry()`) injects only
travelCalib/trackWidth/rotationalSlip — never `fullDutyVelocity`. A
wrong FF gain hides at tour speeds: if the true value is ~600 mm/s, the
I term silently supplies ~22% of every commanded speed and saturates
(`iMax` = 765.6 counts/s ≈ 55 mm/s) at a commanded ~250 mm/s — below
that, steady-state speed still lands and nothing looks wrong; above it,
the robot genuinely runs slow with the integrator pinned.

## Proposed fix

Measure it by saturating the duty rail: command `WHEELS 1200 1200`
(mm/s, far above achievable; FF alone demands ~156% duty, clamped to
the 100% rail, `satL/satR` latch true). The steady-state encoder
`vl`/`vr` plateau then reads true full-duty wheel speed directly.

1. **Floor run (loaded — the number that matters)**, over the zavaz
   relay ch 4: lights confirmed on via GetStatus; measured camera start
   fix (AprilTag 1 sanity, tag 53 for vevov); pre-flight path check
   (usable straight run ~110 cm inside the 12 cm margin — a 1000 ms
   timed hold at worst-case ~770 mm/s travels ≤ 77 cm plus coast;
   shorten to 800 ms if the measured start makes it tight); `TLM POSE`
   streaming with sequence ids throughout; camera fix at rest after;
   repeat in reverse for direction asymmetry.
2. **Bench run (unloaded — separates load effect)**, USB, one serial
   session per experiment (port open resets the target); confirm
   surface from the data (OTOS ox/oy ~mm on the stand), not memory.
3. **Reduce**: `fullDutyVelocity_measured [counts/s] = plateau_mm/s ×
   cpm` (cpm = 10/0.7122 = 14.04); note `vl_mmps` telemetry is already
   converted through the flashed calib, so divide back out with that
   same calib. Write `captures/vevov-full-duty-<date>.md` with a table
   (run, direction, loaded/unloaded, encoder plateau, camera
   cross-check, battery state) and the comparison vs the baked 10795.

Out of scope here, follow-up decisions once the number exists:
- Fixing the constant — `SET full_duty_velocity <v>` at session start
  (wire ordinal 1, already plumbed), extending `_inject_geometry()`'s
  bake (tools/), or changing the shims.cpp default (src/, needs a
  ticket).
- Re-deriving the other kernel constants (iMax/pidMax/vMin/posErrMax
  are round mm numbers at tovez's 12.76 counts/mm; vevov is now 14.04).

## Verification

- The capture file names its artifacts (CSV paths, camera reads, date,
  board) per the measurement-citations rule.
- Sanity gates during the run: `satL`/`satR` true during the plateau;
  robot stays inside field margins; camera and encoder distances agree
  to a few percent.

## Related

- `captures/vevov-wheel-scale-20260828.md` — the wheel change and new
  travelCalib this measurement must be reduced against.
- Commit 5fb41b0 — per-robot geometry bake (geometry only; this
  constant deliberately not injected).
- `clasi/issues/rotation-error-is-injected-by-the-legs-not-the-pivots.md`
  — same error-budget program.

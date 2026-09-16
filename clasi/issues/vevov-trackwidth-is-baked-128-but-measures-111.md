---
status: pending
---

# vevov's baked trackwidth is 128.0 mm; the stakeholder measures 111 mm

## The numbers

- Flashed firmware (verified in the built scratch copy,
  `.tmp/deploy-head/src/motion/motion_engine.h`, 2026-09-16):
  `trackWidth_ = 128.0f`, `rotationalSlip_ = 1.1013f`,
  `travelCalib_ = 0.79324f`. Rotations therefore use an effective track
  of 128.0 / 1.1013 = **116.2 mm**.
- **Stakeholder caliper measurement, 2026-09-16: 111 mm.**
- The 128.0 came from the stakeholder's own caliper measurement recorded
  in `radio-robot-lib/config/robots/vevov.json` on 2026-08-28, after the
  chassis rebuild. Something has changed since, or that measurement no
  longer describes where the wheels contact.

## Why it is not a simple swap

A too-large configured track makes the robot OVER-rotate, because the
firmware commands more wheel travel per degree. vevov **under**-rotates.
So correcting 128 -> 111 alone moves the error the wrong way: with a
true track of 111 and an effective 116.2, pivots should run about 5 %
long, and they run ~25 % short.

The remainder is scrub — the wheels slipping sideways during a pivot,
which the encoders cannot see and which `rotational_slip` exists to
absorb. On this surface it is large.

MEASURED vevov 2026-09-16, `captures/039-002-repro-20260915/` session
and `reports/vevov-turn-cal-20260916/`:

- Pre-flight dance, twice: pivots landed -36 / -41 / -17 deg and
  -22 / -21 / -34 deg against commanded +90 / +180 / +90.
- `calibrate.py turns` (2 reps per cell, `--trackwidth-mm 111`):
  fit gain 0.9221, offset +1.71 deg, mean abs error 8.8 deg, and a
  strong direction asymmetry — **left turns short by 8.4 deg, right
  turns long by 9.2 deg**. Its suggestion: slip 1.0153,
  stop_distance 1.51 mm.
- Those were live-SET and re-danced: pivots improved to -9 / -31 / -6,
  drift per 90 deg halved from -30.3 to -12.9. **Still FAILED the
  dance.**

Note the two instruments disagree about magnitude — the dance saw ~25
deg of shortfall where `turns` saw ~9 deg with a direction split. That
disagreement is itself unexplained and worth resolving before trusting
either number.

## What needs doing

1. Re-measure the track width and agree on the geometric value. The
   project rule is that trackwidth carries the geometric measurement and
   is never "corrected"; `rotational_slip` carries everything else.
2. Re-fit `rotational_slip` on THIS surface with more reps than 2 per
   cell, and investigate the left/right asymmetry rather than averaging
   it away — a direction-dependent error does not come from a track
   width.
3. Bake both into `radio-robot-lib/config/robots/vevov.json`'s
   `firmware_bake` and reflash. **The current corrections are live-SET
   only and are lost on reboot** — vevov has already rebooted once today
   when it migrated farm nodes.
4. Re-run the dance until it passes before any rotation-dependent work
   on this robot.

## Scope

Not part of sprint 039. Ticket 003's pulse gate is unaffected: it
measures straight-line wheel travel from the encoders, cross-checked
against the camera over a cumulative burst, and never pivots. But vevov
should not be used for turning work until this is settled.

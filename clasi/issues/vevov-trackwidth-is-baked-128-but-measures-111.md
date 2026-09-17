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

## Independent corroboration of 111 (2026-09-16)

The nezha-robot-template session calibrated **tovez**'s turns the same
night and landed on an effective track of **111.1 mm** (baked as
trackWidth 114.2 mm with rotational_slip 1.028; 114.2/1.028 = 111.1).
That came purely from camera-truthed partial turns — no calipers.

So two independent methods, on two robots of the same chassis family,
agree to about 0.1 %: Eric's calipers say 111 on vevov, and camera-fitted
rotation says 111.1 on tovez. Their verification run: +90 -> +90.40,
-90 -> -90.57, +180 -> +181.64, -180 -> -180.18.

That is strong evidence 111 is the right neighbourhood and 128 is not.

## The whole-revolution trap (their mechanism, worth testing)

That session produced a bogus b = 128.9 mm earlier the same evening and
caught it. The cause is worth recording because it is invisible by
construction: **they were fitting from whole revolutions, and a 360 ends
where it started, so a near-zero residual means EITHER a perfect turn OR
no turn at all.** With the geometry badly wrong the robot was barely
rotating, the residual looked excellent, and they reported 0.14 %
accuracy on a robot that was not turning. Partial turns exposed it
immediately, because +-90 and +-180 must end somewhere different from
where they began.

**Caveat before adopting this as the explanation for vevov's 128:** it
does not fit the recorded provenance. `vevov.json` describes 128.0 as
the stakeholder's CALIPER measurement from 2026-08-28, not a fitted
value, and the 2026-09-05 slip fit used +-90/107/180 pivots rather than
whole revolutions. So for vevov the likelier stories are that the
chassis changed after August, or that the August caliper measurement
took a different span (e.g. wheel outer faces rather than contact
patches). Worth resolving by asking what was measured, not only by
re-measuring.

Either way the lesson generalises: **never fit rotation from whole
revolutions alone.** Any re-fit under this issue must use partial turns.

### The cheapest test of the caliper-span theory needs a human

If 128 was measured across the wheels' OUTER FACES and 111 across the
CONTACT PATCHES, the difference is roughly two wheel widths and would
explain the gap outright, with no robot fault at all. Settling it costs
one bench measurement: **measure BOTH spans on any one of these
chassis** and see whether the difference accounts for 128 vs 111.

This is a physical measurement. No agent session can perform it — it
wants calipers and hands, and it is worth asking for while robots are
being moved anyway. Until someone does, treat both 128 and 111 as
measurements of possibly-different quantities rather than as a
contradiction.

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

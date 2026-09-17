---
status: in-progress
sprint: 039
tickets:
- 039-001
- 039-003
- 039-004
- 039-005
---

# Nudge mode — settle-gated pulse stepper for sub-floor micro-moves

Full analysis: `reports/crawl-mode-analysis-20260831.md` (2026-08-31).

The kernel's floor (`vMin` 70 mm/s) makes ~67 °/s the slowest
sustainable pivot rate, and rotation targets under ~2–3° are deliberate
no-ops (margins + `pivot_overrun`), so `tools/park.py` absorbs small
heading residuals instead of executing them. The robot cannot execute a
1–2° heading trim or a sub-centimeter position nudge today.

Proposal: a MotionEngine-level "nudge mode" — kernel raw-duty pulses
(amplitude ~22–25 %, width 1–3 ticks) fired only when both wheels are
settled, remaining error re-read from encoder counts between pulses,
terminated on margin/deadline/pulse budget. Auto-routed from `MOVE_X`
requests below what the floor can execute (roughly |dist| < 15 mm,
|rot| < 5°). No kernel change (it is vendored/byte-synced with the
radio-robot firmware); no new wire verb.

Explicitly NOT: turning on the existing `crawl_pulse` dither.
MEASURED tovez 2026-08-29, `captures/tovez-taper-20260829/variants.json`
(`reports/tovez-taper-stall-20260829.md`): `crawl_pulse 0.09` made
end-of-leg stalls worse; the floor-70 default already solved leg
endings.

## Gates

1. **Go/no-go characterization first**, on the floor, camera-truthed
   (wheels-up stiction is not a proxy for loaded stiction): per-pulse
   displacement map over amplitude × width, per wheel, warm and cold.
   Accept if some cell gives a repeatable 0.3–2 mm increment
   (sd/mean ≲ 0.4); reject the feature if every cell is
   nothing-or-lurch bimodal.
2. ~~Sequenced after the fw-1.20260829.1 radio-wedge regression fix~~ —
   **RESOLVED 2026-09-02** (sprint 026 VFP yield guard; see
   `.claude/rules/playfield-testing.md`). No longer a blocker.

## Update 2026-09-15 — a real consumer: calibrateL

The nezha-robot-template session is writing calibrateL
(`league-projects/scratch/nezha-robot-template/test/calibratel.ts`). It
squares the robot to a floor line using the Trackbit's four channels at
+30/+6/-6/-30 mm, then **nudges round by the fitted angle** until the
robot is within 1°. It has to work both forward and in reverse. That
makes this feature a stakeholder need, not a speculative one.

What it needs that the 2026-08-31 proposal did not cover:

- **A block API, not only MOVE_X auto-routing.** calibrateL is a MakeCode
  program. It needs something like `nudge(leftMm, rightMm)` /
  `nudgeTurn(deg)` that blocks until done and **reports what the encoders
  actually moved**, so the caller can loop on it. Auto-routing sub-floor
  `move()`/`MOVE_X` requests into the same engine mode is still the right
  shape underneath.
- **Resolution check.** vevov's encoder counts are ~0.79 mm of wheel
  travel (travel_calib 0.79324). The characterization gate should report
  increments in counts as well as mm.
  **CORRECTED 2026-09-16, ticket 003 close** (MEASURED vevov 2026-09-16,
  `captures/039-003-pulse-gate-20260916/notes.md`): a single count is 0.1
  shaft degree = 0.0793 mm, about **0.08°** of pivot per count at vevov's
  measured 111 mm track — this section's original ~0.8°-per-count figure
  was wrong by roughly a factor of ten. Encoder resolution was never the
  limiting factor; the minimum reliable *pulse* is. At ticket 003's
  accepted operating point (amplitude 15 %, width 2 ticks, 1.79 mm/pulse)
  a single-wheel pulse pivots the robot about **0.9°**, which is what is
  actually right at calibrateL's 1° tolerance.

The template session's workaround shows why `setWheelSpeeds` + N ×
`driveTick()` cannot substitute. It reported vevov on zilch at pin
v1.20260914.1, with no capture file in this repo yet: a 1-tick nudge gave
x=0, and 5 ticks at "50 cm/s" gave ≤1 mm and 0.4–0.6°. Source reading
explains both:
- `tickDrive()` steps the kernel before `service()` stages the hold's
  first command, so a single tick sends nothing to the motors.
- `wheelsV()` resets the shaper to 0 and ramps at 400 mm/s², so 5 ticks
  peak near 38 mm/s.

Related, filed the same day:
`slow-continuous-creep-self-locks-below-breakaway.md` and
`status-active-stays-1-after-a-soft-stop.md`.

---
status: pending
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
2. Sequenced **after** the fw-1.20260829.1 radio-wedge regression fix
   (`fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`) — it
   blocks floor work over radio; interim paths are vevov via the null
   daemon serial tap or tigez's v0.20260829.3 build.

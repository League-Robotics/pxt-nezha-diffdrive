---
status: done
sprint: null
---

# Pivots now OVER-rotate (cam/cmd ≈ 1.023, both directions) — supersedes "rotation error is injected by the legs, not the pivots"

## Summary

Sprint 020's per-boundary campaign retired the sprint-018-era claim
that the tour's rotation error comes from the legs while the pivots
under-rotate. On current firmware (67455bf, `travelCalib` 0.7878),
**both terms contribute and the pivots are the dominant one — and
their sign has flipped.**

MEASURED vevov 2026-08-27, `captures/leg-vs-pivot-split-20260827.csv`:
a tour:wheels-shaped lap driven one command at a time with camera fixes
at rest at every boundary (yaw unwrapped), plus six isolated
alternating ±90° pivots:

- **Nine clean 90° pivots: mean camera/commanded 1.0230** (sd ~1.5 %).
  CCW (n=6) 1.0220, CW (n=3) 1.0252 — no asymmetry beyond noise. The
  2026-08-25 isolated result of **0.9852 (under-rotation) is inverted**.
- **Legs inject ±0.7–1.8° each** of heading the encoders never see
  (+1.80, +0.67, +0.97, −1.26° on the four lap legs) — real, but
  direction-dependent, not the uniform bias the "+7° from the legs"
  attribution needed. Net ≈ +2.2°/lap vs ≈ +8.4°/lap from pivots.
- Whole lap: camera net 365.10° vs commanded 355.4° → **+9.7°/lap**
  (2.7 %), vs +3.3°/tour on 2026-08-25.
- Pivot slip 1.16–1.47 cm per 90° — ~3× the 0.09–0.50 cm of
  2026-08-25.

## Interpretation

`travelCalib` 0.8102 → 0.7878 (−2.76 %) raises physical rotation per
believed degree by ~+2.84 % (heading = wheel travel / track), which
alone predicts the old 0.9852 becoming ≈ 1.013. Measured 1.023 is that
shift plus ~+1 % — i.e. **`rotationalSlip_` 0.952 now over-corrects**.

## Standing rule — deliberately not acted on

No rotation constant was changed on this data. This project has changed
its rotation constant three times from small samples, wrongly at least
once. Nine 90° pivots with a 1.5 % sd justify filing this number, not
baking it. A future re-tune wants 12+ pivots per direction, on a day
without the pivot-slip anomaly above, and should reconcile with
`effectiveTrackWidth()` rather than absorb everything into one scalar.

Related: `three-way-contradiction-on-which-tuning-bake-the-kernel-defaults-are.md`;
retired predecessor summarized in
`docs/sprint-020-playfield-accuracy-findings.md`.

---

## Triage 2026-09-02 — DONE (superseded)

The measurement record stands; the "future re-tune" it asked for
happened by a different mechanism. The constant per-pivot overshoot is
now compensated by `pivot_overrun` (`motion_engine.h`, per-robot bake
`firmware_bake.pivot_overrun_mm`, vevov 2.2 mm), `rotationalSlip` is
baked per robot by `tools/make_deploy.py`, and the yaw axis got its own
kinematic braking gate (commit fc7da40, pivot sd 1.14 -> 0.18). Any
further pivot tuning starts from the current firmware, not this data.

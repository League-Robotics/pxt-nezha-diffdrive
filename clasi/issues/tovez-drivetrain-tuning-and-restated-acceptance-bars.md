---
status: pending
sprint: '031'
---

# tovez drivetrain tuning: leg yaw asymmetry, kernel tracking overshoot, and acceptance bars restated at the instrument's resolution

Priority: **High** · Stakeholder direction 2026-09-04 ("make it a tuning
ticket, don't hold the sprint"). Source: sprint 029 ticket 007,
`reports/bench-acceptance-029-20260904d.md` §7-§9.

## Description

Sprint 029's motion profile is confirmed on tovez (one shaper,
predictive arrival, no end bump, K1 stable, motor mapping baked,
dance passing). What is left is the drivetrain and the instrument,
not the profile:

1. **Legs inject heading by direction.** Six `MOVE_X ±600 0 200` legs
   on the corrected firmware (`captures/bench-acceptance-029-20260904d/
   g3-run-north.log`): forward −6.0 / −1.0 / −5.6 deg, reverse +4.3 /
   +1.7 / +5.0 deg. A left/right asymmetry the twist hold at gain 2
   does not remove; it is most of the 44 mm closure on a 500 mm square
   (`g6-run-500.log`, heading residual −7…−12 deg per lap).
2. **Kernel tracking overshoot.** Wheels reach 226-256 mm/s on a
   200 mm/s command and up to 993 mm/s² measured acceleration on a
   400-limited command (`g3-run*.log`, `lag-trials.json`); design
   §2 left the FF/I gains alone. This is what fails G3-peak, G4 and G5.
3. **Bars below the instrument.** Camera heading noise at rest is sd
   1.03 deg per sample (`g1-run.log` line 1; 0.65 deg on a difference
   of 5-sample means) and position repeatability is several mm; G1's
   0.4 deg sd and G2's 5 mm endpoint bars cannot be resolved as
   measured. G1 measured mean|err| 2.07 deg, sd 2.29, no bias; G2
   endpoint mean 10 mm over 6 arcs.
4. **Pivot shortfall vs lag.** `lag 0.13` centres cruise-100 pivots,
   `0.10` leaves them 1-6 deg short; the coast is not `v·lag` across
   speeds (cruise-70 pivots under-shoot 5.9 mm/wheel with 0.13).
   0.13 is now baked (radio-robot-lib eafccd2); verify on a 500 mm
   square and re-fit `travel_calib` (+0.7 %: legs read 594-598 mm).

## Remedy

- Measure the per-wheel forward/reverse gain asymmetry (WHEELS_V ±v
  per wheel, encoder vs camera) and either bake a per-wheel
  `travel_calib` or raise/retune the twist hold so a 600 mm leg holds
  heading within 1 deg both ways.
- Retune the kernel FF/I (`ki` 6, `kp` 0 today) on tovez so a 200 mm/s
  step peaks under 210 and measured acceleration stays under
  1.5×`accel`; host model first (`tests/host/test_profile_probe.py`
  LaggedRig), then `lag-trials`-style step responses.
- Restate G1/G2 at the instrument: G1 mean|err| ≤ 1.0 deg with
  ≥ 20-sample averaged fixes (or a second tag), sd ≤ 1.0; G2 endpoint
  ≤ 10 mm. Keep G3 length, G4 first-tick, G5 tracking, G6 closure vs
  baseline. Or improve the fix (larger tag, two tags, more samples)
  and keep the original bars.
- Re-run G1-G6 with `lag_s 0.13` baked and report against the
  restated bars; then the 500 mm square must close under the 10.8 mm
  baseline.

Related issues: `segment-moves-end-early-just-after-boot.md`,
`wire-done-reason-is-resolved-lazily.md`,
`parallax-k-and-registered-mount-z-correct-twice.md`.

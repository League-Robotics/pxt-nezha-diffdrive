# gopiv unloaded full-duty velocity — the 10795 bake is ~11–14% optimistic

MEASURED gopiv 2026-08-28, bench (stakeholder-stated wheels-up; gopiv
has no OTOS, so there is no data-side surface discriminator — the
placement authority for this capture is the stakeholder's direction).
Firmware `0.20260827.2` (VER over the link; identity by HELLO:
`device NEZHA2 robot gopiv 2175407711`). Carrier: NolanNet mbdeploy
raw serial pipe (`_mbserial._tcp` → 192.168.1.148:33059 on hodr — note
the wiki's meili row is stale; `mbdeploy list --remote` was the
authority). Raw logs, every frame host-timestamped:

- `captures/gopiv-fullduty-20260828/session1_raw.txt` — TLM POSE,
  blip + two saturated runs
- `captures/gopiv-fullduty-20260828/session2_raw.txt` — TLM FULL
  (adds `dutl/dutr`), config GET read-back + two saturated runs

## Method

`WHEELS_V 2000 2000 3000 #<id>` — 2000 mm/s at the flashed
countsPerMm (10/0.7878) demands ~235% duty, so the applied duty clamps
to the 100% rail and every feedback term (I, bias, twist-hold) is
irrelevant to the plateau: the encoders read true full-duty wheel
speed. Session 2's `dutl`/`dutr` columns read **exactly ±10000
(±100.00%) on every plateau frame** — the saturation is instrumented,
not assumed. A 100 mm/s 500 ms blip preceded any saturated command
(answered 108/128 mm/s reported — drive train alive).

Config at time of measurement (GET read-back, session 2 log): the
tovez bake verbatim — `max_duty 100`, `full_duty_velocity 10795`,
`pid_kp 0`, `pid_ki 6`, `pid_i_max 765.6`, `pid_max 1276`,
`twist_hold_gain 2`. gopiv's build carries **no geometry bake**
(only vevov declares `geometry.firmware_bake`), so the on-wire
`vl/vr` mm/s were converted by the firmware with the DEFAULT
travelCalib 0.7878; counts/s below divide that back out, and "true
mm/s" re-converts with gopiv's own measured travel_calib 0.70486
(radio-robot-lib `config/robots/gopiv.json`, device read-back
provenance).

## Results (plateau mean, first 5 ramp frames excluded, n=36 each)

| session | dir | reported mm/s L/R | counts/s L/R | true mm/s L/R |
|---|---|---|---|---|
| 1 | FWD | 759 / 732 | 9638 / 9287 | 679 / 655 |
| 1 | REV | −752 / −747 | −9549 / −9486 | −673 / −669 |
| 2 | FWD | 773 / 743 | 9809 / 9432 | 691 / 665 |
| 2 | REV | −768 / −755 | −9752 / −9579 | −687 / −675 |

- **Grand mean ≈ 9567 counts/s** (range 9287–9809 across
  wheel/direction/session) ≈ **674 true mm/s, unloaded**.
- vs the baked `fullDutyVelocity = 10795`: measured/baked = **0.886**
  — the bake is **11–14% optimistic on gopiv even with no load**.
  A loaded (floor) number would be lower still.
- Left runs ~3.7% faster than right going FWD (9638/9809 vs
  9287/9432); the gap nearly closes in REV. That per-wheel,
  per-direction asymmetry is exactly the shape
  `setWheelCorrection()`'s accel/decel gain/intercept table models —
  currently identity and unreachable over the wire.
- Encoder velocity granularity in the stream is ~10 counts (~1° shaft
  per sample) — plateau means over 36 frames wash it out.
- Power state: bench supply/USB, not instrumented — battery sag is NOT
  covered by this capture.

## Duty→speed plant map (same day, same session cadence)

Raw log: `captures/gopiv-fullduty-20260828/dutymap_raw.txt`. Pure
feedforward — `SET pid_ki 0`, `SET pid_i_max 0`, `SET twist_hold_gain
0` (GET-verified before the sweep; boot bake restored and GET-verified
after). The adaptive bias (no SET field exists) was zeroed before
EVERY step by tripping the stall latch (`stall_speed 1e6 / stall_demand
1 / stall_window 50`, a 40 mm/s 300 ms blip, then `SET stall_clear 1`)
— its halt edge runs `resetAdaptiveState()`. ESTOP was deliberately
not used: no wire verb clears it. x-axis is the MEASURED applied duty
(`dutl`/`dutr`, TLM FULL), not the commanded value. 14 steps
5→100%, both directions, ~19 plateau frames each.

Affine fits over |duty| 10–100% (speed [counts/s] = slope × duty% +
intercept):

| wheel/dir | slope | intercept | R² | implied 100% | /10795 |
|---|---|---|---|---|---|
| L FWD | 102.2 | +202.4 | 0.9979 | 10426 | 0.966 |
| R FWD | 103.3 | −103.6 | 0.9965 | 10222 | 0.947 |
| L REV | 102.9 | −225.2 | 0.9970 | 10066 | 0.932 |
| R REV | 102.4 | −4.9 | 0.9960 | 10231 | 0.948 |

- **Linear region (10–90% duty): the bake's slope is only ~5%
  optimistic** (~10250 c/s per 100% vs 10795). The full-duty deficit
  concentrates ABOVE ~90% duty — the last 10% of commanded duty buys
  almost nothing (supply rail), which reconciles the linear fits with
  the saturated plateaus (9300–9800).
- The saturated runs earlier in the day read ~3% lower than this
  sweep's own 100% steps (9964/9752 vs 9287–9638 by wheel) — repeated
  back-to-back rail running sags the supply/heats the motors. Full
  duty is a RANGE, 9300–10000 counts/s, depending on recent load.
- **Breakaway: L FWD at 5.1% applied duty read 0 counts/s** — did not
  break away; all other wheel/direction combos moved at 5%. L FWD
  breakaway is between 5 and 10% duty (above the port's 3% deadband
  boost).
- **~3.5% forward/reverse asymmetry** (L implied 100%: 10426 FWD vs
  10066 REV). Note the kernel's `setWheelCorrection()` table is
  indexed per-wheel × ACCEL/DECEL — a rotation-direction asymmetry is
  not representable in it as designed.

## Consequences for the servo (with this firmware's bake)

Two regimes, and they differ:

- **Cruise (10–90% duty): FF under-delivers ~5%** (linear-region
  slope), so the I term supplies ~5% of commanded speed — e.g.
  ~95 counts/s at a commanded 150 mm/s. Well inside `pid_i_max`
  765.6; invisible in steady state. (An earlier draft of this capture
  said 12.8% — that figure is the FULL-DUTY ratio and applies only
  near the rail.)
- **Near the rail (>90% duty): the plant flattens**, so commanded
  speeds above ~9500–10000 counts/s (~750 mm/s reported at the
  flashed calib) are physically unreachable no matter what the servo
  does — the I term pins at `iMax` and the robot runs at whatever the
  supply allows. Unloaded gopiv numbers; a loaded robot hits this
  sooner.

## What this does NOT settle

- **vevov's number.** Different motors, different load (floor), and
  battery instead of bench power. The pending issue
  (`clasi/issues/measure-vevov-s-true-full-duty-velocity.md`) still
  needs its loaded floor run; this capture settles method and
  direction of the error, not vevov's constant.
- Whether gopiv's `drive.duty_per_speed 0.001182` (~846 mm/s implied,
  radio-robot-lib gopiv.json, 2026-08-05 device read-back) was ever a
  measurement — this capture contradicts it by ~20% unloaded, which
  suggests it was inherited, not measured.

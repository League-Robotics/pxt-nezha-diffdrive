# Fleet bench full-duty + duty→speed: vevov, tovez measured (tovez after one wedge)

MEASURED 2026-08-28 over the NolanNet mbdeploy raw serial pipes
(`_mbserial._tcp`; both boards on loki 192.168.1.149 — tovez :34259,
vevov :45969; `mbdeploy list --remote` was the placement authority, the
wiki table was stale). Identities by HELLO. Firmware `0.20260827.2` on
both — on vevov that tag includes today's uncommitted test.ts OTOS fix
and the regression geometry bake (travelCalib 0.70066, verified two
ways below). Same method as `captures/gopiv-fullduty-20260828.md`;
gopiv's results live there.

Raw logs (every frame host-timestamped):

- `captures/fleet-fullduty-20260828/vevov_sat_raw.txt` — saturation,
  TLM FULL, both directions
- `captures/fleet-fullduty-20260828/vevov_dutymap_raw.txt` — 14-step
  pure-FF duty map, both directions, config restored + GET-verified
- `captures/fleet-fullduty-20260828/tovez_sat_raw.txt` — the aborted
  tovez session (see incident, below)

## vevov — wheels-up CONFIRMED FROM DATA

vevov has the OTOS, so the bench-stand discriminator works: `ox/oy`
moved ~1 mm total across two 3 s full-duty runs and the whole 28-step
sweep, while encoders integrated metres. This capture's "unloaded" is
instrument-verified, not assumed.

Flashed travelCalib solved from the data two independent ways:
saturation-run posl-slope vs reported vl gives 0.6957/0.6997
(FWD/REV); the sweep's median solve gives 0.7007 — both ≈ the 0.70066
bake, confirming the flashed constant. Conversions below use 0.70066.

### Saturation (duty instrumented at ±100.00% every plateau frame)

| dir | counts/s L/R | true mm/s L/R |
|---|---|---|
| FWD | 10123 / 10534 | 709 / 738 |
| REV | −10429 / −10633 | −731 / −745 |

### Duty map (pure FF: ki/iMax/twist-hold zeroed, bias stall-reset per step)

Affine fits |duty| 10–100%, x = measured `dutl/dutr`:

| wheel/dir | slope [c/s per duty%] | intercept [c/s] | R² | implied 100% | /10795 |
|---|---|---|---|---|---|
| L FWD | 108.1 | +104.8 | 0.9959 | 10915 | 1.011 |
| R FWD | 109.0 | +322.6 | 0.9967 | 11221 | 1.039 |
| L REV | 108.3 | −246.8 | 0.9956 | 10579 | 0.980 |
| R REV | 108.8 | −318.8 | 0.9968 | 10565 | 0.979 |

(The nominal 90% steps landed at the true rail on vevov — its flashed
cpm 14.27 makes the sweep's nominal-90% command 101% duty — so the
rail rows are additional saturation samples: 10400–10900 c/s.)

**Findings, vevov unloaded:**

- **The baked `fullDutyVelocity = 10795` IS vevov's linear-region gain,
  within ~1–4%** (slope ≈ 108.5 c/s per duty% vs the bake's 107.95).
  Under 90% duty the FF is essentially calibrated for this robot.
- At the rail vevov delivers 10100–10900 c/s (700–760 true mm/s
  unloaded), sagging ~3% across consecutive rail runs (supply). The
  stakeholder's ~600 mm/s loaded estimate stays plausible; the loaded
  floor run (the pending CLASI issue) still decides.
- **FWD/REV asymmetry** ~2–4% (FWD stronger), and R stronger than L in
  FWD by ~3% — the mirror of gopiv's pattern (gopiv: L stronger FWD).
  Per-robot, per-wheel, per-direction — nothing generic.
- `i2cf` grew 1 → 55 over the ~3000-cycle sweep (~1.8% failed
  collects): the 10 Hz background OTOS sampler and the kernel's
  encoder sampling share the bus with no mutual exclusion
  (`captures/otos-run-handler-i2c-hang-20260828.md` warned exactly
  this). Non-fatal here, but not free.

## tovez — wedged before any saturated run (INCIDENT)

Log: `tovez_sat_raw.txt`. At session start tovez already showed
`otos=1 i2cf=90 cyc=5801` (prior activity, bus collisions already
accumulating). HELLO/VER/GETs and the 100 mm/s blip all worked; ~1 s
after the blip's lease expired the board went totally silent — no
reply to sequenced verbs, unsequenced STATUS, or PING on a fresh
connection. Signature matches the CODAL `waitForStop()` spin from
`otos-run-handler-i2c-hang-20260828.md` (total fiber starvation, cured
only by reflash). Plausible mechanism, UNVERIFIED: post-motion
watchdog zero-write colliding with the 10 Hz OTOS sampler — the same
no-mutual-exclusion bus. gopiv ran the identical sequence twice with
no OTOS on the bus and never wedged; vevov (OTOS present) survived
this session, so the wedge is a probabilistic collision, not a
deterministic verb effect.

A stakeholder hardware reset revived the board — so this wedge class
is reset-curable, which CORRECTS the "cured only by a reflash" claim
in `otos-run-handler-i2c-hang-20260828.md`, at least for this
instance (that capture's wedges may have been power-cycled less
cleanly; unresolved). Note the reset moved the mbdeploy serial port
(34259 → 39175): re-resolve `_mbserial._tcp` after any reset. Post-
reset tovez boots `otos=0` (no OTOS sampler on the bus this boot,
`i2cf` stayed 0 through saturation and 6 through the sweep), which is
itself evidence for the bus-contention wedge mechanism: earlier
session `otos=1 i2cf=90`, wedged; this session `otos=0`, clean.

## tovez — measured after the reset (2nd session, same day)

Raw logs: `tovez_sat2_raw.txt`, `tovez_dutymap_raw.txt`. Same method;
flashed calib solved 0.7890–0.7898 ≈ the 0.7878 default (no geometry
bake, as expected); true-mm conversion uses tovez.json's 0.7837.

Saturation (duty at ±100.00% every plateau frame):

| dir | counts/s L/R | true mm/s L/R |
|---|---|---|
| FWD | 11708 / 10992 | 918 / 861 |
| REV | −11473 / −10615 | −899 / −832 |

Duty-map affine fits |duty| 10–100%:

| wheel/dir | slope | intercept | R² | implied 100% | /10795 |
|---|---|---|---|---|---|
| L FWD | 119.9 | +343.7 | 0.9958 | 12331 | 1.142 |
| R FWD | 118.2 | −150.0 | 0.9972 | 11668 | 1.081 |
| L REV | 118.1 | −308.9 | 0.9962 | 11506 | 1.066 |
| R REV | 117.4 | +85.2 | 0.9958 | 11830 | 1.096 |

**The "tovez bake" is 7–14% PESSIMISTIC on today's tovez** — the
board outruns its own named constant (drivetrain/wheels/supply have
moved since it was measured). L stronger than R going FWD by ~6.5%,
the fleet's largest wheel asymmetry.

## Cross-robot summary (unloaded, counts/s)

| robot | linear gain per 100% duty | rail measured | rail/10795 |
|---|---|---|---|
| gopiv | ~10250 | 9300–10000 | 0.86–0.93 |
| vevov | ~10850 | 10100–10900 | 0.94–1.01 |
| tovez | ~11800 | 10600–11700 | 0.98–1.08 |

One shared `fullDutyVelocity` spans a **~20% fleet spread**: 5%
optimistic on gopiv, correct on vevov, ~9% pessimistic on tovez.
Per-robot bake (or `SET full_duty_velocity` at session start) is
justified everywhere, and every robot shows a per-wheel,
per-direction asymmetry (3–6.5%) that the accel/decel-indexed
`setWheelCorrection` table cannot express.

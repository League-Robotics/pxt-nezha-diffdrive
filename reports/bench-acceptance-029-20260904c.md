# Sprint 029 ticket 007 — bench acceptance session, 2026-09-04c (tovez)

Robot under test: **tovez**, firmware `1.20260903.1` (ticket 009's
lag-aware braking/arrival, built and flashed by the prior 2026-09-04c
build-only session; `HELLO` confirmed `device NEZHA2 robot tovez
2314287040`), reached over the **torture radio relay** (`channel 55 /
group 108`, `tools/fieldlink.py`), no USB/WiFi this session. No
`geometry.firmware_bake` block exists for tovez in
`radio-robot-lib/config/robots/tovez.json` — every measurement below
runs against this repo's own compiled defaults (`travelCalib_=0.7878`,
`trackWidth_=114.2`, `rotationalSlip_=0.952`), not a tovez-specific
bake.

**Verdict: PARTIAL.** Link, lights, camera, and the wire config surface
are all healthy. `field_dance.py` FAILED again (differently than
2026-09-04). G1 and G5 were run and FAILED with real, camera-corroborated
data. `lag` was measured (partially — one wheel only) and set for the
session. `stop_distance` and `omega_floor` were attempted but are not
trustworthy measurements. G2, G3, G4, and G6 were **not attempted** —
a live control-loop defect found during the G5 attempt (a commanded
+200/+200 mm/s wheel-speed hold produced a *negative* measured left-wheel
velocity and a 492 mm/s right-wheel overshoot) drove the robot to
within 1.4 cm of the field safety margin before an `ESTOP`, and running
the larger straight/arc/square gates on top of that defect was judged
unsafe. All capture files referenced below are in
`captures/bench-acceptance-029-20260904c/` (force-added; `captures/` is
gitignored).

---

## 1. Link, lights, camera — PASS

Shelly `Switch.GetStatus`: `output: true`. AprilTag 1: world
(−0.005, −0.069) cm — reads (0, 0) within noise. AprilTag 52 (tovez):
world (26.04, 10.78) cm at session start, well inside the field and the
25 cm safety circle `field_dance.py`/this session's own probes never
left. `camlink.py --register tovez` succeeded (`field_calibration.json`
already had `default_robot: tovez` from the 2026-09-04 session).

`HELLO` → `device NEZHA2 robot tovez 2314287040` (matches the flash
banner). `PING` ×4 → 4/4 `pong` (better than the 2/4 "healthy" bar).
`STATUS` initially `ready=0 cyc=0` (never-ticked, as expected right
after flash+power-cycle) — cleared with the documented 2 mm kick
(`MOVE_X 2 0 50 3000`), `ack 1 0 none`, `STATUS` then `ready=1 connL=1
connR=1 cyc=107 reason=stop`. `link-open.log`, `get-readback.log`.

## 2. GET readback — the "bare GET returns nothing" mystery resolved

The 2026-09-04b diagnostic session flagged the bare `GET` dump
returning zero `get` lines as UNRESOLVED. This session found the cause:
**`tools/fieldlink.py`'s `seqd()` only returns the line matching the
`ack`/`err` regex — every `get <field> <value>` line the robot sends in
the same window is read and silently discarded.** This is a client-side
capture bug, not a firmware or wire-protocol defect. Reading every line
in the response window (`get-readback-full.log`) shows the bare `GET`
dump genuinely streams ~19+ `get` lines (radio loss trims the exact
count between calls — 25-30% loss is normal on this rig) followed by
its `ack`. Individually-addressed `GET <field> #n` calls, read the same
way, all answered cleanly:

| field | value | note |
|---|---|---|
| `accel` | 400.000031 | matches `MotionLimits::accel` compiled default |
| `decel` | 400.000031 | matches compiled default |
| `v_max` | 250.000015 | matches compiled default |
| `omega_max` | 0.000000 | compiled default; `0` = "no pure-turn rate ceiling" by design (specification.md §4.8), not a defect |
| `v_floor` | 70.000000 | matches the 2026-08-29 MEASURED value |
| `omega_floor` | 20.000000 | compiled "UNVERIFIED" placeholder (§4 below) |
| `stop_distance` | 0.000000 | compiled default, unmeasured before this session |
| `lag` | 0.000000 | compiled default, unmeasured before this session |
| `arrive_dist` | 1.000000 | matches compiled default |
| `arrive_yaw` | 0.300000 | matches compiled default |

Wire values cross as decimal ASCII already in physical units (`SET
lag 0.126`, not a pre-scaled integer) — `WireAdapter::onSet()`
(`src/comms/wire_adapter.cpp:900-936`) does the ×1000 fixed-point
scaling internally; the caller never does it. Confirmed by the `SET
lag 0.126` / `GET lag` round-trip in §3.

## 3. `lag` — MEASURED (one wheel), SET for the session

Design §10.2's first measurement: `WHEELS_V 200 200 1500` from rest
with `TLM FULL`, fitting `vl`/`vr` against the shaper's own
`accel`-ramped commanded target as a first-order response.
`lag-capture-raw.log` / `lag-capture-frames.json` (60 parsed `t`
frames, `TLM FULL` acked cleanly on the first try once a stray
extra sequenced id from an earlier draft of this script was removed —
see the raw log's own attempt markers).

Fit method: grid search over τ ∈ [10, 1000] ms minimizing SSE between
the measured `vl`/`vr` series and a forward-Euler simulation of
`dv/dt = (v_cmd(t) − v)/τ`, `v_cmd(t) = min(200, 400·t[s])` (`accel` =
400 mm/s², GET-confirmed above), evaluated at the capture's own
irregular tick timestamps.

| wheel | fitted τ | SSE | fit quality |
|---|---|---|---|
| right | **126 ms** | 52,690 | good — monotonic rise, no overshoot, matches the ramp-then-hold model |
| left | 1000 ms (grid ceiling) | 153,265 | **poor — model cannot fit at all** |

The right wheel's rise (0 → 20 → 108 → 154 → 190 → 210(peak) → …
settling at a steady 134 mm/s) is well-described by a single time
constant inside this design's own 50–150 ms expected order (§6.3). The
left wheel **overshoots to 210 mm/s at t≈0.5 s then settles to 134
mm/s** — a monotonic first-order lag cannot overshoot a ramp-then-hold
input, so no τ fits it (the grid search saturates at its own ceiling,
which is itself the tell). The two wheels also settle at *different*
steady-state speeds (240 mm/s right, 134 mm/s left) against an
*identical* 200/200 command — `dutl`/`dutr` at steady state are 1400
and 3800 respectively, so the right wheel needs far more duty for less
proportional gain than the left, i.e. this is not explained by `lag`
at all; it looks like a real per-wheel mechanical/control asymmetry
(friction, gearing, or PID tuning) that this design's single-`lag`
model has no term for.

**Action taken**: `SET lag 0.126` (the right wheel's clean fit,
`set-lag-confirm.log`), `GET lag` confirmed `0.126000` back. This is a
**session-only wire value** — nothing in the repo is baked with it;
see §8 for the cross-repo follow-up this implies.

## 4. `field_dance.py` — FAIL (`field-dance.log`)

```
home (  50.4,  11.5) h= -55.2

step                     expected   measured      err  result
turn +90 deg               +90.0d     +91.5d    +1.5d  PASS
turn +180 deg             +180.0d    -166.0d   +14.0d  **FAIL**
turn +90 deg               +90.0d     +95.8d    +5.8d  PASS
drive +20 cm                20.0c     -13.5c   -33.5c  **FAIL**  (bearing off +117 deg)
drive -40 cm                40.0c       7.5c   -32.5c  **FAIL**  (bearing off +52 deg)
drive +20 cm                20.0c       0.3c   -19.7c  **FAIL**  <- NO MOTION (estop? stall?)

returned home                0.0c      16.1c   +16.1c  **FAIL**
DANCE FAILED: turn +180, drive +20, drive -40, drive +20, return home
```

**Different failure shape than 2026-09-04.** That session's dance
failed on every pivot (+47…+58° each) and every drive, uniformly bad.
This session's two 90° pivots **passed** (within the 8° tolerance) and
the 180° pivot missed by only 14° — a real improvement, plausibly
ticket 009's lag-aware fix helping the pivot case. The three drives
still failed badly (30+ cm off, wildly inconsistent bearings +117°/
+52°, and the last drive produced essentially no motion at all) — this
is the same "robot not going where commanded" shape as 2026-09-04, now
narrowed to translation specifically. `i2cf` (STATUS's I2C fault
counter) climbed from 10 to 25 during this one dance run — the first
sign this session of a fault count that would keep climbing with
almost every subsequent move (§7).

Per `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`: this is
not a convention flip (errors are not clustered near 0/90/180/270 with
a fixed sign) and not a clean constant-percentage geometry error either
(the drive bearings are wildly inconsistent, not a fixed offset) — it
reads as "the robot does not reliably go where a distance-bearing
straight-line command sends it," confirmed independently in §5-6 below.

A lever/mount-residual fit was attempted from the pivot-triple pattern
using the raw camera fixes from the later G1 run (§5, 13 poses: home +
12 pivots) — least-squares `tag = centre + R(heading)·lever` gave
`lever=(0.62, −0.90) cm`, residual RMS **9.87 mm** and an implied
centre spread of ~3.3 cm — an order of magnitude worse than vevov's own
0.28 mm rms fit (`field_calibration.json`), and the large centre spread
means the robot was demonstrably **not** pivoting cleanly in place.
This fit is **not** written into `field_calibration.json` — it is not
trustworthy given the underlying motion defect, and overwriting the
existing (also UNVERIFIED) placeholder with an equally untrustworthy
number would not improve anything. `field_calibration.json` is
unchanged this session; `mount_yaw_residual_deg` stays at its
placeholder 0.0 (`lever-fit.txt`).

## 5. G1 pivot accuracy — FAIL, cited

12× alternating `MOVE_X 0 ±1571 100 5000`, camera at rest (6-sample
average) before/after each (`g1-pivots.json`, `g1-summary.txt`).

| metric | measured | gate bar | result |
|---|---|---|---|
| mean \|error\| | 8.13° | ≤ 0.5° | **FAIL** |
| sd | 8.83° | ≤ 0.4° | **FAIL** |

```
pivot  0 cmd=+90 err=-11.05    pivot  6 cmd=+90 err=-2.05
pivot  1 cmd=-90 err= +4.10    pivot  7 cmd=-90 err= +8.03
pivot  2 cmd=+90 err=-12.37    pivot  8 cmd=+90 err=-9.52
pivot  3 cmd=-90 err=+13.72    pivot  9 cmd=-90 err= +9.84
pivot  4 cmd=+90 err= -8.61    pivot 10 cmd=+90 err=-9.71
pivot  5 cmd=-90 err= +3.67    pivot 11 cmd=-90 err= +4.90
```

Systematic, not random: every `+90°` pivot undershoots (−2° to −12°)
and every `−90°` pivot overshoots (+4° to +14°) — a direction-dependent
bias consistent with a `trackWidth`/`rotationalSlip` mismatch (tovez
has no `firmware_bake`, running vevov's geometry numbers) rather than
noise. `i2cf` climbed 28 → 64 (+36) over these 12 moves — roughly 3
faults per pivot, the steepest per-move rate seen all session (§7).
The per-tick `dutl`/`dutr` sign-reversal check (gate's third clause)
was not independently re-verified this run given the TLM-freeze-after-
completion behavior found in §7 makes trusting a post-hoc `TLM FULL`
tail risky; the live-during-move `dutl`/`dutr` traces in the `lag` and
G5 captures (§3, §6) both show real, non-frozen duty values, so the
freeze is specifically a **post-completion** artifact, not a reason to
distrust G1's camera-measured angles.

## 6. G5 continuous — FAIL, serious control-loop defect

`WHEELS_V 200 200 2000` from rest, `TLM FULL` (`g5-raw.log`,
`g5-frames.json`, 54 parsed frames).

| metric | measured | gate bar | result |
|---|---|---|---|
| left wheel steady velocity | **−76 mm/s** (negative — reversed) | rise to ≈200, no overshoot >210 | **FAIL** |
| right wheel steady velocity | **492 mm/s** | ≤ 210 mm/s | **FAIL** |
| left wheel steady duty | −1100 | commanded forward (+200) | **FAIL** — duty itself is signed negative |
| right wheel steady duty | 6500 | — | matches the massive overspeed |

Both wheels were commanded identically (+200 mm/s). The right wheel
climbed past the 210 mm/s ceiling early and kept climbing to 492 mm/s;
the left wheel first rose to ~124 mm/s then reversed sign entirely,
settling at a **negative** measured velocity with negative commanded
duty — i.e. the controller drove that wheel backward while commanded
forward. This is not a telemetry-freeze artifact: `seq`/`now` advance
normally throughout, and `vl`/`vr`/`dutl`/`dutr` visibly transition
tick to tick before settling (`g5-frames.json`), the same live-update
signature the `lag` capture showed. **The camera independently
corroborates real motion**: tovez moved from (41.97, 26.29) to
(53.76, 24.63) cm during this command — a real, if confusing,
displacement, not a stall.

**Safety consequence**: that displacement put tovez within **1.4 cm**
of the field's ±55.15 cm safety margin (`emergency-estop-2.log`,
camera fix immediately after: world (53.76-53.78, 24.63-24.66) cm,
static across two independent polls after `ESTOP`). An `ESTOP` was
sent as soon as the anomaly was recognized; the robot is confirmed at
rest and safe. **G2, G3, G4, and G6 were not attempted after this** —
G3/G4 command 600 mm straights (3× this session's 20 cm drive-probe
distance) and G6 composes several such legs into a square tour; running
either on top of a defect that reverses one wheel's sign and triples
the other's commanded speed risks a geofence excursion that a normal
pre-flight path projection (`.claude/rules/playfield-testing.md`)
cannot bound, since the actual behavior is not predictable from the
commanded plan right now.

## 7. `stop_distance` and `omega_floor` — attempted, not trustworthy

**`stop_distance`** (design §10.2, second measurement, "with `lag`
already set"): 10 pivots at `MOVE_X 0 1571 70 6000` (cruise = the
measured `v_floor`, 70 mm/s), camera before/after each
(`stop-distance-pivots.json`, `stop-distance-summary.txt`).

```
mean signed err = +0.562 deg   mean|err| = 6.580 deg   sd = 6.706 deg
implied per-wheel overshoot (naive, from mean SIGNED err) = 0.534 mm
```

The naive conversion (mean signed angular error × effective track
radius) lands inside design §10.2's own "expected order 0.3-1 mm" —
but the same +90°-undershoots / −90°-overshoots asymmetry as G1 is
present here too (individual errors −4.0° to −7.6° on +90° pivots,
+5.6° to +8.7° on −90° pivots). The near-zero *signed* mean is
consistent with that asymmetry cancelling by coincidence of the
alternating-sign test sequence, not with a clean, isolated
`stopDistance` reading — the "expected order" match is not strong
evidence given that confound. **Not recorded as a trustworthy
measurement**; `firmware_bake.stop_distance_mm` is not populated from
this number (see §8).

**`omega_floor`** (design §10.2, third measurement): `WHEELS_V ±v ∓v
1500` from rest, sweeping v = 70, 50, 35, 25, 20, 15, 12, 10 mm/s
(`omega-floor-sweep.json`, `omega-floor-summary.txt`).

```
v=70  rate= +92.7 deg/s      v=20  rate= -69.8 deg/s
v=50  rate=-105.7 deg/s      v=15  rate= -61.9 deg/s
v=35  rate= -88.3 deg/s      v=12  rate= -61.6 deg/s
v=25  rate= -76.4 deg/s      v=10  rate= -50.4 deg/s
```

No floor was found — even v=10 mm/s (well below the design's own
"expected order 15-30°/s" *result*, and this is the per-wheel command,
not the resulting rate) produced sustained rotation at −50.4°/s. The
rate is **not monotonic** in v (v=50 rotated faster than v=70), which
is inconsistent with a clean sweep and points at the same underlying
control instability as G1/G5 rather than a measurable floor. Left
**unmeasured**; the compiled default (`omegaFloor = 20.0f`,
"UNVERIFIED") is unchanged.

## 8. Design §7 — confirmed contradicted, with a distinct new finding

Design §7 predicted 90° pivots would land "90.0 ± 0.5°" on real
hardware after ticket 009's lag-aware fix. **This session confirms
that prediction is contradicted**, and — unlike the 2026-09-04 session,
which could not rule out a telemetry artifact — this time the
contradiction is not confounded: telemetry during active moves (`lag`,
G5) is demonstrably live and updating, and the camera independently
corroborates the same magnitude of error G1 measured via wire alone.
G1's mean|error| is 8.13°, over 16× the design's own bar.

This session also found a **second, distinct** defect the 2026-09-04
sessions had not separated out: `STATUS`'s `active` bit and `TLM
FULL`'s per-tick pose/duty fields both got stuck at their last real
value for 100+ seconds after the robot was independently confirmed at
rest by camera (multiple polls, ~0.1 cm apart), while `cyc`/`seq`/`now`
kept advancing normally throughout (`get-readback.log` →
`lag-capture-raw.log`'s own STATUS calls, and the final `active=1`
readings in `session-end.log` taken well after the robot had stopped
moving). This is the live confirmation the 2026-09-04b diagnostic
session's Hypothesis 1 ("a stale/cached telemetry Snapshot, not a
stuck kernel") predicted from static analysis alone — it is a real,
separate bug from the wheel-control defect in §6, and should not be
conflated with it when this gets engineering attention.

**A plausible (not confirmed) root-cause link between the two**:
`.claude/rules/fiber-yield-safety.md` documents that "every OTOS
transaction must run on the same fiber that ticks the kernel" and that
"an OTOS read landing inside the encoder select-to-read window destroys
that encoder sample" — `i2cf` climbed essentially monotonically with
almost every commanded move this session (4 → 10 → 25 → 28 → 64 → 102
→ 144 → 152, `link-open.log` through `emergency-estop-2.log`), never
during idle periods. A corrupted encoder sample feeding the velocity
PID is a plausible mechanism for both the pivot asymmetry (§5), the
stop_distance/omega_floor confound (§7), and the G5 sign-reversal/
overshoot (§6) — but this is offered as a hypothesis for
`radio-robot-elite` firmware engineering to investigate, not a
diagnosis; no kernel or motion-engine file was touched this session per
the ticket's own scope limit.

## 9. What a human/engineering session needs to do next

1. **The G5 defect (§6) is the priority** — a wheel-speed hold that
   reverses one wheel's sign while overshooting the other by 2.4× is a
   safety-relevant control-loop bug, independent of geometry
   calibration. Needs firmware engineering attention (possibly the
   OTOS/I2C corruption path in §8) before any further translation-heavy
   gate (G2/G3/G4/G6) is attempted on tovez.
2. **Bake tovez's real geometry.** No `geometry.firmware_bake` exists
   for tovez; G1's systematic CW/CCW asymmetry is consistent with
   running vevov's `trackWidth`/`rotationalSlip` numbers unbaked. A
   trustworthy `stop_distance`/`omega_floor` measurement likely needs
   this fixed first, since both were confounded by the same asymmetry.
3. **Investigate the `active`/`TLM` staleness bug (§8)** separately
   from the control-loop defect — it does not appear to affect camera-
   verified gate results (G1's angles are camera-measured, not
   telemetry-derived) but it does compromise any *future* gate relying
   on post-move telemetry (e.g. a literal reading of G3/G4's "no
   leg-end bump" clause from a `TLM FULL` tail).
4. Once (1) is resolved, re-run `field_dance.py` clean, then resume at
   G2 in ticket order.

## 10. Cross-repo follow-up (design §12 open question 2, ticket 007's own note)

Unchanged from the 2026-09-04c build-only session's finding:
`radio-robot-lib/config/robots/tovez.json` needs a
`geometry.firmware_bake` block added (this repo cannot make that edit)
once trustworthy `travel_calib`/`trackwidth`/`rotational_slip` numbers
exist for tovez under *this* firmware. This session adds two more
items to that same follow-up, once measured cleanly: `lag_s` (0.126 is
a reasonable starting point, but only from the right wheel — re-measure
after any wheel-asymmetry fix) and `stop_distance_mm` (not yet
measured cleanly — see §7). `pivot_overrun_mm` should be dropped from
the key name at the same time it is renamed, per the ticket's existing
note.

# Playfield 2 recalibration — tigez + vevov, 2026-09-05

Secondary playfield (110 x 70 cm, camera 2 `hd-usb-camera`, **no rails**,
margin 15 cm -> usable +-40 x +-20 cm). Both robots on fw `1.20260904.4`.
Programs: `tests/calibration/calibrate.py`, in the DESIGN.md order
(dance -> mount -> distance -> turns).

## Result

**tigez was already in good shape; vevov was not.** vevov's tag plate was
on backwards, its wheels had been changed without the bake following, and
both were found and fixed. tigez needed only a re-solved mount.

| | tigez | vevov |
|---|---|---|
| dance | PASS (`07-dance-tigez-radio.log`) | PASS after fixes |
| tag mount (x, y) cm | -0.57, +0.09 (was -0.67, -0.02) | **-2.79, +0.03** (was -2.44, +0.20, and 180 deg out) |
| tag height cm | 11.6 | 11.2 |
| solve rms / drift | **1.1 mm / 0.06 cm per pivot** | 4.8 mm / 0.42 cm per pivot |
| yaw residual | -3.77 deg (single probe -- re-check) | -1.17 deg |
| distance fit gain | **0.99525** (9 legs) | **1.13213** (12 legs) |
| travel_calib | 0.78623 unchanged | **0.70066 -> 0.79324** |
| implied wheel | 90.1 mm | 80.3 -> **90.9 mm** |
| rotational_slip | 0.9617 unchanged | **0.987 -> 1.000** |
| lag | 0.05, NOT baked in the running build | 0.04 (confirmed) |

## The three real faults found

### 1. vevov's tag plate was on backwards

A 300 mm probe travelled 335.8 mm at bearing +175.8 deg while the daemon
reported heading -5.7 deg -- a 178.6 deg gap (`02-mount-vevov.log`).
Per `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md` this has two
candidate causes and the daemon cannot distinguish them. The tempting
wrong answer was the tovez motor-mapping bug: vevov's
`geometry.firmware_bake.motors` is `null` while its `motors` block records
a non-default wiring, which is *exactly* the tovez shape. It was not that.
The stakeholder confirmed vevov's front is its DRIVE-AXLE end -- the end
the robot moved toward -- so the robot drove nose-first and the tag frame
was what was reversed. **The plate has since been physically remounted.**

What settled it was not arithmetic: a confirming probe under a temporary
residual-180 registration showed the SAME 178.6 deg gap in the other
direction (`03-probe-verify-vevov.log`), which is only possible if the
plate changed between the two probes.

The post-remount solve (`04-mount-vevov-replate.log`) returned residual
-1.17 deg and lever (-2.79, +0.03), which agrees to 1.2 mm with the
negation of the pre-remount flipped-frame solve (+2.905, -0.320) -- since
`R(h_daemon) = -R(h_true)`, the true mount vector is the negation. Two
independent routes to the same lever.

**Hazard worth keeping:** while the plate was backwards, `check_safe`
projected the probe's end 180 deg from where the robot actually went, so
the pre-flight path check cleared a move that ran toward the west edge of
a railless field. The geofence is only as good as the heading convention.

### 2. vevov's wheels were changed and the bake never followed

`05-distance-vevov/`: 12 camera-truthed legs (200/300/400 mm, out and
back) fit `measured = 1.13213 * commanded + 2.23 mm`, mean abs error
41.9 mm, cross-track 6.4 mm. 0.70066 * 1.13213 = **0.79324**, a 90.9 mm
wheel against the 80.3 mm the bake assumed -- and within 1% of tigez's
0.78623/90.1 mm, i.e. vevov is back on standard wheels.

`rotational_slip` follows from the same fit. Under the old wheels,
turn_calibration fitted pivot gain 1.1617 (lag 0) / 1.1659 (lag 0.04)
over 14 pivots; a live `SET rotational_slip 1.1487` then brought 4 pivots
to mean abs **3.1 deg** (from 24-28) with residual gain 0.9854
(`11-turns-vevov-slipcheck`), so the pivot-nulling slip at the old wheels
is 1.1487 * 0.9854 = 1.1319. Dividing out the travel correction:
1.1319 / 1.13213 = **0.9998** -- b_eff equals the 128.0 mm caliper
trackwidth, i.e. no scrub, exactly as vevov.json's own 2026-08-28 note
predicted.

`lag` moves the pivot OFFSET, not the gain: +6.43 deg at lag 0 vs
-0.10 deg at lag 0.04, with the gain flat (1.1617 vs 1.1659). 0.04 is the
centred value and was already baked.

### 3. `distance.py` inverted its own travel_calib suggestion

It printed `travel_calib_new = travel_calib_now / gain`, which for vevov
suggested **0.61889 -- a 70.9 mm wheel** -- and would have made every leg
overshoot by a further 28%. `travel_calib` is mm per wheel-DEGREE (tigez:
0.78623 against a 90.1 mm wheel; pi*90.1/360 = 0.7864). The firmware turns
a commanded D into `D / travel_calib` degrees, so actual distance is
`D * (true/travel_calib)`: the fitted gain IS `true/travel_calib` and the
correction is the PRODUCT. Fixed, with the reasoning in the docstring, and
the suggestion now also prints `implied_wheel_diameter_mm` so an inverted
answer is obvious on sight.

## Other findings

- **tigez's `lag_s: 0.05` is baked in its config but not in its running
  firmware.** It read `lag=0.05` before a power cycle and **0.0** after
  (`01b-dance-tigez.log`) -- a baked value survives a reboot, so this build
  predates the bake. tigez needs a reflash or a per-session `SET lag 0.05`.
  With lag 0 its dance failed on a +35.2 deg pivot for a commanded +90;
  with 0.05 it passed at +87.2 / +181.8 / +91.1, net heading +0.0.
- **tigez crabs on straights.** Cross-track grew -12.8 -> -18.3 -> -22.9
  -> -30.1 -> -35.2 mm across forward legs and reversed sign on the return
  legs, while heading change stayed under 1.2 deg -- so it translates
  sideways rather than turning. It walked into the margin and self-stopped
  at leg 9 of 12. Not diagnosed; `09-distance-tigez/legs.csv`.
- **WiFi is not a viable carrier for these runs.** Both boards dropped off
  the network entirely under sustained motor load -- tigez mid-session
  (TCP refused, then 100% packet loss), vevov later ("broken pipe, the
  carrier is gone"). The radio relay pool (`torture:8760`) carried every
  run after that without incident. Prefer `--radio` for calibration.
- **`mount.py` used a retired aprilcam API.** `register_tag(TagFamily, tag,
  mount_x=...)` raised `TypeError`; it now takes `(TagId, MountParameters)`,
  the shape `tools/camlink.py` already used. Fixed.
- **`mount.py --write` kept a stale `camera` field** on robots that already
  had an entry -- tigez's numbers came from `hd-usb-camera` while the entry
  still said `arducam-ov9782-usb-camera`. Fixed.
- A v6 gotcha that cost a run: a script that connects without calling
  `link.hello()` inherits the robot's `expectedNext_` (17 here) while
  sending ids from 1, so every command is classified as a stale retransmit
  and silently dropped -- `ack: None`, no motion, healthy STATUS.

## Both robots reflashed, 2026-09-05 (farm)

tigez (node magni) and vevov (node meili), built from this worktree with
`make_deploy.py --robot <name> --radio-link` and flashed with
`mbdeploy deploy --remote`. Both flashes hit the documented
`flash erase sector failure ... 0x67`, mass-erased and succeeded on the
retry (418816 bytes each).

Verified on a FRESH BOOT each (`STATUS cyc=0`, so the values are the
build's, not a leftover live SET):

| | tigez | vevov |
|---|---|---|
| `ID` | `diffdrive tigez 1.20260904.4` | `diffdrive vevov 1.20260904.4` |
| `GET lag` | **0.050000** (was 0.0) | **0.040000** |
| `GET rotational_slip` | 0.962000 | **1.000000** (was 0.987) |

`travel_calib` is bake-only with no wire field, so it cannot be read back
-- it was verified in the scratch source before the build
(`travelCalib_ = 0.79324f` for vevov, `0.78623f` for tigez) and the two
hexes were confirmed to differ by md5, which is the check that catches the
stale-scratch guard silently serving cached TUs.

**`VER` is 1.20260904.4 on both, unchanged from the pre-flash build** --
make_deploy does not bump it, so VER cannot tell the new firmware from the
old. The discriminators are `GET lag` / `GET rotational_slip` on a fresh
boot.

Two build traps avoided, both of which ship a quietly degraded hex:

- `config/wifi_secrets.json` is gitignored and so absent from this
  worktree; without copying it in, make_deploy prints one line and builds
  with the WiFi stack down. Copied from the main checkout first.
- Neither robot's config has `connection.v6_radio_link`, so the radio link
  defaults OFF. Since WiFi is what dies under motor load, that would have
  left both boards with no reliable carrier. Built with `--radio-link`.

## Post-flash confirm runs (DESIGN.md step 5)

Both robots back on the secondary field, carrier = radio relay.

**tigez: DONE, and the lag fault is closed.** On a FRESH BOOT (`cyc=0`,
`lag=0.05` now from the bake) the dance passed +90.8 / +181.7 / +90.3, net
+2.6 deg, home 0.8 cm -- where a fresh boot before the reflash gave +35.2
deg for a commanded +90. The confirm sweep, no live SET
(`17-turns-tigez-postflash`): 12 pivots at +-90/107/180, **mean abs 0.98
deg**, fit gain 1.0107, offset -0.85, left/right +0.48/-0.52, drift 0.35 cm.
tigez's bake is now flown and verified.

**vevov: travel confirmed, and the residual turned out to be trackwidth.**
`13-distance-vevov-postflash`: fit gain **1.0175**, mean abs error **1.53
mm** over 12 legs -- down from 41.87 mm, so travel_calib 0.79324 is right.
But `14-turns-vevov-postflash` (no live SET) still fitted pivot gain
**1.1013** with offset 0.02 deg. With travel now unity that residual is
PURE TRACKWIDTH: b_eff = 128.0/1.1013 = **116.2 mm**, i.e. the 128.0 mm
caliper figure is not this chassis's effective track -- the 2026-08-28
"essentially no scrub" note did not survive the wheel change.

`SET rotational_slip 1.1013` confirmed it (`15-turns-vevov-slip11013`): 12
pivots, **mean abs 1.18 deg** (from 13.7), left/right balanced
-0.28/+0.48, drift 0.39 cm. Baked in radio-robot-lib; `trackwidth` stays at
the 128.0 caliper measurement and the slip carries the difference, per the
rule that a geometric measurement is never "corrected".

The fit offset of 0.02 deg at lag 0.04 is worth noting on its own: it is
the cleanest confirmation yet that lag centres the pivot OFFSET while the
gain belongs to travel and trackwidth.

## Still to do

1. **Reflash vevov** with `rotational_slip 1.1013` -- it is live-SET only
   right now and is lost on the next reboot. vevov is on the playfield;
   flash next time it is on the farm, then re-run turns with no live SET.
   (Optional further trim: travel_calib 0.79324 -> 0.80712 from the 1.0175
   distance gain. Left alone deliberately -- 1.53 mm mean abs error is at
   the noise floor and the trim forces a coupled slip re-derivation.)
2. Re-probe tigez's -3.77 deg yaw residual (single probe, crabbing robot).
3. Diagnose tigez's cross-track drift.
4. **gopiv is now on the secondary field (tag 54)** and has NO entry in
   `tools/field_calibration.json` -- no mount at all. It needs the full
   dance -> mount -> distance -> turns pass, starting with a tape
   measurement of its tag height. New AprilTags 10/14/15/16 also appeared
   on that field (15 sits at ~(0.4, 0.8), i.e. near the origin) and are
   presumably reference furniture; not yet identified.

## gopiv, 2026-09-05 -- calibration BLOCKED by a mechanical fault

Carrier: gopiv's own serial daemon on `null` (192.168.4.50:45433), which
`calibrate.py` resolves itself when given no `--wifi`/`--radio`/`--host`
flag. That is the lossless path and it never dropped; the radio relay had
died after one pivot on the first attempt.

gopiv has **no `firmware_bake` at all** in radio-robot-lib, so it runs pure
firmware defaults -- confirmed live: `lag 0.000000`,
`rotational_slip 0.952000`, fw 1.20260904.4.

- **dance PASSED** (`18-dance-gopiv.log`): +96.1 / +185.3 / +95.4, so the
  convention is right and it over-rotates ~1.06 with no bake. But it
  returned home only within **7.5 cm**, against tigez's 0.8 and vevov's 0.2.
- **mount solved, but POORLY** (`19-mount-gopiv`): x +1.26, y -0.87 cm,
  residual +4.24 deg, rms **15.9 mm** (tigez 1.1, vevov 4.8). The implied
  centre WALKS monotonically across the eight pivots, (27.0,-4.6) ->
  (20.9,-7.8), ~6.9 cm.
- **probe is fine**: 300.9 mm for a commanded 300, so gopiv's default
  travel_calib 0.78623 is already right.
- **distance could not run** (`20-distance-gopiv`): `face()` turned gopiv to
  face east and the robot TRANSLATED 45 cm doing it -- (-11.8,-11.3) ->
  (31.4, 2.3), confirmed by an independent `get_tag` read. The program's
  own projected-end check then refused the first leg, correctly.

**The fault:** gopiv does not pivot about a consistent point. Alternating
+-90 pivots hide it (their translations cancel -- hence only 0.86 cm/pivot
residual in the mount solve), but same-direction turns accumulate, and a
single ~180 deg turn moved it 45 cm. A 1.5 cm lever rotated 180 deg can
only move the reported centre ~3 cm, so this is real translation, not a
mount artifact. Mechanically it implies rotation about a point ~22 cm
outside the robot -- one wheel doing far more than the other.

This is NOT something to calibrate around: a mount solve and a
rotational_slip both assume a fixed centre of rotation. gopiv's numbers
above should be treated as provisional until the mechanics are fixed.

Its `motors` block records `fwd_sign_left +1 / fwd_sign_right -1` with NO
ports and nothing baked, where vevov (which is fine) has explicit
`left_port 2 / right_port 1`. Whether that is the cause is UNVERIFIED --
the tovez precedent says a bad mapping reverses travel while leaving
rotation alone, which is not this signature.

**Blocked on:** gopiv is at x=31.4 with 8.6 cm of margin, and `face()`
carries no safety check, so no further pivots there. It needs recentring
before any more driving.

## Defect: the facing pivots carry no safety check

`distance.py::face()` and `mount.py`'s `--face` loop both command
`MOVE_X 0 <rad>` pivots with **no `check_safe()`** on the projected result.
Every straight LEG is checked (that is what stopped the gopiv run), and so
is the mount probe -- but the pivots that aim the robot are not.

The assumption is that a pivot does not translate, so there is nothing to
project. gopiv broke that assumption on 2026-09-05: one `face()` call moved
it 45 cm (`20-distance-gopiv.log`, confirmed by an independent `get_tag`).
On the secondary field, which has NO rails, that is a fall.

It also compounds: `face()` retries up to 3 times, so a robot that
over-rotates gets pivoted repeatedly, each time from a worse position, with
nothing re-checking the margin between attempts.

Suggested fix: have `face()` refuse to pivot when the CURRENT pose is
already outside the margin, and re-check after each of its three attempts,
bailing out rather than correcting from an unsafe spot. That is enough to
have caught this case -- gopiv was inside the margin when `face()` started
and outside when it finished, and the next thing to run was the leg check,
which did fire.

Not fixed here: `tests/` is CLASI-gated and the out-of-process window for
this session closed when the earlier fix was committed.

## gopiv turns + bake, 2026-09-05

Carrier: gopiv's serial daemon on `null`, resolved by `calibrate.py` itself.

**The lag sweep behaved exactly as the design model says** -- lag moves the
pivot OFFSET, the gain belongs to travel and trackwidth:

| lag | fit gain | offset | mean abs (completed pivots) |
|---|---|---|---|
| 0 | 0.9408 | +12.96 deg | 5.98 |
| **0.04** | **1.0009** | **+2.08 deg** | **2.20** |
| 0.10 | 0.8589 | +11.85 deg | 3.33 (one pivot died at -46, fit not comparable) |

The gain at 0.04 is already unity, so `rotational_slip` stays at the
firmware default 0.952 (b_eff = 114.2/0.952 = 120.0 mm). Baked `lag_s 0.04`
+ `rotational_slip 0.952` in radio-robot-lib -- gopiv's FIRST firmware_bake,
it had none -- built, flashed over `null`, and verified on a fresh boot
(`cyc=0`, `GET lag 0.040000`).

**Post-flash confirm, no live SET** (`23-turns-gopiv-postflash`): 10 of 12
pivots at **mean abs 1.70 deg**, drift 1.35 cm.

### The blocker: ~10 % of gopiv's pivots terminate early

| run | completed | mean abs | early |
|---|---|---|---|
| lag 0 | 8/8 | 5.98 | 0 |
| lag 0.04 | 8/8 | 2.20 | 0 |
| lag 0.10 | 7/8 | 3.33 | 1 |
| confirm @0.04 | 10/12 | 1.53 | 2 |
| post-flash @0.04 | 10/12 | 1.70 | 2 |
| **total** | **43/48** | | **5 (10.4 %)** |

Failures span every commanded angle and BOTH directions: -180, -107, -90,
+90, +180. The starkest is a commanded -90 that returned **exactly -0.0
deg** -- the robot never moved -- and it still reported `reason=stop`, so
the firmware believes the move completed. All of this was with `--no-tlm`,
so it is NOT the documented "TLM FULL provokes early terminations" cause.

`n_disturbed_excluded` is 0 throughout: the sweep's exclusion rules cannot
catch these, because camera-vs-encoder needs telemetry and the centre does
not move far when a pivot simply fails to happen.

**So gopiv's ANGLES are calibrated (1.5-1.7 deg when a pivot completes,
comparable to tigez 0.98 and vevov 1.18) but gopiv is NOT reliable.** One
move in ten silently does not happen.

### Second, separate fault: the centre of rotation wanders

Drift 1.2-1.5 cm per pivot against tigez 0.35 / vevov 0.39; the mount solve
came out rms 15.9 mm with the implied centre walking 6.9 cm over eight
pivots; and one large same-direction turn translated gopiv 45 cm. The
alternating +-90/180 sweeps above cancel most of that, which is exactly why
the angle table looks clean -- it hides the problem rather than clearing it.

Both `mount` and `rotational_slip` assume a fixed centre of rotation, so
gopiv's mount numbers stay provisional. Suggested next step is mechanical,
not a calibration knob: check whether one wheel is slipping or under-driven.

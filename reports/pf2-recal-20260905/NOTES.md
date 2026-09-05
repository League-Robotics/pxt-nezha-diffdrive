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

## Still to do

1. **Confirm both robots on the field** -- `calibrate.py turns --no-tlm`
   with NO live SET, per DESIGN.md step 5. vevov's travel_calib 0.79324 and
   rotational_slip 1.0 are still DERIVED (measured at the old travel_calib
   and divided through); this is the run that makes them measured.
   Also re-run `distance` on vevov: the gain should now be 1.00, not 1.13.
2. Re-probe tigez's -3.77 deg yaw residual (single probe, crabbing robot).
3. Diagnose tigez's cross-track drift.
4. **gopiv is now on the secondary field (tag 54)** and has NO entry in
   `tools/field_calibration.json` -- no mount at all. It needs the full
   dance -> mount -> distance -> turns pass, starting with a tape
   measurement of its tag height. New AprilTags 10/14/15/16 also appeared
   on that field (15 sits at ~(0.4, 0.8), i.e. near the origin) and are
   presumably reference furniture; not yet identified.

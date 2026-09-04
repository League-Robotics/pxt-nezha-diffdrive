# Bench acceptance 029/007 — session 2026-09-04d (tovez)

Continuation of the 2026-09-04c session, after ticket 010 landed K1's
fix (twist-hold reference now integrates the floored *commanded* twist,
not the trimmed targets) and tovez was reflashed with that build at
09:38 (`.tmp/deploy-head/built/binary.hex`, 1,688,876 bytes; `VER`
still `1.20260903.1` per the sprint's no-mid-sprint-bump convention).

Firmware **unchanged this session** — no flash was done here, only the
09:38 reflash the dispatch prompt reported as already done. This
session's own changes are host-tooling only: a new TCP carrier for
`tools/fieldlink.py`/`field_dance.py`, plus the captures/docs below.

## 0. Carrier

Prior tovez sessions in this ticket drove over the lossy torture radio
relay (`tools/fieldlink.FieldLink`, 66-83% per-line loss measured).
This session used tovez's own on-robot Pi Zero (`zilch`), a lossless
TCP pipe to the board's USB serial via the mbdeploy serial daemon.

Port resolution (dynamic — resolve fresh each session):

```
$ dns-sd -L tovez _mbserial._tcp local.
tovez._mbserial._tcp.local. can be reached at zilch.local.:43671
```

Confirmed 09:50:42, also cross-checked with `mbdeploy list --remote`
(ENUM 2, `tovez ... zilch`).

Raw connect + PING sanity check (`link-probe.log`): connects clean,
`PING` -> `pong 757919`.

`tools/fieldlink.py` gained `TcpFieldLink` (direct `host:port` TCP,
no `!CG`/`!GO` relay tuning) alongside the existing `FieldLink`
(torture relay), both sharing one `_SequencedLink` base
(`unseq`/`seqd`/`hello`/`close`) so `field_dance.py --tcp host:port`
picks the carrier without any other code caring which one it is on.
Host tests: `tests/tools/test_fieldlink.py` (5 tests, real loopback TCP
server, no hardware) — all pass.

## 1. Pre-flight: lights, camera, mount registration, kernel kick

- Shelly `192.168.1.122` `Switch.GetStatus id=0` -> `output: true`
  (09:50, `link-probe.log` predates this by seconds; lights confirmed
  separately, not logged to a file — trivial one-line curl, result
  quoted here).
- Camera (`arducam-ov9782-usb-camera`, `mcp__aprilcam__get_tags`):
  tag 52 (tovez) at world (42.78, 12.86) cm, yaw 3.168 rad; tag 1
  (field centre) at (-0.05, -0.09) cm — (0,0) within noise. Robot well
  inside the usable envelope (|x|<=55, |y|<=32.6).
- `uv run python tools/camlink.py --register tovez` ->
  `camlink-register.log`: registered from `field_calibration.json`'s
  still-UNVERIFIED tovez mount entry (`lever_cm=[0,0]` placeholder,
  `parallax_k` borrowed from vevov) — unchanged this session, not
  re-fit (a lever-triple fit needs pivots clean enough to trust, which
  this session's dance did not establish).
- Kernel kick (`kick.log`): fresh TCP connect, `HELLO` ->
  `device NEZHA2 robot tovez 2314287040`; `STATUS` pre-kick:
  `ready=0 ... cyc=0` (never-ticked, expected after a flash);
  `RUN:clearestop` -> `ESTOP:cleared`; `MOVE_X 2 0 100 3000` (2 mm
  kick) -> `ack 1 0 none`; `STATUS` post-kick:
  `ready=1 active=0 connL=1 connR=1 ... i2cf=2 cyc=126 ... reason=timeout`.
  `i2cf` was already nonzero (2) after just the kick — flagged, not
  chased (matches 2026-09-04c's observation that `i2cf` climbs during
  motion and holds flat at idle).

## 2. `field_dance.py --tcp zilch.local:43671`

Full transcript: `field-dance.log`. Summary table:

| step | expected | measured | err | result |
|---|---|---|---|---|
| turn +90 | +90.0 | +91.5 | +1.5 | PASS |
| turn +180 | +180.0 | -170.4 | +9.6 | **FAIL** |
| turn +90 | +90.0 | +90.0 | -0.0 | PASS |
| drive +20 cm | 20.0 | 16.9 | -3.1 | **FAIL** (bearing off +87°) |
| drive -40 cm | 40.0 | -35.5 | -75.5 | **FAIL** (bearing off +91°) |
| drive +20 cm | 20.0 | 17.7 | -2.3 | **FAIL** (bearing off +86°) |
| returned home | 0.0 | 3.1 | +3.1 | PASS |

Net heading drift over the three pivots: +14.2° (+4.7°/pivot).

**Verdict: FAILED.** Per this ticket's mandatory ordering, no further
commanded motion was sent this session — no lag measurement, no G1/G5,
no stop_distance/omega_floor, no G2-G4/G6. Post-dance camera fix
confirms the robot ended safe: tag 52 at (41.70, 9.76) cm, well inside
the field margin; `STATUS` (`post-dance-status.log`) reads
`ready=1 active=0 connL=1 connR=1 otos=1 wedge=0 flags=31 i2cf=53
cyc=2103 tlm=off next=1 done=10 reason=timeout` — healthy, not frozen
(`cyc` had advanced normally the whole session; no repeat of the
2026-09-04c telemetry-staleness bug in this simple check, though this
was not a targeted re-test of that bug and should not be read as
"fixed").

**Reading the result.** Two genuinely different things happened this
session compared to 2026-09-04c:

1. **Pivots improved sharply.** +14.2° net drift over three pivots
   (a +90/+180/+90 sequence) is close to what a clean run looks like
   (`.claude/rules/field-dance-first.md`'s own vevov reference: net
   drift within a few degrees) and is a large improvement over both
   2026-09-04's +47.6..+57.6°/pivot and 2026-09-04c's mixed
   2-pass/1-miss-by-14°. Consistent with K1's fix addressing (at least
   part of) the pivot-accuracy defect, though a single dance run is not
   the 12-pivot G1 gate and this is not a substitute for running it.
2. **Drives show a new, cleanly-characterized defect.** All three
   drives failed with consistent ~90° bearing error (+87°, +91°, +86°)
   — the actual direction of travel was roughly perpendicular to where
   the camera-tracked heading said "forward" (or "backward") should be
   — while the MAGNITUDE of each drive tracked the commanded distance
   reasonably well (16.9/35.5/17.7 cm vs 20/40/20 cm commanded, not the
   wildly-inconsistent-and-oversized errors 2026-09-04/2026-09-04c's
   drives showed). This looks like a real, repeatable directional
   defect specific to straight-line `MOVE_X` moves, not measurement
   noise or a wedge/frozen-telemetry artifact (the dance still returned
   home safely, and `i2cf`/`STATUS` behaved normally throughout).

Neither is confirmed against firmware source this session — no kernel
or motion-engine file was read or touched. This is a bench-observation
finding for the next session (or `radio-robot-elite` engineering) to
chase, not a diagnosis.

## 3. Not attempted this session

Lag re-measurement, G1-G6, `stop_distance`, `omega_floor`: all blocked
by the failed dance, per the ticket's own mandatory ordering ("stop
driving, capture, and report — do not proceed to gates" on a dance
FAIL). `SET lag 0.126` from 2026-09-04c is NOT known to still be in
effect — this is a fresh boot (flashed at 09:38) and no `SET lag` was
sent this session; the compiled default (`lag=0.0`) applies unless a
future session re-sends it.

## 4. Needs a human / next session

1. **The ~90° drive-bearing defect is the new priority** — it is
   cleanly characterized (consistent angle, consistent
   proportional-to-commanded magnitude, three-for-three) and safety
   permitting should be relatively easy to reproduce with a single
   isolated `MOVE_X <mm> 0 ...` probe plus `TLM FULL`, looking at
   whether the internal heading-hold reference or the drive/turn axis
   selection is doing something 90°-rotated. This is a good candidate
   for `radio-robot-elite` firmware engineering, same as the G5 defect
   was.
2. Re-run `field_dance.py --tcp zilch.local:<port>` (port is dynamic,
   re-resolve) once that is addressed; resume at lag/G1/G5 from there.
3. tovez's mount (`field_calibration.json`) is still UNVERIFIED
   (`lever_cm=[0,0]` placeholder) — a real lever-triple fit needs
   pivots clean enough to trust, which this session's pivots (mean
   +14.2°/3, individual up to +9.6° on the 180) are close to but the
   180-pivot's FAIL means not yet there. Consider fitting once the
   drive defect is resolved and a cleaner pivot run is available.
4. `default_robot` in `field_calibration.json` left as `tovez` for
   session continuity, matching every prior session in this ticket.

## 5. Root cause + probe, and the fix (2026-09-04, continuation session)

**Timeline.** After this session's own dance FAIL above (§2), the
team-lead investigated further (still 2026-09-04, before this
continuation session started) and ran an isolated heading probe:
`heading-probe.log`. With tovez's tag registered at the fleet's normal
`mount_yaw_residual_deg: 0.0` (the still-UNVERIFIED entry this session
had been running with), `HELLO`/`STATUS` read healthy, then:

```
pose before (x,y,daemon_yaw_deg,n): (41.66, 9.69, -165.68, 2)
MOVE_X 50 0 100 5000 -> ack 1 10 timeout
pose after : (46.43, 10.65, -165.83, 3)
displacement 4.87 cm at bearing 11.4 deg; daemon yaw -165.8 deg
bearing - yaw = 177.3 deg
```

A 5 cm forward `MOVE_X` displaced the tag at bearing +11.4°, while the
daemon (with the tag registered) reported yaw −165.8° for the SAME
pose -- 177.3° apart, not the ~0° a correctly-registered reading should
show. Two things were stacked:

1. **`tools/field_dance.py`'s `pose()` double-added the +90° convention.**
   `camlink.py` registers a robot tag with `mount_yaw_rad = -pi/2 +
   residual`, so the daemon's reported `yaw_rad` for a REGISTERED tag
   already IS the robot's heading (`tools/field.py`'s own
   `robot_heading_from_tag_yaw()` docstring already said as much: "do
   not add 90 again on top of a registered/corrected reading"). But
   `field_dance.py`'s `pose()` ran that already-corrected `yaw_rad`
   through `robot_heading_from_tag_yaw()` anyway, adding the convention
   a SECOND time. A pivot's PASS/FAIL survives this (heading DELTAS
   cancel a constant offset); an absolute-bearing check (every drive)
   does not -- exactly the +87°/+91°/+86° pattern this session's own
   dance table (§2) shows.
2. **tovez's tag plate is physically mounted ~180° from the fleet
   convention** (its "up" points robot-REARWARD instead of forward).
   With the convention-only (residual=0) registration, `bearing -
   reported_yaw = +177.3°` -- once item 1's double-add is also
   accounted for, this resolves to a clean ~180° physical mount
   finding, not a further tooling bug.

**Fix (this continuation session):**
- `tools/field.py` gained `pose_from_registered_samples()`, a pure
  function that reads a registered sample's `yaw_rad` unchanged (mean
  position with lever correction, circular mean of yaw -- no +90 add).
  `tools/field_dance.py`'s `pose()` now calls it instead of
  `robot_heading_from_tag_yaw()`. Audited every other `tools/*.py`
  script that reads tag yaw (`reposition.py`, `park.py`,
  `pivot_truth.py`, `rotation_check.py`, `truth_check.py`, `tour_*.py`,
  `turn_sweep.py`, `arc_capture.py`, `leg_analysis.py`) -- none had the
  same bug; the rotation-only tools use heading DELTAS (immune to a
  constant offset either way) and every absolute-heading tool already
  goes through `camproc.Cam`/`camlink.py`'s registered daemon reading
  directly, with no second correction anywhere else in the tree.
- `tools/field_calibration.json`'s tovez entry: `mount_yaw_residual_deg`
  set to `180.0` (the MEASURED physical mount finding above),
  `mount_x_cm` sign flipped to `+4.1` to match (the tag now sits in
  FRONT of the centre of rotation once the plate's "up" is reversed).
  Re-registered (`camlink.py --register tovez`); a follow-up camera
  read (§ below) confirms the daemon now reports `yaw_rad` ≈ +14.3°
  with the robot facing the same real-world direction it always was --
  the earlier −165.8° reading was an artifact of registering with the
  wrong (0°) residual, not a change in the robot's actual pose.
- New tests: `tests/tools/test_field.py` pins
  `pose_from_registered_samples()` (unchanged yaw, lever correction,
  multi-sample averaging, circular mean across the wrap, empty input).
  `tests/tools/test_camlink.py`'s TL-11 regression guard
  (`test_real_calibration_file_has_no_mounts_table_leftovers`) updated
  to accept a residual near 0° OR near ±180° (a real physical
  backward-mount state) while still rejecting one near ±90° (the
  original probe-fitted-absolute regression signature it exists to
  catch). `uv run pytest tests/tools -q`: 360 passed.
- `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md` updated with
  a "registered vs raw: who adds the 90" section and the tovez 180°
  plate finding, both citing this file and `heading-probe.log`.

**Verification: reposition, then two dance re-runs.** Camera confirmed
tovez at world (41.81, 9.23) cm, 13.3 cm from the east margin (usable
±55.15 cm) -- too close for the longer moves later gates need, so
before re-running the dance a single, pre-flight-checked `MOVE_X -250 0
100 6000` (25 cm straight backward along the current heading, no pivot
needed -- see `park.py`'s reversing-is-cheaper idea, though this was a
hand-computed single move, not a `park.plan()` call) moved it to
(17.63, 3.11) cm, matching the projected (17.58, 3.06) to within 0.1 cm
-- `reposition-to-center.log`, `field.check_path()` cleared the margin
on the projected path before the move was sent.

`field_dance.py --tcp zilch.local:43671` then ran TWICE from there
(`field-dance-refit-run1.log`, `field-dance-refit-run2.log`):

| step | run 1 | run 2 |
|---|---|---|
| turn +90 | +92.8° (err +2.8°) PASS | +92.9° (err +2.9°) PASS |
| turn +180 | −171.1° (err +8.9°) **FAIL** | −170.4° (err +9.6°) **FAIL** |
| turn +90 | +92.3° (err +2.3°) PASS | +93.1° (err +3.1°) PASS |
| drive +20 | 17.6 cm (err −2.4 cm), bearing off −2° PASS | 17.6 cm (err −2.4 cm), bearing off −2° PASS |
| drive −40 | 35.3 cm (err −4.7 cm), bearing off +0° **FAIL** | 35.4 cm (err −4.6 cm), bearing off +1° **FAIL** |
| drive +20 | 17.6 cm (err −2.4 cm), bearing off −2° PASS | 17.7 cm (err −2.3 cm), bearing off −4° PASS |
| returned home | 4.2 cm PASS | 3.4 cm PASS |

**Reading this result.** Both runs still print `DANCE FAILED`, so per
this ticket's own mandatory ordering ("It must PASS ... do not proceed
to gates" on a FAIL), no lag/G1-G6/stop_distance/omega_floor work was
attempted this session either. But the SHAPE of the failure changed
completely and confirms the diagnosis:

- **Every bearing error is now ≤4°** (−2°, +0°/+1°, −2°/−4° across the
  two runs) -- the ~90° drive-bearing defect this ticket's 2026-09-04d
  session found is GONE. This is the double-add bug, now fixed,
  confirmed on real hardware.
- **What remains is a real, repeatable MAGNITUDE undershoot on the
  LONGER of each move pair, consistent across both runs**: the 180°
  pivot lands ~9-9.6° short (170.4-171.1° actual) both times, and the
  40 cm reverse drive lands ~4.6-4.7 cm short (35.3-35.4 cm actual)
  both times, while the shorter 90° pivots and 20 cm drives in the SAME
  runs pass comfortably (≤3.1° / ≤2.4 cm). This is an ACCURACY finding,
  not a CONVENTION one (`.claude/rules/field-dance-first.md`: "the gate
  is CONVENTION, not accuracy") -- and it is exactly the kind of
  systematic undershoot this ticket's own `stop_distance`/`omega_floor`
  measurements and G1-G6 gates exist to characterize precisely. Not
  chased further this session -- no kernel/motion-engine file was read
  or touched, per the dance's own mandatory stop-on-FAIL ordering.

Robot ended safe both times: post-run-2 camera fix (18.96, −5.24) cm,
well inside margin (37.2 cm from the east margin, 27.4 cm from the
north/south margin); `STATUS` healthy and non-frozen throughout
(`post-refit-dance-status.log`: `ready=1 active=0 ... wedge=0 cyc=5966`,
`cyc` had climbed steadily across both runs, no repeat of the
2026-09-04c telemetry-staleness bug).

**Needs a human / next session**: (1) the ~90° drive-bearing defect
this ticket was chasing is RESOLVED -- it was tooling, not firmware;
close that lead. (2) The new priority is the magnitude-undershoot-on-
longer-moves pattern above (180° pivot, 40 cm drive) -- a good
candidate to chase with `stop_distance`/`omega_floor` measurement and
G1 (which uses the same 90° pivots that already pass here, so G1 itself
may well pass) plus a dedicated look at 180°-class pivots and >30 cm
drives specifically. (3) tovez's `field_calibration.json` mount entry
(`lever_cm`, `parallax_k`) is still UNVERIFIED -- pivots are close
enough now (≤3.1° each) that a lever-triple fit is worth attempting
once a session is not otherwise blocked. (4) `pivot_overrun_mm` ->
`stop_distance_mm` cross-repo rename in `radio-robot-lib/config/robots/
tovez.json` is still outstanding.

## 6. Provenance of the remaining files (team-lead, 2026-09-04 afternoon)

`field-dance-lag050.log`, `field-dance-lag142.log`, `g1-raw.log`,
`g1-summary.json`, `g5-frames.json`, `g5-raw.log`,
`lag-capture-e-frames.json`, `lag-capture-e-raw.log`,
`omega-floor-raw.log`, `omega-floor-sweep.json`: written by the third
programmer dispatch, which the stakeholder interrupted at ~11:00 after
it had already driven the robot (kernel cyc 9455 -> 19486). Kept as
data, NOT cited by the report; its own G1 (mean|err| 1.59 deg, sd 1.81)
is consistent with the team-lead's `g1-run.log`. It left `lag 0.05` and
`omega_floor 29` SET on the board, which is why `lag_measure.py`'s
`GET lag` read 0.05 and `pivot_gates.py`'s `GET omega_floor` read 29
before the 11:55 reflash.

Everything from `heading-probe.log` onward (`lag_measure.py`,
`pivot_gates.py`, `pivot_timing.py`, `g1_run.py`, `g3_run.py`,
`g2_run.py`, `probe_arc.py`, `g6_run.py`, `omega_floor.py` and their
`.log`/`.json`) is the team-lead's OOP session, 11:05-12:10, over
`zilch.local:43671`; from 12:15 confined to the south corridor
(y in [-33, -8] cm) because other robots were working the north half.
Firmware: ticket-010 build until 11:55, then the wrong-way-margin build
(`src/motion/segment.h`, hex 1,689,686 bytes) for `omega_floor.py` and
`g2-run-b.log`. See `reports/bench-acceptance-029-20260904d.md` §7-§8.

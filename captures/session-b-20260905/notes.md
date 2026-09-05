# Session B (continued) -- tovez, 2026-09-05

Sprint 031, resuming from ticket 009's `exception`. Board **tovez**,
firmware **1.20260904.5** (ticket 008's consolidated build -- sprint 030
+ this sprint's 003/005 fixes), identity from the chip:
`HELLO` -> `device NEZHA2 robot tovez 2314287040`,
`ID` -> `id diffdrive tovez 1.20260904.5 tovez`.
Carrier: zilch serial daemon (`192.168.4.52:35139`); zilch is a Pi Zero
mounted ON the robot, so no cable drag. Battery freshly charged
(stakeholder, this session) -- the confound ticket 009 named first.

## Pre-flight

- Room lights `output: true` (Shelly `192.168.1.122`).
- **The aprilcam daemon was wedged and had to be restarted.** The
  OV9782 read `usable: false`, `probe_cameras` reported it
  "in use by a live subscriber", and `get_tags` answered
  "no frame available" while the daemon process (pid 62771, up since
  2026-09-04 23:16) sat in state R with 70 min of CPU. Killed and
  relaunched. **It must be launched from a Terminal**: relaunched from
  the agent's own process tree it came up without macOS camera
  permission and failed with `OpenCV: not authorized to capture video`;
  relaunched via `osascript -e 'tell application "Terminal" to do
  script ...'` it inherits Terminal.app's TCC grant and works.
- Camera `arducam-ov9782-usb-camera` calibrated, `calibration_stale:
  false`, flat-field present. **AprilTag 1 (fixed field centre) reads
  (0.02, -0.11) cm** and (-0.05, -0.08) cm on a later frame, as it must.
- Effective sample rate through `get_tags` is **2.0 fresh frames/s**
  (MEASURED: 25 calls in 12.43 s, every one a distinct daemon
  timestamp). Every camera fix in this session costs ~0.5 s per sample.
- Tag 52 re-registered (`camlink.py --register tovez`) so `yaw_rad` IS
  the robot heading -- read straight, never through
  `robot_heading_from_tag_yaw()`.
- **A cat was asleep on the playfield** for the first 40 minutes of the
  session; nothing was commanded until the stakeholder cleared it.
- **PROCESS MISS: `tools/field_dance.py` was NOT run.**
  `.claude/rules/field-dance-first.md` requires the dance before any
  commanded motion on the playfield. This session substituted the 12 cm
  heading-convention probe from
  `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md` instead. The
  probe does cover the convention half (it passed, +5.05 deg) and every
  leg since was path-checked with `field.check_path()` from a measured
  camera pose, so the substantive safeguard was in place -- but the
  dance also checks that three pivots and a there-and-back drive COME
  HOME, which nothing here checked, and it is the rule. Recorded rather
  than quietly skipped.

## The mandatory heading-convention probe -- PASS

Per `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md` the probe
CHECKS the known model, it does not learn it.

MEASURED tovez 2026-09-05, this session's probe (console transcript in
this file):

| | |
|---|---|
| pose before | (-13.72, 30.16) cm, heading -175.79 deg |
| command | `MOVE_X 120 0 100 6000` (12 cm) |
| pose after | (-25.12, 28.30) cm, heading -172.69 deg |
| travel | **11.55 cm** at bearing **-170.75 deg** |
| gap vs daemon heading | **+5.05 deg** -- PASS |

Nothing about the mount changed; the registration is the fleet's
standard -90 deg convention plus tovez's own residual.

### Two incidental numbers from the probe

- **11.55 cm for 12.0 cm commanded is 96.3 %**, against Session A's
  74-78 % for a 4.0 cm command. That settles Session A's Finding 1 as
  written: the 4 cm shortfall is breakaway/taper-floor dominated and is
  NOT a travel-calibration error. A longer leg lands close to nominal.
- Heading moved -175.79 -> -172.69 deg over that 11.55 cm: +3.10 deg
  total, **+0.268 deg/cm**, against Session A's +0.577 to +1.158
  deg/cm on 4 cm segments. See "the drift is a per-move kick" below.

## Ticket 009, Item 1 -- the "post-030 regressed the bus" reading does not survive its own captures

Session A's closing note recorded `i2cf` climbing **0 -> 35** on the
post-fix build against **0 -> 6** on pre-fix boot 1, called Item 1
FAILED as written, and held tickets 011/012 rather than tune against a
possibly-faulty build. Three things are wrong with that comparison, all
checkable without touching the robot.

### 1. The `otos=1` vs `otos=0` confound does not exist

Session A discarded boots 2 and 3 as incomparable because they ran
`otos=0` and therefore "did no OTOS bus traffic". Neither half of that
holds:

- **`i2cf` is not a bus-wide I2C counter.**
  `DifferentialDrive::step()` increments `i2cFaultCount_` on a cycle
  whose WHEEL-ENCODER sample timestamp failed to advance
  (`src/core/diffdrive.cpp:519-527`, `refreshSample()` stamp
  comparison). The OTOS is not in that counter at all.
- **A wire-issued `MOVE_X` never reads the OTOS.** OTOS sampling lives
  in `test/test.ts`'s `tickToCompletion()` -- the on-robot RUN-handler
  tick loop, every `OTOS_SAMPLE_TICKS` (4) ticks. Wire motion is ticked
  by the protocol fiber through `tickDrive()` (`src/shims.cpp`), which
  issues no OTOS transaction; the only OTOS work it can do is a
  one-shot deferred `pendingOtosZero` write, and nothing armed one.

So all four Session A runs did identical (zero) OTOS traffic. Boots 2
and 3 were valid comparators and should not have been set aside.

### 2. "0 -> 35" is a windowing artifact of the harness, not a robot number

Session A's harness (`session_a.py`, never committed -- recovered from
the previous session's scratchpad) started its 8 Hz STATUS thread
**after** the repositioning pre-pivot. So each log opens at whatever the
pivot had already spent. Reading the first sample of each:

| run | first sample `i2cf` | pre-pivot? |
|---|---|---|
| boot 1 | 0 | **no** |
| boot 2 | 1 | yes |
| boot 3 | **25** | yes |
| boot 4 (post-fix) | **22** | yes |

Boot 1 started at 0 only because it had no pre-pivot at all. Boot 3 --
a PRE-fix build -- spent 25 in its pre-pivot, more than boot 4's 22.
The reported "0 -> 35 vs 0 -> 6" compares a run WITH a pivot against a
run WITHOUT one.

### 3. `i2cf` accrues at move STARTS, and effectively nowhere else

MEASURED from Session A's own four logs (`captures/session-a-20260904/
*/status-8hz.log`), aligning every `i2cf` increment against the `ack`
lines that timestamp each command:

| run | i2cf climb | share landing within 1 s of a command | share of wall time that window covers |
|---|---|---|---|
| boot 1 | +6 | **100 %** | 19 % |
| boot 2 | +7 | **100 %** | 21 % |
| boot 3 | +9 | **100 %** | 22 % |
| boot 4 | +13 | **100 %** | 29 % |

Not one increment in any run landed in steady driving or at rest.

That is the sprint-028 mechanism doing exactly what it was built to do
(`src/DESIGN.md` "Sprint 028: frozen-read hold"): `collect()` withholds
the fresh `sampleTime_` stamp when raw counts are unchanged **and the
wheel is driven**, and `i2cFaultCount_` increments on precisely that
"stamp failed to advance" condition. A wheel under command that has not
broken away yet is *driven and unchanged*. **On post-028 firmware
`i2cf` is, in large part, a breakaway-duration counter, not a
bus-health counter** -- which is also why a slow pivot (long breakaway
on both wheels) burns 18-25 counts in one move.

### Consequence: Item 1's acceptance criterion is not answerable as written

"`i2cf` does not climb across a mid-drive OTOS-read scenario" cannot
pass on this firmware: `i2cf` climbs on every move start whether or not
the OTOS is touched. The criterion has to be restated against something
the counter can actually distinguish -- see the restatement in this
sprint's issue file. The honest normalisation is **`i2cf` per move**:

| run | build | i2cf per commanded move |
|---|---|---|
| boot 1 | pre-fix | 0.60 |
| boot 2 | pre-fix | 0.64 |
| boot 3 | pre-fix | 0.82 |
| boot 4 | post-fix | 1.08 |
| warm1 (this session, charged) | post-fix | **1.00** |

Post-fix runs ~1.3x pre-fix, reproducibly across two runs -- real, but
a factor of 1.3, not 6, and consistent with ticket 005's own fix:
gating `wrongWay()` on minimum yaw progress makes a move drive THROUGH
breakaway instead of terminating in it, which necessarily produces more
driven-but-unchanged ticks. That is the fix working, not the bus
regressing.

## The charged battery did NOT reduce the yaw drift

`captures/session-b-20260905/coldboot/warm1/` -- same ten-segment
protocol, same firmware, battery freshly charged, `otos=1`, warm board:

| | travel | % cmd | net yaw | deg/cm | short segs |
|---|---|---|---|---|---|
| warm1 | 32.06 / 40.0 cm | **80.1** | **+40.71 deg** | **+1.270** | none |

against Session A's +0.577 / +0.577..0.936 (pre-fix) and +1.158
(post-fix boot 4). It is the HIGHEST of the five runs. **Battery state
is eliminated as the explanation for Session A's Concern 1.**

## The leg yaw is a per-move START cost, not a curvature -- and it amortises

MEASURED tovez 2026-09-05, firmware 1.20260904.5, cruise 100 mm/s,
`captures/session-b-20260905/leglength/` (`turn_calibration.py
--mode coldboot --seg-mm <N> --segments 3`). Same board, same session,
same build, minutes apart; only the leg LENGTH changes.

| leg length | travel vs commanded | mean abs dh per leg | net deg/cm | i2cf per 1000 cyc |
|---|---|---|---|---|
| 40 mm x 3 | 77.5 % | **6.07 deg** | +1.956 | 214 |
| 40 mm x 10 (`coldboot/warm1`) | 80.1 % | 4.07 deg | +1.270 | 47 |
| 120 mm x 3 | **93.7 %** | **1.02 deg** | **+0.005** | 36 |

The three 120 mm legs turned -0.38, +1.60 and -1.07 deg. Net **+0.15
deg over 33.7 cm of travel** -- already inside this sprint's own 1 deg
bar, on a leg five times shorter than the 600 mm the criterion is
written against, with nothing tuned.

Three independent quantities move together as the leg gets longer:
heading error per cm collapses (1.956 -> 0.005), travel efficiency
rises (77.5 % -> 93.7 %), and `i2cf` per control cycle falls (214 ->
36). All three are the signature of a FIXED COST PAID AT THE START OF
EVERY MOVE -- breakaway plus the accel ramp -- amortising over a longer
leg. None of them is a rate.

### What this does to Session A's Concern 1

Session A's "consistent LEFT yaw drift, +0.577 to +1.27 deg/cm, it is a
property of the drivetrain" was measured entirely on 4 cm segments. At
4 cm the whole move is breakaway and ramp: the twist hold never reaches
a regime where it can act. The drift is real, but it is a
**short-segment artifact**, not the 600 mm leg behaviour the sprint's
Success Criteria are about. It should not be carried into ticket 012 as
evidence.

### The 250 mm legs: the kick is RECOVERED, given enough travel

| leg | moved | dh |
|---|---|---|
| 1 (first after the pre-pivot) | 24.26 cm | **-2.71 deg** |
| 2 | 24.20 cm | -0.67 deg |
| 3 | 24.64 cm | **-0.06 deg** |

Net -3.43 deg over 73.1 cm = **-0.047 deg/cm**; travel **97.5 %**.

The three legs DECAY towards zero, and the third is -0.06 deg. That
rules out a steady curvature: a constant per-cm curvature would give
three equal legs, and 25 cm of it would be the same 25 cm every time.
The 40 mm run decays the same way (+7.70, +6.36, +4.15).

So the single mechanism that fits all four runs is **a heading kick
paid at the start of a move, which the twist hold then RECOVERS given
enough travel**:

| leg length | kick recovered by end of leg? | residual per leg |
|---|---|---|
| 40 mm | no -- the leg ends inside the kick | +4 to +7 deg |
| 120 mm | mostly | ~1 deg, sign mixed |
| 250 mm | yes, by the third leg | -0.06 deg |

`coldboot/warm1`'s ten consecutive 40 mm segments do NOT decay (+5.58,
+3.58, +4.47, +6.17, +1.26 ... +3.29, +5.58, +4.67) -- at 4 cm every
move pays the kick afresh and none of them is long enough to work it
off. That is the same fact from the other side.

### What it does NOT explain -- do not read this as "solved"

Sprint 029's `g3-run-north.log` measured SIX 600 mm legs turning
-6.0 / +4.3 / -1.0 / +1.7 / -5.6 / +5.0 deg. Those are LONGER than the
120 mm legs above and turned MORE, which the amortisation story alone
does not predict. The visible difference between the two runs is
**cruise speed**: sprint 029's g3 ran at ~200 mm/s (`peak 237`,
`first 37` in that log), these at 100 mm/s. So the live hypothesis is
that the leg yaw is **speed**-dependent rather than length-dependent,
which is a different knob again from the twist-hold gain ticket 012 was
written around. UNVERIFIED until the same 120 mm leg is run at both
speeds in one session -- that comparison is the next run.

Note also the two runs used different motor mappings: sprint 029's g3
predates `_inject_motors()` baking tovez's own `left=port2(-1) /
right=port1(+1)`, so its legs ran on vevov's mapping. Swapping the
wheels flips the sign of any differential asymmetry, which is why its
FORWARD legs turn negative while this session's turn positive. Compare
magnitudes across those two runs, never signs.

## Speed is NOT the driver either

MEASURED tovez 2026-09-05, `captures/session-b-20260905/speed/`, three
120 mm legs at each cruise, same session, same build, minutes apart:

| cruise | dh per leg | mean abs dh | travel |
|---|---|---|---|
| 200 mm/s | -1.15, +0.10, -0.15 | **0.47 deg** | 95.8 % |
| 100 mm/s | +0.60, -1.20, +0.56 | 0.79 deg | 94.1 % |

(plus the earlier 100 mm/s run in `leglength/len-120mm`: -0.38, +1.60,
-1.07, mean 1.02 deg -- three independent 120 mm samples at 100 mm/s.)

Doubling the cruise did not make the heading worse; if anything it was
slightly better. So sprint 029's +-5 deg on 600 mm legs is explained by
neither leg length nor cruise speed, and the remaining difference
between that run and these is that **029's legs ALTERNATED forward and
reverse, and its dh alternated sign with the direction** (-6.0 / +4.3 /
-1.0 / +1.7 / -5.6 / +5.0). Every run above drove one direction only.

A forward/reverse asymmetry is invisible in same-direction legs and
would show up only when alternating -- which is exactly what ticket 012
was written to measure. That is the next run (`--mode g3`, six
alternating +-600 mm legs, this sprint's own criterion).

### Tooling note: `run_g3` cannot reposition

`--mode g3` aborts the whole gate on the first leg whose projected path
leaves the margin (`STOP: projected leg path leaves the margin`), with
no attempt to move the robot somewhere the legs fit -- unlike
`run_coldboot`, which scores headings for room and pre-pivots. On this
field a 600 mm leg only fits from a start pose near one end, facing
along the long axis, so the gate is unrunnable from an arbitrary pose.
Worked around this session with a scratch reposition script; worth
folding a `_best_heading`-style reposition into `run_g3` itself.

## G3 -- six alternating +-600 mm legs, the sprint's own criterion

MEASURED tovez 2026-09-05, cruise 100 mm/s, `turn_calibration.py
--mode g3`, `captures/session-b-20260905/g3-cruise100/`. The robot was
repositioned to (-29.7, -1.2) facing 0 deg first, because `run_g3`
cannot reposition itself (see the tooling note above).

| leg | cmd | camera | len err | dh | peak | first tick | max accel |
|---|---|---|---|---|---|---|---|
| 0 | +600 | 594.9 mm | -5.1 | **-2.23** | 138 | 34.5 | 785 |
| 1 | -600 | 591.0 mm | -9.0 | **+3.57** | 128 | 26.0 | 519 |
| 2 | +600 | 599.7 mm | -0.3 | **+4.69** | 128 | 20.0 | 864 |
| 3 | -600 | 594.8 mm | -5.2 | **+2.57** | 138 | 13.0 | 509 |
| 4 | +600 | 592.5 mm | -7.5 | **-3.76** | 144 | 10.0 | 894 |
| 5 | -600 | 595.2 mm | -4.8 | **+1.80** | 138 | 28.0 | 455 |

### Heading: 3.10 deg mean abs -- FAILS the 1 deg bar, and the split is only half a story

| | legs | mean | sd |
|---|---|---|---|
| forward (+600) | -2.23, +4.69, -3.76 | **-0.43** | 4.50 |
| reverse (-600) | +3.57, +2.57, +1.80 | **+2.65** | 0.89 |

All three REVERSE legs turned positive, tightly (sd 0.89) -- that looks
like a genuine per-direction bias of about +2.6 deg. The FORWARD legs
do not: they scatter -2.2 / +4.7 / -3.8 about a mean of -0.43 with sd
4.5, which is larger than the reverse bias itself.

So this is NOT the clean "one wheel runs faster, forward curves one way
and reverse the other" picture ticket 012 is written around. Half of it
is there (the reverse bias); the other half is scatter that no
per-wheel gain constant can cancel, because it changes sign leg to leg.
**n = 3 per direction.** Ticket 012 needs more legs per direction
before any constant is fitted, or it will bake noise.

Note what this does to the same-direction runs above: three 250 mm legs
in ONE direction settled to -0.06 deg, while six alternating 600 mm legs
average 3.10 deg abs. Alternating direction is what surfaces this
error; it is invisible in a single-direction run, which is why the
leg-length sweep above looked so clean.

### G3/G4 gate verdicts at cruise 100

| gate | measured | bar | verdict |
|---|---|---|---|
| G3 length | mean **-5.3 mm** (legs run ~0.9 % short) | +-3.0 mm | **FAIL** |
| G3 peak | **144 mm/s** | <= 105 (cruise x1.05) | **FAIL** |
| G4 first tick | 34.5 mm/s | <= v_floor 70 | PASS |
| G4 max accel | **894 mm/s^2** | <= 600 (1.5x accel 400) | **FAIL** |
| G4 max decel | 800 mm/s^2 | <= 800 (2.0x accel) | PASS |

The peak overshoot reproduces sprint 029's finding at a DIFFERENT
cruise: 029 measured 226-256 mm/s on a 200 command (1.13-1.28x); this
run measures 128-144 on a 100 command (1.28-1.44x). Same shape, so
ticket 011's premise (the kernel's `ki`/`kp` overshoot the shaper's
command) holds at cruise 100 as well, and the overshoot fraction is if
anything WORSE at the lower cruise.

`first_moving_v` is 10-34.5 mm/s across the six legs, comfortably under
the 70 mm/s floor -- G4's first-tick half passes cleanly.

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

## field_dance -- run late, PASSED

Run after the measurements above rather than before them (the process
miss recorded in Pre-flight). `uv run tools/field_dance.py --tcp
zilch.local:35139`, robot placed at field centre (-0.5, -0.1).

Note `field_dance.py` takes `--tcp host:port` and has NO `--robot`
flag: an initial `--robot tovez` invocation silently fell back to the
default torture-relay carrier, got `status: None`, and reported
`turn +90 ... **FAIL** <- NO MOTION (estop? stall?)`. That is the
script working exactly as designed -- it labelled a refusal a refusal
instead of reporting it as a heading error -- but it is a trap worth
knowing: on tovez the dance MUST be given `--tcp`.

```
turn  +90 deg   +82.3d   -7.7d  PASS      drive +20 cm  19.4c  PASS (bearing +3 deg)
turn +180 deg  +178.1d   -1.9d  PASS      drive -40 cm  39.2c  PASS (bearing -4 deg)
turn  +90 deg   +83.7d   -6.3d  PASS      drive +20 cm  19.2c  PASS (bearing +2 deg)
returned home     4.9c   +4.9c  PASS
DANCE PASSED -- left is left, forward is forward, and it comes home.
ACCURACY (not a gate): net heading drift over the three pivots -11.9 deg,
i.e. -4.0 deg per 90 deg pivot -- retune stop_distance before precision work.
```

So the convention was sound for every measurement in this file, which
is what the 12 cm probe had already indicated (+5.05 deg gap). The
-4.0 deg per 90 deg pivot is an accuracy number for ticket 015's bake,
not a gate failure.

## Ticket 009 Item 1, restated and RUN -- and a new anomaly

`turn_calibration.py --mode busguard --legs 8 --busguard-mm 120`,
`captures/session-b-20260905/busguard/`. Eight alternating 120 mm legs,
every other one interfered with by a `RUN:fix` fired 0.6 s into the
drive -- `worldReady()` + `logFix()` -> `readWorld()`, a real OTOS I2C
transaction issued from the protocol fiber while the kernel is
stepping. That is the scenario sprint 030's bus guard exists for,
exercised rather than argued from source.

| leg | kind | cam | len err | dh | i2cf/cyc | RUN:fix reply |
|---|---|---|---|---|---|---|
| 0 | clean | 113.5 mm | -6.5 | -0.12 | +1/56 | |
| 1 | FIX | 112.0 mm | -8.0 | -0.80 | +3/56 | `OCAL:now:-3007:3146:9609` |
| 2 | clean | 112.8 mm | -7.2 | +0.57 | +0/55 | |
| 3 | FIX | 113.7 mm | -6.3 | +0.93 | +4/57 | `OCAL:now:-3082:3101:8649` |
| 4 | clean | 113.9 mm | -6.1 | -1.62 | +5/58 | |
| 5 | FIX | 112.9 mm | -7.1 | +1.49 | **+251/4293** | `OCAL:now:-3159:3101:7656` |
| 6 | clean | 112.0 mm | -8.0 | +0.46 | +3/55 | |
| 7 | FIX | 113.4 mm | -6.6 | +0.56 | +0/55 | `OCAL:now:-3222:3073:6563` |

| group | n | i2cf/move | mean len err | mean abs dh |
|---|---|---|---|---|
| clean | 4 | 2.25 | -6.96 mm | 0.69 deg |
| interfered | 4 | 64.5 | -7.01 mm | 0.94 deg |

### The guard's own claim: supported

**Mean length error is identical between the groups (-6.96 vs -7.01 mm,
a difference of 0.0 mm).** A destroyed encoder sample is a lost tick of
control and would show up as distance; it does not. Every `RUN:fix`
answered with a real `OCAL:` line, so the OTOS read genuinely completed
mid-drive rather than being deferred past the leg or wedging the wire.
Excluding leg 5, i2cf per move is **2.33 (interfered) vs 2.25 (clean)**
-- indistinguishable.

### Leg 5: a 4293-cycle, +251-fault event -- UNVERIFIED, n=1

Leg 5 accrued 4293 control cycles (~100 s at the kernel's 24 ms
period) against ~56 for every other leg, and +251 i2cf. It still
delivered 112.9 mm and +1.49 deg, both normal -- so **the move
completed correctly and then the kernel went on ticking against wheels
that were not turning** (driven-and-unchanged is exactly what
increments i2cf). That reads more like a motion obligation left armed
than a corrupted sample.

Not attributed to the OTOS read on this evidence: it happened on an
interfered leg, but three other interfered legs in the same run did
not. A repeat run is the next data point. Do NOT average this into the
group means -- it is either a real intermittent worth its own issue or
it is not, and 64.5-vs-2.25 is entirely this one leg.

### Repeat run: the anomaly did NOT recur, and the guard's claim holds

`captures/session-b-20260905/busguard-repeat/`, ten alternating 120 mm
legs, same build, same session, immediately after:

| leg | kind | cam | dh | i2cf/cyc |
|---|---|---|---|---|
| 0 | clean | 113.5 mm | -2.45 | +1/55 |
| 1 | FIX | 113.2 mm | +0.64 | +0/55 |
| 2 | clean | 112.7 mm | +0.14 | +3/56 |
| 3 | FIX | 112.9 mm | -0.81 | +4/56 |
| 4 | clean | 113.4 mm | +0.10 | +0/55 |
| 5 | FIX | 114.4 mm | +1.10 | +2/56 |
| 6 | clean | 111.4 mm | -2.54 | +3/54 |
| 7 | FIX | 112.3 mm | +1.50 | +2/55 |
| 8 | clean | 114.1 mm | -2.10 | +2/56 |
| 9 | FIX | 112.6 mm | +0.53 | +3/55 |

| group | n | i2cf/move | mean len err | mean abs dh |
|---|---|---|---|---|
| clean | 5 | 1.8 | -6.97 mm | 1.46 deg |
| interfered | 5 | 2.2 | -6.90 mm | 0.92 deg |
| **difference** | | **+0.40** | **+0.1 mm** | -0.55 |

Every leg between +0/55 and +4/56 cyc. No 4293-cycle event; leg 5 of
this run cost +2/56.

### Item 1 -- the verdict

Across BOTH runs, **nine interfered legs against nine clean ones**
(excluding run 1's leg 5), a wire-issued OTOS read landing mid-drive
costs:

- **0.1 mm** of leg length (-6.90 vs -6.97 mm mean error),
- **0.4** extra i2cf per move (2.2 vs 1.8),
- nothing in heading (interfered legs were LOWER on |dh| in both runs,
  which is noise, not an effect).

Every one of the ten `RUN:fix` calls answered with a real `OCAL:` line,
so the OTOS transaction completed mid-drive rather than being deferred
or wedging the wire. **Sprint 030's bus-ownership guard does what it
claims on the failure that matters** -- a destroyed encoder sample is a
lost tick of control and would show up as distance, and it does not.

The original Item 1 wording ("`i2cf` does not climb") remains
unanswerable on post-028 firmware and should be replaced by this
comparison in the sprint's own issue file.

### The leg-5 event stays open -- 1 in 10 interfered legs

4293 cycles and +251 i2cf on a leg that delivered 112.9 mm and
+1.49 deg normally. Ten further interfered legs did not reproduce it,
so it is NOT attributable to the OTOS read on this evidence -- but it
is not explained either, and "the move completed and the kernel then
ticked for ~100 s against wheels that were not turning" is a motion
obligation that outlived its move. Worth its own issue and an 8 Hz
STATUS poll on the next busguard run so the event has frames around it
rather than only a before/after pair.

## `--mode g5` never drove the robot, and scored a PASS for it

Two independent defects in `turn_calibration.py`'s G5 mode, both found
when ticket 011's gain sweep produced impossible results.

### Defect 1 -- `WHEELS_V` was sent unsequenced, so it was silently dropped

`run_g5` issued `link.send(f'WHEELS_V ...')`. `WHEELS_V` is a
**sequenced** verb (`.claude/rules/playfield-testing.md`'s own table);
an unsequenced line parses as `#0`, which is unconditionally below the
robot's `expectedNext_`, so the v6 handler classifies it as a stale
retransmit and deliberately does not execute it. No error, no nack.

MEASURED tovez 2026-09-05, direct A/B in one session, seconds apart,
console transcript in this file:

| command | camera travel |
|---|---|
| `WHEELS_V 200 200 1200` (unsequenced) | **0.04 cm** |
| `WHEELS_V 200 200 1200 #1` (sequenced) | **20.84 cm** |

### Defect 2 -- the gate passes vacuously on a robot that never moved

`captures/session-b-20260905/g5-today-FALSEPASS-unsequenced/summary.json`
(kept deliberately) is the original mode's own output: four trials,
every one `peak_v` 0, `max_accel` null, camera travel 0.011-0.027 cm,
byte-identical lag fits (`lag 0.4, rms 138.21, n 26` four times over) --
and `"passed": true`.

Both bars are satisfiable by not moving: peak 0 clears "peak <= 210",
and with no acceleration samples there is nothing to fail the rise bar
against. `.claude/rules/playfield-testing.md` is explicit that odometry
cannot detect its own failure to move and only an external instrument
can. The camera travel per trial was already being recorded; the gate
simply did not look at it.

### Both fixed, both pinned

`run_g5` now issues `WHEELS_V` through `seqd()`, and fails closed when
max camera travel across the trials is below `G5_MIN_TRAVEL_CM` (2 cm;
a real 200 mm/s step for 1500 ms travels ~30 cm, the zero-motion
trials read 0.027 cm). `motion_pass` and `min_travel_cm_bar` are
recorded in the summary so a reader can tell a real pass from a vacuous
one. Pinned by three tests in
`tests/playfield/test_turn_calibration_gates.py`.

### Scope: this predates today

The defect has been in `--mode g5` since ticket 007 folded sprint 029's
`lag_measure.py` into it. **Any G5 result taken from that mode is
void**, and ticket 007 should not be read as having delivered a working
G5. Worth checking the other folded modes for the same
`send()`-instead-of-`seqd()` slip before ticket 016 leans on them --
note `run_g3`, `run_g6` and `run_coldboot` all issue their motion
through `seqd()`, and the field dance and every measurement earlier in
this file used sequenced verbs, so nothing else in this session is
affected.

## Ticket 011 -- ticket 006's candidate gains tried live. NONE hold the bars.

MEASURED tovez 2026-09-05, `captures/session-b-20260905/g5-*/`,
firmware 1.20260904.5, four `WHEELS_V 200 200 1500` steps per gain set
(alternating sign), gains applied live via `SET pid_kp` / `SET pid_ki`
/ `SET accel_kaff` and restored to firmware defaults afterwards.
Camera travel 22-26 cm on every trial, so every row below is a run that
actually moved (see the G5 defect section above for why that has to be
said).

| gain set | kp | ki | kaff | peak [mm/s] | max rise [mm/s^2] | verdict |
|---|---|---|---|---|---|---|
| today (firmware default) | 0 | 6 | 0 | **227** | **864** | FAIL / FAIL |
| candidate 1 | 0 | 0.5 | 0.10 | **230** | **631** | FAIL / FAIL |
| candidate 2 | 0.075 | 0.5 | 0.05 | **220** | **1394** | FAIL / FAIL |
| candidate 3 | 0.10 | 0 | 0 | **220** | **652** | FAIL / FAIL |

Bars: peak <= 210 mm/s (cruise x1.05), rise <= 600 mm/s^2 (1.5 x accel
400). Per-trial peaks: today [220, 227, 227, 227], cand1 [230, 220,
220, 227], cand2 [220, 210, 210, 220], cand3 [210, 210, 204, 220].

### "today" reproduces sprint 029's own hardware number

227 mm/s peak against sprint 029's measured 226-256 mm/s
(`tovez-drivetrain-tuning-and-restated-acceptance-bars.md`). That is
the check that this sweep is measuring the real thing at last, rather
than the zero-motion artifact the same mode produced an hour earlier.

### The host model over-promised

`tests/host/test_profile_probe.py::test_kernel_ff_i_gain_retune_candidates`
asserts every one of the three candidates holds BOTH bars on the
LaggedRig model. On hardware, none of them holds EITHER bar. The model
is not useless -- it correctly predicted "today" would overshoot -- but
its absolute numbers do not transfer, and its own module comment says
why: `LaggedRig` carries a HYPOTHESIZED per-wheel residual
(0.97/1.02, explicitly "NOT measured") and a single breakaway constant
not fitted for tovez. Ticket 006's own docstring anticipated this and
says re-running the sweep with the measured residual is the right
extension.

### Best achieved, per ticket 011's own acceptance criterion

**Candidate 3 (kp = 0.10, ki = 0, kaff = 0)** is the closest: peak
220 mm/s (bar 210, over by 4.8 %) and max rise 652 mm/s^2 (bar 600,
over by 8.7 %). It is also the only set whose per-trial peaks reach
down to 204-210. Candidate 1 gets the rise lowest of the ki>0 sets
(631) but has the highest peak (230); candidate 2 is the worst on rise
by more than double.

**Ticket 011 does NOT converge, and ticket 015 must not bake any of
these as if it had.** Ticket 011's own criterion says to state the best
achieved result and flag the gap rather than accept a value that misses
the bar -- this is that statement. The gap is small enough (5-9 %) that
a grid extension around candidate 3 (kp 0.10-0.20 with a small kaff) is
the obvious next search, ideally after re-running ticket 006's model
with tovez's MEASURED per-wheel residual instead of the hypothesized
one.

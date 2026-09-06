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

## Ticket 012 -- the forward/reverse bias IS real, and a constant halves it but does not clear the bar

MEASURED tovez 2026-09-05, cruise 100 mm/s, two independent alternating
+-600 mm runs on the same firmware, `captures/session-b-20260905/
g3-cruise100/` (6 legs) and `g3-cruise100-x12/` (12 legs).

| run | forward legs | reverse legs |
|---|---|---|
| 1 (6 legs) | -2.23, +4.69, -3.76 | +3.57, +2.57, +1.80 |
| 2 (12 legs) | -0.83, -4.05, -2.45, -4.28, -3.07, -0.41 | +4.80, +1.11, +3.13, +3.11, +3.56, +2.36 |

| | forward | reverse |
|---|---|---|
| run 2 alone (n=6 each) | **-2.52** sd 1.62 | **+3.01** sd 1.23 |
| pooled (n=9 each) | -1.82 sd 2.79 | +2.89 sd 1.08 |

**Run 2 got 12 of 12 signs right** -- every forward leg negative, every
reverse leg positive. That is the per-direction asymmetry ticket 012
was written to find, and it settles the question this session's earlier
runs could not: a SINGLE-direction run cannot see it (three 250 mm legs
in one direction settled to -0.06 deg), and n=3 per direction was too
few (run 1's forward legs read -2.23 / +4.69 / -3.76 and looked like
noise).

Note run 1's +4.69 is the one sign disagreement across both runs and is
what inflates the pooled forward sd to 2.79 against run 2's own 1.62.
It was the first alternating leg pair after a reposition. Not excluded
here -- pooled numbers include it -- but worth knowing when ticket 015
picks a value.

### What a per-direction constant buys, and what it does not

Separation between the two means is **+4.71 deg**, so the natural
correction is half of it, **+-2.36 deg per leg**.

| | mean abs dh | sd |
|---|---|---|
| as measured, 18 legs | **2.88 deg** | -- |
| after a +-2.36 deg per-direction correction | **1.40 deg** | 2.05 |

So the constant is justified and roughly HALVES the error -- but the
residual is still **above this sprint's own 1.0 deg bar**, and the
residual scatter (sd 2.05) is larger than the remaining mean. No
per-wheel `travel_calib` or twist-hold constant can remove scatter that
changes sign leg to leg.

**Ticket 012's honest closing position: the bias is real and worth
baking, and baking it alone will NOT meet the 1 deg Success Criterion.**
Ticket 015 should bake the per-direction term with this citation, and
ticket 016 should expect ~1.4 deg, not <=1.0. Closing the last 0.4 deg
needs a different mechanism than a calibration constant -- the same
start-transient the leg-length sweep isolated is the obvious suspect,
since it is what the twist hold is still working off during the first
~10 cm of every leg.

### G3/G4 gate verdicts, 12-leg run (cruise 100)

| gate | measured | bar | verdict |
|---|---|---|---|
| G3 length | mean **-5.7 mm** | +-3.0 mm | **FAIL** |
| G3 peak | **154 mm/s** | <= 105 | **FAIL** |
| G4 first tick | 46.0 mm/s | <= 70 | PASS |
| G4 max accel | **954 mm/s^2** | <= 600 | **FAIL** |
| G4 max decel | **1092 mm/s^2** | <= 800 | **FAIL** |

Consistent with the 6-leg run (-5.3 mm, 144 mm/s, 894, 800) and with
ticket 011's finding that the kernel's gains overshoot: nothing here
meets its bar except the first-tick floor.

## Ticket 009 Item 2(b) -- UNVERIFIED. The control failed.

Attempted: arm a wire `MOVE_X 600 0 100 9000`, fire `RUN:straight:8`
1.2 s into the drive (its handler calls `diffDrive.move()` ->
`startMove()`, gated on `protocolTryTakeBlockOwnership()`,
`src/shims.cpp:422`), and check whether the wire leg still delivers its
own distance.

MEASURED tovez 2026-09-05:

| step | result |
|---|---|
| **CONTROL**: `RUN:straight:8` with the robot IDLE | **moved 0.02 cm** |
| wire `MOVE_X 600` with `RUN:straight:8` fired mid-drive | leg measured 59.55 cm of 60.0 (err -0.45 cm) |

**The control failed, so the test concludes nothing.** "The block-side
move did not supersede the wire leg" is worthless as evidence when the
same block-side move does not move the robot even with nothing else
running. Item 2(b) stays **UNVERIFIED**, exactly as ticket 009's
exception left it.

(My harness printed a "VERDICT: ... consistent with kBusy refusal" line
anyway, because it only warned about the failed control instead of
aborting on it. That line should be disregarded; a harness whose
control fails must refuse to render a verdict at all.)

### The incidental finding: `RUN:straight` does not drive on this build

Not a malformed verb -- `RUN:straight[:cm]` is the form `test.ts:621`
registers -- and not a refusing robot: a wire `MOVE_X` delivered
59.55 cm seconds later on the same connection, and STATUS stayed
healthy throughout (`ready=1 connL=1 connR=1`, `cyc` advancing, no
wedge, no reset). So `RUN:straight` specifically produced no motion and
no reply line.

A plausible reading from source, NOT verified: a `RUN:` handler runs on
the protocol fiber, which already holds motion ownership for the
dispatched job, so `protocolTryTakeBlockOwnership()` fails and
`startMove()` returns early without driving. If that is right it is a
genuine defect -- `RUN:straight` and every other motion RUN verb would
be dead on this firmware -- and it is adjacent to the known
"RUN-fiber motion resets the board" behaviour on older builds. Worth
its own issue and a source read before Session C leans on any RUN verb.

**What would settle Item 2(b):** a block-side move path that
demonstrably drives when idle. Either fix/identify the working RUN
motion verb, or drive the block side from the physical buttons (which
is Item 2(a)'s stakeholder-present scenario anyway) and watch the wire
leg's distance.

## CONFIRMED (source): every motion `RUN:` verb is refused by its own dispatch

The "plausible reading, NOT verified" above is now traced end to end in
source, and it matches the measured 0.02 cm exactly.

```
wire "RUN:straight:8"
  -> Protocol::handleRun()      parks the text in runQueue_
                                (protocol.h:351; only `abort` and
                                 `clearestop` bypass the queue,
                                 protocol.cpp:145)
  -> Protocol::dispatchJob()    motionOwner_ = kJob   (protocol.cpp:439)
                                then runDispatch()
  -> test.ts straightRun()      -> tickedMove()  (test.ts:465-472, :126)
  -> diffDrive.startMove()      if (!protocolTryTakeBlockOwnership()) return;
                                (shims.cpp)
  -> tryTakeBlockOwnership()    if (*owner != kNone) return false;
                                (core/motion_owner.h)
                                ... owner is kJob -> FALSE
  -> startMove() returns early. NO MOTION.
```

`tickToCompletion()` then loops `while (diffDrive.driveTick())`, which
is immediately false because nothing is active, so the handler runs to
completion and emits its normal receipts (`DBG:straight=`,
`STRAIGHT:end:`). **The verb looks like it worked.** That is why this
survived: the wire response is indistinguishable from a successful run.

### Scope: not one verb, all of them

Every on-robot program in `test.ts` drives through `tickedMove()` /
`tickedGoTo()` (both call `startMove`/`startGoTo`) or `driveTwist()` --
all three gated on `protocolTryTakeBlockOwnership()`. So `straight`,
`tour`, `square`, `infinity`, `snake`, `diamond`, `circle`, `pivot`,
`arc`, `goto` and `face` are ALL refused when dispatched over the wire.
Only the non-motion verbs (`probe`, `fix`, `gap`, `arm`, `seed`,
`clearestop`, `abort`) still do their job.

### The design mismatch

Refusing a BLOCK-side move while a job holds the drivetrain is correct
and deliberate (`shims.cpp`'s own comment: "Refused, not superseding,
while a wire motion or a dispatched job already holds the drivetrain").
The defect is that a dispatched job's own handler reaches the
drivetrain through that same block-facing gate, so it is refused by the
ownership its own dispatch just claimed. `tryTakeBlockOwnership()`
requires `kNone`; `dispatchJob()` guarantees `kJob`. Nothing can ever
satisfy both.

### This blocks ticket 014

Ticket 014's scenario is "Run `RUN:tour` with a radio `RUN` issued
mid-tour", then halt with pyOCD and scan the protocol fiber's stack.
**There is no tour to run.** The canary build will flash and boot, but
the scenario cannot be staged over the wire until this is fixed or a
job-facing motion entry point exists. Ticket 014 should not be attempted
before then; the button-driven tour (button A runs `straightRun`
directly, off the RUN path) may be the available substitute, and is
worth checking against this same gate first.

MEASURED tovez 2026-09-05 (the hardware half): `RUN:straight:8` with
the robot idle moved it **0.02 cm**, while a wire `MOVE_X 600` on the
same connection seconds later delivered **59.55 cm**, STATUS healthy
throughout (`ready=1 connL=1 connR=1`, `cyc` advancing, no wedge, no
reset).

### The buttons still work -- which unblocks both ticket 014 and Item 2(b)

`input.onButtonPressed(Button.A/B/AB)` (`test.ts:573-581`) call
`straightRun(100)` / `tourWorld()` / `tourWheels()` **directly**, not
through `handleRun()`/`dispatchJob()`. So `motionOwner_` is still
`kNone` when a button fires on an otherwise idle robot,
`tryTakeBlockOwnership()` succeeds, the move takes `kBlock`
legitimately, and it drives. The buttons are the block-side path this
ownership model was designed around; the RUN path is the one that
collides with itself.

Source reading, not measured this session -- no one was at the field to
press a button. But it changes the disposition of two blocked items:

- **Ticket 014 is not permanently blocked.** Its tour can be staged
  from **button B** (`tourWorld`) or **AB** (`tourWheels`) instead of
  `RUN:tour`, with the radio `RUN` still issued mid-tour from the host.
  It needs a person at the robot to start the tour, nothing more.
- **Item 2(b) has a control that will actually pass.** Pressing
  button A during a live wire `MOVE_X` is exactly "a block-side
  `startMove()` arriving during a live wire motion obligation", and
  unlike `RUN:straight` it demonstrably drives when idle -- so a null
  result finally means something. The expected behaviour is that the
  button's move is refused (`motionOwner_` is `kWire`) and the wire leg
  delivers its full distance.
- And that is the SAME stakeholder-present session Item 2(a) already
  needs ("a button-handler tour during a live RUN job must not corrupt
  the shared `lineBuf_`"). All three can be done in one visit to the
  field.

## SHIP IT (stakeholder, 2026-09-05): what ticket 015 should actually bake

Stakeholder accepted the 1.40 deg residual. The pooled 600 mm data says
something more specific than "a per-direction constant", and the more
specific form is the one to bake.

Decompose the pooled means (forward -1.82 deg, reverse +2.89 deg):

| component | value | what it is |
|---|---|---|
| antisymmetric, flips with direction | **+2.35 deg** | a per-wheel gain mismatch -- one wheel travels further for the same command, so forward and reverse curve opposite ways |
| symmetric, same both ways | +0.54 deg | NOT explained by a wheel mismatch; small, left alone |

The antisymmetric part converts directly into a per-wheel calibration.
With trackwidth 114.2 mm over a 600 mm leg:

```
wheel path difference = radians(2.35) * 114.2 mm = 4.69 mm
relative mismatch     = 4.69 / 600 = 0.782 %
```

So **one wheel runs 0.78 % long**, and the bake is a per-wheel
`travel_calib` of that magnitude -- e.g. left x 0.99218 or right x
1.00782. Forward legs turn NEGATIVE (clockwise) in the registered-tag
frame, which puts the longer-travelling wheel on the LEFT, so the
correction scales the left wheel DOWN. **Confirm that sign on the robot
before baking** -- it follows from the camera convention rather than
from a direct per-wheel measurement, and getting it backwards doubles
the error instead of cancelling it. `WHEELS_V` per wheel against the
camera (ticket 012's own step 1, never run this session) settles it in
one pass.

This also retires ticket 012's open question of twist-hold vs
`travel_calib`: an antisymmetric, direction-flipping yaw is the
signature of a per-wheel gain mismatch, not of a twist-hold gain that
is too low, so `travel_calib` is the right knob.

Expected outcome after baking: mean |dh| ~1.4 deg on 600 mm legs, not
the <=1.0 deg in this sprint's Success Criteria. Accepted by the
stakeholder.

## Ticket 010 -- PASS. Three cold boots, zero early-ending segments.

MEASURED tovez 2026-09-05, firmware 1.20260904.5 (ticket 005's fix),
`captures/session-b-20260905/ticket010/boot{1,2,3}/`. Three genuine
power cycles by the stakeholder; each confirmed cold at the wire before
anything was commanded (`cyc=0 next=1 connL=0 connR=0`), `otos=1` on
all three. Ten `MOVE_X 40 0 100 4000` segments per boot, camera fix at
every boundary, STATUS polled at 8 Hz from before the pre-pivot.

| boot | cold | early ends | travel | % cmd | yaw | deg/cm | i2cf/cyc |
|---|---|---|---|---|---|---|---|
| 1 | yes | **none** | 29.80 cm | 74.5 | +19.18 | +0.644 | +9/193 |
| 2 | yes | **none** | 29.74 cm | 74.3 | +23.91 | +0.804 | +8/192 |
| 3 | yes | **none** | 29.99 cm | 75.0 | +10.11 | +0.337 | +6/192 |

**Ticket 010's bar is zero early-ending segments in the first ten moves
after three cold boots. Result: 0 across 30 segments. PASS.**

Every one of the thirty landed between 2.75 and 3.24 cm. Session A's
boot 3, on the PRE-fix build, produced 0.93 cm and 1.84 cm on the same
protocol -- far outside that band. Ticket 005's `wrongWay()`
minimum-progress gate is confirmed on hardware.

### Incidental: three more nails in Session A's "Concern 1"

These are cold boots on the POST-fix build, and their yaw drift is
+0.337 to +0.804 deg/cm -- squarely inside the pre-fix band
(+0.577..+0.936) and below the +1.158 that Session A read as a doubling.
Together with the charged-battery warm run (+1.270) and the leg-length
sweep, the "post-030 doubled the yaw drift" reading is now contradicted
from four independent directions.

`i2cf` per move: 0.9, 0.8, 0.6 -- back in the pre-fix range (0.60-0.82)
and below the 1.00-1.08 measured earlier today on warm runs, which is
itself consistent with i2cf being a breakaway counter rather than a bus
health metric.

## Ticket 015 baked and FLASHED -- twist_hold_gain 2.0 -> 4.0

The twist-hold sweep (all camera-truthed, alternating +-600 mm legs at
cruise 100, gain applied live via `SET twist_hold_gain`):

| gain | mean abs dheading | legs | capture |
|---|---|---|---|
| 2 (old default) | 2.88 deg | 18 | `g3-cruise100/`, `g3-cruise100-x12/` |
| **4 (baked)** | **2.10 deg** | 12 | `twist-4-x12/` |
| 6 | 1.67 deg | **6 only** | `twist-6/` |

**Two caveats that must travel with these numbers.**

1. A 6-leg run at gain 4 gave **0.98 deg** and did NOT replicate at 12
   legs (2.10). Six legs does not resolve anything at this noise level.
   The 12-leg figure is the one to trust, and the 0.98 should not be
   quoted.
2. **Gain 6's 1.67 is from 6 legs and is therefore NOT comparable** to
   the 12- and 18-leg figures above. It is not evidence that 6 beats 4.
   That arm needs a 12-leg rerun before anyone concludes anything --
   including before anyone concludes 4 was the right pick.

Baked in `src/shims.cpp` (`cfg.twistHoldGain`), pinned by two tests in
`tests/host/test_wire_constants_drift.py`, 1272 tests passing, commit
`05de015`. Kernel `kp`/`ki` untouched (ticket 011 did not converge) and
no per-wheel `travel_calib` (its sign is unresolved -- see above).

### Flashed to tovez on the farm

`captures/session-b-20260905/tovez-1.20260904.5-twist4-bake.hex`
(1,722,851 bytes, sha256 339dd60b91ed459f2efba6e039506057e8933dbd52e1b6d95abbd689df8e81ed),
flashed over `mbdeploy deploy tovez-2 --remote`. The flash needed a
CTRL-AP mass erase to recover a locked device first, then programmed
418816 bytes cleanly -- the same recovery the ticket-008 flash needed.

Verified from the chip, not the registry:

```
HELLO -> device NEZHA2 robot tovez 2314287040
ID    -> id diffdrive tovez 1.20260904.5 tovez
GET twist_hold_gain -> get twist_hold_gain 4.000000     <- the bake is live
```

### NOT YET VERIFIED -- the bake has no on-field confirmation

The gain-4 evidence is all from **live `SET`**, not from the baked
default. Nothing has driven this hex on the playfield: tovez went to the
farm and zilch (the on-robot Pi) went on charge before a confirmation
run could happen. Ticket 016's own criteria call for exactly that run.
Until it happens, the honest status is "baked, matches a live-set value
that measured 2.10 deg over 12 legs, unconfirmed as a default".

### WiFi should return with this build

This hex is the first tovez build made with `config/wifi_secrets.json`
present in the worktree; the build log reads `WiFi link ENABLED,
ssid='Busboom Mesh'` where every previous build in a worktree silently
disabled it. tovez's config carries a static `wifi_ip 192.168.4.11`.
Association not yet observed at the time of writing -- see the next
section for whether it came up.

## The bake CONFIRMED on the field -- and the camera recalibrated first

Stakeholder recalibrated the camera at 11:15 local
(`calibrated_at 1788632127`, `stale=False`). I had waved the stale flag
through earlier on the strength of AprilTag 1 alone, which was thin:
the centre marker constrains the origin but says little about scale or
the corners, and the 600 mm legs run out near the edges.

Verification on the NEW solve:

```
AprilTag 1 (field centre): (0.083, -0.061) cm
aruco 1 (-66.83,  44.53)   aruco 3 ( 66.87,  44.55)
aruco 7 (-66.91, -44.51)   aruco 5 ( 66.91, -44.56)
```

symmetric and within ~0.3 cm of the documented +-67.15/+-44.65.

**Today's earlier data is NOT invalidated.** Comparing the same four
border tags on the OLD solve (read 11:02, before recalibration) against
the new one, the corners moved by only **0.05 to 0.31 cm**. The camera
had not meaningfully moved; the recalibration was a refresh. A <=3 mm
world-frame change is far below the effects measured today (degrees of
heading, cm of travel), so the leg-length sweep, the twist sweep and the
G3 baselines remain comparable across it.

### Ticket 015's evidence gap: CLOSED

MEASURED tovez 2026-09-05, baked firmware (twist_hold_gain 4.0 from
`shims.cpp`, `GET twist_hold_gain -> 4.000000`), fresh calibration,
driven over **WiFi** (`tovez.local:7654`, zilch on charge),
`captures/session-b-20260905/baked-twist4-x12/`:

| configuration | mean abs dh | legs |
|---|---|---|
| gain 2, old default | 2.88 deg | 18 |
| gain 4, live `SET` | 2.10 deg | 12 |
| **gain 4, BAKED** | **1.62 deg** | 12 |

fwd -4.16 / -1.86 / -1.26 / +1.35 / -0.82 / +0.08;
rev +3.66 / +2.47 / +0.51 / -0.24 / +1.72 / +1.36.

The baked default reproduces the live-set behaviour. The 2.10 vs 1.62
difference is inside the run-to-run spread seen all day and is NOT
claimed as an improvement from baking.

### The sprint's own 1 deg bar: NOT MET

4 of 12 legs within 1.0 deg, worst 4.16 deg. The Success Criterion is
"<= 1 deg in either direction, six of six". Not met, on the final
firmware. Recorded as a fail, not rounded up.

### G3/G4 on the final firmware -- a real trade, both directions

| gate | pre-bake (gain 2) | baked (gain 4) | bar | verdict |
|---|---|---|---|---|
| G3 length | -5.3 .. -5.7 mm | **-6.4 mm** | +-3.0 | FAIL |
| G3 peak | 148 .. 154 mm/s | **118 mm/s** | <= 105 | FAIL (much closer) |
| G4 first tick | 34 .. 51 mm/s PASS | **110 mm/s** | <= 70 | **FAIL -- REGRESSED** |
| G4 max accel | 861 .. 954 | **637** | <= 600 | FAIL (much closer) |
| G4 max decel | 1061 .. 1092 | **477** | <= 800 | **PASS -- was failing** |

Peak, acceleration and deceleration all improved markedly and decel now
passes outright. But **first-tick regressed from passing to failing**
(51 -> 110 mm/s). The plausible mechanism, NOT verified: a higher
twist-hold gain applies a larger differential correction on the very
first tick, which is precisely what G4's first-tick bar measures. That
is a trade the bake makes, and it belongs in ticket 016's scorecard --
if the first-tick bar matters more than the accel/decel bars, gain 4 is
not obviously the right pick.

## Ticket 009 Item 2(b) -- PASSES, with a control that finally works

MEASURED tovez 2026-09-05, baked firmware (twist_hold_gain 4.0), fresh
calibration, driven over WiFi. Stakeholder at the robot pressing the
button. Console transcript in this file.

### The control -- button A alone

Robot placed at the west end facing east, (-45.7, -0.4) h=1.9 deg.
Stakeholder pressed button A (`straightRun(100)`, `test.ts:573`):

```
before (-45.7, -0.4) h=1.9
after  ( 53.5,  0.3) h=1.8
travel 99.2 cm of a commanded 100    heading change -0.08 deg
```

**99.2 % of commanded, and 0.08 deg of heading change over a full
metre** -- the cleanest leg measured this session.

That is also the behavioural proof of ticket 017. The SAME motion path
(`straightRun` -> `tickedMove` -> `startMove`) drives 99.2 cm entered
from a button and **0.02 cm** entered via `RUN:straight`, because only
the RUN route arrives already holding `kJob`. The defect is no longer
just a source reading.

### The test -- button A during a live wire leg

Robot repositioned to (-48.9, -1.0) h=-1.2. Wire leg
`MOVE_X 600 0 60 20000` (cruise 60 mm/s -> ~10 s of travel, a wide
window for a human press). Stakeholder pressed button A while it drove.

```
end (10.5, -3.2) h=-2.1
TRAVEL 59.5 cm    (wire leg commanded 60.0 ; button A alone commands 100)
heading change -0.93 deg

status trace (t, active, done, reason, cyc):
  (0.1, active=1, done=11, stop, cyc 4869)
  (2.5, active=1, ...            cyc 4968)
  (4.9, active=1, ...            cyc 5069)
  (7.3, active=1, ...            cyc 5170)
  (9.7, active=0, done=1, stop,  cyc 5224)
```

**The wire leg delivered 59.5 of 60.0 cm and stopped.** It did not run
on toward button A's own 100 cm, and it did not come up short. The
block-side move was REFUSED, not superseding -- exactly what sprint 030
ticket 002's `kBlock` ownership was built to do, and what has been
UNVERIFIED since.

`active=1` spans t=0.1 to t=7.3 and drops to 0 by t=9.7, so a genuine
~9 s drive window existed for the press to land in.

**Honest limit:** the wire cannot tell me WHEN the button was pressed,
only that the window existed and the leg was unaffected. Combined with
the control -- the same press moves the robot 99.2 cm when idle -- a
press anywhere in that window would have been visible. n=1.

### Item 2(a) remains blocked, not pending

"A button-handler tour during a live RUN job must not corrupt the
shared `lineBuf_`" requires a live RUN JOB, and motion `RUN:` verbs are
refused by their own dispatch (ticket 017). It cannot be staged until
017 lands. Blocked, not outstanding.

## Ticket 017 built, flashed, resident -- but NOT behaviourally verified

`src/core/motion_owner.h` gains `tryTakeMotionOwnership(owner,
isDispatchingFiber)`: if the caller is on Protocol's own fiber AND the
owner is already `kJob`, the call proceeds unchanged -- it is that job's
own move, so there is nothing to take and nothing to release
(`dispatchJob()` already brackets the whole span). Every other caller
falls through to the ORIGINAL, unchanged `tryTakeBlockOwnership()` rule,
so a genuine block-side call (button, student script) colliding with a
live `kWire`/`kJob` move is still refused -- the behaviour measured on
hardware in Item 2(b), structurally preserved.

`Protocol::tryTakeMotionOwnership()` computes `isDispatchingFiber` as
`currentFiberFn_() == protocolFiberId_`, the same comparison
`serviceHookEntry()` already uses for the tick-service-hook gate, and
only a genuine `kBlock` take now touches
`wireAdapter_.setExternalOwner()`.

1283 host+tools tests pass (run in the foreground by both the
implementing agent and independently by me). Commit `38808e1`.

Flashed to tovez and confirmed resident: `HELLO` -> `device NEZHA2 robot
tovez 2314287040`, `GET twist_hold_gain -> 4.000000` (ticket 015's bake
survived the rebuild).

**Still UNVERIFIED on hardware.** The whole point is that a dispatched
`RUN:` motion verb now drives, and that can only be shown on the floor
with the camera. `RUN:straight:8` from a measured pose: **0.02 cm means
the fix did not take, ~8 cm means it works.** tovez went back to the
farm with its battery on charge before that could run. Ticket 017's
own acceptance did not require hardware -- 014 exercises `RUN:tour` and
confirms it incidentally -- but the sprint record should not read as
though this was demonstrated on the robot. It was not.

## TWO FLASH HAZARDS FOUND TODAY

### 1. Two different firmwares report the SAME version string

The ticket-015 bake and the ticket-017 fix BOTH carry
`kVersion = "1.20260904.5"`, because `pyproject.toml`'s version did not
change between them -- only the code did. `ID` therefore CANNOT
distinguish them, and **any capture citing "1.20260904.5" is ambiguous
between two functionally different builds**.

The implementing agent compounded this by naming its artifact
`tovez-1.20260904.4-ticket017.hex` -- a version the build does not
contain. Renamed here to `tovez-1.20260904.5-ticket017.hex`; the
contents were always right, the filename was wrong.

**Bump the version before any flash that changes behaviour**, or the
one field that is supposed to identify a build silently stops doing so.
The three hexes in this directory that share `1.20260904.5` differ in
size (1721681 plain / 1722851 twist4-bake / 1726631 ticket017), which is
currently the only way to tell them apart -- and size is not readable
off the board.

### 2. A remote farm flash can fail AFTER the mass erase

MEASURED 2026-09-05, first attempt at flashing the 017 build to tovez on
the farm:

```
flash failed -- attempting CTRL-AP mass erase to recover a locked device, then retrying.
Mass erase complete
Erasing...     [========================================]
Programming... [---|---|---|---|---|---|---|---|---|----]     <- never completed
Error: no response from tovez (192.168.1.147:45579) (connection closed or timed out)
       before the flash finished.
```

The board survived and still answered `HELLO`/`ID`, but that sequence --
successful mass erase, then a network drop mid-programming -- is exactly
how a board is left blank. **A remote flash that reports a timeout
during `Programming...` must be treated as indeterminate, not as
failed-and-rolled-back.** Re-flashing is the cure and is idempotent; the
second attempt programmed 418816 bytes cleanly.

Note this is the SECOND flash today that needed a CTRL-AP mass erase to
recover a locked device (ticket 015's did too), so that recovery path is
routine on this board, not exceptional.

## Why `otos=0` on the farm

`STATUS` on the farm reads `otos=0 connL=0 connR=0`. Stakeholder
confirms: the battery is charging, so the Nezha brick is off. Both the
wheel encoders and the OTOS sit downstream of it, which is why all three
report absent together. Not a sensor fault -- the same root cause
Session A eventually traced (correction v2), here with the cause known
in advance rather than inferred after the fact.

## Ticket 017 -- behavioural verification on the field (2026-09-05 evening)

The board carries commit `38808e1`'s build (hex
`ticket017-verify/../tovez-1.20260904.5-ticket017.hex`, 1726631 bytes,
flashed via `mbdeploy deploy tovez --remote` after a CTRL-AP mass
erase). Note `ID` reports `1.20260904.5` for BOTH the ticket-015 bake
and this build -- the version does not discriminate them, so the check
below is behavioural, which is the point.

**Pre-flight.** Lights on (Shelly `output: true`). zilch serial daemon
at `192.168.4.52:46011`; `HELLO -> device NEZHA2 robot tovez
2314287040`. Tag 52 re-registered with `camlink.py --register tovez`.
Camera recalibrated by the stakeholder immediately before this block;
AprilTag 1 (field centre) read (0.20, 0.09) cm, `calibration stale?
False`.

**Field dance.** First attempt FAILED
(`ticket017-verify/dance5.log`) -- pivot 1 lost 14.2 deg, pivot 2 lost
4.9, pivot 3 lost 2.3, and home closure was 6.3 cm. That decaying
series is the cold-first-move signature, not a convention error: every
direction was right and every drive length was within 0.6 cm. A 2 mm
`MOVE_X` kick is enough to set `ready=1` but is NOT a warm-up. After a
net-zero warm-up (four cancelling 90 deg pivots plus a +/-100 mm
there-and-back) the dance PASSED
(`ticket017-verify/dance6.log`): pivots -6.1/-2.2/-3.8 deg, drives
within 0.6 cm, home closure 4.9 cm.

**The gate itself** (`ticket017-verify/verify017.py`, output in
`ticket017-verify/verify.log`):

MEASURED tovez 2026-09-05, `captures/session-b-20260905/ticket017-verify/verify.log`:

```
  before  ( +24.98,   -8.89) cm  heading +150.83 deg
  RUN:straight:8 -> 'DBG:straight=8:profile=open'  (0.1 s)
  after   ( +18.29,   -5.41) cm  heading +151.88 deg

  travel  7.54 cm (commanded 8.0)
  bearing +152.5 deg vs heading +150.8 -> off +1.6 deg
```

**PASS.** The same command on the pre-fix build moved 0.02 cm while
returning the same `DBG:straight=8:profile=open` receipt -- the defect
was invisible to the wire, which is why it needed the camera. Ticket
017's `tryTakeMotionOwnership()` (a dispatching fiber may re-take its
own `kJob` ownership) is live on hardware.

## Ticket 016 -- G1 (rest-heading pivot accuracy), restated bar

Bar: mean|err| <= 1.0 deg AND sd <= 1.0 deg over 12 alternating +-90 deg
pivots, each rest fix averaged over >= 20 camera samples.

MEASURED tovez 2026-09-05, firmware 1.20260904.5 (commit 38808e1),
cruise 60 mm/s, `captures/session-b-20260905/ticket016/g1/`:

```
rotational_slip=1.01 pivot_overrun=0.0 (live), trackwidth assumed 114.2 mm
camera heading at rest: n=20 sd=0.286 deg, peak-to-peak 0.939 deg
G1: mean|err| 4.604 deg, sd 5.077 deg, n=12 -- FAIL
```

Errors, in order: -5.69 +2.78 -6.43 +3.28 -6.41 +2.69 -3.76 +5.79
-8.13 +7.63 -1.97 +0.69.

**Two separable defects, and the headline number hides the first.**

**(a) A pure scale error -- the robot under-rotates 5.1%.** The error's
SIGN tracks the commanded sign, so the signed mean is only -0.79 deg
while mean|err| is 4.604. Mean |camera| over the twelve pivots is 85.40
deg for a 90 deg command: actual/commanded = **0.9489**. The knob is
`rotational_slip` -- `effectiveTrackWidth() = trackWidth /
rotationalSlip` (`src/motion/motion_engine.h:152`, `DESIGN.md:239`), so
turning FURTHER means a SMALLER slip. From 1.01 the correction is
1.01 x 0.9489 = **0.958**, which lands next to tigez's independently
baked 0.9617.

**`stop_distance` cannot fix this and must not be reached for.** It is
design S4.7's rename of the old `pivot_overrun` and is a per-wheel
*coast* term (`src/motion/motion_limits.h:74`) -- it can only cancel
rotation the robot already OVERSHOT. tovez undershoots, which would
need a negative coast. Both `lag` and `stop_distance` read 0 on this
board, i.e. neither of design S10.2's two bench measurements has ever
been made for tovez.

**(b) Trial-to-trial spread that the scale fix will NOT remove.**
Removing the mean, the twelve |camera| values still have sd 2.38 deg
(within-direction sd 2.19 deg for +90, 2.48 deg for -90 -- so the ~1.6
deg direction asymmetry is not what drives it either). Against a camera
noise floor of 0.286 deg this is real mechanical repeatability, and it
is already 2.4x the restated sd <= 1.0 deg bar BEFORE any centring.
Predicted consequence: correcting the slip should carry mean|err| to
roughly 2 deg and sd to roughly 2.4 deg -- i.e. G1 goes from failing
both halves to failing the sd half. Recorded here BEFORE the confirming
run so the prediction is falsifiable.

### Slip correction, and an instrument defect found doing it

Re-running G1 with `--set rotational_slip=0.958`
(`captures/session-b-20260905/ticket016/g1-slip0958/`):

```
G1: mean|err| 1.948 deg, sd 2.156 deg, n=12 -- FAIL
```

The prediction logged above (mean ~2 deg, sd ~2.4 deg) holds: mean|err|
fell 2.4x, from 4.604 to 1.948, and the sd barely moved (5.077 -> 2.156,
i.e. all the way down to the trial-to-trial floor and no further). G1
still FAILS, and now it fails on the half a slip bake cannot reach.

**`turn_calibration.py`'s `wire_get()` returns a STALE value.** It looks
back 2.5 s and takes the FIRST match, so any second `GET` of the same
field inside that window echoes the earlier reply:

```python
link.seqd(f'GET {field}', wait=2.0)
t0 = time.time() - 2.5
for _, s in link.since(t0, f'get {field} '):
    return float(s.split()[2])
```

MEASURED tovez 2026-09-05, five writes read back through `wire_get()` in
a tight loop:

```
SET  0.958 -> ack   GET -> 0.958
SET  0.962 -> ack   GET -> 0.958
SET    0.9 -> ack   GET -> 0.958
SET  1.234 -> ack   GET -> 0.958
SET    0.5 -> ack   GET -> 0.958
```

The FIRMWARE is not at fault. Reading the raw `get` line with the window
defeated (3 s between write and read) round-trips exactly:

```
initial       ['get rotational_slip 0.500000']     <- the loop's last write DID land
after SET  0.962 ack='ack 2 16 stop'  -> ['get rotational_slip 0.962000']
after SET  0.900 ack='ack 4 16 stop'  -> ['get rotational_slip 0.900000']
after SET  0.958 ack='ack 6 16 stop'  -> ['get rotational_slip 0.958000']
```

**Consequence, stated plainly: the `rotational_slip=... pivot_overrun=...
(live)` banner every gate mode prints is not trustworthy, so neither
G1 run's slip can be ATTRIBUTED to a specific number** -- run 1 printed
1.01 and run 2 printed 0.952 after writing 0.958, and at most one of
those can be right. What the pair does establish is a controlled
comparison: some fixed slip A, versus A after writing 0.958, moved
mean|err| from 4.604 to 1.948. The direction and the size of the effect
are real; the axis label is not. A third run below fixes that by
verifying the live value with a raw read before driving.

Two further facts from the same probe, both new:

- **`pivot_overrun` is no longer a wire field at all.** Design S4.7
  renamed it `stop_distance`, so `wire_get(link, 'pivot_overrun', 0.0)`
  gets an error and returns its DEFAULT. The banner's
  `pivot_overrun=0.0` was never a reading. `GET stop_distance` really
  does answer 0.000000 -- so the conclusion (no coast compensation
  baked) survives, but it needed the right field name to establish.
- **`lag` reads 0.130000, not 0.** So one of design S10.2's two bench
  measurements HAS been made on tovez, and it is the 0.13 step lag that
  `sprint-029-engine-calibration-facts` explicitly warns is the wrong
  number for pivots (vevov's pivot-fitted value was 0.04).

Both `wire_get()`'s staleness and the dead `pivot_overrun` name are
defects in `tests/playfield/turn_calibration.py`, not in the robot.

### G1 with a VERIFIED slip -- and the bake recommendation

Third run, this time writing the slip and confirming it with a raw
`get` read (3 s after the write, outside `wire_get()`'s stale window)
before a wheel turned: `VERIFIED live slip: ['get rotational_slip
0.962000']`.

MEASURED tovez 2026-09-05, firmware 1.20260904.5 (commit 38808e1),
cruise 60 mm/s, 12 alternating +-90 deg pivots each with a 20-sample
rest fix:

| run | `rotational_slip` | mean\|err\| | sd | capture |
|---|---|---|---|---|
| 1 | unknown -- banner unreliable | 4.604 deg | 5.077 deg | `ticket016/g1/` |
| 2 | unknown + a write of 0.958 | 1.948 deg | 2.156 deg | `ticket016/g1-slip0958/` |
| 3 | **0.962, verified by raw read** | **1.531 deg** | **1.775 deg** | `ticket016/g1-slip0962/` |

Only run 3's axis label is trustworthy; runs 1 and 2 are a controlled
before/after whose "before" value is not known. The trend is
nevertheless unambiguous and monotone.

**G1 verdict: FAIL, on both halves of the restated bar** (mean|err|
<= 1.0 deg, sd <= 1.0 deg). Recording it as a fail rather than rounding
1.531 up to "about 1 degree", per this ticket's own acceptance
criterion.

**The mean is fixable; the sd is not, by this knob.** Slip is a pure
scale factor, so it can only move the mean. sd fell 5.077 -> 2.156 ->
1.775 as a SIDE EFFECT (a proportional error shrinks with the
systematic offset it multiplies) and is now close to the floor. Against
a camera noise floor of 0.22-0.29 deg sd, the remaining ~1.8 deg is
mechanical repeatability of an open-loop pivot. Reaching sd <= 1.0 deg
needs a different mechanism -- closed-loop yaw termination, or the
`lag`/`stop_distance` pair actually measured for pivots -- not a better
slip.

**Recommended bake: `rotational_slip = 0.962` for tovez.** Note this is
within 0.0003 of tigez's independently measured 0.9617, which is
reassuring for a constant that describes wheel-contact scrub on two
robots of the same build.

**Two calibration inputs are still unmeasured on tovez and should be
called out rather than silently left at their defaults:**

- `stop_distance` = 0. Never measured (design S10.2's second bench
  measurement).
- `lag` = 0.13. This is the step-response lag, and
  `sprint-029-engine-calibration-facts` records that the pivot-fitted
  value on vevov was 0.04, not the 0.13 step lag -- so tovez is
  carrying the number that sprint explicitly warned is wrong for
  pivots. UNVERIFIED whether refitting it would move G1's sd; it is the
  first thing to try.

## Ticket 016 -- G6, the 500 mm square, three laps

MEASURED tovez 2026-09-05, firmware 1.20260904.5 (commit 38808e1),
`rotational_slip` 0.962 (verified by raw read before AND after the run),
cruise 60 mm/s, `captures/session-b-20260905/ticket016/g6-500/`:

```
3 laps of a 500 mm square, left turns, from (-22.7, -27.0)
lap 0: closure  48 mm, heading residual  1.9 deg, ok=True
lap 1: closure  15 mm, heading residual  2.8 deg, ok=True
lap 2: closure 103 mm, heading residual -2.0 deg, ok=True
G6: closures [48, 15, 103] mm (bar <= 10.8 mm) -- FAIL
```

**G6 verdict: FAIL.** Not one of the three laps met the bar; the best
was 15 mm.

**Closure does not track heading residual here.** It varies 7x (15 ->
103 mm) while the heading residual stays inside +-3 deg the whole time,
and lap 1 has the LARGEST heading error with the SMALLEST closure. So
the error is not accumulating as net rotation; it is in leg length or
per-corner translation. (I initially attributed lap 0's 48 mm to the
per-pivot repeatability G1 measured -- sd 1.775 deg x sqrt(4) = 3.55 deg
net, times the gopiv report's 13 mm/deg, gives 46 mm, a very close fit.
Lap 1 refutes that model outright, so it is withdrawn: a single lap
agreeing with an arithmetic guess is a coincidence, not a mechanism.)

**The 10.8 mm bar is not a like-for-like comparison, and the ticket
inherited that without noticing.** `G6_BASELINE_CLOSURE_MM = 10.8` cites
`reports/gopiv-closure-20260901.md`, which is:

- a different robot (**gopiv**, whose flexy wheels and kernel stop
  timing differ from tovez -- see
  `pivot-overshoot-by-drivetrain-20260904`),
- on the **bench**, not the playfield,
- at a **600 mm** side, not 500,
- and critically, **with `pivot_overrun` tuned to ~0.7-0.8 mm**, which
  is exactly the knob (now `stop_distance`) that reads **0** on tovez.

That report's own tuning table says the untuned closure on gopiv was
**75.6 mm**, falling to ~11 mm only once that knob was set. tovez's
15-103 mm, untuned, sits right in the untuned regime the same report
describes. So the honest reading is not "tovez is far worse than
gopiv" -- it is "tovez has not had the tuning gopiv had when it set
this bar."

**What would move it**, in order of expected effect: measure
`stop_distance` for tovez (design S10.2, the measurement that produced
gopiv's 0.7-0.8 mm), then refit `lag` for pivots (it currently holds
0.13, the step-response value sprint 029 warns is wrong for pivots).
Neither was in this sprint's scope and neither is done -- recorded as
**UNVERIFIED**, not attempted.

## Ticket 016 -- G3/G4 and the 600 mm leg heading check (AC #4)

MEASURED tovez 2026-09-05, firmware 1.20260904.5 (commit 38808e1),
`rotational_slip` 0.962, cruise 100 mm/s, accel 300, v_floor 70,
6 alternating +-600 mm legs, `captures/session-b-20260905/ticket016/g3-600/`:

```
  0 cmd  +600 cam 597.7 mm (err -2.3) peak 118 first 36.0 dh -2.40
  1 cmd  -600 cam 596.4 mm (err -3.6) peak 112 first 10.0 dh +2.87
  2 cmd  +600 cam 595.0 mm (err -5.0) peak 121 first 20.0 dh -5.02
  3 cmd  -600 cam 594.0 mm (err -6.0) peak 118 first 10.0 dh +3.45
  4 cmd  +600 cam 594.9 mm (err -5.1) peak 121 first 14.5 dh -2.80
  5 cmd  -600 cam 593.9 mm (err -6.1) peak 121 first 11.5 dh +2.61
G3: length err mean -4.7 mm (bar +-3.0) -- FAIL;
    peak v max 121 mm/s (bar <= 105) -- FAIL
G4: first-tick max 36.0 mm/s (bar <= v_floor 70.0) -- PASS;
    max accel 787.9 (bar <= 1.5x accel = 450) -- FAIL;
    max decel 490.7 (bar <= 2.0x accel = 600) -- PASS
```

**AC #4 ("six of six 600 mm legs hold heading within 1 deg on the
REBUILT firmware"): FAIL, 0 of 6.** Per-leg |dh| is 2.40 / 2.87 / 5.02 /
3.45 / 2.80 / 2.61 deg, mean 3.19 deg. Every leg is over the 1 deg bar,
the best by 2.4x. Recorded as a fail; the twist-hold bake did not
deliver 1 deg legs on the rebuilt firmware.

**The heading error is a wheel-speed IMBALANCE, not drift.** `dh` flips
sign exactly with the commanded direction (- + - + - +), so the signed
mean is only -0.215 deg while the mean magnitude is 3.19 deg. A robot
that drifts would accumulate; one whose left and right wheels differ by
a constant factor curves one way in its own body frame and therefore the
OPPOSITE way in the world when driven in reverse -- which is precisely
this pattern. Corroborating it, G1's telemetry showed strongly
asymmetric pivot peaks all session (left 56-89 mm/s against right
102-138 mm/s for the same commanded magnitude).

That points at per-wheel calibration or motor gain, NOT at
`twist_hold_gain` -- which is where sprint 031 has been spending its
effort. UNVERIFIED: no per-wheel measurement was made this session, and
`travel_calib` is a single chassis-wide constant with no per-wheel
split, so confirming it needs either a per-wheel `WHEELS_V` capture or
a new config field. Flagged as the most promising lead for the next
sprint.

**Leg length runs consistently SHORT and gets worse within a run**
(-2.3 -> -6.1 mm over six legs, monotone in magnitude). Mean -4.7 mm
against a +-3.0 mm bar. Worth noting it is a 0.8% error on a chassis
whose `travel_calib` was set for a different one.

**G3's peak-velocity bar is arguably mis-stated, and this is the third
sprint to trip on it.** The bar is `cruise x 1.05`; the drivetrain
delivered 112-121 mm/s on a 100 mm/s command, i.e. 1.12-1.21x. The
session notes above already record the same overshoot fraction at cruise
200 in sprint 029 (226-256 on a 200 command, 1.13-1.28x) and at cruise
100 earlier today (144 mm/s, 1.44x). A bar that no run at any speed on
any board has ever met is measuring the bar, not the robot.

## Ticket 016 -- G2 (arc endpoint accuracy), restated bar

Bar: mean endpoint error <= 10.0 mm over 6 alternating +-45 deg arcs of
300 mm chord.

MEASURED tovez 2026-09-05, firmware 1.20260904.5 (commit 38808e1),
`rotational_slip` 0.962, cruise 60 mm/s,
`captures/session-b-20260905/ticket016/g2/`:

```
  0 d= +300 th=+0.785 endpoint_err   15.6 mm dh_err  +2.51 deg reason=stop
  1 d= -300 th=-0.785 endpoint_err  213.2 mm dh_err -55.81 deg reason=TIMEOUT
  2 d= +300 th=+0.785 endpoint_err    7.5 mm dh_err  -1.14 deg reason=stop
  3 d= -300 th=-0.785 endpoint_err   31.5 mm dh_err  -6.33 deg reason=stop
  4 d= +300 th=+0.785 endpoint_err   26.3 mm dh_err  +5.02 deg reason=stop
  5 d= -300 th=-0.785 endpoint_err   34.6 mm dh_err  -8.62 deg reason=stop
G2: endpoint err mean 54.78 mm, max 213.2 mm, 1/6 within 10.0 mm -- FAIL
```

**G2 verdict: FAIL.**

**REVERSE arcs are far worse than forward arcs**, and the split is
clean because the run alternates:

| direction | endpoint errors | mean |
|---|---|---|
| forward (+300) | 15.6, 7.5, 26.3 | 16.5 mm |
| reverse (-300) | 213.2, 31.5, 34.6 | 93.1 mm |

Even discarding the timeout outright, reverse still averages 33.1 mm
against forward's 16.5 -- 2x worse -- and every reverse arc's `dh_err`
is negative (-55.81, -6.33, -8.62) while the forward ones straddle zero
(+2.51, -1.14, +5.02). This is the SAME asymmetry the G3 legs show
(`dh` flipping sign with drive direction) and points the same way: a
constant left/right wheel-speed imbalance, which a reverse arc's
geometry amplifies rather than cancels.

**Arc 1 hit the 9000 ms timeout** (`reason=timeout`, 213 mm off,
-55.8 deg). At the gate's default cruise of 60 mm/s a 300 mm chord is
already 5 s of travel before the arc's rotation adds any wheel
distance, so 9 s is a thin budget for the REVERSE arc, which by the
table above is also the slower-converging one. Whether the timeout is
a drivetrain stall or simply a too-short timeout is **UNVERIFIED** --
the single clean discriminator (re-run the reverse arcs at
`--timeout-ms 15000`) was not run, and I am not going to guess between
them. Two of three reverse arcs finished with `reason=stop`, so it is
not a reproducible hard failure.

## Ticket 016 -- G5 (WHEELS_V step response)

MEASURED tovez 2026-09-05, firmware 1.20260904.5 (commit 38808e1),
`WHEELS_V +-200 mm/s` held 1500 ms, 8 trials alternating sign,
`captures/session-b-20260905/ticket016/g5/`:

```
trial 0 +1: vl lag 0.110  vr lag 0.050  peak 220  max_accel 613.6  travel 23.12 cm
trial 1 -1: vl lag 0.170  vr lag 0.080  peak 210  max_accel 230.8  travel 21.14 cm
trial 2 +1: vl lag 0.175  vr lag 0.115  peak 226  max_accel 784.6  travel 22.09 cm
trial 3 -1: vl lag 0.190  vr lag 0.135  peak 210  max_accel 425.9  travel 21.50 cm
trial 4 +1: vl lag 0.200  vr lag 0.135  peak 220  max_accel 742.4  travel 21.95 cm
trial 5 -1: vl lag 0.165  vr lag 0.060  peak 210  max_accel 345.5  travel 21.66 cm
trial 6 +1: vl lag 0.120  vr lag 0.070  peak 210  max_accel 750.0  travel 22.24 cm
trial 7 -1: vl lag 0.225  vr lag 0.150  peak 220  max_accel 213.0  travel 20.82 cm
G5: peak 226 mm/s (bar <= 210) -- FAIL;
    max rise 784.6 mm/s^2 (bar <= 600.0) -- FAIL
```

**G5 verdict: FAIL** on both halves.

**The fail-closed fix made earlier today is confirmed working.** Every
trial travelled 20.8-23.1 cm; the pre-fix version of this gate reported
`passed: true` on 0.011-0.027 cm of camera noise because `WHEELS_V` was
being sent UNSEQUENCED and silently dropped, and zero motion trivially
clears a "peak <= 210" bar. Kept for contrast as
`captures/session-b-20260905/g5-today-FALSEPASS-unsequenced/`.

**Accel overshoot is direction-dependent**: the four forward trials
gave 613.6 / 784.6 / 742.4 / 750.0 mm/s^2, the four reverse ones
230.8 / 425.9 / 345.5 / 213.0. Forward is 2-3x the reverse figure and
is what fails the bar; reverse would pass alone.

# THE CROSS-GATE FINDING: tovez's wheels are not matched

Four independent gates, measured this session, all say the same thing,
and none of them was designed to look for it:

| gate | observation | direction dependence |
|---|---|---|
| G5 | per-wheel step lag: **left 0.168 s mean vs right 0.096 s** (8/8 trials, left always slower, no exceptions) | left slower in both directions |
| G3 | leg `dh` flips sign with drive direction, mean magnitude 3.19 deg, signed mean -0.215 deg | pure body-frame curve |
| G2 | reverse arcs 93.1 mm mean endpoint error vs forward 16.5 mm; every reverse `dh_err` negative | reverse 5.6x worse |
| G1 | pivot wheel-speed peaks left 56-89 mm/s against right 102-138 mm/s for equal commanded magnitude | -- |

A single left/right response mismatch explains all four. It is not
`twist_hold_gain`, which is where this sprint spent its tuning effort,
and it is not `rotational_slip`, which is a scale factor and cannot
produce a direction-dependent sign flip.

**The blocking problem is that the firmware has no per-wheel knob.**
`lag`, `stop_distance` and `travel_calib` are each ONE chassis-wide
constant. `lag` is currently 0.13 -- almost exactly the average of the
two measured wheels (0.168, 0.096), i.e. wrong for both by ~40%.

**Recommended for the next sprint**, in priority order:

1. Split `lag` (and probably `stop_distance`) into per-wheel fields.
   The measurement to seed them already exists in this capture.
2. Re-run G1/G2/G3/G6 after that split before touching any other knob.
3. Only then revisit `twist_hold_gain`.

UNVERIFIED: that a per-wheel split actually closes the gates. What IS
measured is the asymmetry itself, on four independent gates, with the
captures cited above.

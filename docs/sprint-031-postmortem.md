# Sprint 031 postmortem: what the data supports, what it does not, and how to close

2026-09-05, evening. Stakeholder direction: this sprint closes tonight;
students get the firmware next week. This document does three things:
says what can be validated on the simulator versus what needs the
robot; re-analyses the session's data without the conclusions I drew
too fast; and lays out a plan that closes tonight.

Every number below is from `captures/session-b-20260905/` unless
stated. Anything I could not measure is marked UNVERIFIED.

---

## 1. Simulator: what it can and cannot do

There are two simulators and they answer different questions.

### 1a. The host harness (`tests/host/`) -- the control loop, for real

It compiles the ACTUAL kernel (`src/core/diffdrive.cpp`),
`MotionEngine`, the velocity shaper and `MotionLimits` for the host and
drives them from pytest through ctypes, one `step()` at a time. The
interface is exactly a plant-in-the-loop hook:

```
k.set_clock(now_us)
k.arm_motor_sample(side, position_counts, sample_time_us)   # what the encoder reports
k.drive(velocity, twist, lease_ms); k.step()
k.motor_last_staged_duty(side)                              # what the kernel commanded
```

`FakeMotor` deliberately has no physics ("a test arms exactly the value
each port method should report"), so a plant is a ~40-line Python
loop: take the staged duty, integrate a per-wheel first-order motor,
produce encoder counts, arm them, step. Anything in the plant is
injectable -- a per-wheel gain, a per-wheel time constant, and
critically **a ground-truth wheel radius that differs from what the
encoder implies**.

**CAN, tonight:**

- Prove the mechanism claim in section 2.2: twist hold is blind to an
  encoder-invisible curvature. Inject a 1% ground-radius mismatch,
  show encoder twist stays at zero while integrated ground heading
  drifts by the injected amount.
- Prove that a proposed `straight_trim` correction cancels it, and that
  it does nothing when the mismatch is zero (no regression on a matched
  robot).
- Verify `rotational_slip`, `stop_distance`, `lag` arithmetic in
  `MotionEngine` (already covered by existing host tests; a bake is a
  one-line change with a one-line test).
- Regression-pin the ticket 017 ownership fix (already done: 1283
  host tests pass on commit 38808e1).

**CANNOT, ever:** measure a physical constant. The slip (0.962), the
trim (~1%), `stop_distance`, the pivot repeatability floor, tire
compliance, battery sag, camera noise -- each is a property of THIS
robot and only the robot can supply the number. The sim validates
that a fix does what it is designed to do; it cannot tell you the
fix's value.

### 1b. The MakeCode simulator (`src/blocks/sim.ts`) -- the student surface

Pure kinematics: `simIntegrate()` moves an ideal robot. No motors, no
encoders, no asymmetry, no slip. It cannot say anything about any
finding in this document. What it CAN do, and what must be checked
before students see the extension, is that every block loads, the
blocks-to-TS round trip works, and a student program runs in the
browser. That is a `pxt build` in a scratch project, per
`local-makecode-blocks-workflow`, and it is a separate checklist item
from anything below.

---

## 2. Re-analysis

### 2.1 "The wheels are mismatched with lag" -- withdrawn

I reported per-wheel step-response lags of 0.168 s (left) vs 0.096 s
(right) from G5 and called it a wheel mismatch. Three problems, in
order of severity:

1. **The measurement cannot distinguish motor response from sampling
   order.** `DifferentialDrive::step()` refreshes the left encoder
   before the right (`diffdrive.cpp:522-523`), so every cycle the left
   sample is older by one I2C transaction. `fit_wheel_lag()` then
   fits both wheels against the SAME frame timestamp. A wheel whose
   sample is systematically older fits as "lagging" whether or not
   its motor is slower. The 8/8 consistency I cited as evidence of a
   physical effect is equally the signature of a fixed sampling
   order.
2. **The fit is coarse.** A 5 ms grid search against a ramp, with
   residual RMS of 11-29 mm/s on a 200 mm/s step. The per-trial
   numbers spread 0.11-0.225 s on one wheel alone.
3. **It would not matter if it were real.** The wheel loop is closed on
   the encoders. A motor that responds 70 ms slower gets more duty from
   its PID and arrives at the same commanded speed. A response-time
   difference is exactly the class of thing the controller exists to
   absorb, and G3 confirms it does: both wheels reach cruise and hold
   it.

What survives: the raw numbers, as an observation in the capture.
Not a mechanism, not a diagnosis, and not something to build a config
field around. The issue file I wrote
(`tovez-wheels-are-not-matched-and-lag-is-chassis-wide.md`) is
retitled below.

### 2.2 The legs really do curve, and the knob this sprint tuned cannot see it

This part holds up, and it is geometry rather than a mechanism claim.

MEASURED, `ticket016/g3-600/g3-legs.csv`, six alternating +-600 mm
legs at 100 mm/s:

| leg | dir | dh [deg] | lateral [mm] | length err [mm] |
|---|---|---|---|---|
| 0 | fwd | -2.40 | -18.2 | -2.3 |
| 1 | rev | +2.87 |  -8.3 | -3.6 |
| 2 | fwd | -5.02 | -24.3 | -5.0 |
| 3 | rev | +3.45 |  +7.1 | -6.0 |
| 4 | fwd | -2.80 | -19.6 | -5.1 |
| 5 | rev | +2.61 |  -4.8 | -6.1 |

- **The heading change flips sign with drive direction** (- + - + - +),
  and the signed mean is -0.21 deg against a mean magnitude of 3.19.
  A robot that drifts accumulates; a robot with a fixed body-frame
  curvature turns one way going forward and the other way in reverse.
  This is the second signature.
- **The forward legs curve uniformly.** For a uniform arc,
  lateral = L * tan(dh/2) = 600 * tan(1.7 deg) = 17.8 mm; measured
  18-24 mm. The curvature is spread along the leg, not a kick at the
  start or end.
- **The reverse legs do not** -- lateral 5-8 mm for a similar dh means
  the heading change is concentrated near the end. Forward and reverse
  are not mirror images. Noted; not explained; not needed for the plan.

For the forward legs, 3.4 deg over 600 mm on a 114.2 mm track is
(sR - sL) = 0.0593 rad * 114.2 mm = **6.8 mm of differential ground
travel per 600 mm, i.e. 1.1%**.

**Why raising `twist_hold_gain` could not fix it.** Twist hold
(`diffdrive.cpp:615-641`) holds

```
measuredTwist = 0.5 * ((posR - posR0) - (posL - posL0))   // [encoder counts]
```

to a reference integrated from the commanded twist. It is closed
entirely in encoder space. If the encoders say both wheels travelled
600 mm and the ground says one travelled 606.8, twist hold's error is
zero and it does nothing -- at gain 2, gain 4, or gain 400. Sprint 031
spent tickets 012 and 015 on this gain (2.88 -> 2.10 deg at 12 legs
earlier today; 3.19 deg tonight), i.e. on a controller that cannot
observe the error it was being asked to remove.

**What I do not know, and the five-minute test that would settle it.**
Two hypotheses remain:

- (A) the curvature is **encoder-invisible** -- a ~1% effective-radius
  difference between the tires (0.5 mm on a ~50 mm wheel, ordinary for
  rubber), or asymmetric scrub. Encoder twist at leg end ~ 0 counts.
- (B) twist hold **is** seeing an error but cannot correct it -- e.g.
  the trim is clamped by `headroom` against `fullDutyVelocity`, or the
  speed floor is rescaling it away. Encoder twist at leg end != 0.

One 600 mm leg with `TLM FULL` captured and `posl`/`posr` read at the
end discriminates them. It was not run: `--mode g3` collects the
frames and never writes them (only `sweep` does), and I did not notice
until the robot was off the socket. UNVERIFIED. Either hypothesis has
the same practical fix for the forward case (section 3), which is why
the plan does not wait on it.

### 2.2a CORRECTION, measured after the above was written: it is start-of-leg breakaway, not curvature

Two four-leg runs with telemetry kept
(`captures/session-b-20260905/discriminator-20260905{,-v2}/`) showed the
"uniform curvature" reading in 2.2 was wrong. The same +600 mm command
from the same pose gave camera heading changes of -1.37 then +4.59 deg
(run 1) and -2.76 then +7.61 deg (run 2). A constant cannot do that, and
the camera is not at fault: on run 2's leg 2 the robot started pointed
-10.8 deg, ended at -3.2, and its travel bearing from the two position
fixes was -4.8 -- it really did end up pointing where the camera says,
and it got there EARLY in the leg. The encoder heading's first-20% slice
on that leg is the run's largest (-1.68 deg, wrong sign vs the ground)
and `i2cf` -- the driven-but-not-counting counter -- accrues in the same
slice.

One wheel breaks static friction before the other. The robot pivots
toward the wheel that has not moved; that wheel's encoder is not
counting; twist hold at gain 4 answers a 20-count twist with ~80 counts/s
of trim, which is nothing against stiction. Which wheel sticks first sets
the sign, how long it sticks sets the size (2-8 deg tonight). It is the
`cold-first-move-yaws` mechanism, persisting warm, once per move -- so
it is proportionally WORST on the short moves students actually make.

The OTOS heading (`oh`) read 0.00 on every leg despite `otos=1`; it is
not a usable reference tonight.

Consequences: `straight_trim` (ticket 019) is the right tool for a
CONSTANT mismatch and stays 0 for tovez; the mechanism proof in its host
test is still correct. The knob for THIS defect is breakaway handling.
Live-`SET` sweep results are in `captures/session-b-20260905/gain-sweep-20260905/`
and summarised in section 3a below.

### 2.3 Pivots: the slip correction is real, the residual is mechanical

MEASURED, `ticket016/g1*/`, 12 alternating +-90 deg pivots each:

| `rotational_slip` | mean\|err\| | sd |
|---|---|---|
| prior value (banner unreliable, section 2.5) | 4.604 deg | 5.077 deg |
| **0.962, verified by raw read** | **1.531 deg** | **1.775 deg** |

tovez was carrying `rotational_slip: 1.01` in
`radio-robot-lib/config/robots/tovez.json` (baked 2026-09-04) -- a value
that left every pivot 5.1% short -- plus `stop_distance` 0 and `lag` at
the 0.13 step value. Ticket 018 replaces the 1.01 with 0.962 through the
same bake path. The
0.962 number is 0.0003 from tigez's independently measured 0.9617,
which is what one expects for wheel-contact scrub on two robots of the
same build. It is set live and **not baked**; it dies at the next
power cycle.

The remaining sd of 1.8 deg, against a camera floor of 0.22-0.29 deg,
is trial-to-trial mechanical repeatability of an open-loop pivot that
stops at a predicted point. `stop_distance` (0, never measured) and a
pivot-fitted `lag` are the design-S10.2 knobs for it. Neither is a
tonight item.

### 2.4 G2 and G6 are consequences, not separate findings

G6's 500 mm square closed at 48 / 15 / 103 mm with heading residuals
inside +-3 deg on every lap -- closure is not tracking net heading, it
is tracking per-leg lateral drift, which is section 2.2's 20 mm per
600 mm leg compounding over four legs. G2's reverse arcs being 2-5x
worse than forward is the same forward/reverse asymmetry section 2.2
records. Neither needs its own fix.

The G6 bar (10.8 mm) came from gopiv, on the bench, at 600 mm sides,
WITH `pivot_overrun` tuned. The same report puts gopiv's untuned
closure at 75.6 mm. tovez's untuned 15-103 mm is that regime.

### 2.5 The bars were research bars, and one instrument was lying

- G1's sd <= 1.0 deg, G2's 10 mm, G6's 10.8 mm were carried forward
  from sprint 029 and restated tighter in 031. No board in this fleet
  has met G3's `cruise x 1.05` peak bar at any speed (029: 1.13-1.28x;
  today: 1.12-1.44x). A bar nothing has ever met measures the bar.
- `wire_get()` returns a stale reading (looks back 2.5 s, returns the
  OLDEST match), so the "(live)" config banner on every gate can be
  wrong. Filed; worked around with a raw read. The firmware is exact.
- `--mode g5` shipped sending `WHEELS_V` unsequenced -- silently
  dropped -- and passed on zero motion. Fixed today; tonight's G5 drove
  20.8-23.1 cm on all eight trials.

---

## 3. Plan to close tonight

Ordered by value per minute. Each is one ticket. Hardware time is the
constraint; everything below is written so hardware is the LAST step
of each item, not the first.

### P1 -- Bake `rotational_slip = 0.962` for tovez. ~20 min, no hardware.

Source edit in the tovez robot config / `shims.cpp` default, one host
test pinning the value reads back over the wire. Measured 3x
improvement; nothing else this sprint is as cheap or as certain.

### P2 -- Add a per-robot straight-line trim. ~90 min, sim-validated. (SUPERSEDED for tovez by 2.2a)

Ticket 019 adds `straight_trim` [1] (default 0): a bias on the twist
REFERENCE so the encoders are deliberately made to twist by the amount
that cancels a CONSTANT ground-side mismatch, with a host-harness
plant-in-the-loop test proving twist hold is blind to an
encoder-invisible curvature and that the trim cancels it.

**As written before the discriminator ran, this section planned to bake
tovez's trim at +1.1%. That is withdrawn.** Section 2.2a shows tovez's
leg yaw is a variable, sign-inconsistent breakaway event on direction
reversal, not a constant curvature; a constant trim sized from one leg
would make the next leg worse. The field ships (default 0 everywhere,
harmless, and the right tool for a robot that DOES have a constant
mismatch), the mechanism proof ships as a regression test, and tovez's
value stays 0. Section 3a records what was tried against the real
defect instead.

### P3 -- Restate the release criteria to what students need, and record the research bars as failed. ~30 min, no hardware.

Proposed release bars for the student firmware:

| what | bar | status tonight |
|---|---|---|
| 90 deg pivot | mean\|err\| <= 3 deg | **met** (1.53) |
| 600 mm forward leg | \|dh\| <= 1.5 deg | not met -- breakaway on reversal, see 2.2a / 3a; no P2 fix |
| 500 mm square, 1 lap | closure <= 50 mm | 2 of 3 laps met |
| `RUN` verbs / blocks drive | drives | **met** (ticket 017) |
| G5 step | robot moves, no oscillation | **met** |

The research bars (G1 sd <= 1.0, G2 10 mm, G6 10.8 mm, G3 peak x1.05)
are recorded FAILED in ticket 016's closing note with this document
as the analysis, and moved to one issue for a future sprint with the
two measurements that sprint needs first (`stop_distance`, the
encoder-twist discriminator in 2.2).

### P4 -- Close. ~20 min.

- Ticket 014 (canary/pyOCD): never run; convert to an issue, close the
  ticket as deferred. It is instrumentation, not release-blocking.
- Ticket 016: closing note already written; append P1-P3's results.
- Retitle the wheel-asymmetry issue to what the data supports:
  "tovez's straight legs curve ~1.1% (encoder-visible or not:
  UNVERIFIED); twist hold cannot correct an encoder-invisible
  curvature by construction."
- `close_sprint`, merge to master (P1/P2 are source; the full suite
  runs in `close_sprint`).

### What this plan deliberately does not do

- Does not chase the reverse-leg profile, the pivot sd, `stop_distance`
  or `lag`. All real, none release-blocking, all recorded with the
  data to resume from.
- Does not put the OTOS heading in the control loop. That is the
  principled fix for 2.2 (it observes ground heading, which the
  encoders cannot) but it is a bus-risk change
  (`run-probe-bricks-the-board`, `tovez-otos-silent-on-i2c`) and not
  a tonight change.

### Order of operations

P1 and the P2 code+sim run with no hardware. When the robot is back
on the socket: P2's one G3 run (5 min), then P3/P4. If the robot does
not come back tonight, P2 ships with trim 0 (no behaviour change) and
tovez's 1.1% goes in the issue as UNVERIFIED -- the students still get
P1 and ticket 017.

---

## 3a. Live-`SET` sweep against the breakaway yaw (added 2026-09-05, late)

Four alternating +-600 mm legs per configuration, camera heading change
per leg, all at cruise 100 with `rotational_slip` 0.962, telemetry kept
(`captures/session-b-20260905/gain-sweep-20260905/<tag>/`). Baseline is
the two discriminator runs (8 legs). Leg 2 in every run is the forward
leg that starts immediately after a reverse leg.

**Where the baseline's `accel 300` came from** (found afterwards):
`test/test.ts:335` `openLoopProfile()` -> `setLimits(300, 300, 200, 90)` is
called only from RUN handlers, and the ticket 017 check ran
`RUN:straight:8` before every gate -- so the whole session ran on the
RUN open-loop profile, not the fleet default of accel 400 that a
student block program gets. A 400 run is recorded in the table below
so the 800 bake is defended against the real default.

| config | leg 0 | leg 1 | leg 2 | leg 3 | mean\|dh\| | max |
|---|---|---|---|---|---|---|
| **baseline** gain 4, v_floor 70, accel 300 (8 legs) | -1.37 / -2.76 | +1.65 / -2.64 | +4.59 / +7.61 | -6.65 / -1.72 | **3.62** | 7.61 |
| gain 20 | +17.06 | -5.34 | +0.68 | (margin) | 7.69 | 17.06 |
| v_floor 150 | +1.11 | -2.08 | +8.89 | +1.04 | 3.28 | 8.89 |
| accel 800 (run 1) | +3.45 | +1.86 | +1.39 | +0.38 | 1.77 | 3.45 |
| accel 800 (run 2) | +1.62 | -0.95 | -0.72 | +0.45 | 0.94 | 1.62 |
| **accel 800, both runs (8 legs)** | | | | | **1.35** | **3.45** |
| accel 400 / decel 400 -- the FLEET DEFAULT (run 1) | +0.58 | +0.87 | +0.58 | +1.01 | 0.76 | 1.01 |
| accel 400 / decel 400 (run 2) | +0.51 | -0.09 | -2.33 | +2.55 | 1.37 | 2.55 |
| **fleet default, both runs (8 legs)** | | | | | **1.06** | **2.55** |

- **Gain 20 is destabilising**: leg 0's encoder twist ran to +125 counts
  and the ground to +17 deg -- the hold overshoots the breakaway instead
  of damping it. The gain axis is closed in both directions (2 -> 4 did
  nothing earlier today; 4 -> 20 is worse).
- **v_floor 150 reduces breakaway EVENTS** -- `i2cf` per leg fell from
  12-43 to 1-6 and encoder twist from 20-40 counts to 1-29 -- **but not
  the worst-case ground yaw**: leg 2 still turned 8.9 deg with an
  encoder twist of -1 count. On that leg the yaw is entirely invisible
  to the encoders.
- **The worst leg is always forward-after-reverse.** +4.59, +7.61, +8.89
  across three runs (gain 20's +0.68 is the exception). Forward after a
  pivot (leg 0) is 1-3 deg. A direction reversal is where one side takes
  up gearbox backlash / breaks loose before the other, and the encoders
  sit on the motor side of that backlash, so they cannot see it.

**Conclusion.** No controller constant reachable over the wire fixes
this, because the defect is invisible to the only sensor the controller
closes on. What would: (a) a ground-referenced heading in the loop --
the OTOS is present but its heading is not updating in telemetry
tonight (`oh` = 0.00 on every leg; see
`clasi/issues/tovez-otos-silent-on-i2c-intermittently.md`), the IMU is
untried; (b) mechanically, a backlash/free-play check on tovez's
gearboxes and wheel hubs; (c) at the block level, a deliberate short
symmetric "settle" before a forward move that follows a reverse. None
is a tonight change. The release ships with the baseline config plus
the slip bake, and the student-facing bar is set from the baseline
numbers below.

**Ramp check on the accel result (before believing it).** Peak
frame-to-frame wheel acceleration and time-to-90 mm/s from the kept
telemetry, per leg:

| config | peak ramp [mm/s^2] | time to 90 mm/s [s] |
|---|---|---|
| baseline, accel 300 | 759, 864, 955, 889 | 0.28, 0.29, 0.24, 0.29 |
| v_floor 150 | 1719, 1519, 1394, 1333 | 0.17, 0.23, 0.13, 0.23 |
| accel 800 (run 1) | 873, 894, 886, 843 | 0.25, 0.24, 0.24, 0.28 |

`accel 800` did NOT change the physical ramp -- the drivetrain already
ramps at ~850 mm/s^2 at accel 300 (which is also why G4's "<= 1.5 x
accel" bar fails at 300: the limit is not what governs the ramp). So
run 1's 1.77 deg mean has no mechanism behind it and is, until the
second run says otherwise, a favourable n=4.

**The second run held.** Over 8 legs accel 800 gives mean|dh| 1.35 deg
(sd 1.36) against the baseline's 3.62 (sd 4.26), max 3.45 vs 7.61, and
the forward-after-reverse legs went from +4.59/+7.61 to +1.39/-0.72;
`i2cf` per leg fell from 12-43 to 2-5. A replicated 2.7x with every leg
under 3.5 deg is enough to ship for students. The MECHANISM is still
unverified -- the ramp did not change, so the leading hypothesis is that
a commanded ramp far below what the wheels do anyway (300 vs ~850)
saturates the wheel PID early and winds the twist hold up during the
very window the breakaway happens in; at 800 the command tracks the
plant. Ticket 020 was dispatched to bake it per-robot with that caveat -- and
then the fleet-default run above came in: at accel 400 / decel 400 the
same four legs read 0.58 / 0.87 / 0.58 / 1.01 deg (mean 0.76, max 1.01,
`i2cf` 1-4). Better than 800. So the whole leg-yaw episode was the RUN
open-loop profile's 300/300 (set by my own `RUN:straight:8` check and
never cleared), which student block programs never enter. The correct
change is NOT an 800 bake but fixing `openLoopProfile()`'s literals to
the fleet default (400/400) and leaving tovez's accel unbaked; 020 is
being redirected accordingly. Replication of the 400 run to n=8 is in
`gain-sweep-20260905/accel400b/`. `v_floor 150` is the only
setting that physically changed the start of the leg (ramp x1.7, time
to speed halved) and it reduced breakaway EVENTS without reducing the
worst-case ground yaw.

---

## 3b. Release build on the field, and the pivot law (added last)

`captures/session-b-20260905/release-verify/`. Build 1.20260905.1 from
clean, bakes proven in the scratch source, flashed over the LAN, wire
check PASS with no `SET` sent (slip 0.962 / trim 0 / accel 400 from
power-on). Four 600 mm legs with no live SETs: +0.44 / -2.08 / +2.38 /
-0.92 deg -- mean 1.46, max 2.38, every leg inside the student bar.

**The 180 deg pivot over-rotates by +8.1 deg, twice identically.** With
the 1.01-slip dance earlier tonight (90 -> ~85, 180 -> 177.8) this fits
an AFFINE pivot law, actual = 1.027 * cmd - 7 deg, which
radio-robot-lib's own 2026-07-29 note on this chassis already recorded.
`rotational_slip` is a pure scale, so 0.962 can zero the error at one
angle only; it was fitted at 90 and is exact there (G1: 1.53 deg mean)
and 8 deg over at 180. The constant term is design S10.2's
`stop_distance` / pivot-fitted `lag`, still unmeasured on tovez -- the
first item for the next sprint, and now with a clean two-point
measurement to start from.

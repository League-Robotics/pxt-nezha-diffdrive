---
status: in-progress
sprint: '044'
tickets:
- 044-001
- 044-002
- 044-003
- 044-004
- 044-005
- 044-006
- 044-007
- 044-008
- 044-009
---

# OTOS fusion drifts worse than the raw sensor, GO_TO_W stalls on targets behind, and legs miss cross-track

## Summary

The 2026-10-28 camera-truthed 100 m run (vevov, 202 random `GO_TO_W`
legs over 54 min, no re-zero; `captures/vevov-otos-drift-20261028/`)
found three faults that together explain why six months of OTOS work
has not improved positioning:

1. **`Odometry::fuseHeading()` makes heading worse than the OTOS alone.**
   Fused heading ended **+79°** off the camera; the raw OTOS **+43°**;
   encoders −50°.
2. **The OTOS gyro has a steady bias** of about **+50°/hour** that
   nothing estimates or removes. Removed, the OTOS's own pose holds
   **12 cm / 3° rms** over 100 m — far better than any other source.
3. **Legs are open-loop after planning.** Arrivals are 2.2 cm median /
   6.0 cm p90; along-track error is tiny (sd 0.56 cm), almost all of
   it is cross-track (sd 3.1 cm) — heading error at the pivot carried
   down the straight. And 11 of 202 legs (5%) **stalled**: target
   nearly behind with a positive bearing, killed by `wrongWay`.

## Evidence

Scripts in `tests/dev/`: `otos_arm.py` (sensor arm), `otos_drift.py`
(the run), `otos_drift_report.py` (scoring), `otos_fusion_replay.py`
(leg-resolution replay of alternative fusions), `otos_gyro.py`
(stationary drift). Logs: `arm1.json`, `drift1.jsonl`,
`drift1_scored.csv`, `gyro1.jsonl`.

Replay of the 100 m log against the camera:

| pose | 50 m pos / head | 100 m pos / head | 2nd-half rms |
|---|---|---|---|
| firmware fused (logged) | 34 cm / +35° | 40 cm / +79° | 38 cm / 66° |
| encoders only | 63 cm / −45° | 92 cm / −50° | 76 cm / 39° |
| OTOS raw x/y/heading | 23 cm / +20° | 25 cm / +43° | 23 cm / 34° |
| OTOS, bias learned causally from encoders | 8 cm / −3° | 19 cm / −4° | 12 cm / 3.3° |
| OTOS, bias rate fitted on first half | 10 cm / −1° | 21 cm / +1° | 13 cm / 1.6° |

The causal estimator is a running least-squares fit of
(OTOS heading − encoder heading) on [1, time, encoder net turn] using
only earlier legs; it converged to +52°/h against the camera's +47°/h.
The encoder-net-turn term soaks up the encoders' own 2% track-width
error, so the encoders need not be well calibrated to teach the bias.

Measured geometry: OTOS sits **4.3 cm behind** the pivot centre,
0.2 cm left (rms 0.44 cm, 12 pivots); OTOS linear scale ≈ 1.009.

## Causes

### 1. `fuseHeading()` re-anchors on every rejected sample (`src/motion/odometry.h:72-91`)

A sample whose step disagrees with the encoders' by > 1° + 30% is
dropped and `offset_ = heading_ - sensor` re-anchors. The encoders'
error over that step is thereby written permanently into `offset_`
and never pulled back. Over 100 m that added 36° on top of the OTOS's
own drift, in 1.5–6° single-leg jumps, weakly correlated with I2C
read failures (1610 `i2cf` over the run, ~8/leg; corr 0.30).

The design also discards the OTOS's own x/y and lays encoder distance
along the OTOS heading — but the OTOS's x/y is the better track.

### 2. No gyro bias handling

`OtosPort::begin()` runs the chip's 255-sample IMU calibration once at
boot and nothing after. The residual bias (+47…52°/h here) integrates
forever. See *Research* for why the chip cannot fix this itself.

### 3. GO_TO_W wrong-way stall (`motion_engine.cpp:74-97`, `segment.h:95-100`)

There is no deliberate reverse decision: `theta = wrapToPi(2*bearing)`
turns a target at bearing +177° into a −5° reverse arc that skips the
50° pivot split. Backing off from rest the chassis veers CCW; on a CW
arc that is "wrong way", and once yaw progress passes 40 counts
(~3°) `service()` silently drops the segment — reported as a normal
`reason=stop`. `wrng` incremented on exactly the 11 stalled legs.
Negative bearings (CCW arcs) never stall. This is very likely the
unexplained early-termination in
[goto-under-closed-profile-terminates-legs-early](high/goto-under-closed-profile-terminates-legs-early.md).

### 4. Leg execution has no world-frame feedback

`goToW()` plans once, then runs encoder-counted segments. A pivot that
lands 2° off (rotational slip varies per surface/speed) becomes
~1.7 cm cross-track over a 50 cm straight. Cross-track bias by leg
kind: reverse arcs +3.9 cm, forward arcs −2.4 cm, pivot+straight
−1.7 cm; along-track ≤ 0.24 cm everywhere.

### 5. The OTOS is never read while the robot is idle

`tickDrive()` reads the OTOS every 4th tick and "every tick once the
drive goes idle" — but TS only calls it inside `while (_tickDrive())`,
so once a move ends nothing reads the chip. TLM `ox/oy/oh` and the
fused heading are frozen caches at rest (a 14-minute stationary test
logged exactly +0.96° throughout). Any at-rest estimator (ZARU) needs
an idle read path. Workaround for host tests: a zero-speed
`MOVE_V 0 0 300` runs the tick loop without turning the wheels.

### Stationary result

With the cache refreshed, vevov **sitting still** (encoders unchanged)
gained **+13.1° in ~16 min ≈ +50°/h**, then ~+60°/h in the following
samples — the same rate as the 100 m run. The drift is a **time-based
gyro bias**, not rotation-driven scale error. (`gyro1.jsonl`; the
stale-cache attempt is kept as `gyro1-stale-cache.jsonl`.)

Formal 30-min stationary run (`otos_gyro.py`, started 16:58 2026-10-28,
right after the 100 m run; `gyro1.jsonl`/`gyro1.out`). Valid rows are
0–58 (19.3 min): at row 59 (19.7 min) the robot was moved (posl 8→11,
posr 31→194, OTOS +77°), and everything after is discarded. The camera
pose froze bit-identical from row 26 (8.7 min), so only rows 0–25 are
camera-verified; rows 26–58 rely on the encoders alone.

| Window | Rows | Min | OTOS rate | Resid sd |
|---|---|---|---|---|
| camera-verified | 0–25 | 8.3 | +44.2°/h | 0.12° |
| before step | 0–38 | 12.7 | +45.4°/h | 0.11° |
| after step | 39–58 | 6.3 | +44.7°/h | 0.09° |
| all valid | 0–58 | 19.3 | +40.7°/h | 0.32° |

At row 39 (13.0 min) OTOS heading **stepped −0.61°** between two samples,
with both encoders and OTOS x/y unchanged: a discrete jump, not drift.
That step alone caused the interim "falling rate" (+43 → +33°/h between
halves); on either side of it the rate is a steady **~+45°/h**.
Rate over ~3.3-min windows: 38.0, 46.4, 48.9, 39.5°/h, so it varies by
±5°/h at most, not a trend. Consequences for the bias tracker
(ticket 002): a constant ~+45°/h is a good prior for vevov in this
state, and continued low-gain adaptation is still needed (across power
cycles and temperature), but there is no evidence of fast in-session
wander. ZARU must tolerate discrete heading steps: re-anchor heading on
a step, do not fold it into the bias.

## Research

SparkFun's OTOS firmware is public (MIT, STM32:
github.com/sparkfun/SparkFun_Optical_Tracking_Odometry_Sensor,
`Firmware/SFE/Src/main.cpp`, `otosKalmanFilter.cpp`). Read directly:

- Heading is **only the integrated LSM6DSO z-rate**, `(raw - gyrOffsetZ)
  * angularScalar`, through a constant-acceleration Kalman filter with
  **no bias state**. The optical sensor never touches heading.
- At power-on it waits 100 ms and runs `calibrateImu(64)` (~0.15 s)
  blind — the source comment: "we don't know if we are [motionless]…
  hopefully the user will trigger a proper calibration later".
- `calibrateImu(n)` is a plain mean of n ≤ 255 samples at 416 Hz
  (≤ 0.61 s), blocking the chip's pose loop. Called while moving, it
  stores the rotation rate as bias.
- **No online, stationary or temperature compensation.** The LSM6DSO
  temperature register is never read; SparkFun staff confirm "no
  temperature compensation" and quote ±0.010 dps/°C ZRO drift
  (0.6°/min per °C).
- Signal-process flags (`enLut/enAcc/enRot/enVar`) affect x/y only.
  The angular scalar is one symmetric value applied after bias
  subtraction — it cannot cancel a time drift.
- Raw gyro registers exist (0x44–0x4F, gyro Z 0x48/0x49) though the
  library does not expose them; writing the position registers
  re-seeds heading, so the host can correct heading at any time.
- FTC localizers (Road Runner, Pedro Pathing) only call
  `calibrateImu()` at init and tune the angular scalar over 10 turns;
  none track bias. FTC matches are 2.5 minutes.

Why the chip cannot "just calibrate it out" (partly inference):

1. **The bias is not fixed.** It moves with temperature (our 0.0144 dps
   is ~1.4 °C of ZRO drift — motor drivers and the board warm up), with
   each power-on, and wanders slowly. A rate learned once does not hold.
2. **A 0.61 s average is too short.** At ~3.8 mdps/√Hz the 255-sample
   mean has ~0.005 dps (≈18°/h) 1σ error; the 64-sample boot mean ≈35°/h.
   At ±2000 dps full scale one LSB is 70 mdps, coarser than the noise,
   so the mean can also carry a fraction-of-an-LSB quantization bias.
   50°/h is about 3σ of calibration error alone.
3. **The chip cannot tell when it is still** — it has no knowledge of
   the motors, and vibration or a slow turn looks like bias. The robot
   does know (encoders, commanded idle), which is why bias tracking
   belongs on the host.

Standard practice elsewhere: zero-angular-rate updates (ZARU) whenever
the platform is known stationary, and a heading+bias filter that makes
bias observable from wheel odometry while moving.

Our firmware: `OtosPort::begin()` already requests 255 samples at
boot, once, cold, and never again.

## Plan

### Hardware configurations (hard requirement)

Most of the fleet has **no OTOS**. The estimator and the closed-loop
leg control must work, and be host-tested, on all three:

| config | heading | position | bias source |
|---|---|---|---|
| OTOS | OTOS gyro − bias | OTOS optical x/y (arm-corrected) | ZARU + encoders |
| gyro only (non-OTOS IMU) | gyro − bias | encoder distance along heading | ZARU + encoders |
| neither | encoders | encoders (today's odometry) | — |

The other gyro part is **not chosen yet**: define a generic gyro source
interface (rate and/or integrated heading, read status), implement it
for the OTOS first plus a simulated gyro for host tests; the real
driver for the other part is a follow-on ticket once the part is
picked. Configuration is detected at boot (probe), never assumed, and
a sensor that disappears or freezes mid-run degrades to the next
configuration down without a heading jump.

### A. Pose estimator (replaces `fuseHeading`)

- Position: integrate the **OTOS's own x/y** increments, rotated into
  the odometry frame by the bias-corrected heading, with the 4.3 cm arm
  applied in software. Encoders remain the fallback when the OTOS
  is absent, frozen or reads fail.
- Heading: OTOS heading minus an estimated bias angle `b(t)`.
- **Idle read path**: keep sampling the OTOS (a few Hz) while no
  motion is active, so at-rest drift is seen and TLM is live.
- Bias: two observations, both cheap on the micro:bit:
  - **ZARU** — while the drive is idle and both encoders are
    unchanged, every OTOS heading change is bias: update the rate
    estimate with a low gain, and subtract the accumulated change.
    Optionally re-run the chip's `calibrateImu(255)` after ~1 s of
    verified stillness (blocks the chip ~0.6 s — only when still).
  - **Encoder comparison during motion** — running fit of
    (OTOS − encoder heading) on time and encoder net turn, as the
    replay does; only straight-ish ticks if needed.
- Rejection never re-anchors permanently: a bad sample is skipped,
  and the reference stays the sensor.
- Telemetry: add `bias` (cdeg/min) and a reject counter to TLM FULL.
- Host test: feed the 100 m log's rest samples through a host build of
  the estimator; assert it reproduces the replay's numbers.

### B. GO_TO_W wrong-way stall

- Make "target behind" an explicit policy: either pivot-then-straight
  (simple, always forward) or a deliberate reverse straight; never a
  near-zero-yaw reverse arc.
- Report a wrong-way termination as its own `reason` and surface
  `wrng` in STATUS.

### C. Leg accuracy (target: < 1 cm median, < 2 cm p90)

- **Pivot closure on fused heading**: end the pivot on the estimator's
  heading, not on encoder counts.
- **Heading hold on the straight**: steer the straight toward the world
  target with the estimator's pose (cross-track feedback), so pivot
  error and slip are corrected while driving.
- **Final residual**: a small correction (≤ ~3 cm) drives a short
  straight/reverse rather than re-pivoting up to 90°.
- Measure with `otos_drift.py` on the same field; compare
  cross-track/along-track decomposition before and after.

### Acceptance

- 100 m random run, no camera re-zero: pose error ≤ 15 cm rms,
  heading ≤ 3° rms (second half), zero wrong-way stalls.
- Arrival miss median < 1 cm, p90 < 2 cm.
- Stationary 30 min: heading change < 2° after the ZARU estimator settles.

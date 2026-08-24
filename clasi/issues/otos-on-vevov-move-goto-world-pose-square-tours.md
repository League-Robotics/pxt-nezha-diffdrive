---
status: pending
sprint: '011'
---

# OTOS on vevov: move()/goTo() + world-pose square tours

## Description

vevov navigates on encoder odometry alone. Odometry accumulates error that
nothing ever corrects: on a 60 cm square tour the best encoder-only runs
close at 9–54 mm with 1–7° of residual heading error, and the spread between
identical runs shows the remaining error is an intermittent per-turn event,
not a constant that can be calibrated away.

A SparkFun OTOS optical tracking sensor gives an independent world-frame
fix (position + gyro heading). Its driver is already ported and
bench-validated on the zeguz rig (`otos_port.{h,cpp}`, commit c6d81a2):
product id 0x5F, gyro tracks a 360° servo, and reported travel stays in the
world frame regardless of sensor rotation.

The sensor now moves onto vevov and becomes the world-pose authority **at
move boundaries only**. Stakeholder doctrine: moves run purely on encoder
odometry; the OTOS is read at the start and end of a move to establish where
the robot actually is, and the next move is planned from that fix. It never
steers a move in flight.

Two functions are wanted, shaped after the V6 protocol spec
(`radio-robot-lib/docs/protocol-v6-spec.md`, MOVE §5.1 / GOTO §5.3 /
SEED §5.5), plus two square tours built on them that hold world position and
heading through the OTOS.

## Proposed fix

Stakeholder decisions on record:

- **goTo steering**: no mid-move retargeting; **start-of-move** retargeting
  only. Pivot in place only when the bearing error is large (turn-first,
  reference default 50°); otherwise one constant-curvature arc computed
  fresh from the OTOS fix — yawing while driving absorbs a few degrees of
  residual bearing error. Arrival nudges are bounded, each a fresh
  start-of-move retarget.
- **Lever arm** (sensor offset from centre of rotation): self-calibrated by
  pivot, not measured with a ruler.
- Reference navigator constants adopted: turn-first 0.8727 rad (50°),
  arrival tolerance 10 mm, max 6 nudges, segment timeout
  `min(ideal*3 + 3000, 20000)` ms.

### 1. `otos_port.{h,cpp}` — lever arm + centre-frame seed

Port the remaining pieces of the reference driver
(`radio-robot-elite/src/firm/hardware/generic/real_otos.cpp`):
`sensorToCentre()` / `centreToSensor()` with `offsetX_/offsetY_/offsetYaw_`
members, so `read()` returns the **robot-centre** pose; `setOffset()`;
`setPose(x, y, h)` (centre-frame seed, generalizing today's `zeroPose()`).
The chip's own offset register stays zeroed — applying the arm in both
places double-corrects (reference measured a 42.7 mm phantom circle on a
pure pivot).

### 2. `shims.cpp` / `protocol.cpp` — shims, boundary cache, dual-pose TLM

`otosSetOffset()`, `otosSetPose()`, and `seedPose(x, y, h)` with V6 SEED
semantics: write **both** pose sources (OTOS and Rig odometry) so their
later divergence is the drift measurement. Protocol TLM extends to
`TLM:t:x:y:h:ox:oy:oh` reporting the **cached** OTOS pose — the protocol
fiber must never touch the I2C bus, since an OTOS transaction interposed in
the Nezha encoder's select→read window destroys the encoder sample
(Phase F). The cache refreshes only when the motion layer takes a boundary
fix on the tick fiber.

### 3. `main.ts` — the functions (cm/deg student units)

- `seedPose(x, y, h)` — declares the world origin.
- `goToWorld(x, y)` — blocking; each phase is `startMove` +
  `while(_tickDrive())`: (1) boundary fix via live `otosRead()`; (2) if
  `|bearing| >= 50°`, pivot by the bearing using the existing exact-turn
  taper machinery, then re-fix; (3) one constant-curvature arc to the
  target, reusing the tangent-circle math already in `startGoTo`
  (`main.ts:197`) generalized to a world-frame target; (4) re-fix, and if
  residual > arrival tolerance and nudges < 6, repeat from (2). Overall
  timeout backstop.
- `otosConnected()`, `worldX()/worldY()/worldHeading()` cached accessors.
- `move(distance, yaw)` is unchanged — already V6 MOVE-shaped (distance or
  angle stop condition plus an internal deadline lease).

### 4. `test.ts` — tours and calibration

- `RUN:6` GOTO tour: `seedPose(0,0,0)`, then corners (60,0) (60,60) (0,60)
  (0,0) cm via `goToWorld`, logging per-corner OTOS residuals.
- `RUN:7` MOVE tour: per corner, explicitly read the OTOS, compute the arc
  in test code, issue a single `move(s, theta)`; no nudges. The contrast
  case for goTo.
- `RUN:8` lever-arm calibration: offsets zeroed, 8 × 45° pivots with an
  OTOS fix logged at each rest (`OCAL:` lines), then a 300 mm straight leg
  for `offset_yaw`. Robot on the mat, not the stand.
- `RUN:1` (encoder-only tour) stays as the A/B baseline.

### 5. `tools/`

`otos_levercal.py`: drive RUN:8 and least-squares fit
`x_i = cx + cos(h_i)·ox − sin(h_i)·oy` (and the y equation) over the eight
fixes for `offset_x/offset_y`; straight-leg displacement vs heading gives
`offset_yaw`. `tour_capture.py` / `tour_chart.py` parse the 7-field TLM and
overlay the encoder path against OTOS fixes, with closure computed from the
OTOS.

## Verification

- Lever arm: a commanded ±360° pivot leaves the reported centre within
  ~10 mm (the reference's uncorrected failure was 42.7 mm).
- GOTO tour: per-corner OTOS residual within the arrival tolerance (10 mm);
  closure measured on both OTOS and encoder pose and charted.
- MOVE tour completes with per-leg curve computation, residuals logged.
- Dual-pose TLM present in the capture CSV; encoder-vs-OTOS divergence plot
  is sane.
- Compare both tours against the `RUN:1` encoder-only baseline (9–54 mm
  closure at 60 cm sides).

## Related

- Driver port and rig validation: commit c6d81a2; rig notes in
  `testrig.ts`, `tools/otos_bench.py`.
- V6 spec: `/Volumes/Proj/proj/RobotProjects/radio-robot-lib/docs/protocol-v6-spec.md`.
  The **full wire protocol is out of scope here** and is a follow-up work
  package (GET/SET, TLM subscription with `thdr:`, `ok`/`err`/`done` ids,
  the uppercase/lowercase case flip, SEED/CAL verbs). The spec was mid-edit
  as of 2026-08-20 (field separator changing from colons to spaces, one or
  two verbs changing) — re-read it before starting that work.
- Reference navigator algorithm (deleted from radio-robot-elite HEAD in
  commit 88dd9ad8; read via `git show 88dd9ad8^:src/firm/motion/...`):
  `navigator.cpp` turn-first policy, `arc_solver.cpp` tangent-circle
  solver, planner terminal fine-align.
- vevov.json (`radio-robot-elite/data/robots/`) carries placeholder OTOS
  and navigator sections copied from tovez; measured values go there only
  with stakeholder approval.
- AprilCam ground-truth of the OTOS world frame is pending the camera's
  return.

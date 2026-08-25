---
status: in-progress
sprint: '011'
tickets:
- 011-001
- 011-005
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

## Bench Campaign Procedure (sprint 011 ticket 005)

**This section does not run the campaign.** Everything below is a
handoff for whoever executes the bench run — the stakeholder, or a
future hardware-validation sprint. Nothing in this section was
performed while writing it; no pass/fail is recorded here. This
mirrors sprint 006 ticket 006's precedent for the same kind of
handoff (`clasi/sprints/done/006-motion-correctness-goto-geometry-and-odometry-truth/issues/brick-reset-odometry-teleport.md`,
"Bench Checklist (stakeholder handoff)").

### Evidence this procedure is built on

A real bench session on vevov, 2026-08-25, over the zavaz radio relay
with overhead-camera ground truth, changed what a valid campaign has
to check. Full detail: `clasi/issues/tour-corner-fixes-are-stale-cache.md`
("RESOLVED ON HARDWARE" and "MECHANISM PINNED" sections). Summary:

1. Two 20 cm legs, camera fix before/after each. Cleanest leg: camera
   (tag 53, mount offset registered) **19.34 cm** (ground truth); live
   OTOS fix (`RUN:fix` -> `OCAL`) **19.15 cm** (2 mm error — the most
   accurate instrument on the robot); encoders (`STRAIGHT:end`)
   **20.1 cm** (+7.6 mm overrun); telemetry `ox`/`oy`/`oh` columns
   **frozen, byte-identical** `(386, 345, -16504)` through the whole
   drive.
2. The OTOS sensor itself is healthy and beats the encoders. What can
   go stale is the telemetry **projection** — `ox`/`oy`/`oh`, the
   columns `tools/tlm.py`'s `otos_cm()` reads and the columns
   `tour_capture.py` writes to its pose CSV. `logFix()`/`RUN:fix` is a
   **different, live** path (`test/test.ts:79-89` ->
   `diffDrive.readWorld()` -> `otosRead()`) and is correct. The
   telemetry cache's only writer is an explicit `logFix()`/`RUN:fix`
   call — motion never refreshes it, so a leg that runs without one
   leaves the projection holding whatever the last fix wrote.
3. At rest, before any motion, the two pose sources were **~11 cm
   apart**: encoders (497, 302) vs. the OTOS telemetry cache
   (386, 345). Two pose sources can legitimately start out disagreeing
   — this alone is not a fault signature.
4. **Scope limit, stated plainly:** vevov runs the **older 12-column
   `POSE` firmware** (`thdr seq now flags x y h ox oy oh vl vr i2cf`)
   and does not answer `STATUS`. This is confirmed on **that build
   only** — current master emits the 20-column `FULL` frame and has
   **not** been confirmed to freeze the same way. Do not overstate
   this finding as a master-firmware defect; it is a vevov-firmware
   finding until re-tested there.

Consequence for this procedure: the telemetry `ox`/`oy`/`oh` columns
are **never** trusted as OTOS ground truth on their own. Every tour
must be bracketed with an independent, live cross-check, and every
captured leg must be screened for a frozen OTOS projection before its
numbers are used.

### 0. Prerequisites already shipped — do not re-debug tooling here

This bench session assumes the following already work, by shipped
path — nobody running it needs to design or implement anything:

- **`tools/tour_capture.py --tour {world,robot,wheels}`** (sprint 011
  ticket 001, done) sends `RUN:tour:world` / `RUN:tour:robot` /
  `RUN:tour:wheels` — never a bare numeric `RUN:<n>` — and records the
  v6 telemetry pose stream to `<out-prefix>_pose.csv` (columns
  `t_host, t_dev_ms, x_mm, y_mm, h_cdeg, ox_mm, oy_mm, oh_cdeg`).
- **`tools/leg_analysis.py`** (sprint 011 ticket 002, done) turns that
  pose CSV into a per-leg table: commanded target, believed (encoder)
  pose, classification, and — as of this ticket's evidence above — an
  `otos_stale` flag (`OTOS_STALE = 'otos-stale'`,
  `detect_otos_staleness()`, `tools/leg_analysis.py:271-303`) plus an
  `otos_distance_cm` figure per leg, built specifically around the
  frozen-projection finding above.
- **`tools/otos_levercal.py --radio --verify`** (sprint 005 ticket
  006's retarget) sends `RUN:cal:1` and reports the residual arm
  directly — confirmed present and already speaking the named `RUN`
  vocabulary by inspection of the current working tree at the time
  this procedure was written; re-confirm this is still true (`git log
  -- tools/otos_levercal.py`) before relying on it, since sprint 005's
  own ticket metadata still marked it "open" as of sprint 011
  planning.
- **`tools/tour_chart.py`** plots the pose CSV (trajectory + wheel
  speed panels) — unchanged by this sprint, used as-is for the visual
  overlay.

If any of the above does not behave as described, stop and file a
finding — this bench session is not the place to fix tooling.

### 1. Pre-flight — confirm camera calibration BEFORE trusting any number

Numbered pre-step, because every ground-truth figure in this
procedure depends on it:

1. Call `list_cameras` (aprilcam MCP `mcp__aprilcam__list_cameras`, or
   the v1 server's `list_cameras`) and check the `calibration_stale`
   field for the camera you intend to use.
2. Use **`arducam-ov9782-usb-camera`** (`tools/camlink.py`'s `CAM`
   constant, also vevov's/tovez's registered camera) — **not**
   `arducam-ov9281-usb-camera`, which frequently returns "no frame
   available" on this rig.
3. **As of 2026-08-25** (confirmed by running `list_cameras` while
   writing this procedure): **both** main-playfield cameras report
   `calibration_stale: true` —
   `arducam-ov9782-usb-camera` (`playfield: main-playfield`) and
   `arducam-ov9281-usb-camera` (`playfield: main-playfield`). **This
   must be resolved (recalibrate the playfield) before any campaign
   number produced by this procedure means anything.** Re-check at
   campaign time — do not assume this has resolved itself since this
   procedure was written.

### 2. Pre-flight — robot placement: FLOOR, not the bench stand, and RECORD which

`tools/robotlink.py`'s own module docstring states the doctrine this
procedure follows: "The bench (USB) and the playfield (radio) are not
interchangeable: the robot's wheels are off the ground on the bench
stand, so anything that needs real motion — which is everything
involving the OTOS — has to run untethered over the zavaz relay."

**A USB-tethered run on the stand produces a complete, plausible-
looking, entirely worthless tour record**: wheels spin freely, duty is
applied, and the encoders integrate a phantom trajectory exactly as if
the robot had driven — while the OTOS, correctly, reports no
displacement. This is not hypothetical: a stand-vs-floor mix-up on
this exact project (tovez, `RUN:tour:wheels`, see
`clasi/issues/tour-corner-fixes-are-stale-cache.md`'s early sections)
produced a ~52 mm "closure" from encoders while the live OTOS fixes
correctly read ~0 mm, because the chassis was on a stand and never
moved. Nothing in the firmware, the tooling, or the tour distinguishes
those two situations on its own.

Every scored campaign run in this procedure:

1. Runs **over the zavaz radio relay** (`tour_capture.py --radio`,
   `otos_levercal.py --radio`), never over USB.
2. Runs with the robot **on the mat/playfield floor**, never on the
   bench stand.
3. **Records which** explicitly in the evidence template below — "on
   the mat, over radio" is not assumed, it is written down every run.

### 3. Camera tag registration

`tools/camlink.py`'s `MOUNTS` dict carries the registered mount
offsets: **vevov is AprilTag 53**, **tovez is AprilTag 52**
(`tools/camlink.py:36-38`). Tag mount parameters are **not** persisted
across an aprilcam daemon restart — an unregistered tag reports RAW
(no parallax, no lever-arm, no mount-yaw correction), which "looks
perfectly plausible" while being the wrong position on the field
(`tools/camlink.py`'s own module docstring). `Cam.__init__` already
calls `ensure_registered()` automatically every time a `camlink.py`
session starts, so any capture that goes through `Cam()` re-registers
for free — still worth an explicit confirmation step if the daemon was
restarted mid-session: re-run `python3 tools/camlink.py --check` (the
two fixed calibration tags 10/11) or read vevov's own tag once
(`python3 tools/camlink.py --tag 53`) before trusting a fix.

### 4. Camera doctrine — restated so nobody wires this into the control loop

**AprilCam is diagnostics and scoring only. It is never in the control
loop for a move in flight.** `goToWorld`'s live steering runs purely
on the OTOS boundary fix; the camera never retargets, corrects, or
gates a move while it is executing. This project's standing rule,
already on record in this issue (`## Related`, and `sprint.md`'s own
SUC-005/SUC-006 framing): **camera at tour start and end is
permitted; camera during a tour is never permitted.** Every camera
read in this procedure happens with the robot at rest, before a tour
starts or after it has fully stopped (`TOUR:end` observed) — never
mid-tour.

### 5. Lever-arm re-confirmation — verify, do not re-derive

The lever arm is already measured and baked into `test.ts`
(`armX = -3.82 cm`, `armY = -0.07 cm`, `armYaw = 0.89 deg`,
`test/test.ts:52-59` — "eight 45 deg pivots swept the sensor around
the centre of rotation on a 38.2 mm circle, fit residual rms 1.34
mm"). This step confirms that value still holds; it does **not**
re-derive it.

```
python3 tools/otos_levercal.py --radio --verify
```

This sends `RUN:cal:1` (`leverCal(true)` in `test.ts` — applies the
already-measured arm via `applyArm()`, then repeats the same eight-
pivot sweep). The tool reports a **residual arm** in mm directly:
with the measured arm correctly applied, the sweep should collapse
from a 38.2 mm circle to (near) a point.

- **Expected**: residual arm near **0 mm** (single digits). The
  reference project's own *double*-corrected failure case was
  **42.7 mm** — nowhere near zero is a red flag, not noise.
- **If the residual is not near zero**: stop before running the tour
  campaign. The arm has drifted (remount, bump, sensor swap) and
  needs re-derivation (`otos_levercal.py --radio`, no `--verify`),
  which is a separate, out-of-scope task for this session — record the
  finding and flag it rather than pushing the campaign through on a
  known-bad arm.

### 6. The campaign runs — camera-bracketed, per repetition

For each of the two tour types below, repeat per the count in
step 7. Each repetition:

1. Confirm the robot is on the mat, radio link up (steps 1-2 above).
2. **Camera fix BEFORE.** Robot at rest, tour not yet started: record
   tag 53's `(x_cm, y_cm, yaw_deg)` — `python3 tools/camlink.py
   --tag 53` (one line) or the aprilcam MCP `where`/`get_tags` tools.
3. **Live OTOS fix BEFORE (cross-check).** Send `RUN:fix` over the
   link and record the resulting `OCAL:now:...` line (0.01 cm / 0.01
   cm / 0.01 deg units, per `test.ts`'s `logFix()` comment). No
   dedicated tool ships a bare `RUN:fix` capture today — watch the
   console, or use `tools/robotlink.py`'s `open_link()` /
   `send_until()` directly for a one-off read.
4. **Run the capture:**
   ```
   python3 tools/tour_capture.py --radio --tour world \
       --out-prefix .tmp/tour_world_RUN01
   ```
   (swap `--tour robot` for the second tour type; increment
   `RUN01`/`RUN02`/... per repetition — never overwrite a prior run's
   files). Do **not** drop `--radio` — step 2 already rules out a USB/
   tethered run for anything scored.
5. **Camera fix AFTER.** Once `TOUR:end` / the tool's own exit is
   observed and the robot is at rest: same as step 2.
6. **Live OTOS fix AFTER (cross-check).** Same as step 3.

### 7. Repetition count — name a specific minimum

**The pre-006 baseline campaign's own repetition count is not
recorded anywhere in this repository** (checked: the issue file, the
sprint 006 archive, and a repo-wide search for the 9-54 mm/1-7° and
"~70%" figures — all report only summary results, never a sample
size). This procedure does not claim to reproduce an undocumented
number.

**Minimum for this campaign: 10 repetitions of each tour type**
(10 x `RUN:tour:world`, 10 x `RUN:tour:robot` — 20 scored runs total).
Rationale: the residual-fault issue's own figure is tours completing
"~70% with near-misses" — an intermittent event at roughly a 30% rate.
At N = 10, the probability of that event appearing at least once is
1 - 0.7^10 ≈ 97%, enough to characterize the closure spread (not just
a single pass/fail) rather than one lucky or unlucky run. If a
stakeholder or a future sprint has an actual historical count for the
pre-006 campaign, that figure should supersede this one.

### 8. Cross-source validity precondition — mandatory, before any run is scored

**A run whose OTOS data cannot be told apart from a stationary robot
must be discarded, not scored.** This is not optional: it is exactly
the gap the evidence in this ticket exists to close (a frozen
projection and a genuinely motionless robot are byte-identical on the
wire).

For every captured run, before recording it in the evidence template:

1. Compute the tour's overall **encoder** displacement (pose CSV's
   first row vs. last row, or the sum of `leg_analysis.py`'s per-leg
   `believed` distances).
2. Compute the tour's overall **camera** displacement from the
   before/after camera fixes (step 6.2 / 6.5).
3. Run:
   ```
   python3 tools/leg_analysis.py .tmp/tour_world_RUN01_pose.csv \
       --out .tmp/legs_world_RUN01.csv
   ```
   Inspect the printed table's `[otos-stale]` flags (and the CSV's
   `otos_stale` / `otos_distance_cm` columns) per leg.
4. **If encoders and camera agree the robot moved a real distance,
   but a leg is flagged `otos-stale`** (OTOS delta ~0 while the
   encoders clearly moved — `detect_otos_staleness()`,
   `OTOS_FROZEN_EPS_CM = 0.1 cm`, `OTOS_STALE_MIN_ENCODER_CM = 2.0
   cm`): that leg's OTOS numbers are **invalid** for OTOS-accuracy
   scoring. Discard them — do not average a frozen 0 into the OTOS
   residual figure. The leg's encoder-vs-camera comparison is
   unaffected and still counts.
5. Apply the same check to the **whole-tour bracketing fixes** (step
   6.3 / 6.6), not only `leg_analysis.py`'s automatic per-leg flag: if
   the before/after `RUN:fix` pair shows ~0 OTOS displacement while
   the camera and encoders agree the robot travelled the full tour
   distance, discard that run's tour-level OTOS number too, for the
   same reason.
6. If encoders, camera, **and** OTOS all agree the robot did not
   move (or barely moved) on a given leg, that is a genuinely
   stationary leg — not stale, nothing to discard.
7. If encoders show real movement, the leg is **not** flagged stale,
   but OTOS and camera still disagree by more than about a
   centimetre, that is a real OTOS accuracy defect for that leg —
   **score it**, do not discard it. Discarding is only for the
   frozen-cache signature (OTOS reads ~0 while the other two sources
   agree real motion happened), never for "OTOS disagreed with
   ground truth."
8. A run where **every** leg is flagged stale is not a partially
   valid run — record it as a fully discarded run in the evidence
   template (its encoder-vs-camera numbers may still be useful for the
   residual-fault campaign, ticket 006, but it contributes nothing to
   this ticket's OTOS-accuracy question).

### 9. Scoring commands and what to record per corner

```
python3 tools/leg_analysis.py .tmp/tour_world_RUN01_pose.csv \
    --out .tmp/legs_world_RUN01.csv
python3 tools/tour_chart.py .tmp/tour_world_RUN01_pose.csv \
    .tmp/tour_world_RUN01_vel.csv .tmp/tour_world_RUN01.png
```
(repeat per run and per tour type — `robot` in place of `world`).

Per corner, record:

- **Target (cm)** — `leg_analysis.py`'s `target_x_cm`/`target_y_cm`.
- **Encoder closure** — `believed_distance_cm` vs. `commanded`, i.e.
  `distance_error_cm` (signed: + overrun, - truncation).
- **Heading residual** — `heading_error_deg`.
- **OTOS closure** — `otos_distance_cm`, gated by `otos_stale` (step 8
  — only record/trust this figure when `otos_stale` is false).
- **Camera ground truth** — only available for the tour's **first**
  and **last** corner (the doctrine in step 4 forbids a mid-tour
  camera read). Compare the post-tour camera fix (step 6.5) directly
  against the pose CSV's final row / the last corner's
  `believed_x_cm`/`believed_y_cm`/`believed_h_deg` — do **not** try to
  force `leg_analysis.py`'s `--ground-truth-csv` flag to align a
  single end-of-tour camera reading with an interior corner; that flag
  is shaped for one ground-truth fix per leg, which start/end-only
  camera reads cannot supply for a multi-corner tour.

### What "meets the issue's verification bar" means, numerically

- **Per-corner OTOS residual**, among legs **not** flagged
  `otos-stale`: within the **10 mm** arrival tolerance (the issue's
  own Verification section).
- **Closure** (both encoder, and OTOS where valid) compared against
  the recorded **9-54 mm / 1-7° encoder-only baseline** (`RUN:1`/
  `RUN:straight`) — does the OTOS-guided tour (`RUN:tour:world`) close
  tighter than that baseline?
- **Camera cross-check**: the OTOS bracketing fix at the tour's start
  and end should sit within roughly the same 10 mm band of the
  camera's ground-truth fix at those same two points (matching the 2
  mm figure observed on the 20 cm reference leg above) — a much larger
  gap, on a run that already passed the step 8 validity check, is
  itself a finding, not noise to average away.

### No campaign has been run, and no result is reported here

**This procedure is a handoff, not a report.** Nothing above was
executed as part of writing it; no acceptance criterion in ticket 005,
or claim in this issue, depends on a hardware result. The command
lines, thresholds, and the evidence-template fields below describe
what to run and what to record — running it, filling it in, and
judging pass/fail against the numeric bar above is the bench
operator's job, not this ticket's.

## Evidence Template (fill in per bench session)

Copy this block once per bench session; copy the per-run table once
per repetition.

```
### Session
- Date / operator:
- Robot: vevov
- Firmware build / column set (POSE-12 or FULL-20; git sha):
- Placement: [ ] floor, over radio   [ ] bench stand, USB (INVALID for scoring)
- Camera used: arducam-ov9782-usb-camera / arducam-ov9281-usb-camera
- Camera calibration_stale at session start (list_cameras): true / false
- Lever-arm verify (otos_levercal.py --radio --verify): residual arm ___ mm
  (expect near 0 mm; STOP campaign if not)

### Per-run table (one row set per repetition, per tour type)

| run id | tour | camera before (x,y,h) | camera after (x,y,h) | OTOS fix before (OCAL) | OTOS fix after (OCAL) | pose CSV | legs CSV |
|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |

### Per-corner rows (from leg_analysis.py's --out CSV, one block per run id)

| corner | target (cm) | encoder closure (cm) | heading residual (deg) | OTOS closure (cm) | otos_stale | camera gt (start/end only) |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |

### Cross-source validity verdict (per run id, step 8)
- Encoder vs. camera overall displacement agree?
- Any leg / the whole-tour bracket flagged otos-stale?
- Run scored / run discarded (why):

### Summary (across all valid runs, per tour type)
- N valid runs (of N attempted):
- Per-corner OTOS residual within 10 mm (non-stale legs only)? Y/N, figures:
- Closure vs. 9-54 mm / 1-7 deg encoder-only baseline: tighter / same / worse:
- Camera cross-check gap at bracketed corners:
- Verdict: meets issue's verification bar / does not / partial (state which numbers)
```

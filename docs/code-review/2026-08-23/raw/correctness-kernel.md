# Correctness review — control core (kernel, motion engine, hardware ports)

**Date:** 2026-08-23
**Scope:** `src/diffdrive.h/.cpp`, `src/motion_engine.h/.cpp`,
`src/nezha_port.h/.cpp`, `src/otos_port.h/.cpp`, `src/platform_ports.h`.
Callers in `src/shims.cpp` and `src/wire_adapter.cpp` were read to judge
contracts; findings are located in the scoped files unless the defect is in
those files' enforcement of a scoped contract.
**Dimensions:** 1 (correctness), 2 (future landmines), 5 (student
readability, grouped).
**Method:** every finding below was traced through the actual code paths
cited; deduped against `clasi/issues/` (including
`intermittent-cw-pivot-abort-wheel-reversal`,
`unpowered-nezha-brick-wedges-program-at-boot`,
`otos-on-vevov-move-goto-world-pose-square-tours`) and the planned
sprint-004/005 scope.

---

### KERN-01 — A stall latch permanently disables all motion; nothing in the package can clear it

- **File:** `src/diffdrive.cpp:384-386, 455-460, 483, 704-706`; exposure
  verified against `src/shims.cpp`, `src/main.ts`, `src/wire_adapter.cpp`.
- **Dimension:** 1 (correctness) / safety.
- **Severity:** Critical.
- **Scenario:** The stall detector ships **enabled** (`ensure()`,
  `shims.cpp:178-180`: `stallSpeed` 191.4, `stallDemand` 510.4,
  `stallWindow` 500 ms). A student's robot drives into a wall, or a hand
  holds both wheels, while any normal move is commanded (a 150 mm/s cruise
  is ~1852 counts/s, far above `stallDemand`). After 500 ms
  `stallLatched_` sets and `step()` promotes it to `stallHalted_ = true`
  (`diffdrive.cpp:704-706`), which forces `effective = kModeNeutral` on
  every subsequent cycle (line 483). The only code that ever clears
  `stallHalted_` is the `clearStallReq_` handshake (lines 455-460), fed
  solely by `clearStallLatch()` — and **`clearStallLatch()` has no caller
  anywhere in the package**: not in `shims.cpp` (no `//%` shim), not in
  `main.ts`, not in the wire surface (`kFields` has no such field; STOP →
  `stopAll()` → `neutral()`; ESTOP → `estopAll()` → `estop()` +
  `emergencyStopMotors()`; `estopClear()` clears only `estopLatch_`).
  Even `SET stall_window 0` over the wire only clears `stallLatched_` via
  `updateLatch()`, never `stallHalted_`. From the latch onward the robot
  never moves again until power cycle, while:
  - `drive()`/`driveDuty()` keep returning `kOk` — `checkCommandable()`
    (lines 308-317) does not test `stallHalted_`, so every block and wire
    verb reports success;
  - blocking moves return instantly "complete": `serviceMove()` sees
    `out.stallHalted` and ends the move on its first tick
    (`motion_engine.cpp:290`), so `while (tickDrive())` exits immediately
    with zero motion and no error.
  Observability exists (DIAG 2 / STATUS flag bit 2); recovery does not.
- **Remedy:** expose `clearStallLatch()` — minimally on the block surface
  next to `estopClear()`, ideally also cleared by `estopClear()` or by
  STOP, per stakeholder choice. Separately, make `checkCommandable()`
  refuse (or `lastError()`-note) commands while stall-halted so the
  failure is loud. Host-testable: `tests/host/test_kernel_harness.py` can
  drive a fake-motor stall, latch, then assert a documented clear path.
- **Confidence:** high (all call sites grepped; latch logic traced).

### KERN-02 — goToR composed with moveX's pivot-first split lands far from the target (≈50–80% miss for bearings ≥ 25°)

- **File:** `src/motion_engine.cpp:150-172` (goToR), `133-140` (moveX
  split), threshold `src/motion_engine.h:278`.
- **Dimension:** 1.
- **Severity:** Major.
- **Scenario:** `goToR(x, y)` encodes the target as a constant-curvature
  arc: `theta = 2*atan2(y,x)`, arc length `s = R*theta`. That encoding
  reaches (x, y) **only if executed as one blended segment**. But
  `moveX()` splits any `|rotation| >= 50°` with nonzero distance into
  pivot-`theta`-then-straight-`s` — which is a different endpoint.
  Worked example: `goToR(100, 100, …)` (target 141 mm away at bearing
  45°). `theta = 90°`, `R = 100`, `s = 157.1 mm`. The split pivots 90°
  then drives 157 mm straight: endpoint (0, 157) vs target (100, 100) —
  a **115 mm miss on a 141 mm hop**. At exactly the 50° threshold
  (R = 100: target (76.6, 35.7)) the miss is ~37 mm on an 87 mm move.
  Every GO_TO_R / GO_TO_W wire command with |bearing| ≥ 25° is affected
  (`wire_adapter.cpp` forwards straight through; main.ts's `goToWorld()`
  is a separate path with its own pivot-bearing-then-arc heuristic and is
  not affected). The host tests deliberately dodge this region —
  `tests/host/test_motion_engine_reductions.py:552-554`: "must stay under
  the pivot-first threshold" — so the composition is green-but-untested.
- **Remedy:** make the split decision inside `goToR()`, not inherited:
  when `|theta| >= kTurnFirstAngleRad`, issue pivot = `atan2(y, x)` (the
  line-of-sight bearing, half of theta) followed by chord =
  `hypot(x, y)` straight — turn-then-chord reaches (x, y) exactly. Keep
  the plain arc below threshold. Add a host test asserting the
  kinematically-integrated endpoint of the issued segments for a
  bearing ≥ 25° target.
- **Confidence:** high (geometry recomputed twice; code paths traced).

### KERN-03 — goToR targets behind the robot command the long-way-around arc — up to a ~31 m runaway leg

- **File:** `src/motion_engine.cpp:156-171`.
- **Dimension:** 1.
- **Severity:** Major.
- **Scenario:** For a target slightly behind, `theta = 2*atan2(y,x)`
  approaches ±2π and the arc solution degenerates to the long way around
  a huge circle. `goToR(-100, 1)`: `theta = 2*(π − 0.01) ≈ 6.263 rad`,
  `R = (100² + 1²)/(2·1) ≈ 5000 mm`, `s = R·theta ≈ 31,320 mm`. Combined
  with KERN-02's split, the robot pivots ~359° then drives **31 metres
  straight**, bounded only by the caller's timeout (a typical 20 s
  backstop at 150 mm/s is 3 m of travel — off any table or playfield).
  With `|y| < 0.1` the special case is merely wasteful, not dangerous:
  `goToR(-100, 0.05)` pivots a full 360° (theta ≈ 2π, several seconds
  plus scrub error) then backs up 100 mm. The `plain reduction, no
  heuristic` posture is documented (motion_engine.h header), but the
  documentation contemplates small corrections; nothing warns that the
  rear half-plane is effectively forbidden input, and the wire accepts it.
- **Remedy:** the KERN-02 remedy (bearing-pivot + chord above the
  threshold) also fixes this: a behind-target becomes pivot ≈ ±180° +
  chord ≈ 100 mm. If the plain-arc posture must be kept verbatim, refuse
  (kRange) targets whose |bearing| exceeds some cap at the adapter, and
  say so in `motion_engine.h`.
- **Confidence:** high.

### KERN-04 — goToR/goToW have no arrival tolerance: a target you are already at (within noise) triggers up to a 180° pivot, and goToW's documented no-op is unreachable

- **File:** `src/motion_engine.cpp:156` (guard), `165-171`; contradicted
  promise at `src/motion_engine.h:239-241`.
- **Dimension:** 1.
- **Severity:** Major.
- **Scenario:** The only no-op guard is `x == 0.0f && y == 0.0f` — exact
  float equality. `goToW()` computes the body delta by subtracting two
  measured poses, which is essentially never exactly zero, yet the header
  promises "A target equal to the current pose reduces to a (0, 0)
  body-frame delta, which goToR() already treats as a no-op." With the
  robot at the target within sensor noise, delta (0.02, 0.05) mm gives
  `theta = 2*atan2(0.05, 0.02) ≈ 136°` → moveX(0.02 mm, 136°) → the
  split fires → the robot executes a **136° pivot** to correct 0.05 mm.
  Delta (0, 0.05) gives a clean 180° pivot. The `arrive` parameter — the
  wire field that exists precisely to carry a tolerance — is accepted and
  discarded (`motion_engine.cpp:152`). Any host loop that re-issues
  GO_TO_W until arrival (the spec's supervisory pattern, which the header
  itself tells callers to implement) oscillates: each "arrived" iteration
  commands a fresh large pivot from pose noise.
- **Remedy:** honor `arrive` (or a default ~10 mm, the reference
  navigator's tolerance per
  `clasi/issues/otos-on-vevov-move-goto-world-pose-square-tours.md`) as a
  radial no-op gate in `goToR()`: `if (hypot(x,y) <= arriveTolerance)
  return;`. Host-testable in
  `tests/host/test_motion_engine_gotow.py` (pose == target ± noise →
  assert no segment is started).
- **Confidence:** high.

### KERN-05 — Seeding the OTOS with |heading| > 180° silently clamps instead of wrapping — up to 170° of seed error and the two pose sources start disagreed

- **File:** `src/otos_port.cpp:57-69` (`writePoseMm` clamp), `186-196`
  (`setPose`); caller `src/shims.cpp:1031-1039` (`seedPose`).
- **Dimension:** 1.
- **Severity:** Major.
- **Scenario:** The chip's heading register is int16 with full scale ±π
  (`kHdgRadPerLsb`, `otos_port.h:108-109`). `writePoseMm` clamps all
  three channels to ±32767. Clamping is correct for x/y (±10 m FSR) but
  **wrong for an angle**, which must wrap. `seedPose(x, y, 35000)`
  (350° — a natural value from a 0–360° camera-yaw convention, or from
  the dead-reckoned `Rig.heading`, which is deliberately unwrapped and
  exceeds ±180° after two same-direction turns) writes: odometry heading
  = 6.109 rad, OTOS heading = clamp(63,755 → 32,767) = **+179.9°** — a
  ~170° disagreement at the very instant `seedPose`'s contract says the
  two sources "start agreed" so "their later divergence IS the drift
  being measured" (shims.cpp:1026-1029). Every drift measurement and
  every subsequent world-frame move from that seed is poisoned, silently.
- **Remedy:** wrap the heading channel into (−π, π] before quantizing —
  in `setPose()` (best: it owns the angle semantics) or via a dedicated
  heading path in `writePoseMm`. Keep the clamp for x/y.
- **Confidence:** high on the clamp behavior (traced); the failure needs
  a caller to pass |heading| > 180°, which both named conventions produce.

### KERN-06 — WHEELS_X/MOVE_X with timeout 0 leaves an armed kernel command with no tick source: a stale motion command fires whenever anything next ticks

- **File:** contract split across `src/motion_engine.cpp:34, 55-59`
  (wheelsX: `timeoutMs == 0` means **uncapped** dead-reckoned lease),
  `src/motion_engine.cpp:123` + `109-113` (moveX: `timeout 0` means
  **instant expiry**), and the unvalidated pass-through in
  `src/wire_adapter.cpp:269-298` (no `timeout == 0` refusal; obligation
  deadline = `now + 0`).
- **Dimension:** 1 / 2.
- **Severity:** Major.
- **Scenario:** v6 calls `timeout` "a required backstop", but 0 is
  accepted and means opposite things in the two sibling primitives. The
  dangerous branch is `WHEELS_X 500 500 50 0 #n`: `wheelsX()` computes a
  dead-reckoned lease of `500/50·1000 = 10,000 ms`, `timeoutMs == 0`
  skips the cap, and `kernel_.drive()` stages a 10 s-lease command. The
  adapter arms the motion obligation to `now + 0`, so
  `hasLiveMotionObligation()` is false and protocol.cpp's fiber **never
  ticks** — nothing moves, `ok` was already sent, and the host believes
  the move ran. The staged command stays lease-live for 10 s: if a
  student's `while (driveTick())` loop (or any other ticker) starts
  within that window, the robot **lurches into the stale wire command**
  with no one having recently asked for motion. Long distances at slow
  cruise stretch the window toward the 1 h `kLeaseMax`. Meanwhile the
  same `0` sent to MOVE_X is a silent instant no-op (deadline == now).
- **Remedy:** refuse `timeout == 0` (kRange) for WHEELS_X/MOVE_X/GO_TO_*
  at the adapter — it is a required field; and make `wheelsX()` and
  `moveX()` agree on the semantics of 0 so a direct C++ caller cannot
  hit the divergence. Also guard `timeout >= 2^31` (the signed-difference
  deadline idiom in `serviceMove`/`startSegment` inverts beyond that).
  Host-testable in `tests/host/test_wire_motion_verbs.py`.
- **Confidence:** high (paths traced end to end, including the
  obligation arming and protocol tick loop).

### KERN-07 — Nezha brick MCU reset mid-session teleports position/odometry by the full accumulated count and spikes velocity

- **File:** `src/nezha_port.cpp:196-239` (collect + two-strike accept),
  `48-72` (begin/offset); downstream `src/diffdrive.cpp:743-751`
  (velocity quotient), `src/shims.cpp:213-233` (odomUpdate).
- **Dimension:** 1 / 2.
- **Severity:** Major.
- **Scenario:** `encOffset_` is captured once at `begin()` and the 0x46
  counter is never device-reset. If the brick's own MCU resets
  mid-session (battery sag/brownout during a stall is a real bench event
  — the retired-theories list in
  `clasi/issues/intermittent-cw-pivot-abort-wheel-reversal.md` shows
  battery sag being investigated), its counter restarts near 0 while
  `encOffset_` still holds, say, 50,000. The first post-reset read is
  rejected by the glitch armor (`mag > 5000`), but the second consecutive
  read is consistent with the first and is **accepted as reality**
  (nezha_port.cpp:215-222, the documented hand-rotation re-sync path):
  `position()` jumps by −50,000 counts (~4 m), `refreshSample()` computes
  a ~2 M counts/s velocity spike from the jump, `odomUpdate()` folds a
  ~4 m teleport into the pose, and any active move instantly "completes"
  or wrong-way-aborts. Nothing re-baselines `encOffset_` on
  reconnection. (The boot-time flavor of brick absence is the known
  issue `unpowered-nezha-brick-wedges-program-at-boot`; this finding is
  the *mid-session recovery* path, which also becomes the common path
  once that issue's graceful-degradation fix lands.)
- **Remedy:** on the two-strike acceptance of a discontinuity, treat it
  as a re-baseline, not motion: fold `raw − lastGoodRaw_` into
  `encOffset_` (position continuous, velocity 0) unless a deliberate
  `rebaseline()` asked otherwise; or surface a `discontinuity` flag the
  kernel/odometry can consume.
- **Confidence:** medium — code path is certain; the premise that a brick
  MCU reset zeroes the 0x46 counter is a hardware assumption. Confirm on
  the bench: power-cycle the brick mid-drive with the tick loop alive and
  watch DIAG 10/11 and pose.

### KERN-08 — OtosPort::heading() violates the PoseSource "unwrapped" contract: it is wrapped to ±π by the chip

- **File:** `src/otos_port.h:66, 108-109` vs the contract at
  `src/motion_engine.h:139` ("[rad] world frame, CCW+ (unwrapped)").
- **Dimension:** 2.
- **Severity:** Minor.
- **Rationale:** The chip's heading register is int16 at ±π full scale;
  a pivot through 180° jumps the reading −π → +π. `goToW()` only feeds
  heading to cos/sin, which is wrap-immune, so nothing breaks **today**
  — but the port advertises "unwrapped", and the first consumer that
  differences headings (drift measurement vs the deliberately-unwrapped
  `Rig.heading`, a heading-hold servo, telemetry deltas) inherits a 2π
  glitch at ±180°. One of the two — the comment or the port — is wrong.
- **Remedy:** either fix the contract comment to "wrapped to (−π, π]"
  (cheap, honest), or unwrap in `read()` by accumulating deltas.
- **Confidence:** high.

### KERN-09 — The kernel's command/config seqlocks are not actually preemption-safe; they are safe only by cooperative-fiber accident

- **File:** `src/diffdrive.cpp:336-337, 353-360, 403-408, 410-418`
  (writers increment once, after the multi-word struct write; readers
  check `s1 != s2` only).
- **Dimension:** 2.
- **Severity:** Minor.
- **Rationale:** `output()` does the odd/even protocol correctly on the
  writer side (`publishOutput`, 777/818), but `drive()`/`neutral()`/
  `setConfig()` write `command_`/`staged_` (multi-word structs) and then
  increment the sequence **once**. A reader preempting mid-write sees
  `s1 == s2` around a torn copy. Under CODAL's cooperative fibers there
  is no yield inside these regions, so no tear is possible today — the
  seqlock is decorative — but this file is the **vendored, shared
  kernel** ("a MicroPython C module implements the same four ports",
  diffdrive.h header), and a preemptive host (RTOS task, threaded
  harness) inherits real torn commands: e.g. a `velocity` from the new
  command paired with a `validUntil` from the old one. Nothing documents
  the cooperative-scheduling assumption.
- **Remedy:** either complete the protocol (increment before and after
  the write, readers reject odd counts — same as `outSeq_`) or document
  "single-scheduler, no preemption" as a kernel port requirement next to
  the ports.
- **Confidence:** high on the pattern; the bite requires a preemptive
  host, which does not exist in this repo.

### KERN-10 — setWheelCorrection accepts gain 0 (or negative): division by zero drives the wheel at full rail regardless of the command

- **File:** `src/diffdrive.cpp:132-153` (finite-only validation),
  `821-833` (`correctedCommand` divides by `wheelGain[w][d]`).
- **Dimension:** 2.
- **Severity:** Minor.
- **Scenario:** Everywhere else in `Config`, 0 means "feature off"
  (`iMax`, `vMin`, `biasMax`, `crawlPulse`, `deficitThreshold`…). A
  future caller who writes `setWheelCorrection(0, 0, 0, 0, …)` intending
  "disable correction" instead gets `magnitude = (|desired| − 0) / 0 =
  +inf`, `copysign(inf)` → the duty demand clamps to the full `rail`
  (`clampf`, line 663-666): the wheel runs at max authority no matter how
  slow the command; if `|desired| == intercept` exactly the quotient is
  NaN, which `clampf` passes through untouched into `Motor::setDuty()`.
  Not reachable today — no caller in this repo invokes
  `setWheelCorrection` and the shim/wire tables don't expose the gains —
  but the kernel is the shared, vendored component and validates
  everything else.
- **Remedy:** refuse (kRefusedNonFinite is wrong; add a range refusal or
  clamp) gains ≤ 0 in `setWheelCorrection`, matching the 0-means-off
  convention or rejecting it explicitly.
- **Confidence:** high on behavior; low on reachability.

### KERN-11 — OtosPort::begin() returns true when a bus error aborts the calibration wait — reopening the exact "seed silently discarded" window it exists to close

- **File:** `src/otos_port.cpp:103-109`.
- **Dimension:** 1.
- **Severity:** Minor.
- **Scenario:** The wait loop `break`s on a failed
  `readReg8(kRegImuCalibration, …)` and `begin()` returns true anyway.
  One transient NAK during the ~612 ms calibration and the caller
  proceeds to `seedPose()` while the chip is still calibrating — the
  chip silently discards the position write and reports origin, which is
  precisely the measured 2026-08-21 failure the block comment above this
  loop documents. The loop also caps at ~1.5 s and falls through with no
  signal if calibration is still running.
- **Remedy:** on read failure, retry a few times before giving up; if the
  loop exits with `remaining != 0` or on error, either return false or
  expose the state so `otosBegin()` can report "present but not
  seed-ready" (`imuCalibrationSamplesRemaining()` already exists for
  callers, but nothing tells them to check it).
- **Confidence:** high.

### KERN-12 — The encoder glitch armor is blind to the destroyed-sample zero signature in two cases

- **File:** `src/nezha_port.cpp:209-222`.
- **Dimension:** 2.
- **Severity:** Minor.
- **Scenario:** A sample destroyed by interposed bus traffic "reads as
  raw 0" (the armor's own comment). Two holes: (a) while the session's
  cumulative counter is within `kMaxDeltaCounts` (5000 counts ≈ 40 cm of
  travel) of zero — i.e. the first leg after a fresh brick power-on —
  raw 0 passes the `mag > kMaxDeltaCounts` gate outright and is accepted
  as a real position, snapping position toward 0 with a velocity spike up
  to ~200 k counts/s; (b) at any position, **two consecutive** destroyed
  samples both read 0, are mutually consistent (`rejMag <= 5000`), and
  the two-strike rule accepts the second — a full teleport to
  `−encOffset_`. Both need a bus-discipline violation to trigger, so
  this is defense-in-depth having a gap exactly where the attack lands,
  not a live bug.
- **Remedy:** treat exact raw 0 as suspect independently of delta when
  the previous accepted raw was nonzero by more than a few counts —
  e.g. require three consecutive zeros, or re-select 0x46 and reread
  before accepting a zero.
- **Confidence:** high on the code, medium on real-world frequency.

### KERN-13 — wedged() latches TRUE on any robot that has merely been stationary for 10 ticks

- **File:** `src/nezha_port.cpp:247-263`.
- **Dimension:** 2.
- **Severity:** Minor.
- **Rationale:** `identicalReads_` increments on every identical
  position read with `connected_` true — which is simply what a parked
  robot does — so `wedgeLatched_` is true within ~240 ms of stopping,
  forever until the next motion. Today it is harmless because nothing
  consumes it: `Output.wedgeLeft/Right` are published but DIAG 6/7 and
  STATUS both read the `wedgeSuspect*` (driven) variants. It is a lie in
  waiting: the first consumer to wire `wedged()`/`Output.wedgeLeft` into
  a UI or a refusal path sees every resting robot as encoder-wedged.
- **Remedy:** gate the plain latch on drive too (or delete
  `wedged()`/`Output.wedge*` and keep only the suspect variant, which is
  the one with meaning).
- **Confidence:** high.

### KERN-14 — float32 encoder positions lose velocity resolution on long sessions (~0.7–1.3 km of accumulated wheel travel)

- **File:** `src/nezha_port.cpp:226-231` (float position, velocity
  quotient), `src/diffdrive.cpp:743-751` (same pattern in
  `refreshSample`).
- **Dimension:** 2.
- **Severity:** Minor.
- **Scenario:** Positions are float counts, never wrapped, and
  `rebasePosition()` is never called (no caller in the package). At
  8.4 M counts the float ulp is 0.5 counts; at 16.8 M it is 1.0. 16.8 M
  counts = 1.68 M shaft-degrees ≈ 1.36 km of wheel travel
  (travelCalib 0.81 mm/deg) — about 2 hours of continuous demo driving
  at 0.2 m/s. Past that, a 24 ms velocity sample of a 12-count delta
  quantizes at ±1 count → ~8% velocity noise (≈42 counts/s), degrading
  the PID, the rest detection (`kRestVelocity` 100), and the stall
  detector's `encoderStill`. Nothing fails suddenly; control quality
  decays silently with session length.
- **Remedy:** keep raw counts in int32 (they already are, in the port)
  and expose deltas, or periodically fold the accumulated count into the
  offset via the existing (currently dead) `rebaseline()` path at safe
  moments (move boundaries).
- **Confidence:** high on the arithmetic, low on anyone driving 1.3 km
  in one session soon.

### KERN-15 — Distance completion uses unsigned progress: motion in the wrong direction counts toward "done"

- **File:** `src/motion_engine.cpp:220-224` vs the signed yaw fix at
  `229-236`.
- **Dimension:** 1.
- **Severity:** Minor.
- **Scenario:** `remain = |distTarget| − |meanProgress|`. A moveX
  commanded +500 counts forward while the robot is rolled/pushed 510
  counts **backward** (slope, hand, or the KERN-07 discontinuity) yields
  `remain ≤ margin` → `distDone` → the move "completes" at −500 counts
  from its target. The yaw axis had exactly this bug and got the signed
  `toward` fix plus a wrong-way abort (the comment at 230-232 explains
  why); distance never did. Low likelihood in normal driving (requires
  net reverse motion of the full commanded magnitude), but it converts
  other faults into silent false completions.
- **Remedy:** mirror the yaw treatment: signed
  `toward = sign(distTarget) * meanProgress`, `remain = |distTarget| −
  toward`, optional wrong-way abort at `toward < −3·distMargin`.
  Host-testable in `tests/host/test_motion_engine_reductions.py` with
  encoders scripted backward.
- **Confidence:** high.

---

## Minor readability findings (dimension 5, grouped)

Students will read this code; none of these are behavior bugs.

- **Three uncorrelated "at rest" thresholds** for the same physical idea:
  `kRestVelocity = 100` counts/s (`diffdrive.h:360`),
  `kStopConfirmVelocity = 102` (`nezha_port.h:70`), `kRest = 25`
  (`shims.cpp:493`). Nothing explains why they differ or that they must
  not drift apart; name and cross-reference them.
- **`emergencyStopMotors()` latches the e-stop as a side effect** its
  name does not state (`diffdrive.cpp:378-382`, also written as
  `estopLatch_ = 1` on a `volatile bool` — the only non-boolean
  assignment to it). Meanwhile `estop()`'s header comment says "zero
  NOW" (`diffdrive.h:198`) but the zero actually lands on the *next*
  `step()`; only `emergencyStopMotors()` writes the ports immediately.
  Two adjacent functions whose comments/name each describe the other.
- **`Output.stallLeft/stallRight` are one shared latch dressed as two**
  (`diffdrive.cpp:804-805`), and both read **false** one cycle after the
  stall halt (the neutral branch clears `stallLatched_` at 536 while
  `stallHalted_` persists) — a diagnostic that vanishes at the moment it
  matters. `stallHalted` is the honest flag; either drop the per-wheel
  pair or make them sticky alongside it.
- **`const uint64_t nowUs = previousCycleStartUs_;`**
  (`diffdrive.cpp:634`) — a "previous" named variable holding the
  current cycle's start, needing a comment to un-lie itself. Rename the
  member (`cycleStartUs_`) or pass the stamp into `controlStep`.
- **Velocity-mode `satLeft_/satRight_` are computed from the *previous*
  cycle's duty demand** (`diffdrive.cpp:565-568` reads
  `dutyDemandLeft_` before line 660 overwrites it). Deliberate one-cycle
  lag feeding lambda's attack — but only archaeology reveals it is
  intentional; one sentence at the site would.
- **`updateLatch`'s `since == 0` doubles as "not started" and as a
  legitimate timestamp** (`diffdrive.cpp:918-928`) — harmless (one-cycle
  delay if the condition starts in the boot millisecond or at the 49.7-d
  wrap) but a classic sentinel trap to flag for readers.
- **`nezha_port.h` splices a `public:` block mid-privates**
  (`nezha_port.h:102-107`) to expose two raw diagnostic members
  (`maxDrivenStreak_`, `glitchCount_`, trailing-underscore names and
  all) that `shims.cpp` pokes directly; two const accessors would keep
  the class shape honest.
- **`diagValue`'s case 25 sits between the "23/24" comment and cases
  23/24** (`shims.cpp:709-712`) — the comment describes lines it no
  longer precedes.
- **`OtosPort` velocities are sensor-frame** (mount-yaw-corrected only —
  no ω×lever-arm term), while the header sells the cached pose as "the
  ROBOT CENTRE's" (`otos_port.h:59-69`); one sentence saying velocity is
  *not* centre-corrected would prevent misuse of `vx()/vy()`.

---

## Not findings (checked, suspicious-looking, actually fine)

- All lease/deadline arithmetic (`validUntil`, `move_.deadline`,
  `hasLiveMotionObligation`) uses the wrap-safe signed-difference idiom;
  the 49.7-day ms wrap is handled. (Degenerate only for spans ≥ 2^31 ms —
  covered under KERN-06's remedy.)
- `drive()` gates on `staged_` while control uses `active_`: benign —
  `snapshotConfig()` is the first thing `step()` does, and velocity mode
  additionally re-checks `active_.fullDutyVelocity` per cycle (line 485).
- E-stop during a move: every path in this package that sets the latch
  goes through `estopAll()`, which calls `engine.endMove()` first, so
  `serviceMove()`'s missing `out.estopped` check is unreachable today
  (worth adding when the kernel is reused elsewhere).
- `updateMove()` calling `serviceMove()` without the `stepBusy` guard:
  safe — `serviceMove()` contains no yield point, so it is atomic under
  cooperative fibers even interleaved with a tick fiber parked in
  `step()`'s settle sleeps.
- The `stepBusy` check-and-set in `tickDrive()` (shims.cpp:460-463) is
  correct: no yield between the final while-check and the set.
- `step()`'s cycle-gap re-anchor (`kMaxCycleGapUs`) correctly reuses the
  first-cycle `dt == 0` path; `positionError()`/`adaptBias()` re-anchor
  rather than integrate on `dt <= 0`.
- ESTOP arriving on the protocol fiber can land a motor write inside the
  tick fiber's encoder settle window, destroying one sample — correct
  priority, and the glitch armor holds position through it.
- `positionError()` re-anchors on `speed == 0`, so a wheel commanded to
  exactly zero in an arc is not position-held (drag scrubs it) — matches
  the documented "stop is stop; never offset it" doctrine.
- `Output.sampleTimeLeft/nowFine` truncate µs to uint32 (71.6 min wrap) —
  no current consumer computes cross-wrap age; kernel freshness math uses
  the uint64 stamps internally.
- `wheelsX()`'s `lround` of a huge computed lease can overflow 32-bit
  `long` on target for absurd distance/cruise ratios — the kernel's
  `kLeaseMax` (1 h) cap bounds the damage.
- Sigma-delta carry is computed before slew limiting
  (`nezha_port.cpp:146-171`) — deliberate: carry accounts for
  quantization only; slew is a rate limiter, not an integrator.
- Watchdog firing during the post-move settle loop: `lastTickUs` can go
  ~100 ms stale across the 12 settle steps, but by then applied duty is
  zero (first settle step delivers the stop), so `commandLooksActive()`
  is false and the port stop does not fire spuriously.
- The deficit detector ships disabled (`deficitThreshold` never set in
  `ensure()`), so its `biasSaturated && pidSaturated` gating is dormant —
  intentional per the tovez bake.
- `kernel.begin()` returning `kRefusedUnconfigured` still sets `begun_` —
  looks odd, but `checkCommandable()` re-checks `maxDuty` on every
  command, so nothing slips through.

---

**Totals:** 1 Critical, 6 Major (KERN-02…KERN-07), 8 Minor (KERN-08…
KERN-15), plus one grouped readability section.

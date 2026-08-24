# Adversarial verification — correctness-kernel findings

**Date:** 2026-08-23
**Scope:** independent re-derivation of KERN-01 (Critical) and KERN-02..07
(Major) from source, plus two Minor spot-checks (KERN-08, KERN-15).
**Method:** every guard, caller, and clamp re-traced from
`src/diffdrive.cpp`, `src/motion_engine.{h,cpp}`, `src/otos_port.{h,cpp}`,
`src/nezha_port.cpp`, `src/shims.cpp`, `src/wire_adapter.cpp`,
`src/wire_handler.cpp`, `src/protocol.cpp`, `src/main.ts`, and
`tests/host/`; all geometry recomputed from the formulas in the code, not
from the review's numbers. Default stance: refute.

## Verdict table

| ID | Reviewer severity | Verdict | Justification (one line) |
|----|-------------------|---------|--------------------------|
| KERN-01 | Critical | **DOWNGRADE → Major (top of band)** | Every factual claim confirmed — `clearStallLatch()`'s only caller in the repo is `tests/host/kernel_shim.cpp:105`; no wire/block/config path clears `stallHalted_` — but the program never hangs (all fibers, wire, and blocking calls keep running), no hardware damage, no safety bypass; per the rubric and this repo's own use of "wedge" (a frozen scheduler, per the unpowered-brick issue) this is Major, aggravated by silent `kOk`. |
| KERN-02 | Major | **CONFIRMED** (blast radius is wider than stated) | Math re-derived: goToR(100,100) → θ=90°, s=157.1 mm; the ≥50° split executes pivot-90°-then-157-straight, endpoint (0,157.1) vs target (100,100) — 115.1 mm miss on a 141.4 mm hop; also hits the block-API `goTo`/`startGoTo` path (main.ts:292-307 → startMove → shims.cpp:411 → engine.moveX), which the review did not claim. |
| KERN-03 | Major | **CONFIRMED** | Math re-derived: goToR(−100,1) → θ=6.2632 rad (358.85°), R=5000.5 mm, s=31,319 mm; split yields a ~359° pivot plus a straight leg bounded only by the caller's timeout. |
| KERN-04 | Major | **CONFIRMED** | Guard is exact float equality (motion_engine.cpp:156), `arrive` is `(void)`-discarded (:152), goToW subtracts measured poses (:180-196); noise delta (0.02, 0.05) mm → θ=136.4° pivot, delta (0, 0.05) → 180° pivot; header promise at motion_engine.h:239-241 is unreachable as written. |
| KERN-05 | Major | **CONFIRMED** | `writePoseMm` clamps the heading channel to ±32767 (otos_port.cpp:61-66) = ±179.89°; seedPose(…, 35000 cdeg) → odometry 6.1087 rad vs chip +3.1397 rad — 170.1° disagreement; no wrap anywhere on the path (setPose :186-196, shims.cpp:1031-1039, main.ts:459-463), and `r.heading` is genuinely unwrapped (shims.cpp:232). |
| KERN-06 | Major | **CONFIRMED** | Traced end to end: timeout 0 passes decode (wire_handler.cpp:751-767) and onWheelsX (no refusal), kills the obligation (deadline=now, wire_adapter.cpp:294-297, 414-420) so protocol.cpp:291 never ticks; wheelsX skips the cap at timeoutMs==0 (motion_engine.cpp:57) leaving a 10 s lease-live staged command (validUntil stamped from the real clock, diffdrive.cpp:334); the kernel fiber is deliberately unwired (shims.cpp:199) and the watchdog can't see or clear the staged command — a later `while(driveTick())` loop (a documented block pattern) executes it. MOVE_X 0 is confirmed the opposite: instant expiry. |
| KERN-07 | Major (conf. medium) | **CONFIRMED (code path); hardware premise UNVERIFIABLE** | Static path certain: `encOffset_` set once (nezha_port.cpp:48-72), never re-baselined (no production caller of `rebaseline()`/`rebasePosition()` — grep), two-strike accept at :212-222 admits the post-reset counter as reality (−50 k counts ≈ 4 m jump, ~1-2 M counts/s spike over the 24-48 ms sample gap); whether a brick MCU reset restarts the 0x46 counter near 0 is undecidable from this repo — the review's named bench experiment (power-cycle the brick mid-drive, tick loop alive, watch DIAG 10/11 and pose) is the decisive test. |
| KERN-08 | Minor (spot-check) | **CONFIRMED** | `heading_` is int16·kHdgRadPerLsb at ±π full scale (otos_port.h:108-109, otos_port.cpp:134/148) — wrapped by construction — while the PoseSource contract it implements says "(unwrapped)" (motion_engine.h:139); one of the two is wrong; harmless today (cos/sin-only consumers), so Minor is right. |
| KERN-15 | Minor (spot-check) | **CONFIRMED** | `remain = fabs(distTarget) − fabs(meanProgress)` (motion_engine.cpp:221-222): a +500-count target with 510 counts of net *backward* motion gives remain = −10 ≤ margin → `distDone`; the yaw axis at :229-236 has exactly the signed `toward` fix plus a wrong-way abort that distance lacks. |

## Notes and arithmetic

### KERN-01 — every candidate clear path hunted, none exists

Paths checked for anything that clears `stallHalted_`:

- `clearStallLatch()` (diffdrive.cpp:384-386) feeds the `clearStallReq_`
  handshake (455-460) — the **only** writer of `stallHalted_ = false`.
  Whole-repo grep (`src/`, `tests/`, `tools/`, `test/`): its only caller
  is the host test shim, `tests/host/kernel_shim.cpp:105`. No `//%` shim,
  nothing in `main.ts`, no wire field.
- `estopClear()` (shims.cpp:672) → `kernel.estopClear()` clears only
  `estopLatch_` (diffdrive.cpp:374-376).
- STOP → `stopAll()` (shims.cpp:657-661): `endMove()` + `neutral()` only.
  ESTOP → `estopAll()` (:664-669): `endMove()` + `estop()` +
  `emergencyStopMotors()` — sets, never clears.
- `SET stall_window 0` → `setKernelValue` ordinal 12 → `setStall(…, 0)`:
  `updateLatch` (diffdrive.cpp:920-928) then forces
  `stallLatched_ = false` each cycle, but line 704's promotion is one-way
  and nothing ever writes `stallHalted_ = false` from it.
- `setKernelValue` ordinals 0-14 (shims.cpp:765-784): none touches the
  latch. `kFields` (wire_adapter.cpp:88-104): config only.
- `resetAdaptiveState()` (diffdrive.cpp:754-771): clears `stallLatched_`
  and `stallSince_`, **not** `stallHalted_`.
- `begin()` (diffdrive.cpp:263-273): does not reset it, and is called
  exactly once (lazy `ensure()`, shims.cpp:161-208); the kernel is a
  process-lifetime singleton, so no re-init path exists short of power
  cycle.

Blocking behavior confirmed: `checkCommandable()` (diffdrive.cpp:308-317)
tests `begun_`/`estopLatch_`/config only, so `drive()`/`driveDuty()`
return `kOk` while halted; `stallHalted_` forces `effective =
kModeNeutral` for **all** modes including raw duty (:483); a fresh
`moveX()` ends on its first `serviceMove()` via `out.stallHalted`
(motion_engine.cpp:290), so `while(tickDrive())` exits after ~one tick
with zero motion and no error. Detector ships enabled (shims.cpp:178-180:
stallSpeed 191.4, stallDemand 510.4, stallWindow 500 ms; a 150 mm/s
cruise is 150·(10/0.8102) ≈ 1852 counts/s ≫ 510.4, so a wall-push
latches in 500 ms).

Severity: the rubric's Critical clauses are damage hardware / bypass
e-stop or safety / lose or corrupt state / **wedge the program**. This
repo's own vocabulary for "wedges the program"
(`clasi/issues/unpowered-nezha-brick-wedges-program-at-boot.md`) means a
frozen fiber scheduler — "total firmware hang". Here nothing hangs:
every fiber runs, the wire answers, blocking calls return promptly; the
halt itself is the safety feature working; recovery is a power cycle.
That is Major — but top-of-band Major: the trigger is an everyday
classroom event and every API reports success while the robot is
permanently immobile, which argues for first-in-queue triage regardless
of the label.

### KERN-02 — arithmetic (re-derived, both examples)

The arc encoding: `theta = 2·atan2(y,x)`, `R = (x²+y²)/(2y)`,
`s = R·theta` (motion_engine.cpp:163-170). A blended constant-curvature
segment of (s, θ) ends at `(R·sinθ, R·(1−cosθ))` — which equals (x, y)
exactly, so the encoding is correct **only if blended**. The split
(motion_engine.cpp:133-137, `kTurnFirstAngleRad = 0.8726646` rad = 50°,
motion_engine.h:278) instead executes pivot-θ then straight-s, endpoint
`(s·cosθ, s·sinθ)`.

goToR(100, 100):
- θ = 2·atan2(100,100) = 2·(π/4) = **π/2 = 90°** ≥ 50° → split fires
  (distance s ≠ 0).
- R = (100²+100²)/(2·100) = **100 mm**; s = 100·π/2 = **157.08 mm**.
- Blended endpoint: (100·sin90°, 100·(1−cos90°)) = **(100, 100)** — target.
- Split endpoint: (157.08·cos90°, 157.08·sin90°) = **(0, 157.08)**.
- Miss = √((100−0)² + (100−157.08)²) = √(10000+3258.1) = **115.1 mm** on a
  √(100²+100²) = **141.4 mm** hop. Review's "115 mm on 141 mm": exact.

At the 50° threshold, R = 100 (target (100·sin50°, 100·(1−cos50°)) =
(76.60, 35.72), matching the review's (76.6, 35.7)):
- s = 100·0.87266 = **87.27 mm**.
- Split endpoint: (87.27·cos50°, 87.27·sin50°) = (56.10, 66.85).
- Miss = √(20.51² + 31.13²) = **37.3 mm** on an 87 mm move. Matches.

Bearing mapping: bearing = atan2(y,x) = θ/2, so the split fires exactly
when |bearing| ≥ 25°. Confirmed.

Blast radius — **wider than the review states**: the wire path
(GO_TO_R/GO_TO_W → wire_adapter.cpp:340-384 → `engineGoToR`
shims.cpp:869-873 → `engine.goToR`, no clamp anywhere) is affected as
claimed, but so is the **block API**: `goTo`/`startGoTo`
(main.ts:292-307) compute the identical `2·atan2` arc in TS and call
`startMove` → shims.cpp `_startMove` → `r.engine.moveX(...)`
(shims.cpp:411), inheriting the same split. Only `goToWorld()`
(main.ts:568-634) is genuinely insulated — it pivots at a 12° bearing
gate and caps residual arcs at 2×25°. (Boundary observation within this
finding: that cap produces θ = 50.0°, sitting exactly on the `>=`
threshold — float rounding decides whether a maximally-capped goToWorld
arc silently becomes pivot+straight.) The dodge in the host tests is
verbatim: `tests/host/test_motion_engine_reductions.py:552-555` asserts
`abs(theta) < radians(_TURN_FIRST_DEG)` "or this test would be
exercising moveX()'s pivot split instead of goToR's own plain arc
reduction."

### KERN-03 — arithmetic

goToR(−100, 1):
- atan2(1, −100) = π − atan(0.01) = 3.1315930 rad.
- θ = **6.2631859 rad = 358.85°**.
- |y| = 1 ≥ 0.1 → R = (10000+1)/(2·1) = **5000.5 mm**.
- s = 5000.5 · 6.2631859 = **31,319 mm ≈ 31.3 m**. (Review: 31,320 —
  same to rounding.)
- Consistency check: blended endpoint (R·sinθ, R·(1−cosθ)) =
  (5000.5·(−0.0199987), 5000.5·0.00019999) = (−100.0, 1.0) — the arc
  really does reach the target the long way round; the encoding
  degenerates, it doesn't err.
- Split behavior: 358.85° ≥ 50° → pivot ~359°, then a 31.3 m straight
  leg terminated only by `move_.deadline` (a 20 s timeout at 150 mm/s
  = 3 m of travel). Confirmed.
- |y| < 0.1 branch: goToR(−100, 0.05) → θ = 2·(π−0.0005) = 6.2822 rad
  (359.94°), s = x = −100 → ~360° pivot then 100 mm reverse. Wasteful,
  not runaway. Matches the review.

### KERN-04 — arithmetic

- Guard: `x == 0.0f && y == 0.0f` (motion_engine.cpp:156); `(void)arrive`
  (:152); goToW body delta = float subtraction of measured poses
  (:180-196) — essentially never exactly zero.
- Delta (0.02, 0.05) mm: θ = 2·atan2(0.05, 0.02) = 2·atan(2.5) =
  2·1.19029 = **2.3806 rad = 136.4°**; |y| < 0.1 → s = x = 0.02 mm;
  moveX(0.02, 2.38) → split fires (s ≠ 0, θ ≥ 50°) → **136° pivot** to
  correct 0.05 mm. Delta (0, 0.05): θ = 2·(π/2) = **180°**, s = 0 →
  pure 180° pivot. Both match.
- The contradicted header promise is verbatim at motion_engine.h:239-241.
  The supervisory re-issue oscillation follows directly. Confirmed at
  Major.

### KERN-05 — clamp located, numbers re-derived

- The clamp: `writePoseMm` (otos_port.cpp:57-69) clamps **all three**
  channels to ±32767 before quantizing; heading scale `kHdgRadPerLsb` =
  0.00549°·π/180 = 9.5819e-5 rad/LSB (otos_port.h:108-109), so ±32767 ≡
  ±3.1397 rad = ±179.89° — a wrap-mandatory quantity clamped like a
  length.
- seedPose(x, y, 35000): h = 350°·π/180 = **6.1087 rad**; raw LSB =
  6.1087/9.5819e-5 = **63,752** → clamped to 32,767 → chip heading
  **+179.89°**, odometry heading **6.1087 rad (≡ −10°)** — **≈170.1°**
  disagreement at the moment the contract says the sources start agreed
  (shims.cpp:1026-1029). Review's numbers check out.
- Reachability of |heading| > 180°: the student block takes plain degrees
  with no wrap (main.ts:459-463 → `Math.round(heading·100)`);
  `poseHeading()` returns the deliberately-unwrapped `r.heading`
  (shims.cpp:232 `r.heading += dHeading`; :734-739), so echoing the
  robot's own reported heading back into seedPose exceeds ±180° after two
  same-direction turns. No wire SEED verb exists yet (grep of
  wire_handler.cpp/protocol.cpp), so exposure is the block/TS surface —
  as the review's confidence note already concedes. Confirmed.

### KERN-06 — lease lifetime traced end to end

`WHEELS_X 500 500 50 0 #n`:

1. Decode passes: fieldCount 4, `parseUint32("0")` OK
   (wire_handler.cpp:751-757, 763-767).
2. `onWheelsX` has no timeout validation; replies `kOk`; arms
   `motionObligationDeadlineMs_ = now + 0` (wire_adapter.cpp:294-297).
   `hasLiveMotionObligation()`: `(int32)(now − deadline) < 0` is false
   from the first call (:414-420).
3. protocol.cpp:291-292 — `if (hasLiveMotionObligation()) tickDrive();`
   — is the wire session's only tick source, and the kernel's own pacer
   fiber is deliberately unwired (shims.cpp:199,
   `// rig->kernel.start();`). So **nothing steps the kernel**.
4. Meanwhile `wheelsX()` computed `computedMs = 500/50·1000 = 10,000 ms`
   and the cap `if (timeoutMs > 0 && timeoutMs < lease)` was skipped at
   0 (motion_engine.cpp:55-57) → `kernel_.drive(…, 10000)`. `drive()`
   stamps `validUntil` from the **real clock at command time**
   (diffdrive.cpp:334-335) — the lease runs on the wall clock whether or
   not anyone steps.
5. "Anything next ticks" concretely: any `step()` within the 10 s window
   sees `leaseLive` → `effective = kModeVelocity` (diffdrive.cpp:474-487)
   and drives. Realistic tickers: the student's documented
   `while (diffDrive.driveTick())` pattern (main.ts:93/113/131/139) or
   `updateMove()`. The starvation watchdog is no defense: it fires only
   when `commandLooksActive()` (shims.cpp:618-622) — applied duty is
   still zero and no move is active — and it never clears `command_`
   anyway.
6. Long window: `dominant/cruise` scales the lease; `drive()` caps it at
   `kLeaseMax` (1 h, diffdrive.cpp:335). Confirmed.

MOVE_X with 0 confirmed as the opposite semantics: `move_.deadline =
nowMs() + 0` (motion_engine.cpp:123), `startSegment` computes
`remainingMs = 0` (:109-113) → lease 0 → expired on the first
serviceMove/step — a silent instant no-op that still replied `ok`.
Divergence between the sibling primitives confirmed exactly as stated.

### KERN-07 — what is statically certain vs. bench-only

Certain from code: `encOffset_` captured once in `begin()`
(nezha_port.cpp:48-72; the comment itself says the device counter is
never reset); `rebaseline()`/`rebasePosition()` have **no** production
caller (grep: only `tests/host/kernel_shim.cpp:108` and the fakes); the
glitch armor's two-strike rule (:212-222) rejects the first post-reset
read (|Δ| ≈ 50,000 > 5000) and accepts the second consecutive
self-consistent one — by design, per its own hand-rotation comment.
Consequences on acceptance: `pos = (raw − encOffset_)·fwdSign` jumps by
≈ −50,000 counts (≈ 4.05 m at 12.343 counts/mm); velocity =
jump/dt with dt ≈ 24-48 ms (sample stamp held through the rejected
tick) ≈ **1-2 M counts/s**; `odomUpdate` (shims.cpp:213-233) folds the
teleport into the pose; `serviceMove` either falsely completes (via
KERN-15's unsigned distance progress) or wrong-way-aborts. Both bricks'
encoders reset together (one MCU), so the mean axis takes the full jump.

Not decidable from this repo: that a brick MCU brownout/reset restarts
the 0x46 cumulative counter near zero (rather than, say, holding it in
battery-backed RAM or wedging the bus). The review's bench experiment is
the right decisive test and is named: power-cycle the brick mid-drive
with the tick loop alive; watch DIAG 10/11 and pose. Verdict stands as
CONFIRMED-conditional at the review's own medium confidence.

### Spot-checked Minors

- **KERN-08** — confirmed; see table. The contradiction is textual and
  real; today's only consumers (goToW's cos/sin) are wrap-immune, so
  Minor is the right bin.
- **KERN-15** — confirmed; see table. `progress()` (motion_engine.cpp:
  300-319) shares the unsigned pattern, consistent with the finding.
  Requires net full-magnitude reverse motion to bite, so Minor/latent is
  right — though note it is exactly the mechanism KERN-07's jump would
  trip.

# Motion, kernel, ports, shims, protocol fiber — annex

Reviewer scope: `src/core/diffdrive.{h,cpp}`, `src/motion/motion_engine.{h,cpp}`,
`src/platform/*`, `src/shims.cpp`, `src/comms/protocol.{h,cpp}`,
`src/comms/{run_queue,emit_queue}.h`. Code state: master at `50efc2d`
(sprint 028 merged). Every algorithm claim below marked MEASURED was run
against the real `diffdrive.cpp` + `motion_engine.cpp` linked to
`tests/host/fake_ports.h` by [`profile_probe.cpp`](profile_probe.cpp);
the full output is [`profile_probe.out`](profile_probe.out). The wheel
model is ideal (wheel speed = applied duty × `fullDutyVelocity`, landing
one tick after it is staged, which is the real stage→tick→motion pipeline)
unless a row says `tau80` (first-order motor lag, 80 ms). The kernel
config is `shims.cpp`'s `ensure()` bake verbatim (`kp` 0, `ki` 6, `iMax`
765.6, `vMin` 893.2 = 70 mm/s, `twistHoldGain` 2.0, 24 ms). Ideal-wheel
numbers bound what the control law itself does; hardware adds motor lag,
stiction and brick latency on top, so a hardware number can only be worse.

Build and run:

```
/usr/bin/c++ -std=c++20 -O1 -w -I src -I tests/host -o /tmp/probe \
    docs/code-review/2026-09-02/raw/profile_probe.cpp \
    src/core/diffdrive.cpp src/motion/motion_engine.cpp && /tmp/probe
```

| ID | Sev | Where | Summary |
|---|---|---|---|
| MK-01 | Major | `motion_engine.cpp:586-622,853` | Pivot completion is detected after the crossing and the neutral lands a tick later; at the 70 mm/s floor that is ~1.5°/tick, so pivots coast +0.8…+2.6° (ideal wheels). `pivot_overrun` calibrates this latency away per robot instead of terminating predictively |
| MK-02 | Major | `diffdrive.cpp:599,617` | Twist-hold reference integrates the *pre-floor* twist while the wheels run the *floored* twist; in every floored crawl the servo accumulates a phantom error and brakes (−11…−13 % reverse duty at pivot end; 45° arc lands 15 mm long) |
| MK-03 | Major | `diffdrive.cpp:643-655,856-873` | No proportional velocity term (`kp` 0) and no anti-windup on the position reference: +10 % overspeed after every ramp (+20 % with 80 ms lag), and a single frozen encoder tick is a +6-point duty kick through the *position* I-term, not the velocity error the open issue names |
| MK-04 | Major | `motion_engine.cpp:338-343,678,793`; `nezha_port.cpp:342-347`; `wheelsV` | Jerk is unbounded at both ends of every move and everywhere outside the move engine: first tick steps to max(70 mm/s, 25 % cruise) (2932-4167 mm/s²) in every mode including jerk-limited, the end is a hard neutral from the crawl, `set wheel speeds` steps 0→200 mm/s in one tick, port slew is ≈1000 %/s |
| MK-05 | Minor | `motion_engine.h:727-728`; `diffdrive.cpp:905-917` | Two floors in two objects: the engine's 25 %/12 % taper floor sits below the kernel's 70 mm/s `vMin` for any cruise under 280 mm/s (583 for turns), so the floor knobs and `test.ts`'s 25/12 vs 45/35 profiles are inert; the crawl is the kernel's |
| MK-06 | Minor | `motion_engine.h:733-815` | Shaped mode is opt-in and only `tools/field_dance.py` opts in; blocks, `test.ts` and the wire default all run the legacy taper whose decel grows as v² (6058 mm/s² at cruise 400) |
| MK-07 | Minor | `motion_engine.cpp:577-578` | Completion margins (4 counts yaw, 10 counts distance) are smaller than one tick of floor crawl (21 counts); they are "have we crossed" tests, not arrival windows |
| MK-08 | Suggestion | `motion_engine.cpp:587-589` | Distance completion uses unsigned progress; a leg driven the wrong way counts toward done, and `wrongWay` exists only for yaw |
| RC-01 | Major | `shims.cpp:1401-1435,1519-1527,1122-1131` | Every OTOS I2C entry (`otosBegin/Read/Zero/Calibrate/SetOffset`, `seedPose`, `SET rebase`) skips the `stepBusy` guard `tickDrive()` takes, so a block program on the main fiber can land a transaction in the other fiber's encoder settle window. The invariant is documented three times and enforced nowhere |
| RC-02 | Minor | `shims.cpp:336-339,825-828`; `encoder_glitch_armor.h:98` | The cross-fiber stop writes the motor register inside another fiber's settle window by design; a destroyed sample reads raw 0, and the armor only rejects `|Δ| > 5000`, so within ~40 cm of the counter's zero a Phase-F zero is accepted as real motion |
| RC-03 | Minor | `protocol.h:146-156`; `shims.cpp:486-571` | `motionOwner_` arbitrates wire vs RUN job; the block program's fiber is a third executor with no arbitration and silently supersedes a live wire move |
| RC-04 | Suggestion | `protocol.cpp:310-328,397-407` | The protocol fiber now hosts the whole TS job call chain; every yield in a job's tick loop pays CODAL's stack copy for that depth. UNVERIFIED; this fiber has overflowed 2 KB before |
| CO-01 | Major | `motion_engine.cpp:500-862` | `serviceMove()` is two profile algorithms interleaved through five mode forks plus a jerk block plus an exit block; extract a `Profile` object |
| CO-02 | Major | `shims.cpp:265-301`; `motion_engine.cpp:516-563,883-914` | The rebase-epoch guard is written three times and the pivot→straight handoff burns a tick, both because the kernel has no "re-anchor at a segment boundary" call |
| CO-03 | Major | `shims.cpp:106-126,265-301,1013-1019,1519-1527`; `encoder_pose_source.h` | Odometry state, its three writers and its read adapter are spread over Rig, `EncoderPoseSource` and four free functions; it wants to be one `Odometry` object that *is* the `PoseSource` |
| CO-04 | Minor | `shims.cpp:842-871,825-828,592` | The soft-stop triplet (`engine.endMove` + `kernel.neutral` + `deliverStopNow`) is written four times |
| CO-05 | Minor | `shims.cpp:1039-1215,923-987`; `wire_adapter.cpp:kFields`; `motion.ts:ConfigField` | The config surface is four parallel tables keyed by ordinal; the diag surface is a fifth |
| CO-06 | Minor | `shims.cpp:184-200,1277-1293` | `pendingGoToDeadlineMs_` is Rig state existing only to dodge PXT's 4-argument shim limit |
| CO-07 | Minor | `diffdrive.h:10-12`; `src/DESIGN.md §2` | The "byte-identical vendored kernel" rule is already broken (`cycleGapCount`), and MK-02/MK-03 need kernel changes; decide whether this repo owns the fork |
| CH-01 | Minor | table below | Comment ratio: `motion_engine.h` 4.3, `protocol.h` 3.7, `radio_transport.h` 7.3, `shims.cpp` 1.5 comment lines per code line vs the kernel's 0.03; a boil-down list of 18 blocks follows |
| CH-02 | Minor | seven sites | Comments that are now false: file names, ordinals, "not consulted by anything yet", "the move engine lives here", "separate capped-curvature path" |
| CH-03 | Minor | six `captures/` citations | MEASURED citations point at artifacts that are gitignored and untracked (`gopiv-profile-sweep-20260901`, `motion-profile-probe-20260901`, `vevov-square-20260829`, `fleet-tours-speed-20260831.json`, `tigez-cal-20260830`); a clone cannot follow them |

---

## 1. Algorithm review — how the profile is shaped, and what it costs

### What the loop actually is

Read `controlStep()` with the fleet bake in hand and the controller is
simpler than the class suggests:

```
duty = ( FF + I ) / fullDutyVelocity
FF   = commanded wheel speed (after twist-hold trim, after the 70 mm/s floor)
I    = clamp(ki · clamp(reference − position, ±posErrMax), ±iMax)
reference += commanded speed · dt        (never clamped)
```

`kp` is 0, `kaff` is 0, wheel gains are 1/0, bias adaptation has a 30 s
time constant, lambda is off. So the *only* feedback is an integral of
position error, and the velocity error `errLeft/errRight` computed at
`diffdrive.cpp:643-644` reaches the duty through nothing but
`adaptBias()`. Two consequences follow directly and both are measured
below: the loop has no damping (MK-03), and the open issue's diagnosis of
the frozen-encoder transient names the wrong term (MK-03).

On top of the kernel, `MotionEngine::serviceMove()` shapes a move by
multiplying one full-rate command by a scale in [floor, 1]: a time ramp
(legacy) or an accel integrator (shaped) on the way up, a
remaining-distance taper (legacy: `remain/distTaper`, i.e. v ∝ remain) or
a `sqrt(2·a·remain)` brake (shaped) on the way down, min-combined, floored,
optionally jerk-rounded, and re-issued every tick with a 500 ms lease.
Completion is a position test after the fact.

### MK-01 — Pivot end: the coast after "reached" is what `pivot_overrun` calibrates

MEASURED (E3c, E3d, ideal wheels, twist-hold off to isolate the
mechanism): a 90° pivot at cruise 100 reads 88.69° at tick 47, 90.22° at
tick 48 (`reached` fires, `neutral()` is *staged*), and the wheels keep
moving through tick 49 because the neutral only lands on the next
`step()`. Terminal crawl is 1.47-1.53°/tick — that is the 70 mm/s floor
(70 mm/s · 24 ms = 1.68 mm per wheel = 21 counts, against a 4-count yaw
margin). Final yaw with the servo off: +1.95° (cruise 60), +2.56° (100),
+0.81° (200).

The measured hardware constant is "+2° per pivot, 3° and 90° alike"
(`motion_engine.h:218-236`), and the compensation is `pivotOverrunMm` =
2.2 mm per wheel — one tick of floor crawl (1.68 mm) plus the brick's own
stop latency. That is a per-robot calibration of a pipeline latency the
engine could compute. Two fixes, either sufficient:

- **Terminate predictively.** Stop commanding when `remain <= v_cmd·dt
  + stopDistance`, where `v_cmd` is this tick's floored command and
  `stopDistance` is the port's measured stop lag. The engine already
  knows `v_cmd` (`velCmd·scale`) and `dt`.
- **A yaw floor in yaw units.** 70 mm/s per wheel is 67°/s on a 120 mm
  track. A pivot's crawl should be set in °/s (e.g. 15-20°/s) so the
  quantum per tick is 0.4°, not 1.5°. `maxYawRateDegS_` caps the top; there
  is no yaw-unit floor.

Dedupe: `clasi/issues/done/pivots-over-rotate-on-corrected-firmware.md`
closed by adding the compensation constant; the mechanism is not filed.

### MK-02 — Twist-hold servo vs speed floor (kernel, vendored)

`diffdrive.cpp:599` integrates the twist-hold reference from
`scaledTwist = lambda · cmd.twist`, *before* `applySpeedFloor()` at
line 617 rescales both wheels up to `vMin`. Whenever the floor binds, the
wheels run a larger half-differential than the reference is integrating,
the error goes negative, and `trim` (gain 2/s, headroom ≈ 9900 counts/s)
brakes the turn.

MEASURED (E3d, E3e, ideal wheels):

| move | twist-hold 2.0 | twist-hold 0 |
|---|---|---|
| pivot 90° cruise 60 | most-negative right duty **−13.0 %**, ends **88.20°** | +0 %, ends 91.95° |
| pivot 90° cruise 100 | **−11.0 %**, ends **88.07°** | +0 %, ends 92.56° |
| pivot 90° cruise 200 | 0 %, ends 91.42° (floor barely binds) | ends 90.81° |
| arc 300 mm / 45° cruise 100 | ends (285.1, 120.2) | ends (269.8, 111.6) — the exact arc endpoint is (270, 112) |

So in the crawl phase of every pivot below ~200 mm/s cruise and every
floored arc, the one servo that exists to hold heading is fighting the
floor, ending with a reverse kick (−11 % duty, a 2°/tick reversal) on ideal
wheels. Hardware magnitude UNVERIFIED — real motors and the brick's
latency change the numbers, and the fleet measures pivots long, not
short — but the two code paths feeding different twist values into one
reference is not in doubt. Fix in the kernel: integrate the reference from
the post-floor half-differential (`0.5·(speedRight − speedLeft)`) and
compute headroom from the same floored speeds. Vendored: upstream both.

Dedupe: none. The twist-hold servo's *existence* is discussed in sprint
015 ticket 005 (the handoff neutral) and `odometry-closure-tuning-knobs`
(memory); the floor interaction is not.

### MK-03 — No damping, no anti-windup; the frozen-tick transient is the position I-term

MEASURED (E1, E7, E11, E1b): a 600 mm straight at cruise 200 peaks at
220.7 mm/s (+10 %) on ideal wheels right after the ramp; at `ki` 3 it is
+8 %, at 1.5 it is +5 %. With an 80 ms motor lag the peak is 241 (+20 %).
`set wheel speeds 200 200` from rest reads 0, 200, 229, 229, 225, 221 mm/s
on consecutive ticks. The cause is the one-tick stage→land→move pipeline:
the reference starts integrating a tick before the wheel can move, the
backlog is a real position error, and with no proportional term nothing
opposes the integral's catch-up.

MEASURED (E5): freezing the right encoder for one tick at 300 mm/s cruise
steps that wheel's duty 35.3 → **41.3 %** for one tick (the position
reference advanced 92 counts while `sample.position` held; 6 · 92 = 551
counts/s = 5.1 % duty) and the wheel genuinely runs 17 % fast for a tick
(measured velocity 4461 vs 3808 counts/s). That reproduces the open
issue's "duty jumps 4-12 points" — through `positionError()`, not through
`errLeft/errRight`. With `kp` 0 the velocity error is not in the duty at
all, so the issue's proposed fix (gate the velocity error on freshness)
would change nothing on the fleet bake. The fix is to freeze the
*reference advance* for a wheel whose sample did not advance
(`positionError()` already knows `dt`; skip `ref.reference += speed·dt`
when `!fresh`).

Anti-windup: `ref.reference` accumulates without bound; only the returned
error is clamped (`diffdrive.cpp:866-871`). A wheel that runs ahead or
behind by more than `posErrMax` (10 mm) for any reason carries the whole
backlog into the taper and discharges it there — the `movex-end-bump-
is-an-i-term-stall` memory is this backlog braking the wheel at the floor.
Clamp the reference to `position ± posErrMax` after each update.

Dedupe: corrects the mechanism in
`clasi/issues/pid-error-uses-a-stale-velocity-sample-after-an-encoder-fault.md`;
cross-reference, do not duplicate.

### MK-04 — Jerk

Nothing in this system bounds jerk where it matters:

- **Start.** `startSegment()` seeds `cmdScale` at 0.25 (legacy) or the
  taper floor (shaped), and `applySpeedFloor()` raises anything smaller to
  70 mm/s, so the first tick is a step to max(70 mm/s, 25 % cruise).
  MEASURED (E1): start accel 2932 mm/s² at cruise 100/200 and 4167 at
  cruise 400 in *every* mode, including `jerk = 4000`; the jerk limiter
  starts from `accelScalePerS = 0` but from a scale that is already a
  quarter of cruise.
- **End.** The move ends with a staged neutral from the crawl speed. The
  profile-exit mode (E9) ends it from 54-64 mm/s instead of 70 and calls
  that a glide. Every mode's peak decel is the stop itself.
- **Continuous drive.** `wheelsV()` hands the step straight to the kernel
  (E7: 0 → 200 mm/s in one tick, 8300 mm/s²). Shaping exists only inside
  the move engine's scale multiplier.
- **Port.** `slewRate_` 25 %/tick = 1040 %/s. Not a limiter.
- **Legacy taper.** v ∝ remain gives decel ∝ v²: MEASURED mid-profile
  peak 1559 mm/s² at cruise 200 and **6058 at 400** (shaped: 553 and 534);
  with 80 ms lag the legacy cruise-400 leg overshoots +5.6 mm, shaped
  −0.6 mm.

Recommendation: put one velocity-setpoint rate limiter (accel, optionally
jerk) in the kernel's command path, so `drive()` from any caller —
`wheelsV`, `wheelsX`, the move engine, a student's `driveTwist` — is
shaped once, in one place. Then the move engine's ramp/jerk code
(`serviceMove` lines 680-760) deletes, and the taper only has to decide
*when to start braking*. Let the taper reach zero and terminate
predictively (MK-01) instead of holding a floor and dropping it.

Dedupe: `moves-crawl-and-correct-instead-of-gliding-to-a-stop.md` (done,
profile exit) and `dist-taper-ceiling-defeats-constant-decel-above-200-mm-s.md`
(done) cover the taper's tail; the start step, the unshaped continuous
path and the port slew are not filed.

### MK-05 — Two floors

`distFloor_` 0.25 / `turnFloor_` 0.12 (engine, fraction of cruise) and
`vMin` 893.2 counts/s = 70 mm/s (kernel). For cruise < 280 mm/s the engine
floor is below the kernel's, so the command that reaches the wheels in the
crawl is 70 mm/s regardless of `SET dist_floor`, `setTaperFloors()` or
`test.ts`'s two profiles (25/12 vs 45/35 — both below 70 at speed 20-40
cm/s). MEASURED (E10): the legacy crawl at cruise 200 runs 48-62 mm/s
actual (commanded 70, the I-term backlog braking it). MEASURED (E3b):
turning `vMin` off changes a cruise-100 pivot from 48 to 64 ticks and from
+0.22° to −0.23° — the floor decides the pivot's end, not the engine.

One floor, in one object, per axis, in axis units.

### MK-06/07/08 — smaller

- Shaped mode is reachable only via `SET a_accel/a_decel/...` and only
  `tools/field_dance.py` sets it. The comments say "UNVERIFIED pending a
  bench sweep" while `captures/gopiv-profile-sweep-20260901/` (untracked)
  suggests the sweep ran. Decide: promote or delete. Two modes in one
  method is the cost either way (CO-01).
- Margins 4/10 counts against a 21-count crawl quantum (MK-07).
- `distDone` on `|meanProgress|` (MK-08).

### Where accuracy goes, ranked

1. Pivot end latency, ~+2° per pivot, calibrated away per robot (MK-01).
2. Twist-hold vs floor in every crawl (MK-02) — hardware magnitude unknown.
3. I-term overspeed after every ramp and backlog discharge in every taper (MK-03).
4. Legacy taper above ~250 mm/s (MK-04); shaped fixes it, nobody runs shaped.
5. Feed-forward gain: `fullDutyVelocity` 10795 is inherited, not measured
   (`measure-vevov-s-true-full-duty-velocity.md`, filed); at cruise > 250
   the I term is pinned and speed is not reached.
6. Reversal dwell asymmetry: after a pivot, the wheel that reversed is held
   at 0 for 100 ms (`nezha_port.cpp:293-303`, credited from the neutral
   tick) while the other starts. MEASURED (E8) on the ideal model the
   twist servo absorbs it (≈1 mm, 0.1°). On hardware UNVERIFIED — worth
   one look at `dutl/dutr` on the first four ticks after a pivot.

---

## 2. Races and the bus

Yield points in this scope (CODAL is cooperative, so these are the only
places state can change under a fiber): `CodalSleeper::sleepMillis/yield`
(kernel settle ×2 per step, `tickDrive` pacing and busy-wait, watchdog
period), `OtosPort::busGap()`/`begin()`, `vfpSafeSleep(2)` in
`emitLineNow`'s radio retry, `vfpSafeSleep(kPollIntervalMs)` in
`Protocol::run()`, `vfpSafeSleep(4)` in `NezhaMotorPort::begin()`, and
anything inside `runAction0()` (the TS handler, which yields in its own
`_tickDrive` loop and `basic.pause`).

### RC-01 — OTOS transactions do not take the bus guard

`tickDrive()` serialises `kernel.step()` behind `stepBusy` and sleeps
while another fiber holds it (`shims.cpp:647-650`). The OTOS surface does
not: `otosRead()` → `OtosPort::read()` issues a write and a 12-byte read
with no check (`shims.cpp:1410`, `otos_port.cpp:116-127`); `otosBegin()`,
`otosZero()`, `otosCalibrate()`, `otosSetOffset()`, `seedPose()` and `SET
rebase` (`setKernelValue` case 32 → `otosRef().setPose()`) likewise.

Concrete scenario: a student program calls `goToWorld()` (main fiber)
while a bench host has a `MOVE_X` obligation live on the protocol fiber.
The protocol fiber is parked in `step()`'s 4 ms settle sleep after
`left_.requestSample()`; the main fiber runs, `readWorld()` writes 0x17;
the protocol fiber wakes and reads 0x10's encoder register, which now
returns the Phase-F garbage the design documents
(`nezha_port.cpp:376-380`). The reverse interleaving (block `move` on the
main fiber, `RUN:fix` arriving over the wire) is now safe only because
sprint 028 put RUN jobs on the protocol fiber; the block-program case is
untouched.

The invariant is stated in `world.ts:9-12`, `otos_port.h:18-22` and
`src/DESIGN.md §7` and enforced nowhere. Remedy: one bus-ownership
object (or just `stepBusy` promoted to a `BusGuard` with `acquire()` that
sleeps while held), taken by `tickDrive()` *and* by every OTOS entry.
Three lines per entry point, and the invariant becomes structural.

### RC-02 — The cross-fiber stop is a Phase-F write

`deliverStopNow()` (`shims.cpp:336`) and the watchdog (`825-828`) write
the motor-run register from whichever fiber calls them. Sprint 006
chose that deliberately so a stop lands inside the tick fiber's settle
window; that is the same interposition RC-01 forbids, and the destroyed
encoder sample "reads as raw 0" (`nezha_port.cpp:378-379`).
`EncoderGlitchArmor` rejects only `|raw − lastGood| > 5000`
(`encoder_glitch_armor.h:98`). The 0x46 counter is never device-reset, so
for the first ~40 cm after the brick powers up a raw 0 is within 5000 of
the last good value and is **accepted** — position jumps back toward 0,
then forward again on the next good read, and `odomUpdate()` integrates
both. Remedy: reject `raw == 0` explicitly when `lastGoodRaw != 0` (it is
the documented Phase-F signature), and prefer staging the stop for the
busy fiber to deliver when `stepBusy` is set.

### RC-03 — Three executors, two arbitrated

`motionOwner_` is `kNone/kWire/kJob`. A block program's own fiber (any
`move`, `goTo`, `driveTick` loop) is a third executor: `startMove()`
(`shims.cpp:486`) calls `engine.moveX()` unconditionally, which supersedes
a live wire move; the wire's `armPendingMotion` then resolves off the
student's move and reports `kStop`. Not a crash; a silent mis-attribution.
Either refuse block motion while `motionOwner_ != kNone` (the obvious
student-facing behaviour is "the bench has the robot") or document the
gap.

### RC-04 — Protocol fiber stack depth (UNVERIFIED)

`dispatchJob()` → `runDispatch()` → `runAction0()` → the TS handler →
`_tickDrive` → `tickDrive()` → `serviceHook` → `serviceOnce()` →
`drainEmitQueue()` (241-byte local) → `emitLineNow()` → `sendLine()`. Every
`vfpSafeSleep` in that chain copies the fiber's stack to the heap
(CODAL stack paging). `radio_transport.h` records this fiber overflowing
a 2 KB stack when scratch buffers lived on it. Worth one measurement of
the high-water mark under a tour; not a defect I can demonstrate.

### What held up

- `ensure()` non-reentrancy: filed (`ensure-is-not-reentrant-two-rigs-can-be-constructed.md`). `otosRef()` has the same shape but `OtosPort()` cannot yield; `protocol()` assigns before `start()`, so both are safe as written.
- `output()`/`snapshotCommand()` seqlocks are correct for the single-writer case, and with cooperative fibers `step()` cannot be interrupted between `++outSeq_` pairs except at its two settle sleeps, which are outside `publishOutput()`.
- `stepBusy` check-and-set has no yield between test and set (`shims.cpp:647-650`); correct under CODAL.
- `cancelMove()` clearing `awaitingHandoffNeutral`, and `moveX()/goToR()` clearing it on entry: correct; the probe's split move (E4) reaches (−7.6, 300.1) for a 90° + 300 mm request — the x error is MK-01's pivot coast, not the handoff.
- `drive()` refusal now gates `move_.active` (08-26 C-07 fixed); `serviceMove()` ends on `estopped` (C-06 fixed); `endMove()`/`wheelsX()` neutral the kernel (C-04, C-09 fixed).
- `kMaxCycleGapUs` re-anchor in `step()` is correct and the comment is the model of a good one.

---

## 3. Cohesion

### CO-01 — `serviceMove()` is two profilers braided together

Lines 500-862: legacy/shaped forks at 601, 651, 697, 723 and 676, the jerk
integrator, the profile-exit test, the handoff, the rebase guard, the
terminator. Thirteen shaping knobs on `MotionEngine`, five of which are
inert below 280 mm/s (MK-05) and four of which nobody sets. The shape that
wants to exist:

```
class Profile {            // owns accel/decel/jerk/floor/exit for ONE axis-set
  float advance(float remainDist, float remainYaw, float dt);   // -> scale
  bool  done() const;      // profile-complete (MK-01 predictive stop here)
};
class MoveState { ... uses Profile ... };   // targets, handoff, deadline
```

with `LegacyTaper` and `TrapezoidProfile` as the two implementations and
a single `if` at construction instead of five in the loop. Then MK-04's
"put the slew in the kernel" removes the ramp half of both.

### CO-02 — Kernel API gaps the engine papers over

- Rebase: `rebasePosition()` is deferred to the next `step()`, so
  `odomUpdate()` (`shims.cpp:276-286`), `serviceMove()` (`557-563`) and
  `progress()` (`894-899`) each carry an epoch re-anchor. Three copies of
  one rule, each with a 15-line comment.
- Handoff: `awaitingHandoffNeutral` exists because the twist-hold
  reference only disarms on a neutral step, so phase 2 waits a tick.

Both are the same gap: the kernel cannot re-anchor its integrators at a
segment boundary on request. One `rearmReferences()` (immediate, no
motor write) retires the flag and lets `rebasePosition()` be synchronous
from the engine's side, deleting all three guards. Vendored — but see
CO-07.

### CO-03 — Odometry is not an object

Rig holds `x/y/heading`, `odomPosLeft/Right`, `odomPrimed`, two epochs;
`odomUpdate()` is a free function over them; `EncoderPoseSource` binds
`const float&` to three of them (with a 45-line lifetime essay);
`resetPose()`, `seedPose()` and `SET rebase` are three writers with three
slightly different pre-steps. `updateMove()` gates the update on
`wasActive`, `tickDrive()` does not, and the telemetry path mutates it as
a side effect of reading (`poseX()`). An `Odometry` class — `update(const
Output&)`, `reset()`, `seed(x,y,h)`, and `PoseSource` implemented directly —
retires `EncoderPoseSource`, the lifetime comment, and the epoch copy in
`odomUpdate`. 08-26 Q-02 asked for this; sprint 028's epoch handling made
it more urgent, not less.

### CO-04/05/06/07

- Four copies of the soft-stop triplet (`stopAll`, `endMove`, watchdog,
  `updateMove` + `serviceMove`'s own neutral). One `softStop()`.
- `setKernelValue` (34 cases), `getConfigValue` (34 cases),
  `WireAdapter::kFields`, `ConfigField` in TS, and `diagValue` (30 cases)
  are five hand-synchronised ordinal tables. One descriptor table with
  getter/setter function pointers replaces three of them and makes the
  `protocol.h` "ordinal 30" comment error (CH-02) impossible.
- `pendingGoToDeadlineMs_` is per-call state stored on the singleton to
  dodge a 4-argument shim limit; make the go-to timeout a config field
  (it already has the machinery) and delete the two-shim dance.
- The kernel is "byte-identical to upstream except `cycleGapCount`", and
  MK-02, MK-03 and CO-02 all need kernel edits. Either this repo owns the
  fork (drop the byte-identical rule, keep a fidelity test on the control
  law's *behaviour*) or the changes go upstream first. Deciding is cheaper
  than three more "local fix not yet ported back" comments.

---

## 4. Comments

### CH-01 — the numbers

Comment-only lines per code line, non-blank (this pass, `awk` over
`src/`):

| file | code | comment | ratio |
|---|---|---|---|
| `comms/radio_transport.h` | 43 | 312 | **7.26** |
| `comms/serial_transport.h` | 19 | 107 | 5.63 |
| `comms/wire_adapter.h` | 66 | 329 | 4.98 |
| `motion/motion_engine.h` | 142 | 610 | **4.30** |
| `platform/encoder_pose_source.h` | 20 | 82 | 4.10 |
| `core/heading_wrap.h` | 11 | 44 | 4.00 |
| `platform/vfp_guard.h` | 13 | 50 | 3.85 |
| `comms/protocol.h` | 87 | 324 | **3.72** |
| `core/encoder_glitch_armor.h` | 42 | 105 | 2.50 |
| `comms/wire_handler.h` | 212 | 524 | 2.47 |
| `blocks/*.ts` (six files) | 556 | 881 | 1.58 |
| `comms/protocol.cpp` | 221 | 342 | 1.55 |
| `shims.cpp` | 577 | 846 | 1.47 |
| `comms/wire_adapter.cpp` | 426 | 548 | 1.29 |
| `motion/motion_engine.cpp` | 418 | 438 | 1.05 |
| `platform/nezha_port.cpp` | 254 | 245 | 0.96 |
| `core/diffdrive.cpp` | 815 | 22 | **0.03** |

The 08-26 review measured project-owned `src/` at 1.22; it is now ~1.4
and every file sprint 026-028 touched grew. The archaeology ratchet
(`_BUDGET = 388`) holds the sprint/ticket-ID count but not the volume —
the new comments cite dates and captures instead of sprint numbers and
are just as long.

### Boil-down list (my scope; replacement text is the whole comment)

| # | file:lines | now | replace with |
|---|---|---|---|
| 1 | `motion_engine.h:1-120` | 120-line header restating both primitives, all four reductions and the sign convention | "Two primitives (`wheelsV`, `wheelsX`) and the reductions onto them; spec: radio-robot-lib motion-api.md §2-3. CCW-positive; b = trackWidth/rotationalSlip. Host-portable: no CODAL includes." (5 lines) |
| 2 | `motion_engine.h:353-407` | 55 lines on `settleToRest()`'s extraction history | "Steps the kernel up to 12 times until both wheels measure < 25 counts/s. Needed because `neutral()` is staged and one step's encoder read can freeze `Output.velocity*` mid-spin-down (measured, commit 3e919e5)." |
| 3 | `motion_engine.h:678-703` | the `rotationalSlip_` derivation | **keep** lines 674-697 (the derivation); delete 699-703 ("REPLACES 1.040…") |
| 4 | `motion_engine.h:733-815` | seven knob comments, ~80 lines | one paragraph per knob: unit, 0-means, the one measured number |
| 5 | `motion_engine.cpp:503-522` + `526-563` | handoff and rebase-race essays | 4 lines each: what the flag waits for, why (twist ref disarms only on a neutral step; rebase is deferred to next step), the measured symptom |
| 6 | `motion_engine.cpp:806-836` | twist-hold handoff essay | 5 lines (already summarised in the header) |
| 7 | `motion_engine.cpp:630-649` | yaw-axis shaped-mode history with the 800/400/100 sweep | keep the measured row, drop the narrative: "Kinematic window, not `yawTaper_`, in shaped mode. MEASURED vevov 2026-09-02: fixed window 800→100 counts traded 375→146 ms per pivot for +0.36→+4.97° error." |
| 8 | `nezha_port.cpp:11-55` | fault-handler forensics plus two dated UPDATE paragraphs | "Fault handlers: stop the motors before anything else — the default weak handler spins forever and the brick holds its last command (MEASURED tigez 2026-08-30, captures/tigez-cal-20260830/). Root cause was the VFP clobber, fixed by vfp_guard.h; the handler stays as the last line of defence." |
| 9 | `nezha_port.cpp:182-219` | 38-line bus-hang guard essay | "codal-nrf52 1fbb724 bounds a stuck I2C call at ~11 s (`NRF52I2C::waitForStop`). Stop at the first failure so a dead brick costs one call, not three per wheel." |
| 10 | `nezha_port.cpp:403-442` | 40 lines on holding `sampleTimeUs_` in the rebaseline branch | "Hold `sampleTimeUs_`: this tick's true velocity is unknown, and a fresh zero sample is what the PID chased to 420 mm/s (MEASURED gopiv 2026-09-02, captures/gopiv-frozen-encoder-fix-20260902/notes.md)." |
| 11 | `shims.cpp:303-335` | `deliverStopNow()` essay | "Immediate port-level zero on both motors. `neutral()` is only staged, and a stop issued from a fiber that is not the ticker would otherwise wait for the watchdog (~100-150 ms). Never `emergencyStopMotors()`: that latches the e-stop." |
| 12 | `shims.cpp:604-634`, `654-672`, `676-702` | `tickDrive()` header and two inline histories | 8 lines total: one step + serviceMove per call on the caller's fiber, absolute-deadline pacing, returns `commandLooksActive()`, settle before reporting done |
| 13 | `shims.cpp:411-432`, `437-462`, `464-478` | wire-forward rationales | one line each: what the forward returns and who calls it |
| 14 | `shims.cpp:184-200`, `1247-1293` | the go-to shim split saga (three blocks) | "PXT rejects `//%` shims with more than four parameters (TS9200). `engineSetGoToDeadline()` supplies the fifth." |
| 15 | `shims.cpp:1062-1140` | per-case commentary in `setKernelValue` | delete; the descriptor table (CO-05) makes the ordinals self-describing |
| 16 | `protocol.h:146-230` | 85 lines on `motionOwner_`, `dispatchJob`, `serviceOnce`, `serviceHookEntry` | 20 lines: the three owners, the one rule (a job is dispatched once; nested `serviceOnce` is the same fiber), and why the hook is a no-op outside a job |
| 17 | `protocol.cpp:40-101`, `138-153` | identity essay; `emitLine` clip archaeology | 10 lines for identity (what each field is, who injects it, "profile ≠ name is the diagnostic"); one line for the clip |
| 18 | `encoder_pose_source.h:1-70`, `heading_wrap.h:1-50` | 70- and 50-line headers over 3- and 6-line bodies | 8 and 6 lines: contract, unit, wrap convention, the one measured number |

### CH-02 — comments that are wrong today

| where | says | actually |
|---|---|---|
| `diffdrive.h:1-3`, `diffdrive.cpp:1` | "differential_drive.h … differential_drive.cpp" | files are `diffdrive.{h,cpp}` |
| `protocol.h:281`, `src/DESIGN.md:832` | RUN drop count is "diagValue ordinal 30" | `shims.cpp:978` — ordinal 28; 30 is `max_yaw_rate` in `setKernelValue` |
| `motion_engine.h:768-787` | `vMaxMmS_`/`brakeFrac_` feed "a future resolver … Not consulted by anything yet" | `defaultCruiseForDistance()` (`motion_engine.cpp:105-109`) reads both |
| `motion_engine.h:69-73` | goToWorld is "a separate TS-level turn-first/capped-curvature call path" | `world.ts:219-226`: cap removed, routes through `startGoTo` → `goToR` |
| `shims.cpp:9-14` | "MOVE ENGINE: … lives HERE as a start/update/end state machine" | moved to `motion_engine.cpp` (sprint 003) |
| `motion_engine.h:9-17` | "the TypeScript block API via shims.cpp's engine* forwards, and the wire adapter via the same forwards" (line-wrapped mid-clause) | blocks reach `startMove()`/`engineGoToRArmed()`, the wire reaches `engineMoveX()` etc.; not "the same" |
| `nezha_port.h:107-118` | `maxDrivenStreak_`/`rebaselineCount_` "exposed via diagValue() ordinal 27" | 27 is the rebaseline sum; the streaks are 21/22 |

### CH-03 — citations a clone cannot follow

`.gitignore:33` ignores `captures/`; 152 files are force-tracked, the
rest are not. Comments in `src/` cite these untracked directories as
MEASURED evidence: `captures/gopiv-profile-sweep-20260901/`
(`motion_engine.h:504,793`, `motion_engine.cpp:67,296,722`),
`captures/motion-profile-probe-20260901/profile_probe.py`
(`motion_engine.h:741`), `captures/vevov-square-20260829/`
(`motion_engine.h:220`), `captures/fleet-tours-speed-20260831.json`
(`motion_engine.h:773`), `captures/tigez-cal-20260830/`
(`nezha_port.cpp:18`). Per `.claude/rules/measurement-citations.md` the
artifact must be nameable *and reachable*; either track the cited
directories (they are small JSON/py files) or move the numbers into a
tracked `reports/*.md` and cite that.

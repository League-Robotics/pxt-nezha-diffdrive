# Adversarial verification — correctness-blocks.md (Majors + 2 Minors)

**Date:** 2026-08-23
**Verifier stance:** refute-first. Every Major was re-derived from source
independently of the reviewer's trace; refutation avenues actively hunted
(hidden tickers, guards, clamps, alternate call paths) are listed per
finding. Severity judged against `docs/code-review/guidelines.md`'s rubric.

| ID | Verdict | One-line justification |
|----|---------|------------------------|
| BLK-01 | **CONFIRMED** | Re-derived interleaving holds end to end: neutral() is staged-only (diffdrive.cpp:364-368), step() snapshots at :472 and writes duty at :493 *before* the settle sleeps (:496,:500), the delivery gate reads `wasActive` only after step returns (shims.cpp:466,482), and the only other ticker (protocol fiber) ticks solely on wire motion obligations (protocol.cpp:291-292) — abandonment until the 100-150 ms watchdog is real. Keep the frequency as a flagged estimate ("roughly a third"), see notes. |
| BLK-02 | **CONFIRMED** (scenario narrowed) | `runArgCount()` (main.ts:233-235) is unguarded vs its guarded sibling (:227); but any top-level `onRun`/`onRunCommand` registration also initialises `runParts` via `ensureRunState()` (:79-84,:190,:206), so the crash needs a call before *both* the first RUN and any registration — soften "any call outside a RUN handler". |
| BLK-03 | **CONFIRMED**, Major stands | Arithmetic re-verified (10/0.8102 = 12.343 counts/mm; 10795/12.343 = 874.6 mm/s); all four verbs resolve 0 through `engineDefaultCruiseMmS()` (wire_adapter.cpp:282-283, 307-308, 347-348, 364-365); no downstream clamp — cruise at 874.6 mm/s puts the dominant wheel's feedforward at the duty rail. "Landmine likely to bite in normal development" fits the Major rubric even though deliberate. |
| BLK-04 | **CONFIRMED** | All three sides traced: protocol strips `RUN:` and parks the bare payload (protocol.cpp:228-234,:106-151), the dispatcher makes "20" the *name* with zero args so `runArg(0)` is 0 (main.ts:160-172,:226-229), and `rigExec(0)` matches none of testrig.ts:62-108's branches; otos_bench.py:39-40 sends exactly those bare numerics. Entire rig vocabulary is a silent no-op. |
| BLK-05 | **CONFIRMED** (fix the scenario's loop) | Odometry gating verified by exhaustive call-site enumeration — nothing updates pose in continuous mode until a pose read, which integrates one chord (shims.cpp:213-233); full-circle arithmetic exact (R = 95.5 mm, 600 mm chord at midpoint heading, heading itself correct). But the cited `while (diffDrive.driveTick())` loop exits after ONE tick in continuous mode (tickDrive returns serviceMove()'s move-active = false; wheelsV cancels the move), so the "~4 s ticked" scenario needs an unconditional tick loop (e.g. testrig.ts:118-120's pattern). |
| BLK-06 | **CONFIRMED** | Wrapper ×10 (main.ts:107) makes `_setWheels` mm/s; `((right-left)/10)/115` (:804) is Δv/1150 — 10× under the physical Δv/115. Decisive cross-check: `_driveTwist`'s sim body (:809-814) is dimensionally correct, so the two equivalent continuous commands disagree 10× *with each other* in the sim; hardware (wheelsV → kernel) turns at Δv/124.8 mm. ±15 cm/s → sim ~15 °/s vs hardware ~138 °/s. |
| BLK-07 | **CONFIRMED** | Hardware latch traced: `estopAll` → `kernel.estop()` (shims.cpp:664-669); `drive()` refuses `kRefusedEstopped` while latched (diffdrive.cpp:311) and step forces neutral (:484) until `estopClear`. Sim `_estopAll` = `_stopAll`, `_estopClear` empty (main.ts:908-914). Spec §5 (specification.md:200-235) never mentions e-stop (grep: estop appears only in §2 and §6.3). |
| BLK-09 (spot check) | **CONFIRMED** | pxt.json:3 = `"1.0.10"`; protocol.cpp:63 `kVersion = "1.0.0"` with its own "keep in sync with pxt.json" comment. Drift is live. |
| BLK-12 (spot check) | **CONFIRMED for isMoving(), REFUTED for moveProgress()** — narrow the finding | `isMoving()` → `_updateMove` → `updateMove()` → `serviceMove()` really does reissue `kernel.drive(..., 500u)` and can end the move at the deadline (motion_engine.cpp:268-271, 290-296), so its "checks state only" doc is false. But `moveProgress()` → `_progress` → `diffDrive::progress()` (shims.cpp:643-646) → `MotionEngine::progress() const` (motion_engine.cpp:300-318) is genuinely read-only on hardware — the finding's "Both ... map to updateMove() → serviceMove()" is wrong for the second function. |

---

## Notes

### BLK-01 — the deep re-derivation the task asked for

**Ordering facts, independently established.**

1. `kernel.neutral()` only stages: it writes `command_` and bumps
   `cmdSeq_` (diffdrive.cpp:364-368). Delivery to motors happens solely
   inside a later `step()` (`snapshotCommand()` at :472 → `controlStep()`
   at :493 writes duty).
2. Within one `step()`, the duty write (:493) happens *before* the two
   settle sleeps (:496, :500; `kSettle = 4` ms each, diffdrive.h:358). So
   any cross-fiber `neutral()` staged during those sleeps was already
   missed twice: the snapshot predates it and the duty is already on the
   motors.
3. `tickDrive()` computes `wasActive = engine.isMoveActive()` at
   shims.cpp:466 — *after* `step()` returns. A cross-fiber
   `endMove()`/`stopAll()` during the sleeps clears `move_.active`, so the
   delivery/settle path at :482 (`wasActive && !moveActive`) is skipped,
   `serviceMove()` early-returns false (motion_engine.cpp:200), the
   `while (_tickDrive())` caller exits, and nothing steps again.
4. **Refutation hunts that failed** (i.e. the finding survives):
   - *Another ticker?* The protocol fiber starts at boot
     (main.ts:86) but calls `tickDrive()` **only** while
     `wireAdapter_.hasLiveMotionObligation()` (protocol.cpp:291-292),
     which only the six wire verbs arm (wire_adapter.cpp). Block-driven
     moves get no rescue tick.
   - *A guard on the teardown side?* `endMove()` (shims.cpp:649-652),
     `stopAll()` (:657-661) and `updateMove()` (:415-425) all skip the
     `stepBusy` flag; only a second `tickDrive()` waits on it (:460-462).
   - *Port-level write in the teardown?* Only `estopAll` →
     `emergencyStopMotors()` (diffdrive.cpp:378-382) touches ports
     directly — exactly the reviewer's "emergencyStop() is immune".
   - *Watchdog earlier?* `kWatchdogTimeoutUs` = 100 ms since
     `lastTickUs`, 50 ms poll (shims.cpp:605-606) → 100-150 ms, matching
     the finding; `commandLooksActive()` fires on `appliedDuty != 0` even
     with the move cleared (:618-622).

**Reachability from the documented block set:** `move(0, 180)` (blocking,
main.ts:247-250 is literally `while (_tickDrive());`) plus
`input.onButtonPressed(..., () => diffDrive.stopMove())` are all
documented blocks; PXT/CODAL button handlers run on their own fiber and
get scheduled at the ticker's yield points — which, during the busy half
of a tick, are exactly the settle sleeps. Reachable, yes.

**The ~35 % figure: keep it, flagged as derived.** A press is *missed*
iff its handler runs inside `step()` after the snapshot — i.e. the press
lands anywhere in [tick start .. end of second settle sleep] (a press
during the busy lead-in is *handled* during the first settle sleep, so
the lead-in counts toward the window; presses in the post-step tail or
the pacing sleep are handled while `stepBusy` is false and the *next*
step delivers the neutral). Window = 8 ms of settle sleeps + the busy
lead-in (controlStep + I2C duty writes, ~1-3 ms) out of a 24 ms period ≈
37-45 %. The reviewer's "~35-40 %" is inside the defensible band; since
it is derived, not hardware-measured, recommend phrasing it "roughly a
third of presses during a move" and keeping the existing
medium-confidence flag rather than dropping the number.

**Scenario (b) verified with its own narrowing intact:** the poller's
`serviceMove()` reads the *previous* tick's published Output, so any
encoder-derived end condition (distDone/yawDone, wrongWay) is always
observed by the ticker first from the same data — the poller can only
win on the clock-based `expired` check (motion_engine.cpp:274). That is
exactly the "blocked move's deadline backstop" case the finding states;
it did not overclaim (b).

**One overstatement to trim:** "coast counts never folded into odometry"
— they are folded *late*: the next `step()` (whenever one runs) reads
the post-coast encoders and the next `odomUpdate()` integrates them,
mis-attributed as one chord; worse, a next `startMove` baselines
`posLeft0/Right0` from the stale pre-coast Output
(motion_engine.cpp:77-79), crediting the coast to the new move. "Folded
late and mis-attributed" is the accurate (and still damning) phrasing.

### BLK-02 — the narrowing

`ensureRunState()` (main.ts:79-84) is called from `onRun` (:190),
`onRunCommand` (:206) and the dispatcher (:163). So a program that has
registered *any* run handler at top level already has `runParts = []`
before the student's button handler can run: no crash there (it returns
-1, a separate small wrongness the finding doesn't claim). The armed case
is real — `runArgCount()` before any registration and before the first
RUN (exactly the "test program logging it at top level" example) — and
test/test.ts:318 indeed only calls it inside a handler. Guard asymmetry
vs `runArgText` (:227) confirmed; remedy correct. Keep Major (panic-980
silent-boot-death class per main.ts:64-72), reword the frequency claim.

### BLK-03 — behavior, intent, and severity

Both sides re-traced: `engineDefaultCruiseMmS()` (shims.cpp:340-346)
returns `fullDutyVelocity / countsPerMm` = 10795 / (10/0.8102) =
**874.6 mm/s**; all four verbs substitute it for 0 (wire_adapter.cpp
lines cited in the table). Hunted for a downstream clamp and found none:
`wheelsX` normalises so the dominant wheel runs at exactly `cruise`
(motion_engine.cpp:40-43), which equals `fullDutyVelocity` in counts —
feedforward saturates duty, PID has zero authority, exactly as claimed.
Intent confirmed (shims.cpp:330-339; src/DESIGN.md:199-200). Under the
rubric, "a landmine likely to bite in normal development" is Major even
when deliberate; the calibration anchors (blocks default 15 cm/s at
main.ts:49; test/test.ts's "60 cm/s ... produced unusable runs") check
out. **Citation nit:** `motion-api.md` is not in-tree — the "pass 0 for
the configured default" contract exists only as verbatim quotes in
source comments (wire_adapter.h:188, shims.cpp:312-314, :330-332). The
finding should cite those, or the doc's actual location.

### BLK-04 — three-sided confirmation

The decisive question was whether the dispatcher could see "RUN" as the
name and 20 as the argument. It cannot: `handleRun()` receives the
payload *after* the stripped `RUN:` prefix (protocol.cpp:228-234) and
parks it verbatim, so the TS dispatcher's `split(":")` on "20" yields
`name = "20"`, no arguments, `runArg(0) = 0`. `rigExec(0)` falls through
every branch with no else — no reply line, no motion. The rig's own
`basic.forever` consumer (testrig.ts:112-117) dutifully executes the
no-op. Fully dead as claimed.

### BLK-05 — the tick-path hunt the task asked for

Exhaustive `odomUpdate` call-site enumeration (all nine):
`startMove` :354, `updateMove` :423 (gated on `isMoveActive`),
`tickDrive` :469 (same gate) and :499 (settle path, inside the same
gate), `poseX/Y/Heading` :722/:729/:736, `resetPose` :744, `seedPose`
:1033. In continuous mode `wheelsV()` clears the move
(motion_engine.cpp:21), so **no tick path updates pose** — `driveTick`,
`_tickDrive`, and the protocol fiber's obligation ticking all route
through the same gated `tickDrive()`. The reviewer missed nothing.
Full-circle arithmetic confirmed exact (see table). UC-009's "pose is
always live-updated from odometry regardless of command mode"
(usecases.md:275) is indeed contradicted.

**Scenario correction (does not weaken the finding):** the cited
`while (diffDrive.driveTick())` loop cannot tick for 4 s — in continuous
mode `tickDrive()` returns `serviceMove()`'s move-active flag
(shims.cpp:470, :544), which is false, so that loop exits after one
tick. (UC-002 step 4 and the `setWheelSpeeds`/`driveTick` doc comments
all prescribe that exact loop; its immediate exit in continuous mode is
a separate discrepancy this verification is not scoped to file.) Any
continuous drive that *is* ticked — testrig.ts:118-120's unconditional
`basic.forever` tick, a for-loop, a `while(true)` — accumulates the
chord error as described. Recommend the finding swap the loop in its
scenario for an unconditional one.

### BLK-06 — factor pinned two independent ways

(1) Dimensional: inputs are mm/s (wrapper ×10, main.ts:107); yaw rate
must be Δv/track_mm = Δv/115; code computes Δv/1150. (2) Internal
consistency: `_driveTwist`'s sim body is correct, so the same physical
command issued through the two continuous blocks turns 10× differently
in the simulator. Hardware reference: `wheelsV` → kernel yields
Δv/effectiveTrack = Δv/124.8 mm — same order as /115, nowhere near
/1150. One nit: spec §5's prose ("half-difference over an assumed track
width") is itself loose — literally read it is off by 2 — but its
explicit "`/115`" parenthetical pins the intended divisor, and the
code's extra `/10` diverges from both readings. The remedy (delete the
`/10`) is right.

### BLK-07 — divergence and spec-gap both real

Hardware refusal is enforced at *two* layers (`drive()`'s
`kRefusedEstopped` gate, diffdrive.cpp:311, and step()'s latch-forced
neutral, :484), so the silent-refusal contract is robust on hardware and
wholly absent in the sim (`_estopAll` delegates to `_stopAll`;
`_estopClear` is empty). Spec §5's divergence list covers
setWheelSpeeds/driveTwist/startMove/updateMove/progress/endMove/stopAll/
pose/setGeometry/setKernelValue/_tickDrive — e-stop is not mentioned
anywhere in §5. Major is consistent with the rubric (dimension-1
"simulator/hardware behavior divergence, silent no-ops in fallback
bodies" plus the UC-011 student-trap inversion).

### Spot-checked Minors

**BLK-09** — trivially decisive; see table. The "misidentifies by ten
releases" framing is accurate (1.0.0 vs 1.0.10).

**BLK-12** — half stands, half falls. The `isMoving()` half is fully
confirmed and is indeed the substrate of BLK-01(b). The `moveProgress()`
half is refuted: it binds to `progress()`, not `updateMove()` — its
"checks state only" doc comment is *true* on hardware (the sim body's
`simIntegrate()` side effect notwithstanding). The finding should be
narrowed to `isMoving()` before it is converted to an issue; its remedy
("bind to `moving()` or make the doc honest") still applies to that
half. Severity Minor unchanged.

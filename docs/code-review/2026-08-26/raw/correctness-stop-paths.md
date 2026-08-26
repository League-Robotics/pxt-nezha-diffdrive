# Annex — Correctness: stop, e-stop, abort, and refusal paths (2026-08-26)

Consolidated as **C-04 … C-09** in [`../review.md`](../review.md). This is the
annex for the stakeholder's explicit question: *"are there ways the code can
fail — it will fail to stop, or any stop might not be respected?"*

Findings C-04 and C-06 were executed against the real firmware C++; the probe is
[`stop_probe.cpp`](stop_probe.cpp).

---

## The stop taxonomy as built

Five distinct "make it stop" mechanisms exist, at three layers. They are all
individually defensible; the trouble is that nothing states which of them a
given entry point actually delivers.

| # | Mechanism | Reaches motors | Latches | Survives next `step()` |
|---|---|---|---|---|
| 1 | `kernel.neutral()` | on the **next** `step()` | no | yes — commanded mode is neutral |
| 2 | `NezhaMotorPort::emergencyStop()` (port-level zero) | **immediately** | no | **no** — next `step()` re-commands |
| 3 | `kernel.estop()` | on the next `step()` | **yes** | yes |
| 4 | `kernel.emergencyStopMotors()` | immediately | **yes** (side effect) | yes |
| 5 | lease expiry | on the next `step()` | no | yes |

Mechanism 2 alone is a **momentary** stop, not a stop. `shims.cpp`'s
`deliverStopNow()` is exactly mechanism 2, and its own comment is explicit that
this is deliberate — it must not latch, so that a resumed tick loop keeps
working. Correct reasoning. The problem is that one caller uses mechanism 2
*without* pairing it with mechanism 1.

```cpp
// shims.cpp:250 -- mechanism 2, correctly non-latching
static void deliverStopNow(Rig& r) {
  r.left.emergencyStop();
  r.right.emergencyStop();
}
```

Callers:

| Entry point | Mechanisms | Complete stop? |
|---|---|---|
| `stopAll()` — block `stop`, wire `STOP` | 1 + 2 (+ `engine.endMove()`) | **yes** |
| `estopAll()` — block `emergency stop`, wire `ESTOP` | 3 + 4 (+ `engine.endMove()`) | **yes** |
| starvation watchdog | 1 + 2 (+ `engine.endMove()`) | **yes** |
| `updateMove()` on move end | 2 (+ `serviceMove()`'s own `kernel_.neutral()`) | yes — via `serviceMove` |
| **`endMove()` — block `stop move`** | **2 only** when no move is active | **no — C-04** |

---

## C-04 — MAJOR: `stop move` does not stop a continuous drive

```cpp
// shims.cpp:704
void endMove() {
  if (rig == nullptr) return;
  rig->engine.endMove();
  deliverStopNow(*rig);
}
```

```cpp
// motion_engine.cpp:88
void MotionEngine::endMove() {
  if (move_.active) kernel_.neutral();   // <-- ONLY if a move was active
  cancelMove();
}
```

After `setWheelSpeeds()` / `driveTwist()`, `move_.active` is false — `wheelsV()`
calls `cancelMove()` on the way in (motion-api.md §6, "wheels_* clears the
planner"). So `engine.endMove()` stages nothing, `deliverStopNow()` writes
port-level zeros, and the kernel's commanded velocity mode — holding
`kLeaseMax`, **one hour** — is untouched. The next `kernel.step()` re-commands
the duty.

### Measured

```
A. `stop move` after setWheelSpeeds(200,200):
  driving, before stop move        dutyL=  23.5%  dutyR=  23.5%
  one tick later                   dutyL=  23.5%  dutyR=  23.5%
  ten ticks later                  dutyL=  24.3%  dutyR=  24.3%   <-- and climbing

   the same sequence via `stop` (stopAll(), which also calls kernel.neutral()):
  driving, before stop             dutyL=  23.5%  dutyR=  23.5%
  one tick later                   dutyL=   0.0%  dutyR=   0.0%
  ten ticks later                  dutyL=   0.0%  dutyR=   0.0%
```

The duty *rises* after the stop — the PID is making up the ground the port-level
zero cost it. So the visible effect on the robot is a stumble, not a stop.

### Simulator parity

```ts
// blocks/sim.ts:208
export function _endMove(): void {
    simIntegrate()
    simMoveActive = false
    simVel = 0            // <-- a full stop
    simYawRate = 0
}
```

The simulator **does** stop. A student who develops in the browser sees
`stop move` halt the robot, then flashes it and it doesn't. That is the
UC-011-class parity trap the use cases exist to prevent, running in the opposite
direction from the 2026-08-23 review's R-13 (where the sim was the permissive
one).

### On the doc comment

`blocks/motion.ts:224` says *"End the current move now (no-op if none). … this
just clears the move-engine state."* Read strictly, that is accurate. But
`deliverStopNow()` was added to this exact function by sprint 006 ticket 002
specifically so that a stop would land within the same tick — which reads as
intent that this *is* a stop, and a student reading a block captioned
"stop move" is not reading the doc comment strictly.

### Remedy

Decide the contract and make all three sites agree:

- **If it means "end the move"**: drop `deliverStopNow()` from `endMove()`
  (leaving it in `updateMove()` and `stopAll()`, where a move genuinely was
  active), and change `sim.ts`'s `_endMove()` to leave `simVel`/`simYawRate`
  alone.
- **If it means "stop"**: add `r.kernel.neutral()` — one line — and note in the
  block's doc that it also ends continuous driving.

The second is closer to what the caption promises and to what the simulator
already does.

---

## C-06 — MAJOR: `serviceMove()` never checks `estopped`

```cpp
// motion_engine.cpp:352
if ((distDone && yawDone) || expired || out.stallHalted || wrongWay) {
  if (wrongWay) ++wrongWayCount_;
  kernel_.neutral();
  move_.active = false;
  move_.hasPending = false;
  return false;
}
```

`Output.estopped` is not in that list, and `Output.stallHalted` is. The two are
the same *kind* of thing — a latched refusal the kernel publishes — and only one
ends the move.

The kernel does refuse to drive under the latch (`diffdrive.cpp:485`,
`if (estopLatch_) effective = kModeNeutral;`), so **the wheels are safe**. But
the move engine does not know, so:

- `isMoveActive()` stays true → `moving()` / `isMoving()` keep answering yes
- `progress()` freezes short of 1000
- `commandLooksActive()` returns true → **every `while (driveTick())` loop keeps
  spinning** until the deadline
- `resolvePendingReason()` returns `kNone` for a goal-directed verb → the wire's
  motion-completion channel reports nothing

### Measured

Latching the kernel e-stop mid-move on a 30 s-timeout move — which is exactly
what `kernel.emergencyStopMotors()` does as a documented side effect:

```
B. e-stop latched WITHOUT going through shims' estopAll():
  mid-move                       dutyL= 10.7%  dutyR= 10.7%  moveActive=1
  10 ticks after estop latch     dutyL=  0.0%  dutyR=  0.0%  moveActive=1
  move stayed 'active' for 1230 further ticks (29.5 s) after the e-stop
```

### Why it is masked today

The one production caller orders it correctly:

```cpp
// shims.cpp:722
void estopAll() {
  Rig& r = ensure();
  r.engine.endMove();          // <-- FIRST: clears move_.active
  r.kernel.estop();
  r.kernel.emergencyStopMotors();
}
```

So the safety of this path rests entirely on an undocumented calling order, in a
different file, from the code that depends on it — `guidelines.md`'s own
"behavior that only works because of an undocumented calling order" category.
Two ways it reopens:

1. Any future caller reaching for `kernel.emergencyStopMotors()` directly. Its
   e-stop latch is a *side effect* (`diffdrive.cpp:379-381`,
   `estopLatch_ = 1;`) that `shims.cpp:247` documents in a comment but the
   kernel header does not.
2. Any reordering of `estopAll()`'s three lines, which look independent.

### Remedy

```cpp
if ((distDone && yawDone) || expired || out.stallHalted || out.estopped || wrongWay) {
```

One term. It makes `estopAll()`'s ordering an optimization rather than a
load-bearing secret, and it makes an e-stopped `while (driveTick())` loop exit
on the next tick instead of the next deadline.

---

## C-07 — MAJOR: `kernel_.drive()`'s refusal status is discarded at every call site

`DifferentialDrive::drive()` returns a `Status`:

| Status | Cause |
|---|---|
| `kRefusedNotBegun` | `begin()` never ran |
| `kRefusedEstopped` | e-stop latched |
| `kRefusedUnconfigured` | `maxDuty <= 0` or `fullDutyVelocity` uncalibrated |
| `kRefusedNonFinite` | NaN/Inf reached the kernel |

`MotionEngine` ignores it at all four call sites:

| Site | Call |
|---|---|
| `motion_engine.cpp:49` | `wheelsV()` |
| `motion_engine.cpp:83` | `wheelsX()` |
| `motion_engine.cpp:137` | `startSegment()` — the one that arms `move_.active` |
| `motion_engine.cpp:340` | `serviceMove()`'s per-tick reissue |

A refused move still sets `move_.active = true`, still reports `progress()`,
still spins to its deadline, and still resolves as `kStop` or `kTimeout` on the
wire — indistinguishable from a move that ran and stopped normally.

The kernel *does* latch the first refusal in `lastError()`, reachable as
`diagValue(20)` / `probe(20)` / DIAG ordinal 20. Nothing between the kernel and
any caller reads it, and no block or wire field surfaces it as a reason.

**Remedy.** At minimum, `startSegment()` should not arm on a refusal:

```cpp
const DiffDrive::DifferentialDrive::Status st =
    kernel_.drive(move_.velCmd * 0.25f, move_.twistCmd * 0.25f, remainingMs);
move_.active = (st == DiffDrive::DifferentialDrive::Status::kOk);
```

That converts a silent 30-second nothing into an immediate honest "no", and it
gives `resolvePendingReason()` something truthful to report.

This is also the smaller half of a design note the 2026-08-23 review already
made and sprint 007 deliberately deferred (`src/DESIGN.md` §10): e-stop, the
stall latch, the watchdog's soft stop, lease expiry, and now a refused drive are
**five** distinct "the robot is off" states a caller distinguishes only by
reading five separate readbacks. `lastError()` is the closest thing to a unified
answer and it is unreachable from any block.

---

## C-08 — MAJOR: a running `RUN:` tour cannot be aborted, and reports success either way

Every `RUN:` handler in `test/test.ts` runs its full sequence inside one
MessageBus event handler, guarded only by a re-entry flag:

```ts
function tourWheels() {
    if (touring) return
    if (!worldReady()) return
    touring = true
    openLoopProfile()
    diffDrive.resetPose(); diffDrive.seedPose(START_X, START_Y, START_H)
    diffDrive.emitLine("DBG:tour=wheels")
    logFix("c0")
    for (let i = 0; i < 4; i++) {
        basic.showNumber(i + 1)
        tickedMove(LEG_CM[i], 0)
        tickedMove(0, 90)
        logFix("c" + (i + 1))
    }
    diffDrive.emitLine("GAP:" + maxGapMs)
    diffDrive.emitLine("TOUR:end")
    basic.showString("W")
    touring = false
}
```

There is no `RUN:abort`, no per-leg abort check, and no consultation of e-stop
state anywhere in the file.

### What a wire `ESTOP` mid-tour actually does

1. `estopAll()` ends the current leg's move and latches the kernel. The wheels
   stop. Correct.
2. `tickedMove()`'s `while (diffDrive.driveTick())` exits — `commandLooksActive`
   is false once the move ended and applied duty is zero.
3. **The handler proceeds to the next leg.** `startMove()` arms a new move;
   `moveX` → `startSegment` → `kernel_.drive()` is refused (C-07, silently);
   `move_.active` is set true anyway; `serviceMove()` never checks `estopped`
   (C-06), so the loop spins for that leg's full deadline.
4. Repeat for every remaining leg.
5. `logFix()` emits an `OCAL:` line at each corner from the stale OTOS cache.
6. `GAP:`, `TOUR:end`, `basic.showString("W")`.

**The operator gets a complete, normal-looking tour transcript for a tour that
never moved.** Nothing in the emitted stream says "estopped".

On a rig whose standing rule is that most "robot faults" here turn out to be
instrument faults — and whose own project memory records a whole error
attribution built on an unverified assumption about a run's conditions — a
transcript that cannot distinguish "drove badly" from "was e-stopped and did
nothing" is a bad artifact to be producing.

### Remedy

Three pieces, all small:

1. A module-level `aborted` flag, set by a new `RUN:abort` handler.
2. `tickedMove()` returns early if `aborted`; each tour's `for` loop breaks on
   it. (`tickedMove` is already the single choke point every leg goes through.)
3. A terminal line that says how the tour ended —
   `TOUR:end:ok` / `TOUR:end:abort` / `TOUR:end:estop` — instead of always
   `TOUR:end`. The e-stop case is readable from `diffDrive.probe(1)`
   (`Output.estopped`) with no new firmware surface.

Fixing C-06 alone also improves this a lot: each post-estop leg would end on the
next tick rather than at its deadline, so an e-stopped tour would race through
its remaining legs instead of taking minutes.

---

## C-09 — MINOR→MAJOR: a "no-op" motion command does not stop prior motion

Three sites treat a degenerate command as "nothing to do" and return without
touching the kernel:

```cpp
// motion_engine.cpp:59 -- wheelsX()
cancelMove();
...
if (dominant <= 0.0f || cruise <= 0.0f) return;   // nothing to command

// motion_engine.cpp:116 -- startSegment()
if (dominant <= 0.0f || cruise <= 0.0f) {
  move_.active = false;                            // same contract as wheelsX
  return;
}
```

`cancelMove()` clears the move-engine flag **without touching the kernel**
(`motion_engine.cpp:83`, and its own comment says so). `moveX()` does not even
call it — it overwrites `move_` directly. In all three cases the kernel's
previous command and its lease survive.

So `WHEELS_X 0 0 100 1000` issued while a `WHEELS_V` hold is in force is acked
`ok`, clears the planner, and **the robot keeps driving** at the old velocity
until the old lease expires.

**Why this is filed low.** The wire closes most routes in:
`onWheelsX()`/`onMoveX()`/`onGoToR()`/`onGoToW()` all refuse `cruise < 0` and
resolve `cruise == 0` through `engineDefaultCruiseMmS()`, refusing if that is
non-positive too. `clampMotionTimeout()` rejects `timeout == 0`. What remains
reachable is a zero-*distance* command (`WHEELS_X 0 0 …`, `MOVE_X 0 0 …`), which
is legal input.

**Why it is worth recording anyway.** The primitives' documented contract —
`motion_engine.h`: *"A zero-magnitude command (both wheels commanding no
distance) or a non-positive cruise is a no-op — nothing is driven"* — is not what
they do when something was already driving. "Nothing is driven" reads as "the
robot does not move"; it means "no new command is issued". Same class as C-04.

**Remedy.** Have the degenerate branch `kernel_.neutral()` before returning, or
change the comment to say plainly that a no-op does not stop prior motion.

---

## C-15 — MINOR: `logFix()` emits a normal-looking fix line after a failed read

```ts
// test/test.ts:105
function logFix(tag: string) {
    if (!diffDrive.readWorld()) {
        diffDrive.emitLine("OERR:read-failed:" + tag)
    }
    diffDrive.emitLine("OCAL:" + tag
        + ":" + Math.round(diffDrive.worldX() * 100)
        + ":" + Math.round(diffDrive.worldY() * 100)
        + ":" + Math.round(diffDrive.worldHeading() * 100))
}
```

The choice to emit anyway is right, and its comment says why — *"A failed read is
logged explicitly: silence would be indistinguishable from a real fix at the
origin."* But the `OCAL:` line itself carries no marker, so any consumer that
greps `OCAL:` without correlating the preceding `OERR:` reads a stale cached
pose as a fresh fix.

Given `tour-corner-fixes-are-stale-cache.md` is an open issue about exactly this
class of mistake — *"The square tour records the SEEDED OTOS pose at every
corner, so its closure number is fiction"* — the staleness belongs **in** the
line, not adjacent to it. `OCAL:<tag>:<x>:<y>:<h>:<ok>` with a trailing 0/1
costs one field and makes every downstream parser able to reject it.

---

## Cross-cutting: the fiber/bus discipline the obligation bug breaks

Filed as **C-05** in the review (the obligation is never cleared on completion);
recorded here because its worst consequence is a *stop/safety* one.

`blocks/world.ts:9` states the invariant:

> "Every read here is a live I2C burst, so these must be called from the same
> fiber that calls `driveTick()` — never concurrently with one (an OTOS
> transaction landing inside the Nezha encoder's select→read window destroys
> that encoder sample)."

`src/DESIGN.md` §2 states the kernel side: *"Anything that lands other I2C
traffic inside that settle window destroys the sample."*

`protocol.cpp:355` ticks the kernel from the **protocol fiber** whenever
`hasLiveMotionObligation()` is true. Because nothing clears
`motionObligationActive_` on natural completion, that stays true for the whole
declared `timeout` after any wire motion verb — up to the 2³¹−1 ms decode clamp.
A `RUN:` tour handler running on the event fiber and calling `readWorld()` while
the protocol fiber sits in `step()`'s 4 ms settle window is exactly the
collision both comments forbid.

`stepBusy` (`shims.cpp:521`) serializes `kernel.step()` correctly and is
adequately reasoned about for the cooperative scheduler. It does **not** cover
this: an OTOS read is not a `step()`.

This is a concrete candidate mechanism for the open issue
`i2c-fault-count-climbs-on-idle-bus.md` — a climbing `i2cf` on a bus nobody
thinks is busy. It needs bench confirmation, not assertion: capture `i2cf` and
`cyc` across a session with and without a preceding wide-timeout `MOVE_X`, and
see whether the climb tracks the obligation window.

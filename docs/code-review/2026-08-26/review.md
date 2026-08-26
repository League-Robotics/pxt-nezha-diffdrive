# Code Review — 2026-08-26

**Scope**: `src/` (C++ firmware + TypeScript blocks), `test/`, `tools/`,
`tests/`, build and doc wiring. Code state: as-built through sprint 013,
closed and merged, plus the post-013 `travelCalib` change.
**Method**: per [guidelines.md](../guidelines.md). Phase 0 first (design docs
against code), then correctness, future landmines, cohesion/duplication,
comment hygiene, and the error/stop paths the stakeholder called out.
**Verification**: every Critical and Major finding below was either executed
against the real firmware C++ (three throwaway host programs linking
`src/core/diffdrive.cpp` + `src/motion/motion_engine.cpp` against
`tests/host/fake_ports.h`) or re-derived twice from source. Measured numbers
are quoted as measured. The review changed no source — `src/` and `tests/`
are protected paths.

**Baseline**: `uv run pytest` → **597 passed**. The suite is green and stays
green through every finding below; none of them is caught by a test today.

**Annexes** (full detail lives there; this report consolidates):
[design-docs](raw/design-docs.md) ·
[correctness-geometry](raw/correctness-geometry.md) ·
[correctness-stop-paths](raw/correctness-stop-paths.md) ·
[correctness-wire-blocks](raw/correctness-wire-blocks.md) ·
[comment-audit](raw/comment-audit.md) ·
[cohesion-and-tooling](raw/cohesion-and-tooling.md), plus the two runnable
verification probes [goto_probe.cpp](raw/goto_probe.cpp) and
[stop_probe.cpp](raw/stop_probe.cpp).

**Totals**: **1 Blocker (docs) · 2 Critical · 9 Major · 14 Minor**, plus a
comment-hygiene assessment with numbers.

---

## Executive summary

Thirteen sprints in, the architecture is holding: the layering in
`src/DESIGN.md` §1 still matches the real include graph after sprint 013's
directory move, the wire grammar's parsing and reliability layers are
genuinely careful work, sprint 005's `tools/` consolidation stuck (all seven
tour tools now share one `Cam`, one `wrap()`, one corner scorer), and the
kernel/ports layer carries the best comments in the repo. Four things need
attention.

1. **The `go to` block is broken, and it is the same bug the last review
   reported.** R-02/R-03 (2026-08-23) were fixed in `MotionEngine::goToR` —
   the *wire* path — and nowhere else. The arc formula they were fixed in is
   hand-copied into three more places, all still pre-fix. Measured on the
   real C++: the student block `goTo(10, 10)` **misses by 112.5 mm on a
   141.4 mm hop**; `goTo(-10, 1)` — a point 10 cm behind the robot — **drives
   a 3.07 m arc and finishes 3.17 m from the target**. `GO_TO_R` to the same
   two targets misses by 2.9 mm and 0.5 mm.

2. **Two of the three stop paths do not stop.** `stop move` after a
   continuous-drive command leaves the wheels turning — measured, the duty is
   back at 23.5% on the next tick and climbing — while the *simulator's*
   `stopMove()` stops dead, so the browser and the robot disagree about the
   student's stop button. And `MotionEngine::serviceMove()` checks
   `stallHalted` but never `estopped`: an e-stop latched by anything other
   than `estopAll()` leaves the move "active" — measured, **29.5 s** of
   `isMoving() == true` and a `while (driveTick())` loop spinning — while the
   wheels are correctly dead. There is no way at all to abort a running
   `RUN:tour`, so an e-stopped tour emits a complete, normal-looking
   transcript.

3. **`clasi design validate` fails, and three docs assert things the code
   contradicts.** Sprint 013 created five subsystem directories under `src/`
   and gave none of them a `DESIGN.md` — the doc set the process requires is
   structurally invalid right now. `src/DESIGN.md` is 44% sprint-history
   appendix (902 of 2045 lines), its "Open questions" section states three
   limitations that were fixed in sprints 005 and 010, `overview.md` says
   "code reflects work through sprint 003", and the geometry constant three
   documents publish (`travelCalib` 0.8102) was replaced by 0.7878 on
   2026-08-25 — two bench tools still hardcode the old one and now mis-scale
   by 2.8%.

4. **The comment volume is a process output, not a drift.** Project-owned
   `src/` runs **1.22 comment lines per code line**. The vendored kernel in
   the same tree runs **0.05**, and `tools/` runs **0.10**. Sprint 009 — a
   whole sprint of comment cleanup — removed a net 294 lines across the
   twelve files it touched, and four of those files have since grown back
   more than the cleanup removed. This does not get fixed by another cleanup
   sprint; it gets fixed by changing what sprints are allowed to write.

None of the four is a regression from sloppy work. Each is a seam the process
does not currently look at: a fix applied on one of four call paths, a stop
verb whose contract was never stated, a doc set validated by hand, and a
comment standard that is enforced retroactively instead of at write time.

---

## Phase 0 — Design documents

### D-01 — BLOCKER: `clasi design validate` fails; five subsystems have no design doc

```
Missing design doc: subsystem directory src/blocks   has no DESIGN.md
Missing design doc: subsystem directory src/comms    has no DESIGN.md
Missing design doc: subsystem directory src/core     has no DESIGN.md
Missing design doc: subsystem directory src/motion   has no DESIGN.md
Missing design doc: subsystem directory src/platform has no DESIGN.md
```

Sprint 013 grouped `src/` into five directories by dependency layer. Under
the CLASI doc model every subsystem directory needs a co-located `DESIGN.md`,
and `guidelines.md` §Phase 0 states flatly: *"The doc set must pass
`clasi design validate`."* It does not. `src/DESIGN.md` acknowledges the
tension — "the directory split is coarse … so this document still carries the
logical subsystem breakdown as sections" — but that is an argument for a
different doc model, not a substitute for the one the project runs. Sprint
013's own final-sweep ticket (006) did not run the validator.

*Remedy*: either write five thin per-directory `DESIGN.md` files that point
into `src/DESIGN.md`'s existing sections, or change `.clasi/config.yaml`'s
`sources:` to declare the five directories explicitly. The first is cheaper
and matches how `tests/` already does it.

### D-02 — `src/DESIGN.md` is 44% sprint-history appendix

| Section | Lines |
|---|---|
| §1–§11 — the actual design (layers, kernel, engine, wire, ports, blocks, open questions, build gate) | 1143 |
| §12 Sprint 006 · §13 Sprint 007 · §14 Sprint 008 · §15 Sprint 012 · §16 Sprint 013 — "architecture diagram and change summary" | **902** |

Nine hundred lines of per-sprint change narrative sit inside the document a
reader consults to learn what the code *is*. This is the design-doc analogue
of the ticket-archaeology comment anti-pattern the guidelines already ban in
source (§Comment hygiene, anti-pattern 1), and it has the same cost: §15
(sprint 012, 315 lines) describes a `main.ts` split whose product is now five
files in a directory §15 does not know exists, so the reader has to reconcile
it against §9 and §16 to find out what is true.

*Remedy*: the per-sprint sections belong in each sprint's own
`clasi/sprints/NNN-*/design/` overlay, which already exists and already holds
them. Keep §1–§11, delete §12–§16, and let the sprint-close process stop
appending to this file.

### D-03 — Every status header is stale, by between two and ten sprints

| Doc | Says | Actually |
|---|---|---|
| `docs/design/design.md` | "as-built through sprint 008 … Sprint 005 roadmapped, not yet detail-planned" | 005–013 all closed and merged |
| `src/DESIGN.md` | "as-built through sprint 008 … sprint 012 **executed and closing**" | 012 and 013 both merged |
| `docs/design/overview.md` §Status | "Code reflects work through sprint 003 … sprints 004/005 (telemetry frames, radio command plane) are **planned, not built**" | both shipped; ten sprints stale |

`overview.md` is the stakeholder-facing document. It currently tells a reader
that the radio command plane does not exist.

### D-04 — `src/DESIGN.md` §10 states three limitations the code fixed

All three are asserted as present-tense fact:

1. *"`tools/`'s bench scripts still parse the old cleartext `TLM:` prefix …
   nothing in `tools/` consumes them yet — that retrofit is sprint 005
   (roadmapped, not yet detail-planned)."* — `tools/tlm.py` is a 430-line
   `thdr`/`t` decoder with its own test suite; sprint 005 is in `done/`.
2. *"`WireAdapter::lastDone()`/`lastDoneReason()` permanently inert — hosts
   cannot observe motion completion."* — sprint 005 ticket 004 built the whole
   resolution machine (`armPendingMotion`, `resolvePendingReason`,
   `forceResolvePending`); §5 of the same document describes it.
3. *"radio's own TX cap (`kMaxPayloadBytes` = 200) …"* and *"An inbound line
   longer than one fragment is **clamped to a parseable prefix**"* — sprint
   010 raised the cap to 240 (drift-tested) and changed over-length RX to
   reject the whole frame, with a comment at `radio_transport.cpp:63`
   explaining exactly why truncate-and-accept was the hazard. The
   single-fragment limit itself is still real; the two specifics are not.

A limitations list that is wrong in the reassuring direction is worse than no
list — it is where a planner goes to decide what still needs work.

### D-05 — `travelCalib` was changed in code; five places still publish the old value

`motion_engine.h:travelCalib_` went 0.8102 → **0.7878** on 2026-08-25 (twelve
camera-truthed legs; the field comment is exemplary). Still saying 0.8102:

| Where | Consequence |
|---|---|
| `src/DESIGN.md:170` | doc drift |
| `docs/design/specification.md:694` (the authoritative constants table) | doc drift |
| `docs/design/usecases.md:410` | doc drift |
| `tools/tour_watch.py:175` — `k = 0.8102/100` | **live chart scaling wrong by 2.8%** |
| `tools/tour_chart.py:61` — `--travel-calib` default | **live chart scaling wrong by 2.8%** |

The two tools convert DIAG/telemetry wheel velocities to cm/s with a constant
the firmware no longer uses. This is exactly the mirrored-constant class the
2026-08-23 review named as "the design's weakest habit", now realized on a
constant that is *specifically* about measurement accuracy, in the two tools
used to measure accuracy.

*Remedy*: the tools should read `travelCalib` off the wire (`GET
travel_calib` does not exist — but `wheelSpeed()` already returns mm/s and
`vl`/`vr` already carry it, so `tour_watch.py`'s conversion may simply be
unnecessary now). At minimum, one source with a drift test, like `kVersion`.

### D-06 — `specification.md` §4.3 documents a behavior the code does not deliver

The spec faithfully describes `startGoTo`'s arc math, then says `goTo`
"drives a curved (constant-curvature) path to a point". C-01 below shows that
above 50° of arc angle it does not. The spec is the authoritative block-API
reference; both sides of this need to move.

### D-07 — Stale paths survived sprint 013's "repo-wide stale-path verification"

`main.ts` was retired in sprint 012 and `src/` was reorganized in sprint 013,
whose ticket 006 was scoped as a repo-wide stale-path sweep. Remaining:

- **16 `main.ts` references in live source** — `shims.cpp` ×5,
  `protocol.h` ×2, `protocol.cpp` ×2, `wire_adapter.cpp` ×2,
  `motion_engine.h` ×2, `motion_engine.cpp` ×1, `sim.ts` ×1, plus
  `tools/tour_square.py`. `protocol.cpp:374` tells a reader that
  `startProtocol()` is "called once from a top-level statement in main.ts's
  `diffDrive` namespace" — the call is in `blocks/motion.ts:66`.
- **6 pre-013 paths in live headers** — `motion_engine.h:135,148` and
  `encoder_pose_source.h:10` cite `src/otos_port.h`; `wire_handler.h:144,168,
  276` cite `src/wire_adapter.{h,cpp}`.
- **23 `main.ts` references in `src/DESIGN.md`**, one in `tools/DESIGN.md`
  (`src/heading_wrap.h`).

### D-08 — The geofence described in the project rules does not exist

`.claude/rules/playfield-testing.md` states the field limits (±67.15 /
±44.65 cm, 12 cm margin) and says *"The geofence is what catches unexpected
drift on top of that."* A repo-wide search for `geofence`, `67.15`, `44.65`,
`134.3`, `89.3` finds those strings **only in that rule file**. No tool, no
block, no test program knows the field limits or checks a projected path
against them. `tools/field.py` carries the 100×60 tour rectangle but no
boundary.

This is a safety control the operating procedure believes it has. Either
build it (`field.py` is the obvious home — it already owns playfield
geometry, and every tour tool imports it) or correct the rule to say the
pre-flight path check is the *only* guard.

---

## Correctness

### C-01 — CRITICAL: the student `go to` block misses its target; measured 112 mm on a 141 mm hop

**Where**: `src/blocks/motion.ts:183` `startGoTo()` → `startMove()` →
`shims.cpp:380` → `MotionEngine::moveX()`.

`startGoTo` encodes the target as a constant-curvature arc — turn angle
`theta = 2·atan2(y, x)`, arc length `s = R·theta` — and hands `(s, theta)` to
`startMove`. That pair is only self-consistent when it is *executed as one
blended arc*. `moveX` splits any `|rotation| ≥ 50°` into pivot-then-straight
(`motion_engine.cpp:161`), which executes `theta` as a pivot and then drives
the **arc length** as a **straight line** — a different endpoint. `startGoTo`
also never normalizes `theta` to the short arc, so a target behind the robot
becomes a near-360° turn around a huge circle.

Sprint 006 fixed exactly this for `MotionEngine::goToR` (KERN-02/KERN-03) by
giving it its own split — pivot to the line-of-sight bearing, then drive the
straight-line chord. The fix was not applied to the TypeScript path, and
`motion_engine.h:70` records the two as deliberately separate ("two paths
sharing one primitive, not one implementation") without noting that one of
them is wrong.

**Measured** (real `MotionEngine` + real kernel + ideal wheels; the
`(s, theta)` pair is computed by transcribing `startGoTo` exactly):

```
blocks/motion.ts startGoTo(10,10) -> startMove(s=15.708 cm, theta=90.000 deg)
  block `go to`  : ends at (3.0, 156.9) mm, heading 89.1 deg  -> MISS 112.5 mm on a 141.4 mm hop
  wire GO_TO_R   : ends at (101.5, 97.5) mm, heading 43.8 deg -> miss 2.9 mm

blocks/motion.ts startGoTo(-10,1) -> startMove(s=307.2 cm, theta=348.6 deg)  [target is 10.0 cm away]
  block `go to`  : ends at (3009.8, -617.1) mm -> MISS 3172.4 mm; drove 3.07 m of arc
  wire GO_TO_R   : ends at (-99.5, 10.1) mm    -> miss 0.5 mm
```

Reproduce with the probe archived at
[`raw/goto_probe.cpp`](raw/goto_probe.cpp).

**Blast radius**: `goTo`, `startGoTo`, `whileGoingTo` — three of the six
blocks in the Move palette. Any student `goTo` whose target is more than 25°
off the bow. Nothing catches it: the host suite tests `MotionEngine`
directly, and no TypeScript in this repo is executed by any test.

*Remedy*: `startGoTo` should not compute an arc at all. Give `shims.cpp` a
`//%` entry point onto `MotionEngine::goToR()` and have `startGoTo` call it —
one implementation, the fixed one, for both callers. Failing that, port
`goToR`'s split and short-arc wrap into `startGoTo`. Either way this needs a
regression test above the 50° threshold; the whole finding exists because the
existing tests deliberately stay below it.

### C-02 — MAJOR: `test.ts`'s `legToward()` has the same defect, in the tours the calibration campaign runs

`test/test.ts:144` pivots when `|bearing| ≥ 50°`, then falls through to the
same arc encoding with `theta = 2·bearing`. For any residual bearing in
**[25°, 50°)** — precisely the "small residual, curve it out" case the
function is designed for — `theta` lands in [50°, 100°) and `moveX` splits
it. At bearing 30° the leg ends **0.53 × distance** from its target: 32 cm
off on a 60 cm leg.

`tourRobot()` is one of the three tours; `RUN:tour:robot` is how the
robot-relative accuracy campaign is run. Two open issues
(`first-camera-scored-tour-fails-closure-gate.md`,
`rotation-error-is-injected-by-the-legs-not-the-pivots.md`) are attributing
tour closure error to the drivetrain. This is a plan-side error of the same
order, in the same tours, and it should be ruled in or out before more bench
time goes into the drivetrain hypothesis.

### C-03 — MAJOR: `goToWorld`'s curvature cap lands exactly on `moveX`'s split threshold

`world.ts:217` caps the arc bearing at `kMaxArc = 25°`, so the rotation it
issues is capped at exactly **50.000°** — and `kTurnFirstAngleRad` is exactly
50°. In float, the comparison fires:

```
rot = 0.872664630   thr(kTurnFirstAngleRad) = 0.872664571   rot >= thr -> TRUE
```

So the leg that the cap exists to make *safe* is the one leg that gets
converted into pivot-50°-then-drive-the-arc-length. The cap only binds when a
prior pivot left ≥25° of residual — the "55 deg of residual" case
`world.ts:207` documents as measured on vevov — so this is the failure mode
compounding, not the common path. It is also a pure landmine: two constants
in two languages in two files, numerically coincident at a threshold, with no
comment linking them and no test. Changing either one silently changes the
other's behavior.

*Remedy*: fold into C-01's fix. If `goToWorld`'s legs route through a
corrected `goToR`, the collision disappears. Otherwise cap at 24°.

### C-04 — MAJOR: `stop move` does not stop a continuous drive, and the simulator says it does

`shims.cpp:704 endMove()` calls `engine.endMove()` + `deliverStopNow()`.
`MotionEngine::endMove()` issues `kernel_.neutral()` **only if a move-engine
move was active** (`motion_engine.cpp:88`). After `setWheelSpeeds()` /
`driveTwist()` no move is active, so nothing is staged; `deliverStopNow()`
writes port-level zeros, and the kernel's commanded velocity mode — with
`kLeaseMax`, one hour — is untouched, so the next `step()` re-commands the
duty.

**Measured**:

```
A. `stop move` after setWheelSpeeds(200,200):
  driving, before stop move        dutyL=  23.5%  dutyR=  23.5%
  one tick later                   dutyL=  23.5%  dutyR=  23.5%
  ten ticks later                  dutyL=  24.3%  dutyR=  24.3%   <-- and climbing

   the same sequence via `stop` (stopAll(), which also calls kernel.neutral()):
  one tick later                   dutyL=   0.0%  dutyR=   0.0%
```

The duty *rises* after the stop because the PID is making up the ground the
port-level zero cost it.

The simulator disagrees: `sim.ts:208 _endMove()` sets `simVel = 0` and
`simYawRate = 0` — a full stop. So a student who develops in the browser sees
`stop move` halt the robot, then flashes it and it does not. That is the
UC-011-class parity trap the use cases exist to prevent, in the opposite
direction from R-13.

The block's doc comment ("this just clears the move-engine state") is
technically defensible, but `deliverStopNow()` was added to this exact
function by sprint 006 ticket 002 specifically so a stop would land
immediately — which reads as intent that it *is* a stop.

*Remedy*: decide the contract. If `stop move` means "end the move", drop
`deliverStopNow()` from it and make the sim match. If it means "stop", add
`kernel.neutral()` — one line — and it becomes `stopAll()` minus the naming.
Either way sim and hardware must agree.

### C-05 — MAJOR: the wire's motion obligation is never cleared on completion, so the protocol fiber co-ticks for the full timeout

`motionObligationActive_` is set by all six motion verbs
(`wire_adapter.cpp:345,376,405,428,449,487`) and cleared in exactly two
places: `onEstop()` and `onStop()`. Natural completion does not clear it —
`resolvePendingIfDue()` clears `pendingActive_` and leaves the obligation
armed.

`protocol.cpp:355` reads it as its tick gate:

```cpp
if (wireAdapter_.hasLiveMotionObligation()) { tickDrive(); }
else { fiber_sleep(kPollIntervalMs); }
```

So after any wire motion verb, the protocol fiber ticks the kernel at 24 ms
for the **whole declared timeout**, however long the move actually took.
`timeout` is a mandatory backstop the API tells hosts to set generously, and
the only ceiling is the shared decode clamp — **2³¹−1 ms, 24.8 days**.

Three consequences, in increasing seriousness:

- Idle I2C traffic that looks like nothing is happening. This is a concrete
  candidate mechanism for the open issue
  `i2c-fault-count-climbs-on-idle-bus.md`, which observes exactly that: a
  climbing fault count on a bus nobody thinks is busy.
- Two fibers ticking. `stepBusy` (`shims.cpp:521`) serializes `kernel.step()`
  correctly, but the bus-discipline invariant is broader than `step()`:
  `world.ts:9` states that OTOS reads "must be called from the same fiber
  that calls driveTick() — never concurrently with one", because an OTOS
  transaction landing inside the encoder select→read window destroys the
  sample. A `RUN:tour` handler doing `readWorld()` on the event fiber while
  the protocol fiber is inside `step()`'s 4 ms settle window is that exact
  collision — and a single earlier `MOVE_X` with a generous timeout is enough
  to keep the protocol fiber ticking for the whole tour.
- A stale obligation survives across unrelated work.

*Remedy*: clear `motionObligationActive_` wherever the pending motion
resolves — `resolvePendingIfDue()` and `forceResolvePending()` are the two
places that already know. That makes the obligation window mean "a motion is
outstanding", which is what `protocol.cpp` reads it as.

### C-06 — MAJOR: `serviceMove()` never checks `estopped`; an e-stopped move stays "active" for its whole timeout

`serviceMove()` ends a move on distance/yaw margin, deadline, `stallHalted`,
or wrong-way (`motion_engine.cpp:352`). `Output.estopped` is not in that
list. The kernel does refuse to drive (`diffdrive.cpp:485` forces neutral
under the latch), so the **wheels are safe** — but the move engine does not
know, so `isMoveActive()` stays true, `isMoving()` keeps answering yes,
`progress()` freezes short of 1000, and every `while (driveTick())` loop
spins until the deadline.

**Measured** (latching the kernel e-stop mid-move on a 30 s-timeout move,
which is what `emergencyStopMotors()` does as a side effect):

```
  mid-move                       dutyL= 10.7%  dutyR= 10.7%  moveActive=1
  10 ticks after estop latch     dutyL=  0.0%  dutyR=  0.0%  moveActive=1
  move stayed 'active' for 1230 further ticks (29.5 s) after the e-stop
```

Today this is masked: the one production caller, `shims.cpp:722 estopAll()`,
calls `engine.endMove()` *before* `kernel.estop()`. That makes the safety of
this path depend entirely on an undocumented calling order in a different
file — the guidelines' own "behavior that only works because of an
undocumented calling order" category. `kernel.emergencyStopMotors()` also
latches the e-stop as a side effect (`diffdrive.cpp:380`), so any future
caller that reaches for it directly reopens this.

*Remedy*: add `out.estopped` to `serviceMove()`'s end conditions, alongside
`out.stallHalted`. One line, and it makes `estopAll()`'s ordering an
optimization rather than a load-bearing secret.

### C-07 — MAJOR: `kernel_.drive()`'s refusal `Status` is discarded at every call site

`DifferentialDrive::drive()` returns a `Status` — `kRefusedEstopped`,
`kRefusedUnconfigured`, `kRefusedNotBegun`, `kRefusedNonFinite`.
`MotionEngine` ignores it at all four call sites (`motion_engine.cpp:49, 83,
137, 340`). A move commanded against an unconfigured or un-begun kernel, or
with a non-finite value that slipped a boundary check, arms `move_.active`,
reports progress, spins to its deadline, and resolves to `kStop` or
`kTimeout` on the wire — indistinguishable from a move that ran.

The kernel does latch the first refusal in `lastError()`, reachable as
`diagValue(20)` / `probe(20)`. Nothing between the kernel and the caller ever
reads it.

*Remedy*: `startSegment()` at minimum should not set `move_.active = true`
when its own `drive()` was refused. That converts a silent 30-second nothing
into an immediate honest "no".

### C-08 — MAJOR: a running `RUN:` tour cannot be aborted, and an e-stopped tour reports success

`test/test.ts`'s handlers (`tourRobot`, `tourWorld`, `tourWheels`,
`straightRun`, `goto`, `face`, `pivot`) each run a full multi-leg sequence
inside one MessageBus handler, guarded only by the `touring` flag against
re-entry. There is no `RUN:stop`, no abort check between legs, and no
consultation of e-stop state anywhere in the file.

A wire `ESTOP` mid-tour stops the current leg's wheels and (via
`estopAll()`'s `endMove()`) ends that leg. The handler then proceeds to the
next leg. The kernel refuses every subsequent command, so nothing moves — but
each leg still spins for its deadline (C-06), each `logFix()` still emits a
plausible `OCAL:` line from the stale OTOS cache, and the tour finishes by
emitting `GAP:`, `TOUR:end`, and `basic.showString("A")`. **The operator gets
a complete, normal-looking tour transcript for a tour that never moved.**
Given the project's own standing rule that most "robot faults" here turn out
to be instrument faults, a transcript that cannot distinguish "drove badly"
from "was e-stopped and did nothing" is a bad thing to have.

*Remedy*: an `abort` flag set by a `RUN:abort` handler and by the wire STOP
path, checked at the top of `tickedMove()` and between legs; and a terminal
line that says how the tour ended rather than always `TOUR:end`.

### C-09 — MINOR→MAJOR: a "no-op" motion command does not stop prior motion

`wheelsX()`, `wheelsV()` and `startSegment()` all treat a zero-magnitude
command or a non-positive cruise as "nothing to command" and return
(`motion_engine.cpp:59, 116`). `wheelsX`/`wheelsV` call `cancelMove()` first,
which clears the move-engine flag *without touching the kernel*; `moveX` does
not even do that. In all three cases the kernel's previous command and lease
survive.

So `WHEELS_X 0 0 100 1000` issued while a `WHEELS_V` hold is in force is
acked `ok`, clears the planner, and **the robot keeps driving** at the old
velocity for the remainder of its lease. The wire's `cruise <= 0` refusals
(`wire_adapter.cpp:363`) close most of the ways to reach this from a host,
which is why this is not filed higher — but the primitive's own documented
contract ("a no-op — nothing is driven") is not what it does when something
was already driving.

### C-10 — MINOR: `execHelp()` silently truncates and can drop its own terminator

`wire_handler.cpp:779` builds the HELP reply with a lambda that stops at
`pos < sizeof(buf) - 1`. Today's 18 verbs produce ~110 bytes against a
240-byte buffer, so it fits. At ~240 bytes it stops mid-name and — because
`"\n"` is appended last — **drops the newline**, producing a line the host's
reassembler never terminates and glues onto the next reply. Unlike
`execRun()` immediately below it, which carries a `+1` on its buffer and a
comment explaining exactly this hazard, `execHelp` has no guard and no test.

### C-11 — MINOR: the OTOS product id is re-typed across the shim boundary

`otos_port.h:102` defines `kExpectedProductId = 0x5F` and `begin()` gates
`initialized_` on it. `world.ts:21` independently re-types the literal:

```ts
export function startWorldTracking(): boolean { return otosBegin() == 0x5F }
```

If the expected id ever changes, `otos_port.h` gets updated, the port
initializes fine, `worldTrackingReady()` returns true, `engineGoToW()`
selects the OTOS — and `startWorldTracking()` returns **false**, so every
program that gates on it refuses to run against a perfectly healthy sensor.
`startWorldTracking()` should return `worldTrackingReady()`; the caller has
no business knowing the id.

### C-12 — MINOR: `RUN:` handlers mutate a global shaping profile and never restore it

`RUN:goto` sets `setTaperWindows(120,80)`, `setTaperFloors(45,35)`,
`setRampMs(180)`, `setDefaultSpeed(40)`, `setDefaultYawRate(120)` and leaves
them set. `RUN:face` sets only the yaw rate. `RUN:pivot` sets taper, floors,
ramp and yaw rate but not speed. `openLoopProfile()` sets a different subset.

So `RUN:face` run after `RUN:goto` executes its heading-closing loop under
the *fast closed-loop* profile (taper 120/80, floors 45/35, ramp 180) instead
of the accuracy profile — the same command, different physical behavior,
determined by which command preceded it. For a bench rig whose open questions
are all about a few degrees of rotation error, that is a reproducibility hole
worth closing: every handler should call one named profile function on entry.

### C-13 — MINOR: `dutl`/`dutr` are percent×100, and nothing says so

`Output.appliedDutyLeft` is already a percentage (`diffdrive.cpp:795`
multiplies the port's `[-1,1]` fraction by 100). `diagValue(12)` multiplies
by 100 *again* (`shims.cpp:797`), so `probe(12)` and the wire's `dutl` column
read **10000 at 100% duty**. `shims.cpp`'s own comment says "duty x100" and
`sim.ts:289` says "applied duty x100" — both read naturally as "percent", and
both are wrong by 100×. `tools/tlm.py`'s unit table — which describes itself
as *"the only place any wire → engineering-unit scale factor is written"* —
documents `x`, `y`, `h`, `ox`, `oy`, `oh`, `vl`, `vr` and omits `dutl`/`dutr`
entirely.

### C-14 — MINOR: the simulator's turn rate is 4% off hardware's

`sim.ts:99` computes `simYawRate = (right - left) / 115`. Hardware's
`setWheels` reaches `wheelsV`, whose yaw rate is `(right − left) /
effectiveTrackWidth()` = `114.2 / 0.952` = **119.96 mm**. The comment says
115 is "this simulator's fixed stand-in for the caliper-measured
trackWidth_ (114.2 mm)" — but hardware does not use `trackWidth`, it uses
`trackWidth / rotationalSlip`. Sprint 007 fixed the 10× error here (R-12) and
picked the wrong one of the two geometry numbers. 4.3% is small; the comment
being wrong about which quantity hardware uses is the part that will mislead
the next reader.

### C-15 — MINOR: `logFix()` emits a normal-looking fix line after a failed read

`test.ts:105`: on `readWorld()` failure it emits `OERR:read-failed:<tag>` and
then **still emits the `OCAL:` line** from the stale cache. The comment
explains the choice ("silence would be indistinguishable from a real fix at
the origin") and it is the right call — but the `OCAL:` line itself carries
no marker, so any consumer that greps `OCAL:` without correlating the
preceding `OERR:` reads a stale pose as a fresh fix. Given
`tour-corner-fixes-are-stale-cache.md` is an open issue about precisely this
class of mistake, the staleness belongs *in* the line.

### C-16 — MINOR: `score_corners()` lets an early corner steal a late corner's sample

`field.py:72` scans `range(used, len(rows))` for each corner's global minimum
and then sets `used = besti`. That correctly stops a *later* corner from
reclaiming an *earlier* one's sample — which is what the docstring claims —
but nothing stops the reverse: the first corner's search covers the entire
remaining run, so if the path passes closer to that dot near the end, `used`
jumps to the tail and every subsequent corner scores from a handful of final
samples. A per-corner time or arc-length window would make the greedy scan
robust.

---

## Cohesion, duplication, and hard-coded constants

### Q-01 — The same arc formula is hand-written in four places, and one of them is right

| Site | Short-arc wrap | Split correct | Status |
|---|---|---|---|
| `motion_engine.cpp:186` `goToR` | yes | yes (bearing + chord) | **correct** (sprint 006) |
| `motion.ts:183` `startGoTo` | no | no | C-01 |
| `world.ts:224` `goToWorld` | n/a (capped) | boundary collision | C-03 |
| `test.ts:161` `legToward` | n/a (pivots ≥50°) | no | C-02 |

This one table is the review's whole thesis. A fix landed on one of four
copies and the copies have no way to know. `goToR` is host-portable, already
built, already tested, and already reachable from `shims.cpp` — every one of
the other three could call it.

### Q-02 — `shims.cpp` is seven subsystems in one header-less file

`src/DESIGN.md` §9 itself enumerates its jobs: composition root, odometry,
move-engine forwarding, tick engine, starvation watchdog, config marshalling
(`setKernelValue`/`getConfigValue`, 18 ordinals each), the OTOS shim surface,
the wire forwards, and the `//%` block surface. 1173 lines, 485 of them code,
reached by two other translation units through hand-maintained forward
declarations because it has no header. It is the single least cohesive file
in the tree and the one every layer depends on.

The header-less convention is deliberate and well-explained (PXT's dependency
scanner). The *breadth* is not defended anywhere. The odometry (`odomUpdate`
+ the `x`/`y`/`heading` fields) is the most separable piece — it is pure
math, it is the thing `EncoderPoseSource` already wraps, and moving it out
would make it host-testable, which it currently is not.

### Q-03 — π and the centidegree conversion are written out 13 times

`3.14159265f` appears in 8 places in `shims.cpp` alone, plus `otos_port.h`,
`motion_engine.cpp` (`kPi`), `heading_wrap.h` (its own longer literal), and
the TS side's `Math.PI`. The `cdeg → rad` conversion `* 0.01f * 3.14159265f /
180.0f` is written out five times verbatim in `shims.cpp`
(272, 300, 385, 1155, 1166) and inverted twice more. `otosGet()` has a local
`kRadToCdeg`; nothing else does. One `constexpr float kCdegToRad` next to the
boundary convention comment would retire all of it.

### Q-04 — `kMaxLineBytes = 240` is declared four times

`serial_transport.h:23`, `radio_transport.h:234`, `radio_transport.h:152`
(`kMaxPayloadBytes`), `wire_handler.h:357`. This one is *guarded* —
`test_wire_constants_drift.py::test_radio_serial_wire_capacity_constants_are_equal_at_240`
pins all four — which is the right mitigation given the layering rule that
forbids `wire_handler.h` from including `wire_adapter.h`. Noted as the
pattern, not as a defect.

### Q-05 — The default cruise speed is two constants in two units

`motion.ts:55` `defaultSpeed = 15` (cm/s) and `shims.cpp:143`
`defaultCruiseMmS_ = 150.0f` (mm/s), the latter commented as "seeded to
150.0f to match the block layer's own `defaultSpeed` (15 cm/s, main.ts)" —
in a file that no longer exists. Nothing enforces the match, and
`default_cruise` is settable over the wire while `defaultSpeed` is settable
from a block, so they diverge the moment either is used.

### Q-06 — Two classes named `Cam` in `tools/`

`camlink.py:52` and `camproc.py:72`. The roles are genuinely different —
`camlink.py` runs *inside* the aprilcam venv as a subprocess, `camproc.py`
spawns it — and all seven tour tools correctly import the latter. But the
shared name means a reader of `tour_run.py`'s `cam = Cam()` has to check the
import to know which contract they are holding.

### Q-07 — `tsconfig.json` cannot run; the TypeScript layer has no standalone check

`tsconfig.json` maintains a hand-edited `files` array (updated by sprints 012
and 013), but `typescript` is not in `package.json` and not in
`node_modules/`. Nothing can execute it. The 1149 lines of student-facing
TypeScript are type-checked only by a full `pxt build`, which the process
runs once per sprint in the build-checkpoint ticket. That is defensible as a
gate — but the file's presence implies a check that does not exist, and C-01
is precisely the kind of defect a `.ts` test harness would have caught. Worth
deciding: either add `typescript` and run `tsc --noEmit` in the suite, or
delete `tsconfig.json`.

### Q-08 — No linter is configured, so 6 real findings hide behind 205 false ones

`ruff check tools tests` reports 211 findings. 91 are `F811` — pytest fixture
shadowing, entirely spurious — plus 39 import-order and 17 shebang notices.
The genuinely actionable set is small: 4 unused imports (`pytest` in
`test_wire_motion_completion.py`, `os`/`pytest` in `test_camproc.py`,
`argparse` in `otos_bench.py`), 2 `B904` bare re-raises in the two tools'
`DeadTelemetryError` handlers, and `truth_check.py:165`'s
`def sampler(prev=math.degrees(c0))` mutable-default idiom.

With no config there is no way to see the six. A `[tool.ruff]` block in
`pyproject.toml` selecting `F, E9, B` and excluding `F811` under `tests/`
would make `ruff check` a meaningful gate. (The host C++ suite compiles
`-Wall -Wextra` and tolerates a wall of `-Wdeprecated-volatile` from the
vendored kernel's `++cfgSeq_` — worth pinning with a targeted `-Wno-` rather
than leaving as noise, since upstream owns that code.)

### Q-09 — One hard-coded absolute path to one person's machine

`camproc.py:58` `_DEFAULT_VENV =
'/Volumes/Cache/User-Eric/.local/pipx/venvs/aprilcam/bin/python'`, overridable
via `APRILTAGS_VENV`. Single-sourced and documented, which is a real
improvement on the five copies the last review found — but it means every
camera tool fails on any other machine until that env var is set, and the
failure surfaces as "camera down" rather than "wrong path".

---

## Comment hygiene

### The numbers

Non-blank lines across the whole tree, comments vs code:

| Group | Code | Comments | Ratio |
|---|---|---|---|
| `src/` project-owned | 3687 | **4508** | **1.22** |
| `src/core/diffdrive.{h,cpp}` (vendored, human-written) | 1103 | 53 | **0.05** |
| `tools/` | 3950 | 408 | **0.10** |

The three groups sit in one repository, are read by the same people, and
differ by a factor of **twenty-four**. The vendored kernel is the most
subtle, most dangerous code in the project — a PID with accel feedforward,
adaptive bias, lambda authority scaling, crawl-pulse dithering and two latch
families — and it is comprehensible at 0.05. Nothing about the wire layer
justifies 24× that.

The worst offenders are all headers, and all project-owned:

| File | Code | Comments | Ratio |
|---|---|---|---|
| `comms/serial_transport.h` | 19 | 107 | 5.63 |
| `comms/radio_transport.h` | 39 | 197 | 5.05 |
| `motion/motion_engine.h` | 82 | 393 | 4.79 |
| `comms/wire_adapter.h` | 64 | 277 | 4.33 |
| `platform/encoder_pose_source.h` | 20 | 82 | 4.10 |
| `core/heading_wrap.h` | 11 | 44 | 4.00 |

`heading_wrap.h` is the clearest specimen: a **six-line** function under
**forty-four lines** of comment, thirty of which explain which sprint,
ticket, issue and code-review ID produced it.

### Sprint 009 ran, and the files under active change grew back

Comment-line counts, immediately before sprint 009's cleanup vs today:

| File | pre-009 | today | Δ |
|---|---|---|---|
| `wire_adapter.h` | 440 | 277 | **−163** |
| `shims.cpp` | 706 | 599 | **−107** |
| `protocol.h` | 216 | 151 | −65 |
| `protocol.cpp` | 245 | 200 | −45 |
| `wire_adapter.cpp` | 423 | 382 | −41 |
| `serial_transport.h` | 133 | 107 | −26 |
| `wire_handler.h` | 471 | 465 | −6 |
| `motion_engine.cpp` | 135 | 135 | 0 |
| `motion_engine.h` | 374 | **393** | **+19** |
| `nezha_port.cpp` | 77 | **118** | **+41** |
| `wire_handler.cpp` | 378 | **427** | **+49** |
| `radio_transport.h` | 147 | **197** | **+50** |
| **total** | **3745** | **3451** | **−294 (−8%)** |

A whole sprint of dedicated cleanup bought 8%, and the four files that
sprints 010–013 actually touched are all *above* their pre-cleanup counts.
`serial_transport.h` was cleaned by sprint 009 ticket 005 and still stands at
5.63:1.

The conclusion is not "clean again". It is that **the process writes
ticket-archaeology comments faster than cleanup sprints remove them**, so the
lever is at write time, not at cleanup time.

### Live instances of the guidelines' own five anti-patterns

The guidelines already name these. All five are present in code written
*after* the guidelines were written.

1. **Ticket archaeology as file header.** `serial_transport.h:25-55` — a
   30-line narration of ticket 006's original 480, its silent truncation to
   224, ticket 005's thrown exception, and ticket 007's remediation, to
   introduce `constexpr uint8_t kRingBytes{255}`. Everything a reader needs
   is: 255 is codal's `uint8_t` ceiling; brace-init makes an overflow a
   compile error. Three lines. Same shape in `encoder_glitch_armor.h`
   ("**What this fixes.**" — a ticket write-up), `heading_wrap.h`,
   `encoder_pose_source.h` (lines 1–70 are one comment block, 63% of the
   file).
2. **Justification-to-reviewer essays.** `wire_handler.cpp:125-149` spends 25
   lines defending why `kMaxMotionTimeoutMs` is a sibling of, and not a reuse
   of, `kWireBoundaryCastCeiling`. The load-bearing fact — 2³¹−1 is the
   signed-difference half-range the wraparound idiom needs — is one sentence.
3. **Stale cross-layer claims.** `radio_transport.h:240` and
   `wire_adapter.cpp:163` both point a reader at `Protocol::formatDiag()`.
   There is no `formatDiag()` in this codebase. Likewise `protocol.cpp:130`
   cites "the old `parseLine()`", `wire_handler.cpp:1138` cites
   "`sendDebug()`-style text", `protocol.h:57` cites
   "`sendTelemetry()`/`sendDeviceBanner()`" — five dangling references to
   functions that do not exist, the exact `readLine()` shape the guidelines
   cite as the canonical example.
4. **Diff restatement.** `shims.cpp:508-518` ("this used to read
   `if (wasActive) odomUpdate(r);`…"), `motion_engine.cpp:349`
   ("extracted verbatim … Behavior is identical to the loop it replaces, not
   merely similar"), `wire_adapter.cpp:270` ("`out.otos` used to hardcode
   false…").
5. **Comments that outlived their code.** The 16 `main.ts` references (D-07)
   and the 6 pre-sprint-013 paths.

### One comment that is actively wrong, in the file students read first

`src/blocks/motion.ts:1-12`, the namespace JSDoc — the text that surfaces in
the extension's own documentation:

> *"The wheel servo runs in its own fiber on the micro:bit (the DiffDrive
> kernel, 24 ms cadence); every command below just talks to it. … the
> function bodies here are the browser-simulator fallbacks."*

Both sentences are false. The kernel's own fiber is *deliberately unwired*
(`shims.cpp:190`), and "the robot only moves while something ticks" is stated
as a **system invariant** in `docs/design/design.md`. The simulator fallbacks
moved to `sim.ts` in sprint 012. This paragraph teaches a student the exact
mental model the tick model exists to replace, and it is the first thing they
read.

Second instance, same class: `motion.ts:201` documents `isMoving()` as
*"Checks state only — it does not itself advance the move."* It calls
`_updateMove()` → `shims.cpp:441 updateMove()`, which calls
`engine.serviceMove()`, reissues `kernel_.drive()`, can end the move, and can
fire `deliverStopNow()`. The 2026-08-23 review already found this comment
false (verify-blocks BLK-12); it is unchanged.

### What "good" already looks like here

The target is in the tree. `motion_engine.h:445-470`'s `rotationalSlip_`
derivation — which names the exact wrong shortcut a future re-measurer would
take and blocks it; `motion_engine.h:420-443`'s `travelCalib_` measurement,
with the camera's own scale check and the scale-vs-offset fit that proves
this is the right knob; `nezha_port.cpp:132-145`'s reversal-dwell comment
with the measured 12/12 latching window; `wire_adapter.cpp:39-67`'s three
numbered hazards. Every one of these is a *measured hardware fact a reader
cannot recover from the code*. That is the whole test, and this repo already
knows how to pass it.

### Recommended standard

Add to `guidelines.md` as a write-time rule, not a cleanup-time one:

> A comment must state something a competent reader cannot recover from the
> code in front of them: a unit, a sign convention, an invariant, a measured
> hardware fact, a wire layout, or a hazard. **Sprint numbers, ticket
> numbers, issue filenames, code-review IDs, and "this used to be X" belong
> in the commit message.** If the comment is longer than the code it
> describes, it is a design-doc section wearing a comment's clothes.

Mechanically enforceable in a host test today: grep `src/` for
`sprint \d`, `ticket \d`, `R-\d\d`, `KERN-\d\d`, `WIRE-\d\d`, `BLK-\d\d`,
`API-\d\d` and fail above a declining budget. Current count is a few hundred;
that is the number to ratchet.

---

## Proposed issues for triage

| # | Issue | Covers | Priority |
|---|---|---|---|
| 1 | `goTo`/`startGoTo`/`whileGoingTo` land the wrong place — route the block path through `goToR` | C-01, D-06 | **Critical** |
| 2 | `legToward`/`goToWorld` share the arc defect; rule it in or out of the open tour-closure issues | C-02, C-03, Q-01 | **Critical** |
| 3 | Stop contract: `stop move` vs continuous drive, and sim/hardware parity | C-04 | High |
| 4 | `serviceMove()` must end on `estopped`; `startSegment()` must honor `drive()`'s refusal | C-06, C-07 | High |
| 5 | Clear the wire motion obligation on completion — and re-check `i2c-fault-count-climbs-on-idle-bus.md` against it | C-05 | High |
| 6 | Abortable `RUN:` tours + an honest terminal line | C-08, C-15 | High |
| 7 | Restore the doc set: five subsystem `DESIGN.md`s, `clasi design validate` green | D-01 | High |
| 8 | `travelCalib` 0.7878 into three docs and two tools; single-source or drift-test it | D-05 | High |
| 9 | Design-doc truthfulness pass: §10's three fixed limitations, three status headers, `overview.md` | D-03, D-04 | Med |
| 10 | Strip §12–§16 from `src/DESIGN.md`; stop sprint-close appending to it | D-02 | Med |
| 11 | Stale-path sweep, done with a test this time: `main.ts`, pre-013 paths, dangling function refs | D-07, hygiene 3/5 | Med |
| 12 | Comment standard + ratchet test; then a cleanup pass on the six worst headers | comment section | Med |
| 13 | Geofence: build it in `field.py`, or correct the rule | D-08 | Med |
| 14 | Wire/shim minors: `execHelp` truncation, `0x5F`, `dutl` units, `wheelsX` no-op-vs-stop | C-09, C-10, C-11, C-13 | Med |
| 15 | Bench reproducibility: one named shaping profile per `RUN:` handler | C-12 | Med |
| 16 | Tooling hygiene: ruff config, `tsconfig` decide-or-delete, sim track width, `score_corners` window | C-14, C-16, Q-07, Q-08 | Low |
| 17 | Constant consolidation: `kCdegToRad`, `defaultSpeed`/`defaultCruiseMmS_` | Q-03, Q-05 | Low |

---

## Appendix — the document set

| File | What it carries |
|---|---|
| `review.md` | this consolidated report |
| [`raw/design-docs.md`](raw/design-docs.md) | Phase 0 in full — D-01 … D-08, with the validator output, the §-by-§ line census, and the doc-set verdict table |
| [`raw/correctness-geometry.md`](raw/correctness-geometry.md) | the arc family — C-01, C-02, C-03, Q-01: the shared mechanism, per-site code, measured endpoints, worked cases, the float boundary proof |
| [`raw/correctness-stop-paths.md`](raw/correctness-stop-paths.md) | C-04 … C-09 and C-15 — the five-mechanism stop taxonomy, the caller table, both measurement transcripts, the fiber/bus argument |
| [`raw/correctness-wire-blocks.md`](raw/correctness-wire-blocks.md) | C-05, C-10 … C-16, **plus what held up** — the closed 2026-08-23 findings and the paths re-verified sound this pass |
| [`raw/comment-audit.md`](raw/comment-audit.md) | the ratio measurements, the per-file table, the sprint-009 recurrence data, the five anti-patterns live, the keep list, and a 12-item work order |
| [`raw/cohesion-and-tooling.md`](raw/cohesion-and-tooling.md) | Q-01 … Q-09 — duplication, hard-coded constants, `shims.cpp`'s breadth, lint and type-check gaps |
| [`raw/goto_probe.cpp`](raw/goto_probe.cpp) | C-01's measurement — links the real firmware C++ against the host harness's fake ports, transcribes `startGoTo`'s arc math exactly, integrates `shims.cpp`'s own `odomUpdate()`, prints the endpoint |
| [`raw/stop_probe.cpp`](raw/stop_probe.cpp) | C-04's and C-06's measurements, same harness |

Build and run either probe with:

```
/usr/bin/c++ -std=c++20 -O1 -w -I src -I tests/host -o /tmp/probe \
    docs/code-review/2026-08-26/raw/goto_probe.cpp \
    src/core/diffdrive.cpp src/motion/motion_engine.cpp && /tmp/probe
```

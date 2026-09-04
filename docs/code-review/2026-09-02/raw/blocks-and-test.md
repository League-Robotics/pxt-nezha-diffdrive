# Blocks + test program review — 2026-09-02

**Scope**: `src/blocks/{motion,world,run,sim,stop,pose}.ts`, `test/test.ts`,
the `//%` shim surface in `src/shims.cpp` they call, `src/DESIGN.md` §9,
`src/blocks/DESIGN.md`, `pxt.json`. Code state: master at `50efc2d`
(sprint 028 merged — RUN dispatch on the protocol fiber).
**Method**: every finding below was read against the current source and
quotes it; nothing was executed on hardware. Severity per
`docs/code-review/guidelines.md`. Dedupe against `clasi/issues/**`,
`clasi/sprints/done/*/issues/**` and `docs/code-review/2026-08-26/review.md`.
**Coverage note**: `tests/host/test_typescript_typecheck.py` type-checks
these files and four source-pin tests read them as text; nothing executes
them. Every finding here is invisible to the suite.

## Summary table

| ID | Severity | file:line | Summary |
|---|---|---|---|
| BT-01 | Major | `test/test.ts:59,84-87,423-439,502-526,652-706,725-736` | `aborted` is reset only by tours; after any `RUN:abort`, every non-tour motion verb (`pivot`, `straight`, `face`, `cal`, `arc`) silently stops after one tick and reports a normal `*:end` |
| BT-02 | Major | `src/blocks/run.ts:72-75`, `test/test.ts:543-549,516,521,614-616,978`; `src/blocks/world.ts:101-104` | RUN handlers now run ON the protocol fiber; any blocking call outside `driveTick()` (750 ms per `showNumber`/`showString`, `basic.pause`, `otosBegin()`'s ≤1.5 s wait) leaves PING/ESTOP/abort unserviced — and both files' comments still say handlers have their own fiber |
| BT-03 | Major | `src/blocks/run.ts:1-5,43-58,198-207`; `src/comms/protocol.h:180-188` | A bypass dispatch (`abort`/`clearestop`) nested inside a running job overwrites the shared `runParts`; the only thing keeping `runArg()` correct is an unstated "read your arguments before your first tick" rule that `run.ts` neither documents nor enforces |
| BT-04 | Major | `test/test.ts:791-813` vs `src/blocks/world.ts:9-12` | The 10 Hz background OTOS sampler is a second fiber doing I2C while the job fiber is inside `kernel.step()`'s yielding settle window — the exact collision the world.ts header forbids |
| BT-05 | Major | `src/blocks/motion.ts:178-186` + `src/blocks/world.ts:9-12,60-62` | `startDrive()` forks a background tick fiber; the natural student follow-up (`read world position` in the main loop) is the same two-fiber I2C collision, and the block docs never say so |
| BT-06 | Major | `src/blocks/sim.ts:129-146` vs `src/motion/motion_engine.cpp:393` | Simulator blends any (distance, yaw) into one arc; hardware splits `|yaw| >= 50°` into pivot-then-straight — `move(20, 90)` ends at different points in the browser and on the robot |
| BT-07 | Major | `test/test.ts:502-526,844-859,864-879,890-907,935-951,961-970` | The five 2026-09-01 tours and `leverCal` set no shaping profile, so they run under whatever the previous handler left (40 cm/s + 180 ms ramp after `RUN:goto`); they also emit no `TOUR:end:<reason>` — regression of C-12 and half of C-08 |
| BT-08 | Minor | `src/blocks/motion.ts:299-309,406-415`; `src/motion/motion_engine.cpp:454,361-368` | "set default turn rate … for move/goTo" is wrong for goTo: `goToR`'s pivot runs at `speed` cruise (≈143°/s at the 15 cm/s default), and `startGoTo`'s timeout comment claims a yaw-rate budget it does not apply |
| BT-09 | Minor | `test/test.ts:275-285` | C-15 still open: `OCAL:` after a failed read carries no stale marker |
| BT-10 | Minor | `src/blocks/world.ts:187,211` | `goToWorld` discards `readWorld()`'s return and plans from the stale cache on a failed read |
| BT-11 | Minor | `test/test.ts:566-568,471-480`; `src/blocks/world.ts:232-245` | `RUN:abort` cannot interrupt a `goToWorld` leg; a one-line `stopMove()` in the abort handler would make abort universal |
| BT-12 | Minor | `src/blocks/motion.ts:51-52,79,445-448` | `ConfigField.ProfileExit` has no block label; `StallClear` is an action inside the "set config %field to %value" dropdown |
| BT-13 | Minor | `src/blocks/motion.ts:235-251,369-391`; `src/blocks/world.ts:232-245`; `test/test.ts:72-102` | Three copies of "start, then `while (_tickDrive())`"; `move()`/`goTo()` omit the `_endMove()` their `while*` siblings call |
| BT-14 | Minor | `src/blocks/world.ts:139,130,148-150`; `src/blocks/motion.ts:296-298` | `turnFirstDeg` is a `let` nothing writes; "set arrival tolerance" only gates `goToWorld`'s pre-check while `goTo` hard-codes 1 mm |
| BT-15 | Suggestion | `src/blocks/stop.ts:15-17`; `src/blocks/motion.ts:355-357`; `src/shims.cpp` `endMove()`/`stopAll()` | `stop` and `stop move` are now the same operation; two blocks for one verb |
| BT-16 | Minor | `src/DESIGN.md:1161-1163,1093-1096,1090-1091` | §9 still says goToWorld is "curvature capped at 25°", puts `onRun` in the Move group, and names one private runner |
| BT-17 | Minor | `test/test.ts:47-49`; `src/blocks/run.ts:117-122,131-134` | Radio comments cite the pre-2026-08-30 channels (tovez 3, vevov 4, "group 10") and the block's `eg:` values match; kGroup is deploy-injected too |
| BT-18 | Minor | `test/test.ts:759-789` | Boot comment asserts "ANY uBit.i2c transaction issued from a RUN handler hangs the board" — contradicted by the same file's RUN handlers and by the root causes since found |
| BT-19 | Minor | `test/test.ts:13-17,104-116` | Header lists 8 of 20 RUN verbs; the RUN:arc block cites a link-hang issue closed in sprint 027 as live |
| BT-20 | Minor | `src/blocks/sim.ts:82-90` vs `src/motion/motion_engine.h:672,704` | Sim geometry constants mirror firmware defaults with no drift test, and per-robot calibration never reaches the browser |
| BT-21 | Suggestion | `test/test.ts:223-229,787-789` | vevov's lever arm is hard-coded into a program flashed fleet-wide; inject it the way `BOOT_ROBOT` is |
| BT-22 | Minor | `src/blocks/run.ts:188-193`; `test/test.ts:909-976` | `runArg()` maps a non-number to 0, so `RUN:circle:abc` pivots in place eight times |
| BT-23 | Minor | `src/blocks/sim.ts:274-288`; `src/shims.cpp` `cycleStat()` | `cycleStat`/`_cycleStat` have no caller in TS, tools or tests — dead shim surface |

## Prior findings status (2026-08-26 review)

| Prior | Status | Evidence |
|---|---|---|
| C-01 startGoTo arc split | **fixed** | `motion.ts:292-314` calls `_setGoToDeadline()` + `_goToR()` (→ `MotionEngine::goToR`); no TS arc math on the hardware path. Pinned by `tests/host/test_goto_block_regression.py`. |
| C-02 legToward | **fixed** | `test.ts:344` `tickedGoTo(bx, by)` — no pivot branch, no `2*bearing`. |
| C-03 goToWorld 25° cap vs 50° split | **fixed** | `kMaxArc` is gone; `world.ts:139` `turnFirstDeg = 12`, residual leg via `tickedGoTo` (`world.ts:226`). Doc drift remains — BT-16. |
| C-04 stop move | **fixed** | `shims.cpp endMove()`: `engine.endMove(); kernel.neutral(); deliverStopNow()`. Sim `_endMove` (`sim.ts:297-302`) matches. |
| C-08 RUN tours not abortable | **partially fixed** | `RUN:abort` + bypass + per-leg checks + `TOUR:end:<reason>` on the three original tours (`test.ts:566-568,375-376`). The five 2026-09-01 tours have abort checks but no terminal line (BT-07); the flag itself is never reset outside tours (BT-01); `goToWorld` legs still uninterruptible (BT-11). |
| C-11 0x5F re-typed | **fixed** | `world.ts:21-24` `startWorldTracking()` returns `worldTrackingReady()`. |
| C-12 RUN handlers mutate global profile | **partially fixed** | `openLoopProfile()`/`closedLoopProfile()` on `tour*`, `straight`, `goto`, `face`, `pivot`, `arc`. Not on `cal` (`test.ts:508-509`), nor on `square`/`infinity`/`snake`/`diamond`/`circle` (BT-07). |
| C-14 sim turn rate | **fixed** | `sim.ts:116` divides by `kSimTrackWidthMm / kSimRotationalSlip` = 119.96 mm. (New drift hazard on the same constants — BT-20.) |
| C-15 logFix stale line | **still open** | `test.ts:278-284` unchanged: `OERR:` then an unmarked `OCAL:`. |
| Q-01 four arc copies | **fixed** | One implementation (`goToR`). The only remaining TS arc math is `sim.ts:199-224`, which is the simulator stand-in by design. |
| Q-05 defaultSpeed 15 / defaultCruiseMmS_ 150 | **partially fixed** | Sprint 019 corrected the `shims.cpp` comment ("read this field back over the wire … not a comment asserting they match"); `motion.ts:86` and `shims.cpp` `defaultCruiseMmS_ = 150.0f` remain two unlinked constants. |
| Q-07 tsconfig cannot run | **fixed** | `tests/host/test_typescript_typecheck.py` runs `node_modules/.bin/tsc --noEmit` every `pytest`. |

---

## Findings

### BT-01 — Major — `aborted` is only ever reset by a tour, so one abort poisons every later non-tour motion verb

**Where**: `test/test.ts:59` (`let aborted = false`), `:84-87` (the check),
and the handlers that never reset it.

`tickToCompletion()` is the runner behind every `tickedMove()`/`tickedGoTo()`:

```ts
    while (diffDrive.driveTick()) {
        ...
        if (aborted) {
            diffDrive.stopMove()
            return
        }
    }
```

`aborted = false` appears in `tourRobot` (`:352`), `tourWheels` (`:386`),
`tourWorld` (`:457`), `squareTour` (`:847`), `infinityTour` (`:867`),
`snakeTour` (`:893`), `diamondTour` (`:937`), `circleTour` (`:964`) — and
nowhere else. `straightRun()` (`:423-439`), `leverCal()` (`:502-526`),
`RUN:face` (`:652-682`), `RUN:pivot` (`:689-706`), `RUN:arc`
(`:725-736`, own loop with the identical check at `:146-149`) all drive
through the runner without touching the flag.

**Failure scenario**: operator sends `RUN:abort` during `RUN:tour:wheels`
(flag → true, tour ends `TOUR:end:abort`). Next, `rotation_check.py`
sends `RUN:pivot:90`. `tickedMove(0, 90)` starts the move, `driveTick()`
runs one 24 ms tick, the check fires, `stopMove()`, return. The handler
then emits `GAP:` and `PIVOT:end` exactly as for a completed pivot. The
robot turned ~1° and the tool records a 90° pivot that "under-rotated by
99%". Every subsequent `RUN:straight`, `RUN:face`, `RUN:cal`, `RUN:arc`
does the same until someone happens to run a tour. This is the
instrument-fault-that-looks-like-a-robot-fault class the project's own
rules warn about, and it is produced by the abort feature itself.

`tests/host/test_run_abort_source_pin.py::test_abort_flag_declared_and_reset_by_every_tour`
counts resets in tours only, so it cannot see this.

**Remedy**: reset `aborted = false` at the top of `tickToCompletion()`'s
callers via one shared entry (e.g. a `beginJob()` that also sets
`touring`), or clear it at the top of every motion handler. Better: have
the `abort` handler call `diffDrive.stopMove()` directly and make
`aborted` a per-job flag (see BT-11).

**Dedupe**: `run-tours-cannot-be-aborted.md` (sprint 016, done) created
the flag; nothing files its non-reset. None found.

### BT-02 — Major — RUN handlers now block the protocol fiber, and two files still say the opposite

Sprint 028 moved RUN dispatch onto the protocol fiber:
`Protocol::dispatchJob()` (`protocol.cpp:310-327`) sets
`motionOwner_ = kJob` and calls `runDispatch()` — the TS callback —
inline. The wire is serviced during a job only through
`tickDrive()`'s service hook (`protocol.cpp:342-345`, `shims.cpp` "Service
hook: fires exactly here on EVERY call"). So any time a handler spends
outside `driveTick()` is time during which no PING is answered, no ESTOP
is parsed, no abort bypass fires, and no telemetry frame goes out.

Blocking calls on that path, all verified against
`.tmp/deploy-head/pxt_modules/core/basic.cpp:37-48` (`showString` of one
character → `printChar(c, interval * 5)` = **750 ms**; longer strings →
synchronous `scroll`):

| Site | Blocks the wire for |
|---|---|
| `test.ts:362,394,470,850,870,896,943` `basic.showNumber(i + 1)` before every leg | 750 ms × legs |
| `test.ts:377,408,437,493` `showString("A"/"W"/"S"/"B")` | 750 ms |
| `test.ts:519,524` `showString("S")`, `showString("OK")` in `leverCal` | 750 ms + ~1.8 s scroll |
| `test.ts:453,270` `showString("NO")` | ~1.8 s scroll |
| `test.ts:516,521` `basic.pause(400)` ×9 in `leverCal` | 3.6 s total |
| `test.ts:616` `basic.pause(300)` in `RUN:seed` | 300 ms |
| `test.ts:858,877,906,950,969` `showIcon(IconNames.Yes)` | PXT default interval (source reading: 600 ms) |
| `world.ts:103` `calibrateWorldSensor()` → `basic.pause(800)` | 800 ms if called from a handler |
| `otos_port.cpp` `begin()` calibration wait, reached from `RUN:probe`/`RUN:fix`/`worldReady()` | up to 1.5 s |

**Failure scenario**: host sends `RUN:cal`. Over the next ~15 s the robot
answers PING only inside the eight pivots; during each 400 ms pause and
the final "OK" scroll it is silent. A host with a 1 s PING timeout
declares the robot dead — the "silent robot" misdiagnosis
`.claude/rules/playfield-testing.md` exists to prevent. An ESTOP sent
during the scroll waits ~1.8 s (the robot is at rest at every one of
these sites, so this is latency, not a safety bypass — which is why this
is Major, not Critical).

The student-facing JSDoc contradicts the code: `run.ts:72-75` *"Handlers
run on their own fiber, so a long test (a full tour) doesn't block the
protocol."* — false since c4ed4c3. `test.ts:543-549` *"that tour's own
handler is mid-execution on its own fiber -- RUN handlers already
interleave"* — false. `run.ts:1-5` *"Safe as shared state because
MessageBus delivers these events one at a time"* — there is no MessageBus
on this path any more, and they are not one at a time (BT-03).

**Remedy**: (1) state the new contract in `onRun()`'s JSDoc: *the handler
runs on the wire's own fiber; keep the wire alive by ticking — anything
that sleeps or scrolls the display stalls PING/ESTOP for its duration*;
(2) in `test.ts`, replace `showNumber`/`showString` with `showLeds`-free
non-blocking forms (`basic.showNumber(n, 0)` still blocks 0 ms×5 → use
`led.plot` or `basic.showString(s, 1)`), and replace the `basic.pause()`
settles with a `while (driveTick())`-style wait so servicing continues;
(3) consider having `dispatchJob()` run the job on a dedicated job fiber
with the protocol fiber parked — out of this reviewer's scope.

**Dedupe**: `single-executor-for-command-dispatch.md` (sprint 028, done)
introduced the inversion and does not discuss handler-side blocking.
`test_run_abort_source_pin.py` header notes abort "needs a robot" to
prove. None found for this consequence.

### BT-03 — Major — nested bypass dispatch clobbers `runParts`; the contract that makes it safe is unstated on the TS side

`run.ts:43-58`:

```ts
        _registerRunDispatch(function () {
            const text = runCommandText()
            if (text.length == 0) return
            ensureRunState()
            runParts = text.split(":")
```

`protocol.cpp:283-297` dispatches `abort`/`clearestop` *"RIGHT NOW, on
whatever fiber called handleRun() … the service hook nested inside a
running job's own tick loop"*. That nested call runs this same callback,
which reassigns the module-level `runParts`. When the outer handler
resumes after its `driveTick()`, `runArg(i)`/`runArgText(i)`/
`runArgCount()` (`run.ts:188-207`) now describe the abort command.

`protocol.h:180-188` knows this and pins it on discipline elsewhere:
*"every onRun() handler in this package reads its arguments only at
entry (test/test.ts), never later during a long-running tick loop."*
True today (every handler in `test.ts` reads `runArg` before its first
move), but: `run.ts` — the file whose API this is — says nothing;
`onRun()`'s JSDoc says *"further arguments are available from
runArg()"* with no timing caveat; and a student's own `on run` block
that reads `runArg(1)` after a `move` block will get 0 (abort has no
args) or wrong values.

**Failure scenario**: a student writes `onRun("box", …)` that does
`move(runArg(0), 0)` then `move(runArg(1), 0)`. A `RUN:abort` arriving
during the first leg leaves the second leg reading `runArgText(1)` of
`"abort"` → `""` → 0 → silent no-move.

**Remedy**: snapshot arguments per dispatch — bind the split array into
the handler call instead of a shared `let` (pass `parts` as a closure
value; `runArg()` can read from a stack the nested call pushes and pops),
or at minimum document the rule in `onRun()`'s JSDoc and have the bypass
path save/restore `runParts` around the nested call.

**Dedupe**: none found (`protocol.h` comment is the only mention).

### BT-04 — Major — the background OTOS sampler violates the one-fiber I2C invariant `world.ts` states

`world.ts:9-12`: *"Every read here is a live I2C burst, so these must be
called from the same fiber that calls driveTick() -- never concurrently
with one (an OTOS transaction landing inside the Nezha encoder's
select->read window destroys that encoder sample)."*

`test.ts:808-813`:

```ts
control.inBackground(function () {
    while (true) {
        diffDrive.readWorld()
        basic.pause(100)
    }
})
```

The comment above it (`:800-807`) concedes *"the two ports share the bus
with NO mutual exclusion"* and argues 10 Hz is "deliberately slower than
the 50 ms telemetry tick" — a rate argument that does not address the
collision: `kernel.step()` yields twice inside its select→read settle
(`shims.cpp` tickDrive: *"step() already yields twice in there for its
own encoder select-to-read settle"*), and CODAL's cooperative scheduler
will run this fiber's `readWorld()` in exactly that gap whenever its
100 ms pause expires there. With `stepBusy` held by the job fiber, the
guard in `tickDrive()` does not cover this fiber because it never calls
`tickDrive()`.

Sprint 028's own issue text says the single executor *"makes the I2C
bus-discipline invariant structural rather than a convention three call
sites each have to remember"* — this fiber is the fourth call site, in
the test program the fleet runs.

**Failure scenario**: during any leg, one in ~N encoder samples is
destroyed; the glitch armor either rejects it (`probe(23/24)` climbs) or
the odometry integrates a bad delta. Either way `i2cf` climbs during
runs, which is what the vevov line-following session observed.

**Remedy**: sample the OTOS from the job fiber — inside
`tickToCompletion()`'s loop (every k-th tick), which is already the
fiber that ticks — and drop the background fiber. For the idle case
(host wants `ox/oy/oh` while no job runs), the protocol fiber's own
`serviceOnce()` is the right place, and that is a `protocol.cpp` change.

**Dedupe**: `i2c-fault-count-climbs-on-idle-bus.md` (open, sprint 018)
is the idle-bus symptom; this is a concrete in-motion mechanism and
should be cross-referenced there, not merged. `tour-corner-fixes-are-
stale-cache.md` motivated the sampler. None found for the collision.

### BT-05 — Major — `startDrive()` makes the two-fiber I2C collision the easy thing to write

`motion.ts:178-186`:

```ts
    export function startDrive(speed: number, yawRate: number): void {
        driveTwist(speed, yawRate)
        if (driveLoopRunning) return
        driveLoopRunning = true
        control.inBackground(() => {
            while (_tickDrive());
            driveLoopRunning = false
        })
    }
```

This is the block a student reaches for to "drive and do other things".
The other things, in the World group next to it, are `read world
position` (`world.ts:60-62`, live I2C), `start world tracking`,
`calibrate world sensor`, `set world pose`. All four now run on the main
fiber while the background fiber is inside `kernel.step()` — BT-04's
collision, built into the API. The `startDrive` JSDoc flags the
two-ticker case as UNVERIFIED (`:166-172`, correct and respectable) but
does not mention the OTOS at all, and `world.ts`'s warning is a file
header students never see.

**Failure scenario**: `on start: start world tracking; start drive 15 0;
forever: if world x > 50 then stop`. Encoder samples are destroyed at
random during the drive; the odometry the watchdog and stall detector
depend on degrades; nothing reports why.

**Remedy**: either (a) make `whileDriving` the only continuous form and
drop `startDrive`, or (b) have `startDrive`'s loop own the OTOS read
(sample every k ticks into the cache so `world x` stays a cache read) and
say in `read world position`'s JSDoc that it is a bus transaction that
must not overlap a background drive.

**Dedupe**: none found.

### BT-06 — Major — simulator blends every move; hardware splits at 50°

`sim.ts:129-146` `_startMove()` computes one blended `simVel`/`simYawRate`
for any `(distance, yaw)`. `motion_engine.cpp:393`:

```cpp
  if (distance != 0.0f && std::fabs(rotation) >= kTurnFirstAngleRad) {
    queuePivotThenStraight(rotation, distance, cruise);
```

`test.ts:822-826` records the physical consequence: *"an arc asked for in
90 deg pieces comes out as a SQUARE … measured 2026-09-01: 90 deg pieces
drew a square, 45 deg pieces drew the circle."* The simulator draws the
circle for both.

**Failure scenario**: student writes `move 47 cm turning 90 degrees`
(a quarter circle of r = 30 cm). Browser: the robot ends 30 cm forward,
30 cm left, facing left. Robot: pivots 90° then drives 47 cm straight
left, ending 0 forward, 47 cm left. The block's own JSDoc (`motion.ts:
228-229`, *"Both at once makes an arc"*) is true in the browser and false
on hardware above 50°. This is the parity class the sprint 007/021
simulator issues were opened for, and the one shape they did not cover.

`sim.ts:179-191` already explains why `_goToR` need not split (same
endpoint either way); `_startMove` is the case where the endpoint
differs, and it has no such note.

**Remedy**: mirror the split in `_startMove` — if `distance != 0 &&
|yaw| >= 50°`, run the yaw first then the distance (two phases, same
`simMoveRemain*` machinery), reading the threshold from a single
constant with a drift test against `kTurnFirstAngleRad` (as
`test_run_tour_programs.py::test_split_threshold_is_where_we_think_it_is`
already does for the tours). Also fix `move()`'s JSDoc to say "both at
once makes an arc up to 50°; beyond that it turns first, then drives".

**Dedupe**: `simulator-parity-turn-rate-and-estop.md` (007, done),
`simulator-yaw-rate-divisor-diverges-from-hardware-track-width.md` (021,
done), `int32-sim-params-break-blocks-conversion.md` (021, done) — none
covers the split. None found.

### BT-07 — Major — the 2026-09-01 tour suite and `leverCal` run under an inherited profile and emit no terminal line

Sprint 018 ticket 001 (closing C-12) made every RUN handler call one
named profile at entry. The tours added on 2026-09-01 do not:
`squareTour` (`test.ts:844-859`), `infinityTour` (`:864-879`),
`snakeTour` (`:890-907`), `diamondTour` (`:935-951`), `circleTour`
(`:961-970`) call neither `openLoopProfile()` nor `closedLoopProfile()`.
`leverCal` (`:502-526`) sets only `setDefaultSpeed(15)`/`setDefaultYawRate(45)`
and inherits taper/floors/ramp.

**Failure scenario**: `RUN:goto:50:30` (closed profile: 40 cm/s, taper
120/80, floors 45/35, ramp 180 ms) then `RUN:circle:30`. The circle
runs at 40 cm/s with the fast taper. The same `RUN:circle:30` after
`RUN:pivot:90` runs at 20 cm/s with the accuracy taper. Two runs of the
identical command, two different figures, in the suite whose whole
purpose is comparing figures against camera truth.

Same five tours: no `TOUR:end:<reason>` line and no `probe(1)` e-stop
check (`:856-858` ends with `stopMove(); touring = false;
showIcon(Yes)`), so an e-stopped circle ends with a smiley and no wire
receipt — the C-08 transcript problem, back.

**Remedy**: one `beginTour(name)` helper that sets `touring`, clears
`aborted` (BT-01), applies a named profile, resets `maxGapMs`, and one
`endTour()` that emits `GAP:` and `TOUR:end:<reason>`; every figure
calls both. `leverCal` should call `openLoopProfile()` then override the
two rates.

**Dedupe**: C-12 → sprint 018 ticket 001 (done); C-08 → sprint 016 ticket
005 (done). This is a regression in code written after both closed.
None found open.

### BT-08 — Minor — "set default turn rate" does not govern `goTo`'s pivot, and `startGoTo`'s timeout comment says it does

`motion.ts:406-408`: *"Default turn rate for move/goTo blocks."*
`motion.ts:299-303`: *"goToR() drives a <=180 deg pivot … using the same
defaultYawRate/defaultSpeed startMove() itself would use for those two
axes"*.

`startGoTo` passes only `speedMmS` (`:295,314`). `goToR`
(`motion_engine.cpp:454`) calls `queuePivotThenStraight(bearingRaw,
chord, speed)`, and `queuePivotThenStraight` (`:361-368`) starts the
pivot as `startSegment(0.0f, pivotRotation, cruise)` — wheel cruise
`speed`, no yaw-rate input at all. At the 15 cm/s default with
`effectiveTrackWidth` ≈ 120 mm the pivot turns at 2·150/120 rad/s ≈
143°/s, whatever "set default turn rate" says (subject to the sprint 025
`MaxYawRate` cap if set). `move` honours the setting; `goTo` does not.

**Remedy**: fix both comments; if `goTo`'s pivot should honour the
default yaw rate, `startGoTo` needs to convert it to a pivot cruise (the
same `yawRadPerS * 0.5 * b` `startMove` already computes in `shims.cpp`).

**Dedupe**: none found.

### BT-09 — Minor — C-15 still open: stale `OCAL:` after a failed read

`test.ts:278-284` unchanged from the 08-26 review: `OERR:read-failed:<tag>`
then an unmarked `OCAL:<tag>:…` from the cache. Any consumer grepping
`OCAL:` reads the stale pose as a fix. Remedy: suffix the tag
(`OCAL:c2!stale:…`) or omit the line.

**Dedupe**: `tour-corner-fixes-are-stale-cache.md` (open, low) — same
class; cross-reference.

### BT-10 — Minor — `goToWorld` plans from a stale fix on a failed read

`world.ts:187` `readWorld()` and `:211` `readWorld()` discard the bool
the block itself documents (*"Returns false if the sensor did not
answer; the last good values are kept"*, `:53-55`). A failed read → the
leg is planned from wherever the cache last was. Remedy: return `false`
from `goToWorld` (it is `void` today) or refuse the leg and emit.

**Dedupe**: `tour-corner-fixes-are-stale-cache.md` — cross-reference.

### BT-11 — Minor — abort cannot stop a `goToWorld` leg; the fix is one line

`world.ts:232-245` `tickedMove`/`tickedGoTo` loop on `_tickDrive()` with
no abort check (by design — `world.ts` cannot see `test.ts`'s flag).
`test.ts:471-480` documents the gap. But since sprint 028 the abort
bypass runs *inside* the leg's own `tickDrive()` (`protocol.cpp:283-297`),
so `diffDrive.onRun("abort", …)` calling `diffDrive.stopMove()` directly
ends the engine move → the next `_tickDrive()` returns false → any loop,
in any file, exits. That also makes the flag in BT-01 unnecessary as a
stop mechanism (keep it only to break the tour's `for`).

**Dedupe**: `run-tours-cannot-be-aborted.md` (016, done) accepted the
scope boundary. Not re-filed there; noted as now cheaply closable.

### BT-12 — Minor — `ConfigField` exposes an unlabeled enum member and an action

`motion.ts:79` `ProfileExit = 31` has no `//% block=` line, so the "set
config" dropdown shows the identifier. `motion.ts:51-52` `StallClear =
17` is an action (`shims.cpp setKernelValue case 17`) inside a
"set %field to %value" block — "set clear stall latch to 5" — while a
real `clear stall latch` block exists (`stop.ts:56-60`). Remedy: label
`ProfileExit`; hide `StallClear` from the block enum (`//% blockHidden`)
or move it out of `ConfigField`.

**Dedupe**: none found.

### BT-13 — Minor — three copies of the tick runner, and two of them differ

| Site | Body |
|---|---|
| `motion.ts:235-238` `move()` | `startMove; while (_tickDrive());` |
| `motion.ts:248-251` `goTo()` | `startGoTo; while (_tickDrive());` |
| `motion.ts:369-376` `whileMoving()` | same + `body()` + **`_endMove()`** |
| `world.ts:232-245` `tickedMove`/`tickedGoTo` | `move()`/`goTo()` re-typed, with a `(0,0)` guard `startMove`→`moveX` already applies (`duration <= 0 return`) |
| `test.ts:72-102` `tickToCompletion` + two wrappers | same again + gap timing + abort |

`world.ts` could call `move()`/`goTo()`; the file's own comment
(`:229-231`) says the point is ticking on "THIS fiber", which
`move()`/`goTo()` already do. Whether `_endMove()` belongs after the
loop should be decided once: `whileMoving` calls it, `move` does not.

**Dedupe**: none found.

### BT-14 — Minor — `turnFirstDeg` is a `let` nothing writes; arrival tolerance applies to one block of two

`world.ts:139` `let turnFirstDeg = 12.0` — no setter, no other write;
`const`. `world.ts:130,148-150` `setArrivalTolerance` ("How close counts
as 'arrived'") gates only `goToWorld`'s pre-check (`:194`); `goTo`
hard-codes `arriveMm = 1` (`motion.ts:298`). A student who sets 5 cm
expects `go to x y` to honour it. Remedy: pass `arriveTolCm * 10` into
`_goToR` from `startGoTo`, or say in the block text which block it
affects.

**Dedupe**: none found.

### BT-15 — Suggestion — `stop` and `stop move` are one operation with two blocks

`shims.cpp endMove()`: `engine.endMove(); kernel.neutral();
deliverStopNow()`. `stopAll()`: identical three calls (plus `ensure()`).
`stop.ts:15-17` and `motion.ts:355-357` are two blocks in the same Stop
group for the same effect; the `stopMove` JSDoc (`:346-348`) says so
itself. One block is easier to teach; keep `stopMove()` as a hidden alias
if tools depend on it.

**Dedupe**: sprint 016 stop taxonomy (`src/DESIGN.md` §12) chose to make
them equal; it did not decide whether to keep both blocks. None found.

### BT-16 — Minor — `src/DESIGN.md` §9 drift

- `:1161-1163` *"pivot-first beyond 12°, curvature capped at 25°"* —
  the cap is gone (C-03 fix); the residual leg goes through `goToR`.
- `:1093-1096` `onRun`/`onRunCommand` *"(Move group in the toolbox …)"* —
  `run.ts:80,96` say `group="Remote"`, subcategory Extra.
- `:1090-1091` *"private `tickedMove()` runner"* — two runners now.

**Dedupe**: `design-docs-assert-fixed-limitations.md` (017, done) was the
last truthfulness pass; these post-date it. None found open.

### BT-17 — Minor — radio comments and block defaults describe the retired addressing

`test.ts:47-49`: *"so `--robot tovez` still lands on channel 3 rather
than vevov's 4"*. Per `.claude/rules/playfield-testing.md` the fleet
migrated on 2026-08-30: tovez 55/108, vevov 37/43; only zeguz/zetuv are
on 3/10. `run.ts:121-122` `eg: 4` / `eg: 10` and `:133-134` *"and group
10"* — `radio_transport.h:240-246` shows **both** `kChannel` and `kGroup`
are deploy-injected, so "group 10" is not what `enableRadioLink()`
brings up on a deployed board. Whether the block's `group = 10` default
collides with the relay's reserved control group under the new scheme is
**UNVERIFIED** here — the relay's own naming code would settle it.

**Dedupe**: `radio-group-setup-block.md` (done) added the block; none
found for the stale defaults.

### BT-18 — Minor — a boot comment asserts a hazard the same file disproves

`test.ts:759-789`: *"ANY uBit.i2c transaction issued from a RUN handler
hangs the board permanently … the CALLING CONTEXT is [at fault]"*, so
OTOS bring-up was moved to boot. The same file's RUN handlers still do
OTOS I2C routinely — `logFix()` → `readWorld()` on every corner
(`:278`), `RUN:fix` → `worldReady()` → `startWorldTracking()` → `otosBegin()`
(`:265,596`), `RUN:seedxy` → `seedPose()` → `otosRef().setPose()` — and
the 2026-08-29 tours ran. The mechanisms since identified are (a) CODAL's
VFP-unsafe context switch (`run-fiber-motion-resets-the-board-on-fw-1-
20260829-1.md`, done — and RUN handlers are no longer on a second fiber
anyway) and (b) CODAL's I2C `waitForStop()` never timing out when the
OTOS does not ACK (`first-i2c-command-can-wedge-the-program-with-no-
recovery.md`, open). Neither is "the calling context". The boot-time
`otosBegin()` at `:777` is itself a caller of (b) on every OTOS-less
board in the fleet.

**Remedy**: replace the block with the two facts that are still true
(OTOS is begun at boot on the main fiber so `otos=` in STATUS is
meaningful; the lever arm is applied here because it is pure software)
and point at the open issue for the no-ACK hazard.

**Dedupe**: both issues named above; the *comment* is not filed. None
found.

### BT-19 — Minor — stale header and a closed-issue citation in `test.ts`

`test.ts:13-17` lists `cal fix seed probe arm gap pivot turnrate`; the
file registers 20 verbs (`abort clearestop tour straight cal fix arm
probe gap seed seedxy goto face pivot arc turnrate square infinity snake
diamond circle`). `test.ts:106-109` cites
`clasi/issues/cleartext-run-hangs-the-link-under-active-telemetry.md` as
a live hazard; it is in `sprints/done/027/issues/done/`. The RUN:arc
sampling design is still sound; the justification is stale.

**Dedupe**: none found.

### BT-20 — Minor — sim geometry mirrors firmware defaults with no drift test, and never sees per-robot values

`sim.ts:89-90` `kSimTrackWidthMm = 114.2`, `kSimRotationalSlip = 0.952`
equal `motion_engine.h:672,704` today. The comment promises the split
into two constants *"so a future geometry/slip bake update can't
silently reopen the gap"* — but nothing compares them
(`test_wire_constants_drift.py` covers wire constants only). And
`_setGeometry`/`_setKernelValue` are recorded and ignored
(`sim.ts:376-386`), so a student who pastes the calibration block the
open calibration-skill issue proposes (`setTrackWidth(12.8)`,
`RotationalSlip 0.987`) gets a browser robot that turns 12% faster than
theirs. Remedy: a drift test now; make the sim honour `_setGeometry` /
`RotationalSlip` later.

**Dedupe**: `calibration-skill-emits-a-paste-able-makecode-block.md`
(open, high) — cross-reference the sim half. None found for drift.

### BT-21 — Suggestion — vevov's lever arm is hard-coded into a fleet-wide program

`test.ts:223-229` `armX = -5.27, armY = -0.12, armYaw = 0.89` (vevov,
2026-08-28) and `:787-789` applies them on any board whose OTOS answers.
Today only vevov has an OTOS, so this is latent; the same file already
has the injection seam for `BOOT_ROBOT`/`BOOT_VERSION` (`:31-32`), and
`radio-robot-lib/config/robots/<robot>.json` is where the arm lives.
Inject it.

**Dedupe**: `calibration-skill-emits-a-paste-able-makecode-block.md`
covers the student path, not `test.ts`. None found.

### BT-22 — Minor — `runArg()` turns a typo into a zero-radius figure

`run.ts:188-193` returns 0 for a non-numeric argument. `test.ts:972-975`
`RUN:circle:abc` → `r = 0` → `arcSegment(0, 45)` → `tickedMove(0, 45)`
×8: the robot pivots a full turn in place and reports `DBG:tour=circle:r=0`.
`RUN:square:abc` → four pivots. Remedy: `runArgCount() > 0 && !isNaN(...)`
in the defaults, or a `runArgOr(i, default)` helper; reject `r <= 0`.

**Dedupe**: none found.

### BT-23 — Minor — `cycleStat` is dead surface

`sim.ts:279-288` `_cycleStat` is neither exported nor called;
`shims.cpp` `cycleStat()` is `//%`-exported and has no caller in `src/`,
`test/`, `tools/` or `tests/` (grep). Its comment says "for desk
verification (and future wire-protocol reporting)"; `diagValue` 16/19
already carry cycle count and overruns. Delete, or wire it to a block.

**Dedupe**: none found.

---

## What held up

- **The arc family is one implementation now.** `startGoTo` → `goToR`,
  `goToWorld`'s residual → `startGoTo`, `legToward` → `tickedGoTo`. The
  only remaining TS arc math is the simulator stand-in, correctly noted
  as reaching the same endpoint. `test_goto_block_regression.py` keeps
  the old reduction as a frozen negative control — the right shape.
- **Units across the shim boundary are right everywhere checked**: cm→mm
  ×10 (`setWheelSpeeds`, `startMove`, `seedPose`), deg→cdeg ×100,
  track width cm→0.1 mm ×100, calibration ×10⁴, config ×1000, OTOS
  offset cm→0.1 mm ×100, `otosGet(0)`/100 → cm, `poseHeading`/100 → deg.
  Every `//%` shim called from TS is ≤4 params; every `//%` sits
  immediately above its signature; every sim body has a statement.
- **`pxt.json` file order** puts `sim.ts` before `motion.ts`, which the
  top-level `_startProtocol()` needs (§9's one load-time constraint).
- **The no-initialiser trap** on `run.ts:15-19` is intact, guarded by
  `ensureRunState()` at every entry, and `runArgCount()` has its null
  guard.
- **`isMoving()`'s JSDoc** (`motion.ts:317-327`) now says it advances the
  move — the 08-23/08-26 "actively wrong comment" is fixed, as is the
  namespace header's "own fiber" claim.
- **`goToWorld` is genuinely one pass** and its pivot-first threshold
  (12°) sits well below `goToR`'s 25°-bearing split, so the C-03 boundary
  collision cannot recur.
- **The abort bypass** in `protocol.cpp` is real and pinned; the TS side
  reads all arguments at entry (BT-03 is about the unstated contract,
  not a live defect).
- **`stop move` == `stop`** on both hardware and sim (C-04).

## Comment boil-down (worst ten, plus factual errors)

Replacement text is what should remain; everything else in the range is
archaeology, diff narration, or justification.

| # | Range | Replace with |
|---|---|---|
| 1 | `sim.ts:154-165` + `:179-197` (`_setGoToDeadline`/`_goToR` preambles, the TS9200 story told twice) | `// Two shims, not one: a five-parameter //% shim fails the PXT packager (TS9200). Deadline is pre-armed by _setGoToDeadline() for the very next _goToR().` and, on `_goToR`: `// [mm] [mm] [mm/s] [mm]. Sim reaches (x, y) as one blended arc; hardware's >=50 deg pivot-then-chord split lands at the same point, so no split is modelled.` |
| 2 | `sim.ts:97-116` (`_setWheels` divisor essay incl. "Previously divided by … R-12/BLK-06") | `// omega = (vR - vL) / effectiveTrackWidth, effectiveTrackWidth = trackWidth / rotationalSlip (motion_engine.h). Same divisor _driveTwist() inverts.` |
| 3 | `sim.ts:234-251` (`_tickDrive` return-value history, "sprint 007 ticket 002, closes R-10/API-01") | `// Returns "anything still commanded" (move active or nonzero velocity), matching shims.cpp's commandLooksActive(): a continuous drive keeps the loop alive; a finished move ends it on the same call.` |
| 4 | `sim.ts:323-329`, `:364-370`, `:414-422`, `:453-457`, `:505-513`, `:527-532` (six restatements of "an empty body is emitted as native-only and crashes the simulator") | One note at the top of the file: `// Every shim body here must contain a statement: pxt emits an empty {} as native-only and the simulator crashes at the call site.` Delete the six copies. |
| 5 | `motion.ts:281-291` (`startGoTo` "sprint 015 ticket 006 … TS9200 … moveX()'s own >=50 deg split reissues …") | `// goToR owns the pivot-vs-arc split; never reduce to (distance, yaw) and go through startMove(), which would land elsewhere above 50 deg.` |
| 6 | `run.ts:28-42` (`wireRunDispatch` "not raised as a MessageBus event … unlike the old event-value-as-slot-number scheme") | `// Called by the protocol fiber, inline, once per dequeued RUN command; abort/clearestop can arrive nested inside a running handler's tick loop.` (This also fixes the factual error at `:1-5` and `:72-75` — see BT-02/BT-03.) |
| 7 | `test.ts:759-789` (boot OTOS "ANY uBit.i2c transaction issued from a RUN handler hangs the board") — **factually wrong** (BT-18) | `// OTOS begun once at boot so STATUS's otos= flag is meaningful. Lever arm applied here: pure software, no I2C. No-ACK hazard: first-i2c-command-can-wedge-the-program-with-no-recovery.md.` |
| 8 | `test.ts:202-222` (two superseded lever-arm measurement narratives stacked above the current one) | Keep `:207-217` (the 2026-08-28 measurement + capture path) and `:219-222` (the camera cross-check). Delete `:202-206` (the 2026-08-20 38.2 mm arm that `:208-210` says was invalidated). |
| 9 | `test.ts:543-560` (abort/clearestop header fused with "RUN handlers already interleave … on its own fiber" — **factually wrong** since sprint 028) | `// abort and clearestop bypass the RUN queue and run nested inside whatever handler is mid-tick (protocol.cpp handleRun); keep them flag-only and non-blocking. clearestop exists because ESTOP had no wire-level clear.` |
| 10 | `stop.ts:4-8` (group layout archaeology "sprint 021 ticket 004, approved layout in block-toolbox-groups-reorganization.md") | Delete; `run.ts:61-65` already says weights/groups come from `reports/blocks-toolbox.csv`. |

Other factual errors in comments (fix text, no rewrite proposed):
`test.ts:47-49` channels (BT-17); `test.ts:106-109` link-hang issue
closed (BT-19); `motion.ts:299-303` goTo pivot "uses defaultYawRate"
(BT-08); `motion.ts:406-408` "for move/goTo" (BT-08); `world.ts:9`
"Every read here is a live I2C burst" — `worldX/Y/Heading` and
`worldTrackingReady` are cache reads (`otosGet`), only `readWorld`,
`startWorldTracking`, `calibrateWorldSensor`, `seedPose`,
`setWorldSensorOffset` touch the bus; `src/DESIGN.md:1161-1163` (BT-16).

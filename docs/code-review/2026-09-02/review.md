# Code Review — 2026-09-02

**Scope**: `src/` (kernel, motion engine, platform ports, shims, comms,
blocks), `test/test.ts`, `tools/`, `tests/`. Code state: master at
`50efc2d`, sprint 028 merged (single executor, frozen-encoder hold, `SET
rebase`).
**Asked for**: errors; complicated code that should be simpler or more
cohesive; excessive comments; race conditions; anything that can
corrupt the shared I2C bus; and a special pass on the motion algorithms —
profile shaping, motion control quality, jerk, and where accuracy is lost.
**Method**: per [guidelines.md](../guidelines.md). Four annexes carry the
full detail and every quoted line; this report consolidates and ranks.
Every algorithm claim marked MEASURED was executed against the real
`diffdrive.cpp` + `motion_engine.cpp` by a host probe archived here
([`raw/profile_probe.cpp`](raw/profile_probe.cpp), output in
[`raw/profile_probe.out`](raw/profile_probe.out)). Nothing under `src/`,
`test/`, `tests/` or `tools/` was changed.
**Dedupe**: every finding was checked against `clasi/issues/**`,
`clasi/sprints/done/*/issues/**` and the 2026-08-26 review. Findings that
are already filed are cross-referenced, not re-reported; three open
issues get a corrected diagnosis (marked ⟲).

**Annexes**:
[motion-and-kernel](raw/motion-and-kernel.md) (MK/RC/CO/CH) ·
[comms](raw/comms.md) (CM) ·
[blocks-and-test](raw/blocks-and-test.md) (BT) ·
[tools-and-tests](raw/tools-and-tests.md) (TL)

**Totals**: **1 Critical · 24 Major · ~35 Minor · ~14 Suggestion**, plus
16 comments that are factually wrong and a 53-block comment boil-down
work order. Test baseline: 922 passed, 1 environment failure (§6).

---

## Executive summary

Three things stand out, and they are connected.

**1. The motion profile is shaped by three uncoordinated mechanisms, and
the accuracy loss the project has been calibrating away is their
interaction.** The kernel has a 70 mm/s speed floor; the move engine has
a 25 %/12 % taper floor that sits below it and is therefore inert; the
kernel's twist-hold servo integrates the *pre-floor* twist while the
wheels run the *floored* twist. MEASURED on the real code with ideal
wheels: every pivot coasts ~1.5°/tick past its target because completion
is detected after the crossing and the neutral lands a tick later
(`pivot_overrun`, 2.2 mm per wheel, is one tick of floor crawl); in the
crawl of every pivot below ~200 mm/s the twist servo fights the floor and
ends with a −11 % reverse kick; the position-only integral loop (`kp` 0)
overspeeds +10 % after every ramp and, on a frozen encoder tick, kicks
duty +6 points through the *position* reference — which is not the
mechanism the open issue on that transient names. Jerk is unbounded at
the start and end of every move in every mode, including the jerk-limited
one, and unbounded everywhere outside the move engine (`set wheel
speeds`, the port's 25 %/tick slew). Section 1.

**2. The one-fiber I2C invariant is documented three times and enforced
nowhere, and sprint 028 made the remaining holes easier to hit.** Every
OTOS entry point on the shim surface skips the `stepBusy` guard that
`tickDrive()` takes; `SET rebase` writes the OTOS from the protocol fiber
while a student's `driveTick()` loop can be inside its settle window; the
fleet test program runs a 10 Hz background OTOS sampler on its own fiber;
the `start drive` block forks a background ticker and the next block over
is a live I2C read. Separately, the tick service hook checks *state*
(`motionOwner_ == kJob`) rather than *fiber*, so a button-handler tour
during a RUN job runs the wire dispatcher on two fibers at once and can
execute a line the host never sent. Section 2.

**3. Cohesion is being lost in exactly the places the last two sprints
touched.** `serviceMove()` is two profile algorithms braided through five
mode forks; the rebase-epoch guard is copied three times; odometry is
spread over `Rig`, a reference-holding adapter and four free functions;
the config surface is five hand-synchronised ordinal tables; `Protocol`
has grown a RUN bridge, a motion arbiter and three radio gates. Comment
volume is back above the 08-26 level (project `src/` ≈ 1.4 comment lines
per code line; the kernel runs 0.03) with a new flavour — dated capture
citations instead of sprint numbers, several of which point at untracked
files. Sections 3 and 4.

Also new since 08-26: the test program's `aborted` flag is reset only by
tours, so one `RUN:abort` turns every later `RUN:pivot`/`straight`/`face`
into a one-tick no-op that reports a normal end; RUN handlers now block
the wire for the duration of every `showString`/`pause`; `TLM NOW` acks
and emits nothing; the simulator blends every move while hardware splits
at 50°. On the bench side, the one Critical: `camlink.py` still carries
tag 53's pre-remount lever and re-registers it into the aprilcam daemon's
*persistent* registry every time a tool starts, while
`field_calibration.json` holds the 2026-09-02 measurement — two
calibrations of record, silently overwriting each other, on the tag whose
pose decides whether vevov drives into a rail. `robotlink.py` still tunes
the relay to vevov's retired 4/10.

What held up: the seqlocks, the run/emit rings, the radio RX handoff, the
tokenizer bounds, the clock arithmetic, the stop taxonomy from sprint 016,
and every 08-26 arc-geometry finding (C-01/02/03, Q-01) — those are fixed
and pinned.

---

## 1. Algorithms — profile, control, jerk, accuracy

Read `controlStep()` with the fleet bake (`shims.cpp:ensure()`) in hand:
`kp` 0, `kaff` 0, `ki` 6, `iMax` 765.6, `posErrMax` 127.6, `vMin` 893.2
(70 mm/s), `twistHoldGain` 2.0. The controller reduces to

```
duty = (FF + I) / fullDutyVelocity
FF   = commanded wheel speed after twist trim and after the 70 mm/s floor
I    = clamp(ki · clamp(reference − position, ±posErrMax), ±iMax)
reference += commanded speed · dt        (never clamped)
```

The only feedback is an integral of position error. On top of it,
`MotionEngine::serviceMove()` multiplies one full-rate command by a scale:
time ramp or accel integrator up, `remain/taper` or `sqrt(2·a·remain)`
down, floored, optionally jerk-rounded, reissued every tick; completion is
a position test after the fact.

### MK-01 — MAJOR: pivots coast one tick past the target; `pivot_overrun` calibrates that latency per robot

MEASURED (`profile_probe.out` E3c/E3d): 90° pivot at cruise 100 reads
88.69° → 90.22° (completion fires, neutral *staged*) → the wheels keep
moving through the next tick because the neutral lands on the following
`step()`. Terminal crawl is 1.47-1.53°/tick — the 70 mm/s floor is 21
counts per tick against a 4-count margin. Final yaw with the twist servo
off: +1.95° (cruise 60), +2.56° (100), +0.81° (200). The fleet's measured
constant is "+2° per pivot, 3° and 90° alike" and the fix shipped as
`pivotOverrunMm` = 2.2 mm per wheel — one tick of floor crawl (1.68 mm)
plus stop lag. Two remedies, either sufficient: terminate predictively
(stop when `remain <= v_cmd·dt + stopDistance`), and give pure turns a
floor in °/s (70 mm/s per wheel is 67°/s on a 120 mm track).
Dedupe: `pivots-over-rotate-on-corrected-firmware.md` (done) added the
compensation; the mechanism is not filed.

### MK-02 — MAJOR (kernel): the twist-hold servo integrates the pre-floor twist and fights the floor in every crawl

`diffdrive.cpp:599` integrates `twistRef_.reference` from `lambda ·
cmd.twist`; `applySpeedFloor()` at line 617 then rescales both wheels up
to `vMin`. Whenever the floor binds, the wheels run a larger
half-differential than the reference integrates, the error goes negative,
and the trim brakes the turn. MEASURED (E3d/E3e, ideal wheels):

| move | twist-hold 2.0 | twist-hold 0 |
|---|---|---|
| pivot 90° @60 | most-negative right duty **−13 %**, ends **88.20°** | ends 91.95° |
| pivot 90° @100 | **−11 %**, ends **88.07°** | ends 92.56° |
| arc 300 mm / 45° @100 | ends (285, 120) | ends (270, 112) — the exact endpoint is (270, 112) |

Hardware magnitude UNVERIFIED (the fleet measures pivots long, not
short, so motor lag dominates there), but two code paths feeding
different twist values into one reference is not in doubt. Fix: integrate
the reference from the post-floor half-differential and compute headroom
from the same floored speeds. Vendored — see CO-07.

### MK-03 — MAJOR (kernel) ⟲: no damping, no anti-windup, and the frozen-tick transient is the position I-term

MEASURED (E1/E7/E11/E1b): a 600 mm straight at cruise 200 peaks at
220.7 mm/s (+10 %) right after the ramp on ideal wheels, +20 % with an
80 ms motor lag; `set wheel speeds 200 200` from rest reads 0, 200, 229,
229, 225 mm/s on consecutive ticks. Cause: the one-tick stage→land→move
pipeline is a real position backlog and nothing opposes the integral's
catch-up.

MEASURED (E5): freezing one encoder for a single tick at 300 mm/s steps
that wheel's duty 35.3 → **41.3 %** for a tick and the wheel really runs
17 % fast. That is the open issue's "duty jumps 4-12 points" — through
`positionError()` (the reference advanced 92 counts while
`sample.position` held; 6 · 92 = 551 counts/s = 5.1 % duty), **not**
through `errLeft/errRight`, which with `kp` 0 reach the duty only via bias
adaptation (τ = 30 s). The issue's proposed fix (gate the velocity error
on freshness) would change nothing on the fleet bake; the fix is to skip
`ref.reference += speed·dt` for a wheel whose sample did not advance.
Anti-windup: `ref.reference` accumulates unbounded and only the returned
error is clamped, so any backlog larger than 10 mm discharges in the
taper — the "end bump is an I-term stall" memory is this.
Dedupe ⟲: `pid-error-uses-a-stale-velocity-sample-after-an-encoder-fault.md`
(open) — corrected mechanism, cross-reference.

### MK-04 — MAJOR: jerk is not bounded where it matters

- **Start.** `startSegment()` seeds the scale at 0.25 (legacy) or the
  taper floor (shaped) and the kernel raises anything below 70 mm/s to
  70: the first tick is a step to max(70 mm/s, 25 % cruise). MEASURED
  (E1): 2932 mm/s² at cruise 100/200, 4167 at 400, in *every* mode
  including `jerk = 4000` — the jerk limiter starts from a scale that is
  already a quarter of cruise.
- **End.** A staged neutral from the crawl. Profile-exit (E9) ends from
  54-64 mm/s instead of 70 and calls that a glide.
- **Continuous drive.** `wheelsV()` hands the step straight to the kernel
  (E7: 0 → 200 mm/s in one tick). Shaping exists only inside the move
  engine's scale multiplier.
- **Port.** `slewRate_` 25 %/tick ≈ 1040 %/s.
- **Legacy taper** demands decel ∝ v²: MEASURED 1559 mm/s² at cruise 200,
  **6058 at 400** (shaped: 553/534); with 80 ms lag the legacy cruise-400
  leg overshoots +5.6 mm, shaped −0.6.

Recommendation: one velocity-setpoint rate limiter (accel, optionally
jerk) in the kernel's command path, so `drive()` from any caller is
shaped once; then `serviceMove()`'s ramp/jerk block deletes and the taper
only decides when to start braking. Let the taper reach zero and end the
move predictively (MK-01) instead of holding a floor and dropping it.
Dedupe: `moves-crawl-and-correct-instead-of-gliding-to-a-stop.md` and
`dist-taper-ceiling-...` (both done) cover the taper's tail only.

### MK-05 — MINOR: two floors in two objects; the engine's is inert

`distFloor_` 0.25 / `turnFloor_` 0.12 sit below the kernel's 70 mm/s for
any cruise under 280 mm/s (583 for turns), so `SET dist_floor`,
`setTaperFloors()` and `test.ts`'s two profiles (25/12 vs 45/35) change
nothing at tour speeds. MEASURED (E3b): turning `vMin` off changes a
cruise-100 pivot from 48 to 64 ticks and from +0.22° to −0.23°. One floor,
per axis, in axis units.

### MK-06/07/08 — MINOR

Shaped mode is opt-in and only `tools/field_dance.py` opts in; blocks,
`test.ts` and the wire default run legacy (MK-06). Completion margins
(4/10 counts) are below one tick of crawl (21 counts): they test "have we
crossed", not "have we arrived" (MK-07). Distance completion is unsigned;
only yaw has a wrong-way check (MK-08).

### Where accuracy goes, ranked

1. Pivot end latency (MK-01) — ~+2° per pivot, calibrated away per robot.
2. Twist-hold vs floor in every crawl (MK-02) — hardware magnitude unknown.
3. I-term overspeed after every ramp, backlog discharge in every taper (MK-03).
4. Legacy taper above ~250 mm/s (MK-04); shaped fixes it, nobody runs shaped.
5. `fullDutyVelocity` 10795 is inherited, not measured (filed:
   `measure-vevov-s-true-full-duty-velocity.md`); above ~250 mm/s the I
   term pins and speed is not reached.
6. Reversal dwell asymmetry: after a pivot, the wheel that reversed is
   held at 0 for 100 ms while the other starts (`nezha_port.cpp:293-303`).
   MEASURED (E8) the ideal model's twist servo absorbs it (≈1 mm, 0.1°);
   hardware UNVERIFIED — one look at `dutl/dutr` on the four ticks after a
   pivot settles it.
7. `goTo`'s pivot ignores "set default turn rate" and runs at the linear
   cruise (≈143°/s at the 15 cm/s default) — BT-08.

---

## 2. Races and the bus

### RC-01 — MAJOR: the one-fiber I2C invariant is enforced nowhere

Four independent holes, one rule. `tickDrive()` serialises `kernel.step()`
behind `stepBusy` and *waits* if another fiber holds it
(`shims.cpp:647-650`). Nothing else does.

| hole | who | evidence |
|---|---|---|
| a. Every OTOS shim entry (`otosBegin/Read/Zero/Calibrate/SetOffset`, `seedPose`) issues I2C with no `stepBusy` check | any fiber | `shims.cpp:1401-1435,1519-1527`; `otos_port.cpp:116-127` — (MK annex RC-01) |
| b. `SET rebase` → `otosRef().setPose()` on the protocol fiber; its gate (`hasLiveMotionObligation() \|\| engineMoveActive()`) misses a student's `setWheelSpeeds` + `driveTick` loop on another fiber | protocol fiber vs main fiber | `wire_adapter.cpp:882-885`; `shims.cpp:1122-1130` — CM-03 |
| c. `test.ts:808-813` runs `readWorld()` at 10 Hz in `control.inBackground` while the job fiber ticks | sampler fiber vs job fiber | BT-04 |
| d. The `start drive` block forks a background ticker; `read world position`, `set world pose`, `calibrate world sensor` next to it in the palette are live bus transactions on the main fiber | student program | `motion.ts:178-186`; BT-05 |

Concrete scenario for (a): a student `goToWorld()` on the main fiber
while a bench host has a `MOVE_X` live on the protocol fiber; the
protocol fiber is parked in `step()`'s 4 ms settle after
`left_.requestSample()`; the main fiber's `readWorld()` writes 0x17; the
protocol fiber wakes and reads a destroyed encoder sample (the Phase-F
signature `nezha_port.cpp:376-380` documents). Sprint 028 closed the
RUN-handler case by moving jobs onto the protocol fiber; (a)-(d) remain.

Remedy: one bus-ownership object — promote `stepBusy` to a guard with
`acquire()` that sleeps while held — taken by `tickDrive()` *and* by every
OTOS entry, three lines each; make `rebase`'s OTOS write deferred to the
ticking fiber (as `kernel.rebasePosition()` already is); move `test.ts`'s
sampler into the job's tick loop; have `startDrive`'s loop own the OTOS
read. Then the invariant is structural.
Dedupe: `i2c-fault-count-climbs-on-idle-bus.md` (open) is a symptom this
could feed; the collision itself is not filed.

### CM-01 — MAJOR: the tick service hook runs the wire dispatcher on whatever fiber ticks

`serviceHookEntry()` (`protocol.cpp:342-345`) gates on `motionOwner_ ==
kJob`, not on fiber identity, and `tickDrive()` fires it on every call
from any fiber. Scenario from the shipped test program: a `RUN:tour` job
is running on the protocol fiber; the operator presses button B
(`test.ts:534-536` → `tourWorld()` on a MessageBus fiber, `while
(driveTick())`). Each of that fiber's ticks now runs `serviceOnce()` →
`wireHandler_.feed()` → `dispatch()`, which sends the ack (a yielding
serial write) and *then* executes `fields[]` — pointers into
`lineBuf_`. The other fiber's `serviceOnce()` feeds the next line into
the same buffer during that yield, and the parked fiber executes a motion
verb with the new line's digits. `stepBusy` still serialises `step()`;
this corrupts the wire layer, not the bus. Remedy: compare the current
fiber against one captured in `run()`. The block program's fiber is in
general a third executor `motionOwner_` does not arbitrate (a block
`move` silently supersedes a live wire move and the wire's completion
resolves off the student's move — RC-03); decide whether it is refused
or owned.

### CM-02 — MAJOR: natural completion clears the obligation only when a host asks

`resolvePendingIfDue()` now clears `motionObligationActive_` (08-26 C-05),
but it is reached only from `lastDone()`/`lastDoneReason()`, i.e. from
`replyAck`/`replyNack`/`STATUS`. A host that sends `MOVE_X … 30000 #7`
and then a cleartext `RUN:tour` sees the job refused for the remaining
27 s while the kernel is stepped the whole time (`protocol.cpp:311,553`).
Remedy: resolve on the fiber loop (`hasLiveMotionObligation()` calls
`resolvePendingIfDue()` first). Dedupe: C-05 residual;
`i2c-fault-count-climbs-on-idle-bus.md` cross-reference.

### Other race/bus findings

- **RC-02 MINOR** — the cross-fiber stop (`deliverStopNow()`, watchdog)
  is a Phase-F write by design; a destroyed sample reads raw 0 and the
  glitch armor only rejects `|Δ| > 5000`, so within ~40 cm of the
  counter's zero a raw 0 is accepted as real motion and odometry
  teleports there and back. Reject `raw == 0` explicitly.
- **RC-04 / CM-09 SUGGESTION (UNVERIFIED)** — the protocol fiber now hosts
  the whole TS job call chain; `execRun()` commits ~750 B of locals before
  the adapter can refuse; this fiber has a measured 2 KB overflow history.
  Measure the high-water mark; move `execRun()`'s buffers below its early
  returns.
- **BT-02 MAJOR** — RUN handlers run *on* the protocol fiber since sprint
  028, so every `basic.showNumber` (750 ms), `showString`, `pause(400)`
  and `otosBegin()`'s ≤1.5 s wait in `test.ts` leaves PING/ESTOP/abort
  unserviced; `run.ts:72-75` and `test.ts:543-549` still say handlers have
  their own fiber. Latency, not a safety bypass (the robot is at rest at
  every such site), hence Major.
- **BT-03 MAJOR** — a nested `abort`/`clearestop` dispatch overwrites the
  shared `runParts`; `runArg()` stays correct only by an unstated
  "read args before your first tick" rule that `run.ts` neither documents
  nor enforces. Snapshot arguments per dispatch.

What held up: seqlocks; `stepBusy` check-and-set; emit/run rings;
radio RX single-slot handoff; tokenizer and field-parser bounds;
signed-difference clock idioms; ESTOP ordering; telemetry built once per
tick; every yield in `src/comms/` through the VFP guard; `ensure()`
re-entrancy is filed and `otosRef()`/`protocol()` do not share it.

---

## 3. Correctness (other)

| ID | Sev | Finding |
|---|---|---|
| BT-01 | Major | `aborted` (`test.ts:59`) is reset only by the eight tours; after any `RUN:abort`, every `RUN:pivot`/`straight`/`face`/`cal`/`arc` stops after one tick and emits a normal `*:end` — an instrument fault that looks like a 99 % under-rotation. Reset it in one shared job entry |
| CM-04 | Major | `TLM NOW` acks `kOk` and emits nothing (`wire_adapter.cpp:924-934`); no one-shot path exists. Implement or refuse `kUnimplemented` |
| BT-06 | Major | Simulator blends every `(distance, yaw)`; hardware splits at 50° (`motion_engine.cpp:393`). `move 47 cm turning 90°` ends 30 cm forward/30 cm left in the browser and 0 forward/47 cm left on the robot |
| BT-07 | Major | The five 2026-09-01 tours and `leverCal` set no shaping profile (inherit 40 cm/s + 180 ms ramp after `RUN:goto`) and emit no `TOUR:end:<reason>` — regression of 08-26 C-12 and half of C-08 |
| CM-07 | Minor | `emitHeader()`/`emitFrame()` drop the `\n` at 239 bytes and both sinks strip the last byte blind → a plausible wrong number; the pinned pathological FULL frame is exactly 239 bytes. C-10's twin |
| CM-06 | Minor | One inbound line per transport per pass (= per 24 ms tick during a job); serial ring overflow and the radio single-slot drop are silent; `rxFrames_`/`rxAccepted_` never increment |
| CM-08 | Minor | `handleRun()` drops overlong/non-printable/empty-name payloads uncounted; the 400 ms dedupe also eats a repeated `abort` |
| BT-08 | Minor | "set default turn rate … for move/goTo" is false for `goTo` (pivot at linear cruise) |
| BT-09/10 | Minor | C-15 still open (unmarked `OCAL:` after a failed read); `goToWorld` discards `readWorld()`'s return and plans from a stale cache |
| BT-11 | Minor | `RUN:abort` cannot interrupt a `goToWorld` leg; since sprint 028 a `stopMove()` in the abort handler would make abort universal |
| BT-22 | Minor | `runArg()` maps a typo to 0: `RUN:circle:abc` pivots in place eight times |
| CM-15/16 | Suggestion | `expectedNext_` wraps at `UINT32_MAX` (theoretical); `GET rebase` answers "unknown name" for an advertised field |

Prior-review status (08-26): C-01/02/03/04/07/10/11/14, Q-01, Q-07 —
**fixed**; C-05, C-08, C-12, Q-05 — **partially fixed** (CM-02, BT-01/07/11,
Q-05's two unlinked constants); C-15, Q-04 — **still open**. Full table
in the blocks and comms annexes.

---

## 4. Cohesion and simplification

The pattern across all four annexes: state that belongs to one thing is
held by two or three, and the compensating logic is copied to each holder.

### CO-01 — `serviceMove()` is two profilers braided together

`motion_engine.cpp:500-862`: legacy/shaped forks at five sites, a jerk
integrator, a profile-exit test, the handoff, the rebase guard, the
terminator; thirteen shaping knobs, five inert at tour speeds (MK-05),
four nobody sets. Extract a `Profile` (`scale = advance(remainDist,
remainYaw, dt)`, `done()`) with `LegacyTaper` and `TrapezoidProfile` as
the two implementations, chosen once at construction. MK-04's kernel
slew removes the ramp half of both.

### CO-02 — the engine papers over two kernel API gaps

The rebase-epoch guard is written in `odomUpdate()`, `serviceMove()` and
`progress()`; the pivot→straight handoff burns a tick
(`awaitingHandoffNeutral`) because the twist-hold reference disarms only
on a neutral step. One `rearmReferences()` on the kernel (immediate, no
motor write) retires the flag and lets `rebasePosition()` be synchronous
from the engine's side, deleting all three copies.

### CO-03 — odometry is not an object

`Rig` holds `x/y/heading`, `odomPos*`, `odomPrimed`, two epochs;
`odomUpdate()` is a free function; `EncoderPoseSource` holds `const
float&` into `Rig` with a 45-line lifetime essay; `resetPose()`,
`seedPose()` and `SET rebase` are three writers with three different
pre-steps; `poseX()` mutates it as a side effect of reading. An
`Odometry` class that *is* the `PoseSource` retires the adapter, the
essay and one epoch copy. 08-26 Q-02 asked for this; sprint 028 made it
more urgent.

### CO-04..07 and the comms/blocks equivalents

- Four copies of the soft-stop triplet (`stopAll`, `endMove`, watchdog,
  `updateMove`) → one `softStop()`; `stop` and `stop move` are now the
  same operation with two blocks (BT-15).
- Five hand-synchronised ordinal tables (`setKernelValue` ×34,
  `getConfigValue` ×34, `kFields`, `ConfigField`, `diagValue` ×30) → one
  descriptor table; this is also what makes the "ordinal 30" comment
  error (CH-02) impossible.
- `pendingGoToDeadlineMs_` is per-call state on the singleton to dodge a
  4-argument shim limit (CO-06).
- `Protocol` carries a separable `RunBridge` (dedupe, ring, bypass,
  current-text, dispatch — CM-13), three scattered radio gates that
  belong on `RadioTransport` (CM-11), copy-pair serial/radio poll branches
  and two identical sinks (CM-12), and `motionOwner_`/`jobOwnsMotion_`
  storing one fact twice (CM-14).
- The transports' two-writer guards and retries are vestigial since the
  emit ring made the protocol fiber the sole producer; their comments
  still describe a TS-fiber writer (CM-05).
- Three copies of the tick runner in TS (`move`/`goTo`, `world.ts`,
  `test.ts`), two of which differ on `_endMove()` (BT-13);
  `turnFirstDeg` is a `let` nothing writes and arrival tolerance gates
  one block of two (BT-14); `cycleStat` is dead shim surface (BT-23).
- The kernel is "byte-identical to upstream except `cycleGapCount`" and
  MK-02, MK-03 and CO-02 all need kernel edits. Decide whether this repo
  owns the fork (CO-07).

---

## 5. Comments

### The numbers

Comment-only lines per code line, non-blank, this pass:

| file | ratio | | file | ratio |
|---|---|---|---|---|
| `comms/radio_transport.h` | **7.26** | | `comms/protocol.cpp` | 1.55 |
| `comms/serial_transport.h` | 5.63 | | `shims.cpp` | 1.47 |
| `comms/wire_adapter.h` | 4.98 | | `comms/wire_adapter.cpp` | 1.29 |
| `motion/motion_engine.h` | **4.30** | | `motion/motion_engine.cpp` | 1.05 |
| `platform/encoder_pose_source.h` | 4.10 | | `platform/nezha_port.cpp` | 0.96 |
| `comms/protocol.h` | **3.72** | | `blocks/*.ts` | 1.58 |
| `comms/wire_handler.h` | 2.47 | | `core/diffdrive.cpp` | **0.03** |

Project-owned `src/` was 1.22 on 08-26; it is ~1.4 now, and every file
sprints 026-028 touched grew. The archaeology ratchet (`_BUDGET = 388`)
holds the sprint/ticket-ID *count*; the new comments cite dates and
capture paths instead and are just as long. Two new anti-patterns join
the five in `guidelines.md`:

6. **Dated UPDATE paragraphs stacked on a comment** (`nezha_port.cpp:11-55`
   has the original forensics plus two dated updates; the third reader
   has to reconcile all three to learn "it was the VFP clobber, fixed").
7. **Citations to untracked artifacts** (CH-03): six `captures/…`
   directories cited as MEASURED from `src/` are gitignored and untracked;
   a clone cannot follow them. Track them or move the number into a
   tracked `reports/*.md`.

### Comments that are wrong today (fix the text; no rewrite needed)

| where | says | actually |
|---|---|---|
| `diffdrive.h:1-3`, `diffdrive.cpp:1` | `differential_drive.{h,cpp}` | files are `diffdrive.{h,cpp}` |
| `protocol.h:281`, `src/DESIGN.md:832` | RUN drop count is "ordinal 30" | `shims.cpp:978` — 28; 30 is `max_yaw_rate` |
| `motion_engine.h:768-787` | `vMaxMmS_`/`brakeFrac_` "not consulted by anything yet" | `defaultCruiseForDistance()` reads both |
| `motion_engine.h:69-73`, `src/DESIGN.md:1161` | goToWorld is a "capped-curvature" path | cap removed; routes through `goToR` |
| `shims.cpp:9-14` | "MOVE ENGINE … lives HERE" | moved to `motion_engine.cpp` |
| `nezha_port.h:107-118` | streaks "exposed via ordinal 27" | 21/22; 27 is the rebaseline sum |
| `run.ts:1-5, 72-75`; `test.ts:543-549` | handlers "run on their own fiber", "MessageBus delivers … one at a time" | they run on the protocol fiber, nested (sprint 028) |
| `test.ts:759-789` | "ANY I2C from a RUN handler hangs the board" | the same file's handlers do OTOS I2C on every corner |
| `radio_transport.h:363` | `Protocol::formatDiag()` | no such function (flagged 08-26, still there) |
| `wire_adapter.h:320-324`, `run_queue.h:13-21`, `emit_queue.h:15-19` | "MessageBus RUN bridge / runSlots_ / listener receives an integer" | `runQueue_` + `dispatchJob()` on the same fiber |
| `serial_transport.h:71-92`, `radio_transport.h:77-89,319-322`, `protocol.h:361-367`, `DESIGN.md §6` | "two fibers call this — the TS fiber via emitLine()" | one fiber since the emit ring |
| `wire_handler.cpp:912-913` | `kVersion` "1.0.10", drift-tested against pxt.json | `"unbaked"`, and the test asserts it is *not* pxt.json's |
| `DESIGN.md §8` | "3 s same-text dedupe" | 400 ms |
| `test.ts:47-49`; `run.ts:117-134` | tovez ch 3, vevov ch 4, "group 10" | 55/108, 37/43; both channel and group are deploy-injected |
| `test.ts:106-109` | cites a link-hang issue as live | closed in sprint 027 |
| `world.ts:9` | "every read here is a live I2C burst" | `worldX/Y/Heading` are cache reads |

### CH-04 — MINOR (stakeholder direction 2026-09-03, fix this round): units in identifier names

The house style is the kernel's — a bare name and a trailing `// [unit]`
comment (`float velocity; // [counts/s]`). Project-owned `src/` drifted
into unit suffixes, and the rule is now written down
(`.claude/rules/no-units-in-identifiers.md`). Inventory of the
project-owned offenders (occurrence counts across `src/`, vendored kernel
and conversion-named functions such as `mradToRad`/`countsPerMm`/
`writePoseMm` excluded):

| identifier | uses | identifier | uses |
|---|---|---|---|
| `nowMs` / `nowMs_` / `wireNowMs` | 78 | `engineDefaultCruiseMmS` / `resolveDefaultCruiseMmS` / `defaultCruiseMmS_` | 36 |
| `aDecelMmS2_` / `aDecelMmS2` / `engineADecelMmS2` | 57 | `timeoutMs` / `durationMs` / `deadlineUs` / `startMs` / `lastTickMs` | 70 |
| `distanceMm` / `rotationRad` / `yawRad` / `omegaRad` / `angleRad` | 69 | `aAccelMmS2_` / `jerkMmS3_` / `vMaxMmS_` / `profileExitMmS_` / `rampMs_` / `pivotOverrunMm_` / `maxYawRateDegS_` | 63 |
| `cruiseMmS` / `speedMmS` / `twistMmS` / `axisCruiseMmS` / `remainMm` / `windowMm` | 42 | `motionObligationDeadlineMs_` / `pendingGoToDeadlineMs_` / `lastRunMs_` / `lastEmitMs_` / `lastTickUs_` / `tickDeadlineUs` | 34 |
| `distTargetCounts` / `yawTargetCounts` / `cruiseCounts` / `stopCounts` / `remainCounts` / `yawCounts` | 28 | `simMoveRemainMm` / `simMoveRemainRad` / `simTickDeadlineMs` / `turnPct` / `lastWrittenPct_` / `dMm` / `dRad` | 42 |

About 520 occurrences over `motion/`, `shims.cpp`, `comms/wire_adapter.*`,
`comms/protocol.*`, `blocks/sim.ts`, `blocks/motion.ts`. Mechanical, but
each rename must land with its `// [unit]` comment or the unit is lost
rather than moved. The motion-profile design (`docs/design/
motion-profile-unification.md`) renames the `motion/` set as part of its
ticket 3; the rest is its own ticket (triage #24).

### Boil-down work order

Forty blocks with a replacement each, in the annexes: 18 in
[motion-and-kernel](raw/motion-and-kernel.md#boil-down-list-my-scope-replacement-text-is-the-whole-comment)
(`motion_engine.h` header 120 → 5 lines; `settleToRest` 55 → 3;
`nezha_port.cpp` bus-hang essay 38 → 3; `shims.cpp` `tickDrive` 30 → 8;
`protocol.h` executor block 85 → 20; …), 12 in
[comms](raw/comms.md#comment-boil-down-list) (`protocol.cpp` identity 62
→ 4; `radio_transport.h` addressing 41 → 3; three dispatch essays → one
block; …), 10 in [blocks-and-test](raw/blocks-and-test.md#comment-boil-down-worst-ten-plus-factual-errors)
(the TS9200 story told twice; six copies of "an empty body crashes the
simulator" → one note; …). Applying them is the same shape of ticket
sprint 009 ran, with the same caveat the guidelines already record:
re-anchor by content, treat every item as a possible no-op, and check
each replacement against the *current* code before landing it.

---

## 6. Tools and tests

**Baseline**: `uv run pytest -q` → **922 passed, 1 failed** (149 s). The
failure is `test_typescript_typecheck.py::test_tsc_noemit_is_clean` —
`node_modules/.bin/tsc` is absent in this worktree (no `npm install`), an
environment precondition surfacing as a red test (TL-19). `ruff check
tools tests` → 5 findings, all in `tests/dev/` and `tests/system/`.

### TL-02 — CRITICAL: two calibrations of record for tag 53, and `Cam()` re-registers the stale one into the daemon's persistent registry on every start

`tools/camlink.py:55` carries `MOUNTS[53] = (-3.61, -0.05, 11.8, -π/2)`;
`Cam.__init__` → `ensure_registered()` (`:80-96`) sends every entry to the
daemon with `register_tag()` unconditionally. Mount registrations now
persist in the daemon (`state_dir/mounts/registry.json`, agent guide §6)
— so this is not "cheap idempotent insurance" as the docstring says; it
is an overwrite. `tools/field_calibration.json` (MEASURED vevov
2026-09-02, after the tag-53 remount) holds a different lever, and
`field_dance.py` assumes the raw tag. Whichever camproc tool ran last
decides what the daemon reports as vevov's centre, silently, and the
2026-08-31 rails crash was a pose-convention disagreement of exactly
this shape. Remedy: one calibration of record (`field_calibration.json`),
`camlink` reads it and never registers a mount it did not load, and
registration is explicit (`--register`), not a constructor side effect.
Dedupe: `camlink-mounts-table-is-stale-for-tigez.md` (sprint 027, done)
fixed tag 57 the same way tag 53 has now gone stale; not filed for 53.

### TL-01 — MAJOR (annex says Critical): `robotlink.py` tunes the relay to vevov's retired address

`tools/robotlink.py:21-22` `ZAVAZ_CHANNEL = 4`, `ZAVAZ_GROUP = 10`; vevov
migrated to 37/43 on 2026-08-30 (`playfield-testing.md`,
`field_calibration.json:radio_channel/group`). Every `open_link(radio=True)`
tool tunes the relay at nothing and presents as a silent robot — the
misdiagnosis the playfield rules exist to prevent. `test_robotlink.py:183`
pins the stale constant. Derive from the board name (the relay's `!N`)
or read `field_calibration.json`.

### Other tools findings

| ID | Sev | Finding |
|---|---|---|
| TL-03 | Major | `rotation_check.py:108-109`, `truth_check.py:120-124`: `total_turn()` cannot resolve a ±180° pivot that over-rotates (`round(0.5) = 0`), so 183° physical reads −177° and the ratio flips sign |
| TL-04 | Major | `robotlink.py:120-123` `_V6_VERBS` names `MOVE/PIVOT/GO_TO/ARC` (not firmware verbs) and omits `MOVE_X/MOVE_V/GO_TO_R`; a `MOVE_X` through `Link` gets no `#id` and is silently dropped |
| TL-05 | Major | The geofence (08-26 D-08) exists in `field.py:42-85` with zero callers; `tour_run.place()`, `Repositioner.go()`, `tour_closedloop` drive unchecked; a second, different field size lives in `test_run_tour_programs.py:171-172` |
| TL-06 | Major | Three pose-CSV schemas (mm/cdeg vs cm/deg) across `tour_capture`/`tour_watch`/`tour_practice`, and `tour_chart.py:107-121` picks a reader by column count — a `tour_watch` CSV plots 10× small with no error |
| TL-07 | Major | 08-26 Q-06/Q-09 still open and their premise is gone: `aprilcam[daemon]` is a dependency of this venv and imports under `uv run`, so `camproc.py`'s subprocess-into-a-second-venv and the second `Cam` have no remaining reason |
| TL-08 | Major | 08-26 C-16 still open: `score_corners()`'s first corner searches the whole run and can starve every later corner |
| TL-09 | Major | `truth_check.py:35-69` is dead on arrival: shells `aprilcam tool get_tags` against a hard-coded `127.0.0.1:5280` and reads v1 JSON keys; duplicates `pivot_truth.py` |
| TL-10 | Minor | `leg_analysis.py:237-243` labels a heading-only miss as overrun/truncation by the sign of a sub-tolerance distance error |
| TL-11 | Minor | `field_calibration.json` stores the fixed +90° convention as a probe-fitted 91.116° — the recurrence `tag-yaw-is-the-front-edge-not-the-hat.md` forbids; store the sub-degree residual only |
| TL-12/13/14 | Minor | Four `wrap()` implementations (two with different boundary semantics); the link layer written four times with three relay addresses and two sequence-id implementations; two repositioning loops, one documenting an ordering bug the other still has |
| TL-15/16 | Minor | Five tools kept "for reference" but still executable on the stale relay address; `tools/DESIGN.md` omits 11 of 30 tools and cites a section that does not exist |
| TL-17/18 | Minor | `tour_chart --meta` reads `start_world_cm[2]` as radians and nothing writes it; `test_make_deploy_robot_channel.py` test names assert "vevov is channel 4" beside a table saying (37, 43) |
| TL-19 | Minor | Host harness: seven `pxt.h`-bound TUs compiled by nothing; the C++11 gate passes `-I src` the real build lacks; Python mirrors of `shims.cpp` under test; one assert-less test; 11 identical `motion_lib` compiles per session; the tsc gate is an environment precondition; `run_tour.py`'s travelCalib mirror unpinned; ruff not gated |
| TL-20..25 | Suggestion | `duty_pct()` tested, uncalled; `field_dance.settle()` degrades to a fixed wait if the record has no `speed`; `seqd()` truthy on `err N`; `probe_port` ≈ 4 min worst case; `t_cut` mixes device and host clocks; `rotation_check` prints a conclusion scaled by the retired 1.040 |

Prior status: D-05 (travelCalib in two tools) **fixed**; Q-08 (ruff config)
**fixed**; D-08 **partial** (functions exist, unwired); C-16, Q-06, Q-09
**still open**. Thirteen comment-block replacements in the annex.

---

## Proposed issues for triage

Grouped so each is one ticket-sized change; ⟲ marks a correction to an
already-open issue rather than a new one.

| # | Issue | Covers | Priority |
|---|---|---|---|
| 1 | Enforce the one-fiber I2C invariant: bus guard on every OTOS entry, deferred `rebase` write, sampler into the job loop, `startDrive` owns the OTOS read | RC-01, CM-03, BT-04, BT-05 | **Critical** |
| 2 | Service hook must check fiber identity; decide the block fiber's place in `motionOwner_` | CM-01, RC-03 | **High** |
| 3 | Pivot end: predictive termination + a yaw-unit floor; retire `pivot_overrun` as a calibration constant — design: [motion-profile-unification.md](../../design/motion-profile-unification.md) | MK-01, MK-05, MK-07 | **High** |
| 4 | Kernel: twist-hold reference from the post-floor twist; freeze the position reference on a stale tick; clamp the reference (anti-windup) ⟲ corrects `pid-error-uses-a-stale-velocity-sample…` | MK-02, MK-03 | **High** |
| 5 | One setpoint slew in the kernel; shaped profile by default or delete legacy; `Profile` object out of `serviceMove()` | MK-04, MK-06, CO-01 | High |
| 6 | Clear the motion obligation on the fiber loop; `TLM NOW` implement-or-refuse | CM-02, CM-04 | High |
| 7 | `test.ts`: one `beginJob()`/`endTour()` (resets `aborted`, applies a profile, emits `TOUR:end:<reason>`); abort calls `stopMove()`; non-blocking display; typo-safe args | BT-01, BT-07, BT-11, BT-02 (test half), BT-22 | High |
| 8 | RUN dispatch contract: per-dispatch argument snapshot; JSDoc for "handlers run on the wire's fiber" | BT-02 (API half), BT-03 | Med |
| 9 | Simulator: mirror the 50° split, drift-test sim geometry, honour `_setGeometry` | BT-06, BT-20 | Med |
| 10 | Odometry object; `rearmReferences()` on the kernel; delete the three epoch copies | CO-02, CO-03 | Med |
| 11 | Config/diag descriptor table replacing five ordinal switches; `softStop()`; go-to deadline as a config field | CO-04, CO-05, CO-06 | Med |
| 12 | `Protocol` diet: `RunBridge`, radio enable on the transport, `routeLine()`, one sink, one owner flag; delete vestigial two-writer guards | CM-05, CM-11..14 | Med |
| 13 | Wire minors: telemetry terminator reserve + sink strip check, drain loop + RX counters, count `handleRun` refusals, seq wrap, `GET rebase` | CM-06..08, CM-15, CM-16 | Low |
| 14 | Comment work order (40 blocks) + 16 factual fixes + track or relocate the six untracked capture citations; extend the ratchet to measure volume | CH-01..03, CM-10, BT-16..19 | Med |
| 15 | Decide the kernel fork question (byte-identical rule vs owning MK-02/03/CO-02 locally) | CO-07 | Med |
| 16 | Glitch armor: reject `raw == 0` explicitly; prefer staged over cross-fiber stop when `stepBusy` | RC-02 | Low |
| 17 | Measure the protocol fiber's stack high-water mark under a tour; move `execRun()` buffers below its early returns | RC-04, CM-09 | Low |
| 18 | `goTo` pivot honours the default turn rate; arrival tolerance applies to both go-to blocks; one tick runner; delete `cycleStat`; one stop block | BT-08, BT-13..15, BT-23 | Low |
| 19 | One calibration of record: `camlink` reads `field_calibration.json`, never re-registers a stale mount over the daemon's registry; `robotlink` derives the relay address from the board name; store only the sub-degree heading residual | TL-01, TL-02, TL-11 | **Critical** |
| 20 | `_V6_VERBS` drift-tested against the firmware verb table; geofence wired into every driving tool; one pose-CSV schema | TL-04, TL-05, TL-06 | High |
| 21 | Analysis fixes: `total_turn()` ±180° wrap, `score_corners` window, heading-only miss label, retired-constant print | TL-03, TL-08, TL-10, TL-25 | Med |
| 22 | Tools consolidation: in-process aprilcam (drop the subprocess and the second `Cam`), one `wrap()`, one link layer, one repositioner, delete dead tools, `tools/DESIGN.md` truth pass | TL-07, TL-09, TL-12..18 | Med |
| 23 | Host harness: tsc gate skips with a reason when `node_modules` is absent, pin the `run_tour` travelCalib mirror, gate ruff, session-scope `motion_lib`, compile the seven uncovered TUs or say why not | TL-19 | Low |
| 24 | **This round (stakeholder, 2026-09-03):** strip units from identifier names across project-owned `src/` per `.claude/rules/no-units-in-identifiers.md`, landing each rename with its `// [unit]` comment; `motion/` goes with design ticket 3, the rest (`shims.cpp`, `comms/`, `blocks/`) here; add a source-pin test that fails on a new `MmS`/`Ms`/`Us`/`Mm`/`Rad`/`Deg`/`Counts`/`Pct` suffix outside the vendored kernel | CH-04 | Med |

---

## Appendix — the document set

| File | What it carries |
|---|---|
| `review.md` | this consolidated report |
| [`raw/motion-and-kernel.md`](raw/motion-and-kernel.md) | MK-01..08, RC-01..04, CO-01..07, CH-01..03 — the algorithm review with every measurement, the yield-point reasoning, the cohesion proposals, 18-item boil-down list |
| [`raw/comms.md`](raw/comms.md) | CM-01..16 — yield-point inventory for `src/comms/`, 14-item what-held-up, 12-item boil-down list |
| [`raw/blocks-and-test.md`](raw/blocks-and-test.md) | BT-01..23 — prior-findings status table, 10-item boil-down list |
| [`raw/tools-and-tests.md`](raw/tools-and-tests.md) | TL-* — tools, host harness, baseline test count |
| [`raw/profile_probe.cpp`](raw/profile_probe.cpp) / [`.out`](raw/profile_probe.out) | the measurement behind every MK claim: real kernel + engine, fake ports, ideal and lagged wheels, dwell emulation, frozen-tick injection |

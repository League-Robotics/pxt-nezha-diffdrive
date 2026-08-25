---
source_file: src-root-DESIGN.md
source_hash: 3a07cea091cf39d4e3ec1a12d961a9288240c3391715fd88f8a5168f03718e55
---

# Diff: src-root-DESIGN.md

Sprint 012 (substantial/structural) split `src/main.ts` into six
cohesion-sized modules (`sim.ts`, `run.ts`, `pose.ts`, `stop.ts`,
`world.ts`, `motion.ts`); this updates §1's layer-map table, §8's RUN
bridge/Lifecycle paragraphs, and §9's "Shim + blocks" section to
describe the new six-file structure instead of a single `main.ts`
(re-attributing every existing design point to the file it now lives
in, unchanged in substance), appends a new §15 with the full sprint
record (sizing, Sprint Changes, component/dependency diagram, Migration
Concerns, Risk, Design Rationale, Open Questions), and updates the
document header's status line. No content describing sprints 006/007/008
as history is altered — only current-state descriptions that this
sprint's split makes stale are updated.

```diff
--- a/src/DESIGN.md
+++ b/src/DESIGN.md
@@ -1,6 +1,6 @@
 # src — the DiffDrive extension
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** in-flux (as-built through sprint 008, closed and merged — wire hardening and tests that can fail: timeout reject/clamp unified across all six motion verbs, `kVersion`/line-cap/`RUN_EVENT_SOURCE`/`kDiag*` single-sourced or drift-tested, the `WaHandle` test doubles re-synced to production, the post-move settle loop extracted into a host-testable `MotionEngine` helper, `TLM AUTO`/`BUFFER` given defined semantics, and a triage-aware `make_deploy.py` plus a standing per-sprint build-checkpoint-ticket convention closing the target-viability gap; sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** in-flux (as-built through sprint 008, closed and merged — wire hardening and tests that can fail: timeout reject/clamp unified across all six motion verbs, `kVersion`/line-cap/`RUN_EVENT_SOURCE`/`kDiag*` single-sourced or drift-tested, the `WaHandle` test doubles re-synced to production, the post-move settle loop extracted into a host-testable `MotionEngine` helper, `TLM AUTO`/`BUFFER` given defined semantics, and a triage-aware `make_deploy.py` plus a standing per-sprint build-checkpoint-ticket convention closing the target-viability gap; sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint; sprint 012 detail-planned — splits the single `main.ts` into six cohesion-sized modules, `sim.ts`/`run.ts`/`pose.ts`/`stop.ts`/`world.ts`/`motion.ts`, replacing `main.ts`'s one entry in `pxt.json`'s and `tsconfig.json`'s `files` arrays; behaviour-neutral by design, not yet executed — gated on sprints 006/007 (closed, satisfied) and 009 (planned, not yet executed) landing first, see §15)
 
 `src/` is flat — no subdirectories — so this one document carries the
 logical subsystem breakdown as sections. Global conventions (units
@@ -28,7 +28,7 @@
 | Transports | `serial_transport.*`, `radio_transport.*` | CODAL (`pxt.h` in the .cpp) — know bytes and framing, **nothing** about verbs, grammar, or motion |
 | Hardware ports | `nezha_port.*`, `otos_port.*`, `platform_ports.h` | `pxt.h` + the port interfaces they implement — know I2C/CODAL, nothing about blocks or the wire; `nezha_port.cpp` additionally calls into `encoder_glitch_armor.h` and `otos_port.cpp` into `heading_wrap.h`, both above (a dependency on a lower, host-portable layer, not membership in this one) |
 | Protocol composition | `protocol.h/.cpp` | everything above — the CODAL fiber that plumbs transports into the wire stack |
-| Shim + blocks | `shims.cpp`, `main.ts` | everything — the composition root and the student-facing API |
+| Shim + blocks | `shims.cpp`, `sim.ts`, `run.ts`, `pose.ts`, `stop.ts`, `world.ts`, `motion.ts` (sprint 012: split from a single `main.ts` — see §9/§15) | everything — the composition root and the student-facing API |
 
 Cross-cutting convention: `shims.cpp` has **no header**. Its C++
 callers (`protocol.cpp`, `wire_adapter.cpp`) reach it via same-package
@@ -612,11 +612,13 @@
 parks the payload in a 4-slot ring (MessageBus events queue; a
 one-minute test handler must not have its text overwritten by the next
 burst) and raises event source 0x2001 with the slot as the value;
-`main.ts` reads it back via `runCommandText()` and dispatches by name
-on the handler's own fiber. 3 s same-text dedupe absorbs hosts
-repeating commands to survive the single-slot radio buffer (measured:
-one 3×-repeated RUN ran three consecutive pivots). **Sprint 008**: the
-literal event source `0x2001` above and `main.ts`'s own
+`run.ts` reads it back via `runCommandText()` (sprint 012: this shim
+body itself lives in `sim.ts`, called cross-file — see §9/§15) and
+dispatches by name on the handler's own fiber. 3 s same-text dedupe
+absorbs hosts repeating commands to survive the single-slot radio
+buffer (measured: one 3×-repeated RUN ran three consecutive pivots).
+**Sprint 008**: the literal event source `0x2001` above and `run.ts`'s
+own (sprint 012: formerly `main.ts`'s)
 `RUN_EVENT_SOURCE = 0x2001` are two independent hand-typed copies of
 the same MessageBus event id (WIRE-01-adjacent minor, R-21) — now
 pinned by a drift test that reads both source files as text and fails
@@ -654,9 +656,14 @@
 this retries once after `fiber_sleep(2)` before giving up silently,
 not in a loop.
 
-**Lifecycle.** Lazy singleton `protocol()`, started by `main.ts`'s
-top-level `_startProtocol()` the moment the extension's compiled code
-loads — never a global constructor (uBit.init ordering). Identity
+**Lifecycle.** Lazy singleton `protocol()`, started by a top-level
+`_startProtocol()` call the moment the extension's compiled code loads
+— never a global constructor (uBit.init ordering). **Sprint 012**: the
+call site lives in `motion.ts` (formerly `main.ts`); the shim body it
+calls lives in `sim.ts`. This is the one load-time file-order
+constraint the sprint 012 split has to satisfy — `sim.ts` must be
+listed before `motion.ts` in `pxt.json`'s `files` array, or this call
+resolves to nothing the moment the namespace loads (see §15). Identity
 constants: drivetrain "diffdrive", profile "tovez", version. **Sprint
 008**: `kVersion` no longer hand-mirrors `pxt.json`'s version as a
 literal that can silently drift (it had, by ten version bumps —
@@ -679,7 +686,7 @@
 will see nothing until they are retrofit onto the new frame (sprint
 005, roadmapped, not yet detail-planned).
 
-## 9. Shim + blocks — `shims.cpp`, `main.ts`
+## 9. Shim + blocks — `shims.cpp`, `sim.ts`, `run.ts`, `pose.ts`, `stop.ts`, `world.ts`, `motion.ts`
 
 **shims.cpp** is the composition root and the MakeCode-facing C++
 surface. The lazy-singleton `Rig` composes: two `NezhaMotorPort`s
@@ -766,7 +773,7 @@
   undocumented `probe(2)`. Two thin new `shims.cpp` forwards close
   this: `clearStall()` (calls `kernel.clearStallLatch()`) and
   `isStalled()` (returns `kernel.output().stallHalted`), each reachable
-  from a dedicated `main.ts` Drive-group block (`clearStallLatch()`,
+  from a dedicated Drive-group block (`clearStallLatch()`,
   `isStalled()`) parked next to `emergencyStop()`/`clearEmergencyStop()`
   — and, on the wire, `stall_clear`'s new `kFields`/`ConfigField`
   ordinal (§5) reaches the same `clearStallLatch()` call via
@@ -832,52 +839,128 @@
   update states plainly rather than leaving the two verbs looking
   identical.
 
-**main.ts** owns the student units and the block API (groups Drive,
-Move, Pose, World, Setup), the browser-simulator fallback bodies (a
-kinematic stand-in that mirrors the tick engine's 24 ms pacing), and
-the RUN dispatcher. Notable TS-side design points, all measured the
-hard way:
+**The TypeScript side** owns the student units and the block API
+(groups Drive, Move, Pose, World, Setup), the browser-simulator
+fallback bodies (a kinematic stand-in that mirrors the tick engine's
+24 ms pacing), and the RUN dispatcher. **Sprint 012** split this out of
+a single `main.ts` into six cohesion-sized modules — see §15 for the
+full sprint record, sizing decision, and diagram. Current structure:
 
-- Continuous-mode commands (`setWheelSpeeds`/`driveTwist`) only move
-  the robot while a `while (diffDrive.driveTick())` loop ticks;
-  blocking moves tick internally. **Sprint 007**: this is now true in
-  fact, not only in prose — `driveTick()`'s return contract fix above
-  is what makes it true; the simulator's own `_tickDrive()` gets the
-  same fix (returns "does anything still look commanded" — sim move
-  active, or nonzero `simVel`/`simYawRate` — instead of raw sim
-  move-engine state) so the browser and hardware idioms match.
-  `startMove`/`startGoTo` + polling does **not** advance a move by
-  itself — a documented tick-model gap, unchanged this sprint.
-- **Sprint 007, simulator/hardware parity**: `_setWheels`' sim body
-  drops a stray `/10` in its yaw-rate term (`(right-left)/10/track`
-  → `(right-left)/track`) that made simulator turns 10× slower than
-  hardware for the same `set wheel speeds` call (R-12/BLK-06) — the
-  formula now matches `_driveTwist`'s own, already-correct sim math. A
-  new `simEstopped` flag, set in `_estopAll()` and cleared in
-  `_estopClear()`, gates `_setWheels`/`_driveTwist`/`_startMove`
-  (checked, no-op while set) — mirroring hardware's intake-time
-  refusal (`checkCommandable()`'s `estopLatch_` gate) so
+- **`motion.ts`** — the `ConfigField` enum, the two movement-default
+  `let`s (`defaultSpeed`/`defaultYawRate`) and their Setup-group
+  setters (`setDefaultSpeed`, `setDefaultYawRate`, `setTrackWidth`,
+  `setWheelCalibration`, `setConfigValue`), continuous-mode drive
+  (`setWheelSpeeds`, `driveTwist`, `driveTick` — Drive/Move groups),
+  position-mode move (`move`, `goTo`, `startMove`, `startGoTo`,
+  `isMoving`, `moveProgress`, `stopMove`, `whileMoving`,
+  `whileGoingTo` — Move group), and the namespace's one load-time
+  side-effecting statement, the top-level `_startProtocol()` call.
+- **`pose.ts`** — `poseX`, `poseY`, `heading`, `resetPose` (Pose
+  group). Reads local (encoder-odometry) pose only; never touches the
+  world/OTOS sensor.
+- **`stop.ts`** — `stop`, `emergencyStop`, `clearEmergencyStop`,
+  `isStalled`, `clearStallLatch` (Drive group). Owns the two
+  independent fault latches (e-stop, stall) and nothing else.
+- **`world.ts`** — OTOS world-pose tracking (`startWorldTracking`,
+  `worldTrackingReady`, `seedPose`, `readWorld`, `worldX`/`Y`/
+  `Heading`, `calibrateWorldSensor`, `setWorldSensorOffset`) and
+  `goToWorld` with its own tuning state (`arriveTolCm`,
+  `turnFirstDeg`) and private `tickedMove()` runner (World group).
+- **`run.ts`** — the RUN command dispatcher: the no-initialiser state
+  block (`runParts`/`runNames`/`runHandlers`/`runAnyHandlers`/
+  `runWired`), `ensureRunState()`, `RUN_EVENT_SOURCE`,
+  `wireRunDispatch()`, `onRun`/`onRunCommand` (Move group in the
+  toolbox, despite being dispatch machinery — see §15's Design
+  Rationale for why block `group=` and module boundary diverge here),
+  and the block-hidden `runArg`/`runArgText`/`runArgCount`. Fully
+  self-contained: nothing outside this file reads or writes its state.
+- **`sim.ts`** — every `//% shim=`-annotated function's TypeScript
+  body: the kinematic browser-simulator state (`simX`/`simY`/
+  `simHeading`/`simVel`/`simYawRate`/…) and its per-tick integration
+  (`simIntegrate()`), the shim bodies that give the browser real
+  motion/pose/stop behaviour (`_setWheels`, `_driveTwist`,
+  `_startMove`, `_updateMove`, `_tickDrive`, `_progress`, `_endMove`,
+  `_stopAll`, `_estopAll`, `_estopClear`, `_poseX`/`Y`/`Heading`,
+  `_resetPose`, `_seedPose`), and the no-op stand-ins for shim-only
+  surface with no browser model at all (`_clearStallLatch`,
+  `_isStalled`, `_setGeometry`, `_setKernelValue`, `_startProtocol`,
+  `probe`, `setTaperWindows`/`Floors`/`RampMs`, `otosBegin`/`Read`/
+  `Get`/`Zero`/`Calibrate`/`SetOffset`, `emitLine`, `runCommandText`).
+  The issue that proposed this split named a `sim.ts` row and a
+  separate `shims.ts` row; verified against the real file, that
+  boundary does not exist — nearly every `//% shim=` function's body
+  *is* the simulator fallback, interleaved throughout, not two
+  contiguous halves — so they are one module here (see §15).
+
+Notable design points, all measured the hard way and unchanged by the
+sprint 012 split (module attribution updated to the file each now
+lives in):
+
+- Continuous-mode commands (`setWheelSpeeds`/`driveTwist`, `motion.ts`)
+  only move the robot while a `while (diffDrive.driveTick())` loop
+  ticks; blocking moves tick internally. **Sprint 007**: this is now
+  true in fact, not only in prose — `driveTick()`'s return contract fix
+  above is what makes it true; the simulator's own `_tickDrive()`
+  (`sim.ts`) gets the same fix (returns "does anything still look
+  commanded" — sim move active, or nonzero `simVel`/`simYawRate` —
+  instead of raw sim move-engine state) so the browser and hardware
+  idioms match. `startMove`/`startGoTo` + polling does **not** advance
+  a move by itself — a documented tick-model gap, unchanged this
+  sprint.
+- **Sprint 007, simulator/hardware parity** (`sim.ts`): `_setWheels`'
+  sim body drops a stray `/10` in its yaw-rate term
+  (`(right-left)/10/track` → `(right-left)/track`) that made simulator
+  turns 10× slower than hardware for the same `set wheel speeds` call
+  (R-12/BLK-06) — the formula now matches `_driveTwist`'s own,
+  already-correct sim math. A `simEstopped` flag, set in `_estopAll()`
+  and cleared in `_estopClear()`, gates `_setWheels`/`_driveTwist`/
+  `_startMove` (checked, no-op while set) — mirroring hardware's
+  intake-time refusal (`checkCommandable()`'s `estopLatch_` gate) so
   `emergency stop` now refuses further motion in the browser exactly
   as it does on hardware (R-13/BLK-07); previously the simulator
   refused nothing, so the UC-011 "forgot to clear" trap was invisible
   exactly where students develop.
-- **Sprint 007**: `runArgCount()` gains the null guard its sibling
-  `runArgText()` already had (`if (!runParts) return 0`) — closing
-  R-15/BLK-02, a documented silent-boot-death (panic 980) class for any
-  call before the first RUN event registers a handler.
-- `goToWorld()` is this project's own TS-level closed-loop heuristic
-  (one pass, pivot-first beyond 12°, curvature capped at 25°,
-  residual error inherited by the next hop) — deliberately a separate
-  call path from the wire's GO_TO_W/`MotionEngine::goToR` plain
-  reduction. The OTOS is read here, between moves only.
-- The `run*` state arrays are declared **with no initialisers** —
-  namespace initialisers run after a test file's top-level code, so an
-  initialiser both crashes early registration (silent boot death,
-  panic 980) and would wipe handlers already registered.
+- **Sprint 007**: `runArgCount()` (`run.ts`) gains the null guard its
+  sibling `runArgText()` already had (`if (!runParts) return 0`) —
+  closing R-15/BLK-02, a documented silent-boot-death (panic 980) class
+  for any call before the first RUN event registers a handler.
+- `goToWorld()` (`world.ts`) is this project's own TS-level closed-loop
+  heuristic (one pass, pivot-first beyond 12°, curvature capped at
+  25°, residual error inherited by the next hop) — deliberately a
+  separate call path from the wire's GO_TO_W/`MotionEngine::goToR`
+  plain reduction. The OTOS is read here, between moves only.
+- The `run*` state arrays (`run.ts`) are declared **with no
+  initialisers** — namespace initialisers run after a test file's
+  top-level code, so an initialiser both crashes early registration
+  (silent boot death, panic 980) and would wipe handlers already
+  registered. **Sprint 012 preserves this verbatim** — it does not
+  become the split's file-order problem (see below); it is a
+  same-file, self-contained pattern regardless of which file `run.ts`'s
+  content lives in.
 - PXT traps pinned in comments: never write the word "radio" followed
-  by a dot in prose (dependency scanner), `//%` must sit immediately
-  above the signature, shims max out at two int args (TS9200 compiler
+  by a dot in prose (dependency scanner) — the one comment threading
+  this today, `emitLine()`'s, moves to `sim.ts` unchanged; `//%` must
+  sit immediately above the signature in every file, not just the
+  original one; shims max out at two int args (TS9200 compiler
   assert).
+- **New (sprint 012): the split's one load-time file-order
+  constraint.** Splitting one file into six means functions in one
+  module now call non-exported helpers declared in another — e.g.
+  `pose.ts`'s `poseX()` calling `sim.ts`'s `_poseX()`. This relies on
+  TypeScript's documented multi-file-namespace merging: files that
+  reopen the same `namespace` and compile as one Program (which is how
+  PXT's `files` list works) share one merged scope, exported or not.
+  Every one of those references in this split is a function-**body**
+  reference — resolved when the function is *called*, after every
+  file has already loaded — so file order does not matter for it. The
+  **one** exception is `motion.ts`'s top-level `_startProtocol()`
+  call (§8's Lifecycle paragraph): that statement executes the moment
+  `motion.ts` loads, so `sim.ts`'s `_startProtocol` definition must
+  already exist — `sim.ts` must be listed before `motion.ts` in
+  `pxt.json`'s `files` array. No other cross-file reference in this
+  split has a load-time ordering requirement. See §15's Design
+  Rationale for how this is verified (ticket 001 IS the empirical
+  test) and the fallback if it is not.
 
 ## 10. Open questions / known limitations
 
@@ -1558,3 +1641,282 @@
   is a real design choice (see `src/DESIGN.md` §1's deliberate
   `shims.cpp`-has-no-header convention) better made deliberately in its
   own review than folded into a Minor here.
+
+## 15. Sprint 012 — architecture diagram and change summary
+
+**Sizing: substantial/structural.** Six new-or-changed modules
+(`sim.ts`, `run.ts`, `pose.ts`, `stop.ts`, `world.ts`, `motion.ts`,
+replacing the single `main.ts`) clears the 3+-modules signal on its
+own, and the split introduces a genuine new cross-module dependency
+class that did not exist before: previously-implicit, same-file
+references between these responsibilities become explicit,
+compile-order-sensitive, cross-*file* references within one TS
+namespace. No dependency-direction change (Presentation/Blocks →
+composition → hardware-or-simulator is unchanged) and no data-model
+change (no persistent data model exists in this embedded package, and
+this sprint doesn't touch the wire protocol's field set). Full
+7-step methodology used, diagram included — this is the same tier the
+component diagram itself exists to clarify, not a sprint where "many
+existing modules touched independently" (sprint 020's exception)
+applies: this sprint *does* compose something new (the six-file
+dependency graph below), even though every function's behavior stays
+byte-for-byte identical.
+
+### Sprint Changes (module level)
+
+- **`src/sim.ts`** (new) — every `//% shim=`-annotated function's
+  TypeScript body: simulator kinematic state + `simIntegrate()` +
+  motion/pose/stop shim bodies + the no-op OTOS/taper/diagnostic
+  stand-ins + `emitLine`/`runCommandText`. Absorbs the issue's
+  separately-proposed `sim.ts` and `shims.ts` rows into one module —
+  see Design Rationale below for why that boundary doesn't survive
+  contact with the real file.
+- **`src/run.ts`** (new) — the RUN command dispatcher: no-initialiser
+  state, `ensureRunState()`, `RUN_EVENT_SOURCE`, `wireRunDispatch()`,
+  `onRun`/`onRunCommand`/`runArg`/`runArgText`/`runArgCount`. Fully
+  self-contained (no cross-file state reference in or out).
+- **`src/pose.ts`** (new) — `poseX`/`poseY`/`heading`/`resetPose`.
+  Calls `sim.ts`'s pose shims cross-file.
+- **`src/stop.ts`** (new) — `stop`/`emergencyStop`/
+  `clearEmergencyStop`/`isStalled`/`clearStallLatch`. Calls `sim.ts`'s
+  stop/latch shims cross-file.
+- **`src/world.ts`** (new) — OTOS world-pose tracking + `goToWorld` +
+  `tickedMove`. Calls `sim.ts`'s OTOS shims and `motion.ts`'s
+  `startMove()` cross-file.
+- **`src/motion.ts`** (new, formerly `src/main.ts`) — `ConfigField`
+  enum, config state/setters, continuous-mode drive, position-mode
+  move, and the top-level `_startProtocol()` call. Calls `sim.ts`'s
+  motion shims cross-file; is called by `world.ts`.
+- **`pxt.json`** — `files` array: `src/main.ts`'s one entry replaced
+  by six entries, in the order `sim.ts, run.ts, pose.ts, stop.ts,
+  world.ts, motion.ts` (the one hard constraint: `sim.ts` before
+  `motion.ts`, see below).
+- **`tsconfig.json`** — same six-file substitution in its own `files`
+  array (currently ungated by any host test — see Open Questions).
+- **`docs/design/specification.md`** — `main.ts` references (its
+  files-array table, the "public surface" paragraph, the `startMove`
+  doc-comment cross-reference, the shim-boundary paragraph) updated to
+  the new module list — execution-time doc work, tracked as ticket
+  acceptance criteria, not part of this overlay (`specification.md` is
+  not part of the canonical `design_docs` set this overlay covers).
+- **`shims.cpp`** and every `.h`/`.cpp` file — **unchanged**. This
+  sprint is TypeScript/manifest-only.
+
+```mermaid
+flowchart LR
+    STUDENT["Student program<br/>(Blocks or TypeScript)"]
+    MOTION["motion.ts<br/>config + continuous/<br/>position-mode drive"]
+    POSE["pose.ts<br/>local pose readback"]
+    STOP["stop.ts<br/>stop + fault latches"]
+    WORLD["world.ts<br/>OTOS world pose<br/>+ goToWorld"]
+    RUN["run.ts<br/>RUN command dispatch"]
+    SIM["sim.ts<br/>every //% shim= body<br/>(browser fallback)"]
+    HW["shims.cpp<br/>hardware — unchanged"]
+
+    STUDENT -->|"block/TS calls"| MOTION
+    STUDENT -->|"block/TS calls"| POSE
+    STUDENT -->|"block/TS calls"| STOP
+    STUDENT -->|"block/TS calls"| WORLD
+    STUDENT -->|"onRun()/onRunCommand()"| RUN
+    MOTION -->|"_setWheels()/_driveTwist()/<br/>_startMove()/_tickDrive()/…"| SIM
+    POSE -->|"_poseX()/_poseY()/<br/>_poseHeading()/_resetPose()"| SIM
+    STOP -->|"_stopAll()/_estopAll()/<br/>_estopClear()/_isStalled()/…"| SIM
+    WORLD -->|"otosBegin()/otosRead()/<br/>otosGet()/_seedPose()/…"| SIM
+    WORLD -->|"startMove() (exported)"| MOTION
+    MOTION -.->|"_startProtocol() — TOP-LEVEL,<br/>load-time: sim.ts must<br/>be listed first in pxt.json"| SIM
+    MOTION -.->|"target=hardware: same<br/>//% shim= call sites compile<br/>against shims.cpp instead"| HW
+```
+
+This diagram **is** this sprint's dependency graph — no separate one
+follows. Every edge above is new only in the sense of becoming an
+explicit cross-*file* reference; none is a new logical dependency (the
+call already existed within the single `main.ts`). No cycles: `sim.ts`
+has no outgoing edges (it is the leaf every other module reaches into,
+plus the hardware-target alternative shown for context), `motion.ts`
+is the only module `world.ts` calls into, and nothing calls back into
+`world.ts`, `pose.ts`, `stop.ts`, or `run.ts` from elsewhere in this
+graph. No entity-relationship diagram: no persistent data model exists
+in this embedded package, and this sprint's changes are confined to
+TypeScript module boundaries and two build manifests — no field-level
+change to the wire protocol or any other data shape.
+
+### Migration Concerns
+
+This is a pure internal restructuring with no student-visible surface
+change by design, so "migration" here means "these six files must
+compile and behave exactly as the one file did," not any data or API
+migration:
+
+- **File-order dependency.** `sim.ts` must precede `motion.ts` in both
+  `pxt.json`'s and `tsconfig.json`'s `files` arrays (`motion.ts`'s
+  top-level `_startProtocol()` call needs `sim.ts`'s definition to
+  already exist at load time). No other pair has a load-time ordering
+  requirement — see §9's new bullet and the Design Rationale below.
+- **The no-initialiser pattern must travel intact.** `run.ts`'s
+  `runParts`/`runNames`/`runHandlers`/`runAnyHandlers`/`runWired`
+  keep zero initialisers, created on first use via `ensureRunState()`
+  — this is a same-file, self-contained pattern in the new layout
+  (unlike the file-order item above), so the split does not make it
+  *harder* to preserve, but it remains the single highest-consequence
+  detail to get right (its violation is the documented panic-980
+  silent boot death).
+- **`//%` annotation adjacency and `group=` values travel with their
+  function, verbatim**, into whichever new file that function lands
+  in — this is mechanical (cut-paste-preserve-comment-order) but easy
+  to get subtly wrong when a function's JSDoc and `//%` lines are
+  separated from a *shared* comment block that also covers unrelated
+  code (see the dual-purpose comment at old `main.ts` lines 58-78,
+  called out explicitly in ticket 002's acceptance criteria).
+- **The `tsconfig.json` manifest is currently ungated.**
+  `test_pxt_manifest_completeness.py` (sprint 007 ticket 006) only
+  reads `pxt.json`; nothing today checks `tsconfig.json`'s `files`
+  array the same way. A file added to `pxt.json` but missed in
+  `tsconfig.json` fails silently at `tsc -p .` time only, the same
+  defect class sprint 007 ticket 006 found and fixed for `pxt.json` —
+  flagged as an Open Question, not mandated as new test-writing work
+  (out of this sprint's stated scope).
+- **Two docs go stale if not updated as part of this sprint's
+  tickets**: `docs/design/specification.md`'s files-array table and
+  its five `main.ts` prose references (lines ~5, 35, 70, 76, 151, 269,
+  765 as of this planning pass) become actively wrong once `main.ts`
+  no longer exists — tracked as ticket 006 acceptance criteria, not
+  this overlay (out of the canonical `design_docs` set).
+
+### Risk
+
+The whole risk surface of this sprint is PXT-specific compile/load
+behavior that no host test reaches (`main.ts`/its successors are
+outside the C++11 gate and outside `tests/host/` entirely — §1's
+layering table). The two concrete risks, both addressed above: (1) the
+`sim.ts`-before-`motion.ts` file-order constraint, mechanically simple
+once known but silent if violated (the symptom would be a load-time
+`ReferenceError`/`undefined is not a function` on `_startProtocol`,
+the TS-side analog of the panic-980 class this project has already
+been bitten by once); (2) whether PXT's compiled-as-one-Program model
+actually honors TypeScript's documented multi-file-namespace merging
+for **non-exported** members the way the language spec says it should
+— nothing in this planning pass can verify that without running a real
+PXT build, so ticket 001 is designed to be the empirical test (see
+Design Rationale). Both risks are retired by evidence (a real build +
+a real simulator run), not by inspection, consistent with this
+sprint's Test Strategy in `sprint.md`.
+
+### Design Rationale
+
+*Decision: merge the issue's proposed `sim.ts` and `shims.ts` rows
+into one module.* Context: the filed issue proposed `sim.ts` (~200
+lines, "the simulator, which nothing on hardware needs") and a
+separate `shims.ts` (~50 lines, "the `//%` shim declarations") as two
+rows. Verified against the real, current `src/main.ts`: from the
+"internal shims" section onward, almost every `//% shim=`-annotated
+function's body *is* the simulator fallback (`_setWheels`,
+`_tickDrive`, `_poseX`, …), and the no-op stand-ins that aren't
+(`_clearStallLatch`, the OTOS/taper stubs) are physically interleaved
+with the real-state functions, not two contiguous blocks — e.g.
+`_seedPose` (real sim state) sits *after* the OTOS no-op stubs at the
+very end of the file. Alternatives: (a) force the two-row split
+anyway, reordering functions to make two contiguous halves [rejected];
+(b) one module for the whole shim surface [chosen]. Why: (a) adds pure
+reordering risk (more diff surface for a behavior-neutral sprint to
+get subtly wrong) for a boundary that isn't real — both halves already
+pass a single cohesion test ("every `//% shim=`-annotated function's
+TypeScript body") more honestly than two artificial ones would.
+Consequences: `sim.ts` is closer to ~370 lines than the roadmap's
+"~200 lines" estimate, but its risk profile (zero hardware coupling,
+first/lowest-risk extraction) is unaffected by line count.
+
+*Decision: split `pose.ts` out on its own, diverging from the
+roadmap's DES-05 recommendation to keep config/motion/pose in one
+file.* Context: DES-05's stated concern was that config, motion, and
+pose "share the `defaultSpeed`/`defaultYawRate` state, and splitting
+them apart risks separating a value from the functions that read it."
+Verified: `defaultSpeed`/`defaultYawRate` are read by exactly one
+function, `motion.ts`'s own `startMove()`, as bare non-exported
+`let`s — pose's four functions never reference them. Pose is reached
+by motion (`whileMoving`/`whileGoingTo` call `poseX()`/`poseY()`/
+`heading()`) exclusively through **exported** functions, which resolve
+safely across files regardless of load order — a categorically safer
+reference than a bare cross-file `let` read. Alternatives: (a) config
++ motion + pose in one file, per DES-05 literally [rejected]; (b)
+config + motion together, pose separate [chosen]; (c) split config
+away from motion too [rejected]. Why: (a) over-applies a caution that
+is genuinely earned for config/motion (a real non-exported `let`
+reference) to pose (which has no such reference) — pose.ts on its own
+cleanly passes the one-sentence cohesion test ("report and reset the
+robot's local pose") and gains nothing from staying bundled. (c) would
+split `defaultSpeed`/`defaultYawRate` from `startMove()`'s direct
+non-exported read of them, which is exactly the risk DES-05 correctly
+flagged. Consequences: six modules instead of a strict five-module
+reading of DES-05; each still passes the cohesion test on its own
+merits, so the count reflects a real extra distinguishable concern
+(fault-latch handling, in `stop.ts`, separated from movement
+commanding), not fragmentation for its own sake.
+
+*Decision: sequence `sim.ts` as ticket 001, and let its build serve as
+the empirical proof of cross-file non-exported namespace visibility,
+rather than a separate throwaway spike ticket.* Context: nearly every
+cross-file call this split needs is a reference to a **non-exported**
+function (`_poseX`, `_stopAll`, `_seedPose`, …) — safe under
+TypeScript's documented multi-file-namespace-merging semantics, but
+unverifiable by this planning pass, which has no PXT build tooling
+available to it. Alternatives: (a) a dedicated ticket 000 adding two
+throwaway dummy files to `pxt.json` purely to test the pattern, then
+reverting them [rejected]; (b) let the first real extraction (`sim.ts`,
+called into by everything still left in the file at that point) serve
+as the test [chosen]. Why: (a) spends a whole ticket proving nothing
+shippable; (b) gets identical evidence for free from real, otherwise-
+necessary work, and keeps the roadmap's independently-argued
+"simulator first" sequencing (lowest risk, zero hardware coupling)
+intact rather than displacing it. Consequences: ticket 001's
+acceptance criteria carry more evidentiary weight than the other
+extraction tickets' — its build success is the proof every later
+ticket's identical cross-file pattern relies on, not only proof that
+`sim.ts` itself works.
+
+*Decision: primary mitigation for the cross-file reference question is
+"rely on the namespace merge, verified by ticket 001's build";
+exporting a currently-private shim function is a fallback, not a
+default.* Context: exporting a function like `_poseX` would make it
+callable from a student's TypeScript-mode program
+(`diffDrive._poseX(...)`) — not reachable today, even though it would
+carry no `//% block=` annotation and so never become a block.
+Alternatives: (a) export every function that crosses a file boundary,
+unconditionally, up front [rejected]; (b) keep everything non-exported
+as today, prove the merge via ticket 001's real build, export only
+whatever a real compile failure names [chosen]. Why: (a) trades a
+confirmed, if minor, behavior-neutrality risk (new TS-reachable
+surface — this sprint's hardest constraint, "not one line of
+student-visible behavior... changes") for a risk that (b) can settle
+empirically at negligible cost by simply attempting the real thing
+first. Consequences: if ticket 001's build cannot resolve a specific
+non-exported cross-file reference, the fallback is scoped to exactly
+the failing symbols, recorded by name in that ticket's completion
+notes, not applied as a blanket policy to every shim function.
+
+### Open Questions (sprint 012)
+
+- Does PXT's actual multi-file compile model resolve non-exported
+  namespace members across files exactly as TypeScript's documented
+  namespace-merge semantics predict? Ticket 001 answers this
+  empirically (a real build + a real simulator/testrig run); this
+  planning pass cannot verify it without that build.
+- Should this sprint also add a `test_tsconfig_completeness.py`
+  mirroring `test_pxt_manifest_completeness.py`'s pattern for
+  `tsconfig.json`'s `files` array, currently ungated by any host test?
+  Flagged, not mandated — a natural, cheap follow-on this sprint's own
+  six-way file split makes more valuable than it was for one file, but
+  outside the issue's and this sprint's stated scope.
+- Where should the file-header doc comment (old `main.ts` lines 1-12,
+  the extension-level `/** DiffDrive — ... */` block) live once
+  `main.ts` no longer exists? Recommend `motion.ts` (the largest
+  direct descendant of the original file), but this is a low-stakes
+  call the ticket 006 programmer can make either way with no behavior
+  consequence (doc comments have no runtime effect).
+- `docs/design/overview.md` (one `main.ts` mention) and
+  `tools/DESIGN.md` (one `main.ts` mention, in a sentence that remains
+  true in substance after the split) carry minor, non-load-bearing
+  stale references this sprint's doc pass could touch up; recommend
+  bundling them into ticket 007's handoff notes on a time-permitting
+  basis rather than gating the sprint on them — unlike
+  `specification.md`'s files-array table, neither becomes actively
+  false.
```

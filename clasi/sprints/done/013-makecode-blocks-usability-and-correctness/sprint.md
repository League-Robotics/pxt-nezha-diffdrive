---
id: '013'
title: MakeCode Blocks Usability and Correctness
status: ticketing
branch: sprint/013-makecode-blocks-usability-and-correctness
use-cases: []
issues:
- int32-sim-params-break-blocks-conversion.md
- simulator-crashes-at-on-start-startprotocol.md
- radio-group-setup-block.md
- arc-moves-abort-distance-never-driven.md
- block-toolbox-groups-reorganization.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 013: MakeCode Blocks Usability and Correctness

## Goals

A student using the locally-served MakeCode editor for this extension
gets: working JS-to-Blocks conversion, a simulator that boots instead
of crashing, a toolbox block to set the radio group, arc moves
(`move` with both distance and yaw) that actually drive and turn as
commanded, and a toolbox whose group layout reads as cohesive rather
than incidental.

Sizing note (for Detail Mode): this reads as one **compact** sprint —
five pending issues, each confined to a small, mostly non-overlapping
slice of `src/*.ts` (sim.ts shim bodies, motion-engine arc path,
radio_transport.h + a new setter, and //% group annotations across
five files), no new cross-module dependency, and no data-model change.
The arc-move kernel bug (#4) is the one item that may turn out
structurally deeper than the others once the motion engine is
inspected — if the fix touches the dependency direction between the
motion engine and the stall/completion logic, re-run the effort
decision for that ticket's slice before writing its architecture
detail.

## Problem

Five pending issues from the 2026-08-25 bench/editor session on tovez,
all against this extension (`pxt-nezha-diffdrive`):

1. **`int32-sim-params-break-blocks-conversion.md`** — `int32`-typed
   parameters on shim-fallback functions in `src/sim.ts` fail MakeCode's
   decompiler with `TS9256` ("bit sizes are not supported for locals
   and parameters"), so every "switch to blocks" on a project using
   this extension fails. Confirmed the native build is unaffected
   (C++ shim signatures govern the ABI, not the TS decl types); a
   scratch `int32`→`number` patch converts cleanly and was verified
   safe on hardware (tovez, `RUN:go`, pose telemetry matched the
   commanded move).
2. **`simulator-crashes-at-on-start-startprotocol.md`** — the
   empty-bodied shim `_startProtocol()` (and other empty-bodied shims
   reachable from sim code, e.g. `_setGeometry`) makes pxt emit a
   `pxsim.diffDrive.*` call with no implementation, so the web
   simulator crashes at boot (`Cannot read properties of undefined
   (reading 'startProtocol')`). Same file, same session as #1 — a
   natural pairing for one ticket.
3. **`radio-group-setup-block.md`** — radio RX is already on by
   default at group 10 / channel 4 (`src/radio_transport.h`,
   `ensureRadioReady()`), but nothing in the toolbox lets a student set
   or see the group. Needs a new Setup block (`set radio group`,
   default 10) plus a TS/shim/C++ setter that applies idempotently
   whether called before or after the radio comes up. Channel stays
   fixed at 4 (fleet convention) — not exposed as a default-changeable
   block.
4. **`arc-moves-abort-distance-never-driven.md`** — a kernel bug in the
   motion engine: `move()` with BOTH distance and yaw nonzero never
   drives the distance component and terminates the yaw component
   early (measured: 2.6° of a commanded 180°, 77° of a commanded 90°).
   Pure pivots and pure straights are correct in isolation. Needs
   motion-engine investigation, a fix, and hardware re-verification on
   tovez (encoder + camera truth, not just believed pose).
5. **`block-toolbox-groups-reorganization.md`** — the current `//%
   group=` layout across `motion.ts`, `stop.ts`, `run.ts`, `pose.ts`,
   `world.ts` doesn't read as cohesive groups (world setup and world
   moves are mixed together; stop blocks live apart from the moves
   they stop; tuning setters are mixed with everyday moves). Purely an
   annotation reorganization — no behavior change — but the proposed
   layout (groups, order, weights, advanced flags) must go to Eric for
   review before any ticket implements it, since "feels cohesive" is
   his call to make.

## Solution

- Fix `src/sim.ts` shim-fallback parameter types (`int32` → `number`)
  so JS→Blocks conversion succeeds (issue 1).
- Give empty-bodied shims reachable from sim code (starting with
  `_startProtocol`, auditing others such as `_setGeometry`) real,
  trivial simulator bodies so the web simulator boots cleanly
  (issue 2). Ticketed together with issue 1 — same file, same editing
  pass.
- Add a `set radio group` Setup block (TS + shim + C++ setter) that
  idempotently applies the group whether the radio is already up or
  not; leave channel fixed at 4 (issue 3).
- Investigate and fix the motion-engine arc path so combined
  distance+yaw moves drive both components correctly; re-verify on
  tovez with camera/encoder ground truth, not just believed pose
  (issue 4).
- Produce a proposed toolbox regrouping (groups/order/weights/advanced
  flags) for `motion.ts`/`stop.ts`/`run.ts`/`pose.ts`/`world.ts`,
  present it to Eric for approval, then apply it as an annotation-only
  ticket once approved (issue 5).

## Success Criteria

- [ ] A project using this extension converts cleanly from JS to
      Blocks in the local editor (no `TS9256`, no conversion dialog).
- [ ] The web simulator boots (shows the start icon, clean Problems
      pane) for a bare project using this extension.
- [ ] A `set radio group` block exists in the toolbox, defaults to 10,
      and a program that calls it actually changes the radio's group
      whether called before or after the radio comes up (verified on
      tovez).
- [ ] `move()` calls with both distance and yaw nonzero drive the
      commanded distance and complete the commanded yaw, verified on
      tovez against camera or encoder ground truth (not just believed
      pose) for at least the two measured repro cases (20 cm/90°,
      20 cm/180°).
- [ ] Eric has reviewed and approved a proposed toolbox group layout,
      and the local editor's toolbox reflects it after implementation.

## Scope

### In Scope

- The five linked issues above, each as one or more tickets in Detail
  Mode.
- `src/sim.ts` parameter-type and empty-shim-body fixes.
- New `set radio group` block: TS declaration, shim, C++ setter in the
  radio transport layer.
- Motion-engine arc-path investigation and fix (kernel-level, wherever
  the distance/yaw completion logic lives).
- `//% group=`/`weight=`/`advanced=` annotation changes across
  `src/motion.ts`, `src/stop.ts`, `src/run.ts`, `src/pose.ts`,
  `src/world.ts` — stakeholder-approved layout only.
- Hardware verification on tovez (mbdeploy + serial pose telemetry;
  `RUN:turn`/`RUN:go`/`RUN:arc` repro verbs already exist in
  `projects/blocktest`) for issues 3 and 4.
- Local-editor verification (`http://localhost:3232/index.html?ws=fs`)
  for blocks conversion, simulator boot, and toolbox layout (issues 1,
  2, 5).

### Out of Scope

- The other pending issues in `clasi/issues/` not linked to this
  sprint: `finish-the-vevov-calibration-verification.md`,
  `first-camera-scored-tour-fails-closure-gate.md`,
  `gotoworld-overshoots-by-fixed-stopping-distance.md`,
  `i2c-fault-count-climbs-on-idle-bus.md`,
  `rotation-error-is-injected-by-the-legs-not-the-pivots.md`,
  `tour-corner-fixes-are-stale-cache.md`,
  `travel-calib-is-2.8-percent-too-large.md` — these are calibration/
  navigation-accuracy issues on vevov's world-frame tour stack, not
  MakeCode blocks/editor issues, and belong to a separate sprint.
- Any change to the radio channel default (stays fixed at 4).
- Exposing radio channel as a student-facing block.
- Any accuracy work beyond what's needed to prove the arc-move fix
  (issue 4) drives and turns correctly — this sprint fixes the abort
  bug, not general motion-accuracy tuning (see the out-of-scope
  calibration issues above).
- Universal-hex / `mbdeploy` tooling fixes noted as secondary findings
  in issue 1 (workspace `_history` 409s, universal-hex vs
  `mbcodal-binary.hex`, WebUSB tab holding the DAP interface) — useful
  operator notes, not sprint deliverables.

## Test Strategy

- **Editor checks** (issues 1, 2, 5): local `pxt serve` fs workspace at
  `http://localhost:3232/index.html?ws=fs` — JS→Blocks conversion
  succeeds, simulator boots with a clean Problems pane, toolbox groups
  match the approved layout.
- **Hardware checks** (issues 3, 4): build + flash to tovez over USB
  (mbdeploy, `built/mbcodal-binary.hex` — not the universal-hex
  MakeCode download), drive via the existing `RUN:turn`/`RUN:go`/
  `RUN:arc`/radio-group repro verbs in `projects/blocktest`, read pose
  via `TLM POSE #1` serial telemetry. Issue 4 additionally needs
  camera or eyeball ground truth per the project's playfield-testing
  rules (believed pose alone is not sufficient — that's the other half
  of the original bug report).
- **Regression**: a full native build (non-simulator) after the
  sim.ts and radio changes, to confirm the C++ ABI is unaffected by
  the TS-level type changes (already spot-checked for issue 1's
  patch, but re-verify on the actual ticket branch).
- No unit-test framework changes anticipated; this extension's tests
  are bench/editor verifications, not an automated suite.

## Architecture

**Sizing: Substantial (by module count), no diagram required** —
overriding this sprint's own roadmap-time "compact" note. Re-evaluated
against the concrete signals during Detail Mode: the five issues touch
four independently-changing areas of `src/` — the Sim Shim layer
(`sim.ts`), the Blocks student-facing layer treated as one unit per
`docs/design/design.md`'s units-ladder table (`motion.ts`, `stop.ts`,
`run.ts`, `pose.ts`, `world.ts`), the Radio Transport leaf
(`radio_transport.h`/`.cpp`), and the Shim boundary / Motion Engine
(`shims.cpp` + `motion_engine.cpp`/`.h`) — which is 3+ modules touched,
the literal substantial-tier trigger, even though no single issue
introduces a new cross-module dependency, a dependency-direction
change, or a data-model change. This is the same shape as sprint 020
(cited precedent): independent bugfix/process-quality work spread
across many existing modules, substantial by module count, but with
nothing new being composed — so **no component/dependency diagram is
included**, for the same reason sprint 020 gave: there is no new
composition between modules for a diagram to clarify. Each of the four
areas below is a single existing module having a self-contained defect
fixed or a narrow addition made; none of them changes who depends on
whom.

### Step 1-2: Problem and Responsibilities

Five independent responsibilities, none newly introduced — all are
either bug fixes to existing behavior or a narrow, additive block:

1. **Blocks-conversion correctness** (Sim Shim layer): `sim.ts`'s
   shim-fallback functions use `int32` parameter types, which the
   MakeCode decompiler's typecheck pass rejects (TS9256) on any
   function that has a body. This is a pre-existing defect in an
   existing module, not a new responsibility.
2. **Simulator-boot correctness** (Sim Shim layer, same file): several
   of `sim.ts`'s shim-fallback functions have empty TS bodies, which
   pxt treats as "native-only" and bundles as an unimplemented
   `pxsim.diffDrive.*` call — crashing the browser simulator the
   instant one is invoked. Same module as #1; ticketed together.
3. **Radio group configurability** (Radio Transport leaf + Blocks
   layer + Shim boundary): today the group is a compile-time constant
   (`kGroup = 10`, `radio_transport.h:182`) applied once, lazily, by
   `ensureRadioReady()` (`radio_transport.cpp:30-47`). This adds one
   new capability — a runtime-settable group — surfaced as one new
   Setup block. It is additive to the Radio Transport leaf's existing
   public surface, not a new dependency: the Blocks layer already
   depends on shims, which already depend on Radio Transport via
   Protocol.
4. **Arc-move (combined distance+yaw) correctness** (Shim boundary +
   Motion Engine): a defect in how the wire-level `startMove()` shim
   (`shims.cpp:379-440`) computes the single `cruiseMmS`/`timeoutMs`
   budget it hands to `MotionEngine::moveX()`. Confined entirely to
   this file pair.
5. **Toolbox cohesion** (Blocks layer): a pure `//% group=`/`weight=`/
   `advanced=` annotation reorganization across the five Blocks-layer
   files. No behavior change, no new responsibility — a presentation
   change to an existing module.

### Step 3: Modules Touched (no new modules)

- **Sim Shim layer** (`src/sim.ts`) — purpose: give the browser
  simulator a kinematic stand-in for every native shim so a
  block/JS program behaves consistently in-browser and on-hardware.
  Boundary: TS-only, no CODAL/C++; everything it exports mirrors a
  `shims.cpp` native shim 1:1. Serves: every use case that runs in the
  local editor (SUC-001, SUC-002).
- **Blocks layer** (`src/motion.ts`, `stop.ts`, `run.ts`, `pose.ts`,
  `world.ts`) — purpose: expose the extension's capabilities as
  student-facing MakeCode blocks in cm/deg units. Boundary: TS only,
  calls down into shims, never into C++ directly; owns `//% group=`
  presentation metadata. Serves: SUC-003 (new radio block) and SUC-005
  (toolbox layout).
- **Radio Transport leaf** (`src/radio_transport.h`/`.cpp`) — purpose:
  get a formatted wire line onto the micro:bit radio, framed for the
  fleet's relay. Boundary: CODAL-facing leaf beneath Protocol; knows
  `uBit.radio` and on-air framing, nothing about pose or verb
  semantics. Serves: SUC-003.
- **Shim boundary / Motion Engine** (`src/shims.cpp`'s `startMove()`
  forward, `src/motion_engine.cpp`/`.h`) — purpose: reduce every
  student-facing move to the two-primitive wheel-segment math and
  service it tick-by-tick to completion. Boundary: `motion_engine.*` is
  host-portable (no pxt.h/CODAL); `shims.cpp` is the integer-unit
  translation layer between the Blocks layer and the engine. Serves:
  SUC-004.

### Step 4: Diagrams

None. See the sizing note above — this sprint's five changes are
independent, self-contained fixes/additions inside existing module
boundaries; no new edge is drawn between any two modules, so a
component or dependency diagram would show exactly the same graph as
today's, with nothing to highlight. No data-model change, so no ERD.

### Step 5: What Changed / Why / Impact / Migration Concerns

**What Changed**

- `sim.ts`: shim-fallback parameter types `int32` → `number` (Ticket
  001). Planning-time audit of the full file found `int32` parameters
  on more functions than the issue's own line list named — see Ticket
  001 for the complete set.
- `sim.ts`: empty-bodied shim functions reachable from the simulator
  (starting with `_startProtocol`, called unconditionally at namespace
  load) given real, trivial bodies so pxt uses the TS body instead of
  an absent native `pxsim.*` implementation (Ticket 001). Planning-time
  audit found more empty-bodied functions than the issue named — see
  Ticket 001.
- New Setup block `set radio group` (default 10) plus a TS declaration,
  a new shim, and a new idempotent C++ setter method on
  `RadioTransport` that applies immediately if the radio is already up
  (`radioReady_ == true`) and just records the value otherwise, for
  `ensureRadioReady()` to apply on its own lazy first call (Ticket
  002). Channel (`kChannel = 4`) stays a compile-time constant — no
  block, no setter.
- `shims.cpp`'s `startMove()` timeout/cruise budget for combined
  distance+yaw moves, and/or `MotionEngine::moveX()`'s
  `queuePivotThenStraight()` two-phase handling, fixed so a combined
  move actually drives both its distance and yaw components to
  completion (Ticket 003). See Design Rationale below for the
  planning-time investigation lead.
- `//% group=`/`weight=`/`advanced=` annotations across `motion.ts`,
  `stop.ts`, `run.ts`, `pose.ts`, `world.ts` — proposal first, applied
  only after Eric approves it (Ticket 004).

**Why**

Each fix removes a concrete, measured obstacle to a student's
edit-run-see loop in the local editor (blocks conversion, simulator
boot, arc moves) or closes a documented capability/comprehension gap
(radio group, toolbox cohesion). None is speculative; all five trace to
the 2026-08-25 bench/editor triage session's issue files.

**Impact on Existing Components**

- Sim Shim layer: parameter-type and body changes are simulator-only;
  the native build's ABI is governed by `shims.cpp`'s C++ signatures,
  unaffected by TS decl types (already spot-checked on hardware for
  the int32 change — tovez `RUN:go` telemetry matched commanded).
- Radio Transport: additive method on `RadioTransport`; existing
  `sendLine()`/`tryReceiveLine()`/`ensureRadioReady()` behavior
  unchanged when the new setter is never called (default stays 10).
- Shim boundary / Motion Engine: the arc-move fix changes internal
  timeout/cruise-budget arithmetic and/or two-phase sequencing: pure
  pivots and pure straights (single-segment moves, the common case)
  must remain bit-for-bit unaffected — the isolated-pivot and
  isolated-straight measurements from the issue's own triage are the
  regression baseline.
- Blocks layer: toolbox reorg is annotation-only; no block's inputs,
  outputs, or C++ call ever changes.

**Migration Concerns**

None. No data model, no persisted state, no wire-protocol change, no
existing block signature changes. The one behavior change a program
could observe is the arc-move fix itself (Ticket 003) — a program that
was silently relying on the abort (unlikely, since the abort is a pure
defect) would now see its move actually complete; this is a bug fix,
not a breaking change, and is called out here only for completeness.

### Design Rationale

**Decision: pursue a targeted fix in `shims.cpp`/`motion_engine.cpp`
for the arc-move defect, not a rewrite of the two-phase split.**
Context: the issue lists three suspects (stall latch, completion
predicate, speed floor). Reading `motion_engine.cpp`'s `serviceMove()`
and `shims.cpp`'s `startMove()` during planning surfaced a fourth,
concrete lead worth flagging for the implementing ticket: `startMove()`
computes ONE flat timeout backstop (`duration*1000 + 1500ms`) sized for
a single BLENDED (simultaneous) distance+yaw segment, but
`MotionEngine::moveX()` actually SPLITS any combined move with
`|rotation| >= kTurnFirstAngleRad` (50°) into TWO SEQUENTIAL phases via
`queuePivotThenStraight()` — pivot alone, then straight alone, each
using the same `cruiseMmS`. Two sequential phases each carry their own
ramp-up (`rampMs_`) and end-of-move taper overhead, which a budget sized
for one simultaneous segment's overhead may not cover — and the larger
the rotation, the larger `dominantCounts` grows relative to the
distance-only leg, which is consistent with the measured pattern
("tighter arc completes earlier": 2.56° of 180° vs. 77.3° of 90°).
Alternatives considered: (a) accept the issue's three suspects at face
value and start there — rejected as the first thing to try, since nothing
in the stall-latch or speed-floor code paths as read explains why
LARGER rotations abort EARLIER, whereas the shared-deadline-across-two-
phases theory does; (b) rewrite `moveX()`'s split to blend distance and
yaw into one true simultaneous arc instead of pivot-then-straight —
rejected as out of scope: that would change `goToR()`'s already-correct
arc-vs-chord math and is a bigger change than this defect calls for.
Consequences: this is a **lead for the implementing ticket's
investigation, not a confirmed root cause** — it must be verified
against actual telemetry (which abort condition fires: `expired` vs.
`out.stallHalted` vs. `wrongWay`) on tovez before committing to a fix,
per the issue's own instruction that this needs motion-engine
investigation. The three suspects the issue names remain live
alternatives if telemetry rules the timeout theory out.

**Decision: keep the arc-move fix inside the existing Shim boundary /
Motion Engine module pair rather than treating it as a new
subsystem.** Context: the sprint's own roadmap note flagged this
ticket as the one that might turn out structurally deeper once the
motion engine was inspected. Alternatives considered: escalate to
substantial-with-diagram for this ticket alone if the fix required a
new dependency (e.g., threading per-phase timeout state up through
`wire_adapter.cpp` as well). Why this choice: reading `moveX()`,
`queuePivotThenStraight()`, and `serviceMove()` shows the fix — whichever
of the four leads above it turns out to be — is expressible as a change
to values already owned by `MotionEngine`'s `move_` state and/or
`shims.cpp`'s existing budget arithmetic; no new class, no new stored
field crossing a module boundary, no change to `wire_adapter.cpp`'s
call shape. Consequences: the sprint-wide "substantial by module count,
no diagram" sizing holds for this ticket too. If the programmer's
investigation finds the fix genuinely requires a new cross-module
dependency (e.g., serviceMove() needing per-phase state from a layer
above MotionEngine), that is grounds to throw a ticket exception rather
than silently expand scope.

**Decision: make the new radio-group setter idempotent across
`ensureRadioReady()`'s lazy-init boundary, rather than requiring
call-order.** Context: a program may call the new Setup block before
or after the radio has been used for the first time (which is when
`ensureRadioReady()` actually runs). Alternatives considered: document
a "call this before anything else" requirement — rejected, since
`on start` block ordering is not something a beginner reliably
controls, and getting it wrong would silently do nothing. Why this
choice: matches the issue's own proposed shape (store the value; apply
immediately if already up, else let the next `ensureRadioReady()` pick
it up) and needs only one boolean/`uint8_t` of new state on
`RadioTransport`. Consequences: the setter must be tested in both
orders on tovez (see Ticket 002's acceptance criteria).

### Step 7: Open Questions

- Ticket 003's exact fix (which of the four leads, or a combination)
  is not decided here — it is an implementation-phase investigation
  with a required hardware-verification step, consistent with the
  issue's own framing.
- Ticket 004's toolbox layout is a proposal for Eric's review, not a
  decision made here — see Ticket 004 and Success Criteria's last
  bullet.

## Use Cases

Sized to the change: each SUC below is a bug-fix or narrow-addition
flow, kept to the essential actor/preconditions/flow/acceptance shape
rather than full multi-page narrative treatment, since none introduces
a new actor or a new subsystem-level flow.

### SUC-001: Convert a project to Blocks in the local editor
Parent: (none — no existing use-case document for this extension's
editor experience; this is the first use case written for it)

- **Actor**: Student (or Eric, verifying)
- **Preconditions**: A MakeCode project depends on this extension and
  contains at least one call into a `sim.ts` shim-fallback function
  with a currently-`int32` parameter (i.e., effectively any project,
  since `move()`/`goTo()`/etc. all route through one).
- **Main Flow**:
  1. Student writes or pastes JS using this extension's blocks API.
  2. Student clicks "Blocks" to convert.
  3. The decompiler typechecks the program, including `sim.ts`'s
     shim-fallback bodies, and succeeds.
  4. The Blocks view renders the equivalent block program.
- **Postconditions**: The project is now editable as blocks; no
  `TS9256` error, no "Oops, there is a problem converting your code"
  dialog.
- **Acceptance Criteria**:
  - [ ] A project using this extension converts JS→Blocks with no
        `TS9256` in the local editor (`http://localhost:3232/index.html?ws=fs`).

### SUC-002: Run a program in the browser simulator
Parent: (none, see SUC-001)

- **Actor**: Student
- **Preconditions**: A bare (or any) project using this extension is
  open in the local editor.
- **Main Flow**:
  1. Student clicks the simulator's start/run control (or the
     simulator auto-starts on load).
  2. The simulator bundle executes the program's `on start` and
     subsequent code, including the namespace-load-time
     `_startProtocol()` call.
  3. Every shim-fallback function the program reaches during
     simulation runs its TS body instead of an absent native
     `pxsim.*` implementation.
- **Postconditions**: The simulator shows the running program (start
  icon, moving sprite/console output as applicable); the Problems pane
  is clean.
- **Acceptance Criteria**:
  - [ ] The web simulator boots without "Cannot read properties of
        undefined" for a bare project using this extension.
  - [ ] The Problems pane is clean for that same project.

### SUC-003: Set the radio group from a block
Parent: (none, see SUC-001)

- **Actor**: Student
- **Preconditions**: A project using this extension is being written
  to receive RUN commands from the fleet's RADIOBRIDGE relay on a
  non-default group, OR a student wants the group visible/teachable in
  their own program instead of an invisible compiled-in default.
- **Main Flow**:
  1. Student drags the `set radio group %group` block into `on start`
     (or anywhere), sets `%group` (default 10).
  2. Program runs; if this is the radio's first use, `ensureRadioReady()`
     applies the stored group directly; if the radio was already up
     (a prior call already triggered lazy init), the setter re-applies
     the new group immediately via `uBit.radio.setGroup()`.
- **Postconditions**: The robot listens for RUN commands on the
  requested group; channel stays fixed at 4 regardless of call order.
- **Acceptance Criteria**:
  - [ ] Calling the block BEFORE any other radio use changes the group
        the first `ensureRadioReady()` applies (verified on tovez).
  - [ ] Calling the block AFTER radio is already active changes the
        live group immediately (verified on tovez).
  - [ ] Channel remains 4 in both cases; no block exposes channel.

### SUC-004: Command a combined distance+yaw move
Parent: (none, see SUC-001)

- **Actor**: Student (program author); Eric (hardware verifier)
- **Preconditions**: Robot is on the playfield (not the bench stand —
  see this project's playfield-testing rule on why bench odometry
  cannot validate this), radio or USB link established.
- **Main Flow**:
  1. Program calls `move(distance, yaw)` (or the wire `RUN:arc:<deg>`
     repro verb) with both nonzero.
  2. The call drives the commanded distance AND completes the
     commanded yaw before reporting done.
- **Postconditions**: Camera or encoder ground truth confirms both the
  commanded distance and the commanded yaw were achieved, for at least
  the two measured repro cases (20 cm/90°, 20 cm/180°); pure pivots and
  pure straights remain unaffected (regression baseline from the
  issue's own isolated measurements).
- **Acceptance Criteria**:
  - [ ] `move(20cm, 90deg)` drives ~20 cm and completes ~90° (camera
        or encoder truth), not the measured-defective 77.3°/~0 cm.
  - [ ] `move(20cm, 180deg)` drives ~20 cm and completes ~180°, not the
        measured-defective 2.56°/~0 cm.
  - [ ] An isolated pivot (`RUN:turn:<deg>`) and isolated straight
        (`RUN:go`) remain correct after the fix (no regression).

### SUC-005: Find a block by browsing a cohesive toolbox
Parent: (none, see SUC-001)

- **Actor**: Student
- **Preconditions**: The toolbox layout proposal (groups, order,
  weights, advanced flags) has been reviewed and approved by Eric.
- **Main Flow**:
  1. Student opens the toolbox looking for a block by task (e.g. "I
     want to stop the robot", "I want to move it to a world
     coordinate", "I want to set up the radio").
  2. The block is in the group a student would guess first, near the
     other blocks used for the same task, with tuning/rarely-used
     setters tucked under Setup/advanced rather than mixed into
     everyday groups.
- **Postconditions**: Eric confirms the layout reads as cohesive (this
  is the acceptance criterion — his judgment, not a mechanical check).
- **Acceptance Criteria**:
  - [ ] Eric has reviewed and approved the proposed layout BEFORE
        Ticket 004's annotation changes are applied.
  - [ ] After implementation, the local editor's toolbox matches the
        approved layout.

## GitHub Issues

(GitHub issues linked to this sprint's tickets. Format: `owner/repo#N`.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [ ] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [ ] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | Fix sim.ts int32 params and empty-bodied shim crashes | — |
| 002 | Add set-radio-group Setup block | — |
| 003 | Fix arc-move (combined distance+yaw) abort in the motion engine | — |
| 004 | Propose and apply toolbox group reorganization | 002 |

Tickets execute serially in the order listed. 001-003 are mutually
independent (different files/subsystems); 004 depends on 002 because
its proposed layout places the new `set radio group` block into a
"Remote" group alongside `on run`/`on run command`, so Ticket 004's
Step 2 (apply) needs that block to exist before it can annotate it.

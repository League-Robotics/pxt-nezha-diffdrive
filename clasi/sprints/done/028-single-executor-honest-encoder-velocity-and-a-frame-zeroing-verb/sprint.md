---
id: 028
title: Single executor, honest encoder velocity, and a frame-zeroing verb
status: done
branch: sprint/028-single-executor-honest-encoder-velocity-and-a-frame-zeroing-verb
use-cases:
- SUC-001
- SUC-002
- SUC-003
issues:
- single-executor-for-command-dispatch.md
- frozen-encoder-read-becomes-a-phantom-zero-velocity-and-the-pid-overreacts.md
- no-wire-verb-reaches-rebaseposition-so-tours-cannot-zero-their-frame.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 028: Single executor, honest encoder velocity, and a frame-zeroing verb

## Goals

Three independent, small-to-medium firmware fixes that share no code but
do share a prerequisite: none of them should start until sprint 027 (one
serial producer — the UART-wedge fix) has landed and been
hardware-confirmed, since two of the three touch the same protocol fiber
027 is repairing.

1. **The full executor inversion** carried out of sprint 026, and
   confirmed still worth doing by the 2026-09-02 triage note in
   `clasi/issues/single-executor-for-command-dispatch.md`: collapse the
   remaining two execution models (`RUN:` motion on a forked MessageBus
   fiber, wire motion on the protocol fiber) into one, so the I2C
   bus-discipline invariant is structural rather than a convention three
   call sites must each remember. This is the piece the triage explicitly
   separated from 027's single-serial-producer piece — not
   host-testable, budget 2-3 bench sessions, and it can wait for a
   reliably reachable board.
2. **Hold, don't zero** on a frozen encoder read
   (`clasi/issues/frozen-encoder-read-becomes-a-phantom-zero-velocity-and-the-pid-overreacts.md`):
   stop a failed I2C read from manufacturing a phantom zero-velocity
   sample that makes the velocity PID lunge toward the rail. Measured on
   gopiv, 7-45 occurrences per tour, clustered tightly on the frozen
   reads. Host-testable via `tests/host/motion_engine_shim.cpp`'s
   existing `meMotorArmPosition`/`meArmSettleProfile` scripting.
3. **A sequenced wire verb that reaches `rebasePosition()`**
   (`clasi/issues/no-wire-verb-reaches-rebaseposition-so-tours-cannot-zero-their-frame.md`):
   let a radio-driven tour zero its own pose/heading frame at leg 1
   instead of starting in whatever boot-anchored odometry frame the robot
   has accumulated. The issue's triage note suggests adding a sequenced
   `ESTOP` clear verb in the same ticket, since the existing
   `RUN:clearestop` is cleartext-only — flag as a candidate, not a
   commitment, pending detail planning's read of the wire grammar (owned
   cross-repo by radio-robot-lib's `protocol.md`).

## Problem

Three defects, unrelated in cause, share only that fixing any of them
touches the protocol fiber or the kernel-adjacent motion/platform layer
that sprint 027 is also working in:

- Command dispatch still runs on three coexisting fiber models instead
  of one deliberate one (sprint 026's item 3, deferred).
- A failed encoder I2C read is silently reinterpreted as "wheel
  stopped," not "read failed," even though the kernel already counts the
  failure (`i2cf`) — so the velocity PID sees a fabricated ~300 mm/s
  error and slams duty toward the rail.
- No wire verb reaches the kernel's existing `rebasePosition()`, so every
  radio-driven tour starts in an arbitrary accumulated heading and every
  chart needs host-side rotation to line up; on chassis with no OTOS
  (e.g. tigez), zeroing at tour start is the *only* mechanism for an
  absolute heading reference.

## Solution

Detail planning decides ticket count and sequencing per issue, but the
shape of each fix is already scoped by its issue:

1. Executor inversion: split `Protocol::run()` into a non-blocking
   service call plus a loop that services the wire, dispatches one queued
   RUN job, and ticks or sleeps; invert the tour's own tick loop onto
   that fiber via a service hook rather than moving the tick into
   TypeScript (explicitly not the superseded from-TypeScript-obligation
   design — see the issue's own "Superseded" section). This is the same
   shape sprint 026 already designed and partially specified before
   deferring it; detail planning should reuse that record rather than
   re-deriving it.
2. Frozen-encoder fix: the issue's own preference order is hold-the-
   previous-velocity first, range-gate against sprint 025's constant-`a`
   accel/decel bounds second. `src/core/diffdrive.{h,cpp}` is vendored
   and has been kept byte-identical through prior sprints; detail
   planning must decide explicitly whether this fix lives entirely in
   the platform/motion layer or requires touching the kernel, and record
   that as a scope decision rather than discovering it mid-ticket.
3. Frame-zeroing verb: add a sequenced wire verb (`SET pose 0 0 0` or a
   dedicated `REBASE`, per the issue's fix shape) that calls
   `rebasePosition()`. Wire grammar is shared cross-repo with
   radio-robot-lib's `protocol.md` — detail planning must account for
   that coordination before picking a final verb name/shape.

## Success Criteria

- Executor inversion: exactly one execution model remains for
  engine-facing motion (the protocol fiber); `RUN:abort` still stops a
  running job with no queue delay; a wire motion request arriving
  mid-job is arbitrated, not silently overwritten. Verified on hardware
  only — no host-test substitute exists for this piece.
- Frozen-encoder fix: a host test proves commanded duty does not step
  toward the rail on the tick following a frozen read or the tick after;
  a hardware re-run of `captures/gopiv-profile-sweep-20260901/tight_tour.py`
  on gopiv shows no speed excursion following an `i2cf` increment.
- Frame-zeroing verb: a tour issuing the new verb at leg 1 produces an
  axis-aligned odometry frame with no host-side rotation needed to read
  the chart; verified on both an OTOS-equipped chassis and tigez (no
  OTOS, wheel-encoder-only heading).
- `uv run pytest` passes throughout each ticket's scoped run, and in full
  at `close_sprint`.

## Scope

### In Scope

- The full executor inversion (protocol fiber split, `motionOwner_`
  arbitration, tour tick-loop inversion via service hook), per sprint
  026's already-specified design.
- The frozen-encoder-read fix in the motion/platform layer (or the
  kernel, if detail planning finds that unavoidable — to be stated
  explicitly, not silently).
- One new sequenced wire verb reaching `rebasePosition()`.
- Detail planning's judgment call on whether a sequenced `ESTOP` clear
  verb rides along in the same ticket as the frame-zeroing verb.

### Out of Scope

- Sprint 027's single-serial-producer fix (the UART wedge) — a hard
  prerequisite, not part of this sprint's own work.
- The genuine upstream CODAL fixes for anything FPU- or fiber-related —
  vendored toolchain, out of bounds, as already decided in sprint 026.
- Fixing the I2C failures themselves (loose connector, bus timing) — the
  frozen-encoder fix only stops a failed read from injecting a phantom
  velocity; it does not reduce how often reads fail.
- `first-i2c-command-can-wedge-the-program-with-no-recovery` and
  `i2c-fault-count-climbs-on-idle-bus` — related I2C issues the
  2026-09-02 triage placed in the next round after this one, not this
  sprint.
- `ensure-is-not-reentrant-two-rigs-can-be-constructed` — adjacent to the
  executor work but explicitly independent and not fixed by it, per the
  issue's own "Related" note.

## Test Strategy

Two of three items (tickets 001, 002) are host-testable and get real
host test coverage: ticket 001 via `tests/host/motion_engine_shim.cpp`'s
existing encoder-scripting seam, ticket 002 via the existing
`WireAdapter`/`WireMockAdapter` host test suite (the same seam
`stall_clear` is tested through). Both also get hardware acceptance
runs, since a host test proves the *decision logic* only, never the
physical I2C/OTOS behavior. Ticket 003 (the executor inversion) has
**no host-test substitute at all** — `protocol.cpp` and the TS RUN
dispatch path both require `pxt.h`/PXT runtime — so its acceptance is
hardware-only, budgeted at 2-3 bench sessions, and sequenced last so a
failure there is never confounded with an unrelated regression from
tickets 001/002. `uv run pytest` runs scoped per ticket during
implementation and in full at `close_sprint`, per
`.claude/rules/source-code.md`. Every hardware claim in every ticket's
acceptance criteria must carry a MEASURED citation naming its capture
file, board, and date (`.claude/rules/measurement-citations.md`) — no
exceptions, including for a "confirmed unchanged" re-check.

## Architecture

**Substantial** — this sprint touches 3+ modules
(`src/comms/protocol.{h,cpp}`, `src/comms/wire_adapter.{h,cpp}`,
`src/platform/nezha_port.cpp`, `src/blocks/run.ts`/`shims.cpp`'s RUN
dispatch seam) and introduces a new cross-module dependency (the
protocol fiber calling directly into the TS action dispatcher,
`runAction0()` — carried over unimplemented from sprint 026's own
substantial-tier design). Full detail lives in this sprint's `design/`
overlay per `design_docs_opt_in` (Project.design_docs_opt_in is
`True`): `clasi/sprints/028-.../design/DESIGN.md` (the edited copy of
`src/DESIGN.md` §§5, 7, 8, 9 — wire adapter, hardware ports, protocol
composition, shim/blocks) and `clasi/sprints/028-.../design/design.md`
(the edited copy of `docs/design/design.md`'s "Execution model" section
— the three-execution-model description it currently carries becomes
inaccurate once ticket 3 lands and must be corrected). This section
summarizes the three independent changes and the one scope decision
each required; see the overlay for full component diagrams, design
rationale, and migration concerns.

**1. Executor inversion** (SUC-001) reuses sprint 026's own
already-specified, unimplemented design verbatim in shape — that
sprint's Architecture section (`clasi/sprints/done/026-.../sprint.md`
§Architecture, its SUC-003) is not re-derived here, only updated for
what actually landed since: sprint 026 tickets 001-002 (VFP guard,
`run_queue.h`) and sprint 027 (protocol-owned `EmitQueue`, draining at
the top of `Protocol::run()`) are both merged; ticket 003 — the actual
collapse of `RUN:` motion off its MessageBus-forked fiber onto the
protocol fiber, via a `motionOwner_` arbitration field and a
tick-loop service hook — was deferred at 026 and is this sprint's item
1, unchanged in design from that record.

**2. Frozen-encoder fix** (SUC-002) — **scope decision: lives entirely
in the platform layer (`src/platform/nezha_port.cpp`), not the
vendored kernel (`src/core/diffdrive.{h,cpp}`), which stays
byte-identical.** Investigation for this planning pass traced the
actual defect precisely: `DifferentialDrive::refreshSample()` (the
vendored kernel) already has a correct hold-gate — it only recomputes
`sample.velocity` when `motor.sampleTime() != sample.sampleTime`, and
`NezhaMotorPort::collect()`'s existing I2C-failure branch already
withholds a fresh `sampleTimeUs_` stamp on an outright read failure, so
that specific case already holds correctly today. The gap is a
DIFFERENT, adjacent case the port does not yet flag: a *successful*
I2C transaction (the bus ACKs, `readEncoderRaw()` returns `true`) that
returns the SAME raw register value as the previous tick while the
wheel is under active drive — `src/DESIGN.md` §7's "encoder wedge"
(an instant H-bridge flip latching the 0x46 readback) is one documented
mechanism for this, though the fix does not need to name the cause to
correct the symptom. In this case `collect()`'s success branch DOES
advance `sampleTimeUs_`, so the kernel's hold-gate does not fire, and
`refreshSample()` faithfully computes `(pos - lastPos) / dt = 0` — a
real zero, honestly derived from stale-but-successfully-read data. The
fix: `collect()` gains one more condition alongside the existing
read-failure branch — when a successful read returns raw counts
unchanged from the last sample AND the wheel is under nonzero applied
duty (reusing the wedge detector's existing "driven" signal,
`appliedDuty()`, at a single-tick threshold rather than the multi-tick
`kWedgeThreshold` the latched/suspect flags use), withhold the fresh
`sampleTimeUs_` stamp for that tick exactly as the failure branch
already does. This makes the kernel's existing, unmodified gate hold
the previous velocity for free, and — because `i2cFaultCount_`
increments on precisely the same condition (`sampleTime` failing to
advance) — the frozen tick becomes visible in `i2cf` too, which today
it is not (a secondary, desirable side effect the issue explicitly
asked for: "the failure should stay visible"). A wheel legitimately at
rest is unaffected: rest is only detected as "driven and unchanged,"
never "undriven and unchanged," so a real stop still advances
`sampleTimeUs_` and correctly reads velocity 0 every tick, and does not
newly tick `i2cf` on an idle bus (the separate, explicitly out-of-scope
`i2c-fault-count-climbs-on-idle-bus` issue).

**3. Frame-zeroing verb** (SUC-003) — **wire-grammar decision: a
write-triggered `SET` pseudo-field (`rebase`), not a new top-level
verb.** `radio-robot-lib/docs/design/protocol.md` §7 states the shared
library "stores no configuration" and owns only the generic `GET`/`SET`
mechanism; field names under it are project-local (this project's own
`kFields` table, `wire_adapter.cpp`), so adding one needs no protocol.md
change and no cross-repo grammar negotiation — the exact path sprint
007's `stall_clear` (ordinal 17) already proved for a write-triggered
action "wearing a config-field's clothes." A new top-level verb (the
issue's other candidate, a dedicated `REBASE`) would instead require
extending `WireHandler::kCommandTable` (currently a drift-tested
18-entry table shared in shape, if not in content, with
radio-robot-lib's own verb registry) and coordinating that addition
across repos — avoidable complexity this sprint does not need. The
issue's flagged candidate — a sequenced `ESTOP` clear riding in the
same ticket — is accepted using the identical `SET estop_clear`
pattern, reusing the same mechanism rather than adding a second new
concept; ticketing below keeps it as one ticket's scope, not a
commitment to ship it if the wire-grammar review below finds a reason
not to.

### Design Rationale

See the `design/` overlay (`DESIGN.md`'s own Design Rationale
subsection) for the full Decision/Context/Alternatives/Consequences
write-ups, carried over from sprint 026 for item 1 and newly authored
for items 2 and 3 above.

### Migration Concerns

- **No data migration** for any of the three items — no persisted
  state changes shape; the RUN queue and emit queue are both in-memory
  only (unchanged from sprints 026/027).
- **Sequencing within this sprint**: items 2 and 3 are independent of
  each other and of item 1, and are host-testable — do them first.
  Item 1 (executor inversion) is hardware-only and should be ticketed
  last, per the roadmap's own explicit sequencing note.
- **Cross-repo**: item 3's `SET rebase`/`SET estop_clear` fields need
  no radio-robot-lib change (see Architecture above) — this is a
  deliberate scope-reducing decision, not an oversight, and should not
  be second-guessed mid-ticket without re-opening this section.
- **Kernel stays byte-identical**: item 2's scope decision means no
  cross-repo kernel resync is needed against radio-robot-firm's own
  fidelity suite (`src/DESIGN.md` §2's vendoring invariant) — verify
  `git diff` on `src/core/diffdrive.{h,cpp}` is empty at every
  ticket's close.
- **Prerequisite**: per the roadmap, this sprint does not start until
  sprint 027 is hardware-confirmed on master — true as of this
  planning pass (027 is closed and merged).
- **Archaeology marker budget**: `test_archaeology_marker_budget.py`
  has historically run at or near zero slack (388/388 as of sprint
  026) — new source comments must describe mechanisms, not cite
  sprint/ticket/`R-NN`/`.md` provenance.

## Use Cases

Substantial sizing (see Architecture below) — four use cases, one per
closable defect plus one for the arbitration edge the executor
inversion introduces. None has a parent in `docs/design/usecases.md`:
all four are internal firmware execution-model/control-loop/wire
guarantees, the same category sprint 026's SUC-001–003 and sprint 027's
SUC-001–002 used, not student-facing block API behavior.

### SUC-001: RUN dispatch and wire motion run on one deliberate execution model
Parent: None — internal firmware concurrency/execution-model guarantee;
no existing UC in `docs/design/usecases.md` covers which fiber executes
which command class. Carried forward from sprint 026's SUC-003
(deferred there, not re-derived here — see Architecture below).

- **Actor**: The protocol fiber itself, arbitrating between a wire
  `MOVE_X`/`GO_TO_*` request and a dispatched RUN job; a host sending
  `RUN:abort` while a job is running.
- **Preconditions**: Sprint 026 ticket 001 (VFP guard) and ticket 002
  (RUN queue) are hardware-confirmed; sprint 027's `EmitQueue` is
  merged (both true as of this sprint's start — see Goals).
- **Main Flow**:
  1. `Protocol::run()`'s loop drains `emitQueue_`, then services one
     wire read/telemetry pass (`serviceOnce()`-shaped, but the existing
     loop body, not a new extraction).
  2. If a job is queued and no job is currently running, the fiber
     dequeues it and invokes the TS handler via `runAction0()` on
     itself — not a MessageBus-forked fiber.
  3. A service hook fires after `stepBusy = false` and before the
     pacing sleep, letting a running job's own `while (driveTick())`
     tick loop advance on this same fiber, one iteration per pass.
  4. If `RUN:abort` or `RUN:clearestop` arrives, it bypasses the queue
     and takes effect immediately, regardless of what is running.
  5. A wire motion request arriving while a job holds
     `motionOwner_ == job` is arbitrated (refused with an error code,
     not silently overwritten).
- **Postconditions**: Exactly one fiber executes all engine-facing
  motion — the I2C bus-discipline invariant (`src/DESIGN.md` §7) is
  structural, not a convention three call sites must each remember.
  `RUN:abort` still stops a running job with no queue delay.
- **Acceptance Criteria**:
  - [ ] `test_run_abort_source_pin.py` (rewritten) proves abort bypasses
        the queue.
  - [ ] A host test or documented manual check confirms a wire `MOVE_X`
        arriving mid-job is arbitrated via `motionOwner_`, not silently
        overwritten.
  - [ ] `test_wire_constants_drift.py`'s now-meaningless
        `RUN_EVENT_SOURCE`/`0x2001` pin is deleted along with the event
        path it pinned.
  - [ ] Hardware: baseline (unfixed) reproduces the second-fiber
        dependency; fixed firmware runs `RUN:square:20` and
        `tests/system/run_tour.py`'s `.tour` suite unchanged, with a
        wire `MOVE_X` sent mid-tour observably refused rather than
        stomping the tour's move.
  - [ ] Not host-testable end to end (protocol.cpp/shims.cpp include
        `pxt.h`) — every criterion above marked "hardware" needs a
        robot; budget 2-3 bench sessions per the issue's own estimate.

### SUC-002: A frozen encoder read no longer manufactures a phantom velocity
Parent: None — internal control-loop correctness guarantee; no existing
UC in `docs/design/usecases.md` covers wheel-velocity derivation from
raw encoder samples.

- **Actor**: The velocity PID inside `DifferentialDrive::controlStep()`
  (vendored kernel), consuming `sampleLeft_.velocity`/
  `sampleRight_.velocity`; a bench host reading `vl`/`vr`/`i2cf` off
  telemetry.
- **Preconditions**: A wheel is under active drive (nonzero applied
  duty) when its I2C encoder select→read transaction returns the SAME
  raw counts as the previous tick — measured as the "frozen read"
  pattern (`captures/gopiv-profile-sweep-20260901/tour_tight.json`
  frames 185-191).
- **Main Flow**:
  1. `NezhaMotorPort::collect()` observes a successful read whose raw
     counts are unchanged from the prior sample while duty is nonzero.
  2. Instead of stamping a fresh `sampleTimeUs_` (which today lets the
     kernel's `refreshSample()` compute `(pos - lastPos) / dt = 0` — a
     fabricated zero-velocity sample), the port withholds the fresh
     stamp for this tick, the same way it already withholds it for an
     outright I2C failure.
  3. `DifferentialDrive::refreshSample()`'s existing
     `sampleTime != sample.sampleTime` gate (unchanged, vendored)
     therefore holds the previous tick's `sample.velocity` rather than
     recomputing.
  4. The held tick is still counted (`i2cFaultCount_`/`i2cf`) — the
     failure stays visible, per the issue's explicit requirement — via
     the same existing counter path a genuine I2C NAK already
     increments through.
- **Postconditions**: The velocity PID's error term for that tick is
  computed against the last known-good velocity, not a fabricated
  ~300 mm/s error; duty does not step toward the rail on the frozen
  tick or the tick after. `i2cf` still climbs on the frozen tick — a
  bad encoder or loose connector stays diagnosable, not smoothed away.
- **Acceptance Criteria**:
  - [ ] A host test scripts a repeated encoder position via
        `tests/host/motion_engine_shim.cpp`'s existing
        `meMotorArmPosition`/`meArmSettleProfile` and asserts commanded
        duty does not step toward the rail on the frozen tick or the
        tick immediately after.
  - [ ] A host test confirms `i2cFaultCount_` still increments on the
        frozen tick (the fix must not make the failure invisible).
  - [ ] A host test confirms a wheel legitimately at rest (zero applied
        duty, unchanged position across many ticks) still reports
        velocity 0 — the fix must not defeat a genuine stop, and must
        not be the mechanism that makes `i2cf` climb on an idle bus
        (that is the separate, explicitly out-of-scope
        `i2c-fault-count-climbs-on-idle-bus` issue).
  - [ ] Hardware: a re-run of
        `captures/gopiv-profile-sweep-20260901/tight_tour.py` on gopiv
        shows no speed excursion in the 1-2 ticks following an `i2cf`
        increment, across the same tour shapes the original capture
        used.

### SUC-003: A radio-driven tour zeros its own pose/heading frame at leg 1
Parent: None — internal wire-protocol capability; no existing UC in
`docs/design/usecases.md` covers frame zeroing over the wire (only the
local `resetPose` block and the kernel's own `rebasePosition()`, neither
wire-reachable before this sprint).

- **Actor**: A bench host or relay-connected tour script issuing the
  new verb at leg 1, before the first move; the stakeholder framing
  that surfaced the issue ("you just have to set the heading").
- **Preconditions**: The robot has booted and is idle (no live motion
  obligation, no job running — the same commandable-state gate other
  state-changing SET actions already check).
- **Main Flow**:
  1. The host sends a sequenced `SET rebase 1 #<id>` — a write-triggered
     pseudo-field on the existing `kFields`/`ConfigField` mechanism,
     the same shape `stall_clear` (ordinal 17) already established, not
     a new top-level verb.
  2. `WireAdapter`'s SET handler calls `kernel.rebasePosition()` (and,
     on an OTOS-equipped chassis, the platform layer's own pose-seed
     path so both pose sources stay agreed, mirroring `seedPose()`'s
     existing "write both" contract).
  3. The ack lands on the same `#<id>` as any other SET.
  4. Leg 1 of the tour proceeds; every subsequent pose/heading reading
     (encoder-only or OTOS) is relative to the zeroed frame.
- **Postconditions**: A tour's odometry chart is axis-aligned by
  construction, with no host-side rotation needed to read it. Works
  identically on an OTOS-equipped chassis and on an encoder-only
  chassis (tigez) — the kernel's `rebasePosition()` is the single
  mechanism either way.
- **Acceptance Criteria**:
  - [ ] A host test proves `SET rebase 1` reaches
        `kernel.rebasePosition()` (via the existing forward-declared
        `shims.cpp` seam, `WireMockAdapter`-style).
  - [ ] A host test proves the verb is sequenced (mandatory `#<id>`,
        participates in ack/nack) and refused (not silently ignored)
        while a motion obligation or RUN job is live, consistent with
        other state-changing SET actions.
  - [ ] `GET rebase` (the stall_clear-style readback convenience) is
        either a defined no-op-safe read or explicitly refused — stated,
        not left ambiguous.
  - [ ] Hardware: a tour issuing the verb at leg 1 on an OTOS-equipped
        chassis and on tigez (no OTOS) both produce an axis-aligned
        chart with no host-side rotation, verified against camera
        ground truth per `.claude/rules/playfield-testing.md`.
  - [ ] If a sequenced `ESTOP` clear (`SET estop_clear 1`, same
        pattern) rides along in this ticket: a host test proves it
        reaches `kernel.estopClear()` and is sequenced/ack'd like any
        other SET, distinct from unsequenced `ESTOP` itself.

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
| 001 | Frozen-encoder read holds the previous velocity instead of manufacturing a zero | — |
| 002 | Sequenced SET rebase (and SET estop_clear) verbs reach the kernel | — |
| 003 | Executor inversion: collapse RUN dispatch and wire motion onto one fiber | — (sequenced after 001, 002 by convention — see ticket 003's own Description for why: no functional dependency, but its hardware-only acceptance should not run against an unconfirmed 001/002) |

Tickets execute serially in the order listed.

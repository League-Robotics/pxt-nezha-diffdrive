---
id: '030'
title: Bus discipline and fiber safety
status: executing
branch: sprint/030-bus-discipline-and-fiber-safety
use-cases:
- SUC-001
- SUC-002
- SUC-003
- SUC-004
- SUC-005
issues:
- code-review/enforce-the-one-fiber-i2c-invariant.md
- code-review/service-hook-must-check-fiber-identity.md
- code-review/clear-motion-obligation-on-the-fiber-loop-and-tlm-now.md
- code-review/glitch-armor-reject-raw-zero-and-staged-cross-fiber-stop.md
- code-review/protocol-fiber-stack-high-water-mark-and-execrun-buffers.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 030: Bus discipline and fiber safety

## Goals

Make the one-fiber I2C invariant structural instead of documented and
violated. `tickDrive()` serialises `kernel.step()` behind `stepBusy` and
waits if another fiber holds it; nothing else on the OTOS bus does.
Promote `stepBusy` to a bus-ownership guard that every OTOS entry point
takes, not only the kernel; make the tick service hook check fiber
identity instead of motion-owner state so a button-handler tour during
a `RUN` job can't run the wire dispatcher on two fibers at once; clear
the wire's motion obligation on the fiber loop instead of only when a
host happens to ask; make `TLM NOW` implement-or-refuse instead of
acking and emitting nothing; reject a raw-zero encoder read explicitly
in the glitch armor; and take one measurement of the protocol fiber's
stack high-water mark under a tour, moving `execRun()`'s buffers below
its early returns regardless of what that measurement shows.

## Problem

Four independent holes let an OTOS I2C transaction land inside another
fiber's encoder select→read settle window, destroying that encoder
sample (the documented Phase-F signature): every OTOS shim entry
(`otosBegin/Read/Zero/Calibrate/SetOffset`, `seedPose`) skips the
`stepBusy` guard `tickDrive()` takes; `SET rebase` writes the OTOS from
the protocol fiber while a student's `setWheelSpeeds` + `driveTick`
loop can be inside its settle window on the main fiber; the shipped
test program runs a 10 Hz background OTOS sampler on its own fiber; the
`start drive` block forks a background ticker while `read world
position`/`set world pose`/`calibrate world sensor` sit in the palette
next to it as live bus transactions on the main fiber. Separately, the
tick service hook (`serviceHookEntry()`) gates on `motionOwner_ ==
kJob`, not on which fiber is calling — a button-handler tour during a
`RUN:tour` job runs `dispatch()` on a second fiber, which sends the ack
(a yielding write) and then executes `fields[]`, pointers into the
shared `lineBuf_`, while the other fiber's `serviceOnce()` feeds the
next line into that same buffer during the yield. `resolvePendingIfDue()`
clears the motion obligation only from `replyAck`/`replyNack`/`STATUS`,
so a host that finishes one job and sends a cleartext `RUN:tour` sees
it refused for the rest of the original job's nominal duration even
though the kernel has been idle the whole time. `TLM NOW` acks `kOk`
and emits nothing — no one-shot telemetry path exists at all. The
glitch armor accepts a destroyed sample's raw-0 read as real motion for
the first ~40 cm after a brick power-up, teleporting odometry there and
back. And the protocol fiber now hosts the whole TS job call chain with
no measured stack margin.

## Solution

One bus-ownership object: promote `stepBusy` to a guard with
`acquire()` that sleeps (through the VFP-safe sleeper) while held,
taken by `tickDrive()` and by every OTOS entry point, three lines each.
Make `rebase`'s OTOS write deferred to the ticking fiber the way
`kernel.rebasePosition()` already is. Move `test.ts`'s sampler into the
job's own tick loop. Have `startDrive`'s loop own the OTOS read (or
retire `startDrive` in favor of `whileDriving`), and document `read
world position` as a bus transaction. Capture the protocol fiber's
identity in `run()` and have `serviceHookEntry()` return unless the
current fiber matches it; decide and document whether the block
program's fiber is refused while `motionOwner_ != kNone` or given its
own owner value. Have `hasLiveMotionObligation()` call
`resolvePendingIfDue()` first (or poll it at the top of `run()`'s
loop). Give `TLM NOW` a one-shot frame path or an honest `kUnimplemented`
refusal. Reject `raw == 0` explicitly in the glitch armor when the last
good value was nonzero, and prefer a staged stop over a cross-fiber
write while `stepBusy` is held. Measure the protocol fiber's stack
high-water mark under a tour with a stack-canary build and pyOCD;
independently of what that measurement shows, move `execRun()`'s three
locals below its early returns.

## Success Criteria

- A host test with `FakeSleeper::onSleep` scripting an OTOS entry
  inside the settle window shows the entry waits until `stepBusy`
  clears; every OTOS I2C caller reaches the bus through the guard
  (source-pin test).
- A host test: a second `tickDrive()` caller during a job never runs
  `serviceOnce()`; a block-side `startMove()` during a live wire
  obligation is refused or reported, never silently superseding.
- A host test: a `MOVE_X` that completes with no further host line
  clears the obligation on the next fiber pass; `TLM NOW #n` produces
  exactly one frame pair or an honest refusal.
- `test_encoder_glitch_armor.py`: a raw 0 after a nonzero good value is
  rejected; a genuine counter restart still rebaselines.
- The stack high-water mark under a tour-plus-radio-`RUN` scenario is
  measured and recorded (or explicitly still UNVERIFIED with what was
  tried), and `execRun()`'s buffers are below its early returns
  regardless.

## Scope

### In Scope

- The bus-ownership guard (`shims.cpp`, `otos_port.cpp`) and every OTOS
  entry point it must cover.
- `SET rebase`'s deferred OTOS write; `test.ts`'s sampler relocation;
  `startDrive`'s OTOS ownership (`test/test.ts`, `blocks/motion.ts`).
- `serviceHookEntry()`'s fiber-identity check and the block-fiber
  `motionOwner_` decision (`comms/protocol.cpp`, `shims.cpp`).
- Clearing the motion obligation on the fiber loop and `TLM NOW`
  (`comms/wire_adapter.cpp`).
- The glitch armor's raw-zero rejection and staged-vs-cross-fiber stop
  preference (`platform/encoder_glitch_armor.h`, `shims.cpp`).
- The protocol-fiber stack measurement and `execRun()` buffer
  relocation (`comms/protocol.cpp` or wherever `execRun()` lives).

### Out of Scope

- Everything in sprints A (motion profile), C (test program/blocks/
  simulator), D (odometry object, config descriptor table, Protocol
  diet), E (bench tools), and F (comment work order). In particular,
  `Protocol`'s broader diet (`RunBridge`, radio gates, `routeLine()`) is
  sprint D; folding `motionOwner_`/`jobOwnsMotion_` into one flag is
  noted here as a byproduct of the fiber-identity fix where it's
  incidental, but the full consolidation is sprint D's.
- The kernel patches (K1-K5) — sprint A.

## Related Issues

- [`code-review/enforce-the-one-fiber-i2c-invariant.md`](../../issues/code-review/enforce-the-one-fiber-i2c-invariant.md)
- [`code-review/service-hook-must-check-fiber-identity.md`](../../issues/code-review/service-hook-must-check-fiber-identity.md)
- [`code-review/clear-motion-obligation-on-the-fiber-loop-and-tlm-now.md`](../../issues/code-review/clear-motion-obligation-on-the-fiber-loop-and-tlm-now.md)
- [`code-review/glitch-armor-reject-raw-zero-and-staged-cross-fiber-stop.md`](../../issues/code-review/glitch-armor-reject-raw-zero-and-staged-cross-fiber-stop.md)
- [`code-review/protocol-fiber-stack-high-water-mark-and-execrun-buffers.md`](../../issues/code-review/protocol-fiber-stack-high-water-mark-and-execrun-buffers.md)

## Test Strategy

Three of five tickets are fully host-testable because their logic is (or
becomes) a host-portable header with no `pxt.h`/CODAL dependency:

- **Ticket 001** (bus guard): `BusGuard` is a new header alongside
  `encoder_glitch_armor.h`, tested the same way — a host test scripts
  `FakeSleeper::onSleep` to fire while `BusGuard::acquire()` is mid-spin
  and asserts the caller does not proceed until `release()` runs on
  another "thread" of the test. A source-pin test (`grep -n 'uBit.i2c'`
  over `otos_port.cpp` plus a grep of `shims.cpp`'s six OTOS entry
  points) asserts every I2C caller reaches the bus through
  `acquire()`/`release()`, not by inspection alone.
- **Ticket 003** (motion-obligation clearing + TLM NOW): both changes
  live in `wire_adapter.cpp`, already covered by the existing
  `WireAdapter`/`WireMockAdapter` host harness (the same seam
  `stall_clear` and sprint 016 ticket 003's original fix were tested
  through) — a host test arms a short-timeout verb, lets it complete,
  calls `hasLiveMotionObligation()` directly (not through
  `lastDone()`), and asserts it now reads false; a second test calls
  `onTlm(kNow)` and asserts exactly one frame is queued without `mode_`
  changing.
- **Ticket 004** (glitch armor): `tests/host/test_encoder_glitch_armor.py`
  already exercises `EncoderGlitchArmor` directly — extend it with a
  raw-0-after-nonzero case and confirm the existing two-strike
  rebaseline case is unaffected. The staged-stop half needs the same
  `BusGuard`-aware host seam ticket 001 introduces to script "stop
  requested while the guard is held."
- **Ticket 005** (execRun/stack): the buffer relocation is a pure
  refactor with no behavior to assert beyond "still compiles and passes
  the existing wire-grammar host suite" (`wire_handler.cpp`'s own host
  tests already exercise `execRun()`'s RUN-verb path). The stack
  high-water-mark measurement has **no host-test substitute at all** —
  it requires a `DIFFDRIVE_FAULT_SPIN` build, pyOCD, and a real radio
  link — and is scoped as a separate, team-lead-run hardware step per
  the ticket's own split.

**Ticket 002 is the one exception with no host-test substitute for its
main claim**: `protocol.cpp` includes `pxt.h`, so `serviceHookEntry()`'s
real fiber-identity check cannot run under `tests/host/`. The
injectable "current fiber" seam is designed so a host test CAN pin the
decision logic (given fiber A's id and fiber B's id, does the hook
fire) even though it cannot exercise real CODAL fibers — write that
narrow test, but treat it as decision-logic coverage, not end-to-end
proof. End-to-end proof (a button-handler tour during a live `RUN:tour`
job no longer corrupts the wire dispatcher; a block-side `startMove()`
during a live wire obligation is refused or reported) is hardware-only.

`uv run pytest` runs scoped per ticket during implementation and in
full at `close_sprint`, per `.claude/rules/source-code.md`. Every
hardware claim in every ticket's acceptance criteria must carry a
MEASURED citation naming its capture file, board, and date
(`.claude/rules/measurement-citations.md`) — including a "confirmed
still broken at baseline" or "confirmed fixed" re-check, no exceptions.
Hardware acceptance for tickets 002 and 005 is run by the team-lead in
one scripted bench session each, not dispatched to a programmer agent
— per team direction on how this project runs on-robot acceptance
(§Architecture, item 5, above).

## Architecture

**Substantial** — this sprint touches 5+ files across three of `src/`'s
five dependency layers (`shims.cpp`/`platform/otos_port.cpp` at the
port/shim boundary, `comms/protocol.cpp`/`comms/wire_adapter.cpp`,
`core/encoder_glitch_armor.h`, plus the TS layers `test/test.ts` and
`blocks/motion.ts`/`blocks/world.ts`), well past the substantial-tier
module-count threshold. No new subsystem and no data-model change — the
five fixes tighten enforcement of invariants the codebase already
documents (bus discipline, `motionOwner_` arbitration, motion-completion
resolution) rather than introducing new ones, the same "substantial by
module count, no new composition" shape sprint 020 used. Full detail
lives in this sprint's `design/` overlay (`Project.design_docs_opt_in`
is `True`): `clasi/sprints/030-.../design/DESIGN.md` (the edited copy of
`src/DESIGN.md` §§5, 6, 7, 8 — wire adapter, transports/protocol-fiber
stack, hardware ports/bus discipline, protocol composition) and
`clasi/sprints/030-.../design/design.md` (the edited copy of
`docs/design/design.md`'s "Execution model" and "Sensor doctrine"
sections — the former's sprint-028 claim that the bus-discipline
invariant was already "structural" is corrected here: it was structural
for the kernel tick only, never for the OTOS sensor). This section
summarizes the five independent fixes; see the overlay for full
component diagrams, design rationale, and migration concerns.

**Every issue's premise was re-verified against current (post-sprint-029)
source before ticketing** — sprint A (029) landed the kernel patches and
`rearmReferences()` but touched none of this sprint's five holes, and
none had been separately closed since the 2026-09-02 review. All five
are still live defects, confirmed by reading the exact lines the issues
cite: `shims.cpp`'s `otosBegin/Read/Zero/Calibrate/SetOffset`/`seedPose`
(1551-1677) take no `stepBusy`/guard; `Protocol::serviceHookEntry()`
(protocol.cpp:457-460) still gates on `motionOwner_ == kJob`, not fiber
identity; `hasLiveMotionObligation()` (protocol.cpp:683) still reads
`motionObligationActive_` directly, never through
`resolvePendingIfDue()` (only reached from `lastDone()`/
`lastDoneReason()`, wire_adapter.cpp:875,880); `onTlm(kNow)`
(wire_adapter.cpp:963-974) still never stores a one-shot request or
emits a frame; `EncoderGlitchArmor::evaluate()`
(core/encoder_glitch_armor.h:107-130) still has no `raw == 0` branch,
only the magnitude check; `test.ts`'s OTOS sampler (808-836) is still a
free-running `control.inBackground` fiber; `execRun()`
(wire_handler.cpp:1439-1475) still declares `argv`/`result` ahead of its
first early return. No no-op tickets — every ticket below is a real fix.
One correction to the roadmap's own framing: `encoder_glitch_armor.h`
lives in `src/core/`, not `src/platform/` as the issue's own path
citation says — a stale path from before sprint 013's directory
regroup; the file's logic and the fix are unaffected.

**1. Bus-ownership guard** (SUC-001, ticket 001) — promotes `stepBusy`
from a bare `bool` on `Rig` to `BusGuard`, a small host-portable class
(`core/bus_guard.h`, alongside `encoder_glitch_armor.h`/
`heading_wrap.h` — the established pattern for extracting a piece of
`shims.cpp`'s logic into something `tests/host/` can exercise directly
against `FakeSleeper::onSleep`) with `acquire(Sleeper&)`/`release()`.
Every OTOS entry point in `shims.cpp` (six functions) acquires it
alongside `tickDrive()`; `SET rebase`'s OTOS write becomes a deferred
`pendingOtosZero` flag performed inside `tickDrive()`, mirroring
`kernel.rebasePosition()`'s existing deferred-request shape; `test.ts`'s
10 Hz background sampler moves into the job's own tick loop;
`startDrive`'s background loop (`blocks/motion.ts`) gains its own
periodic `readWorld()` call inside the loop it already runs, rather than
leaving that OTOS read for some other, ungated fiber to make.

**2. Fiber identity + third motion owner** (SUC-002, ticket 002) — two
related gaps, one root cause (a CODAL `MessageBus` handler is a THIRD
fiber `motionOwner_`'s `kNone/kWire/kJob` split never accounted for).
`serviceHookEntry()` starts checking which fiber is calling
(`currentFiber() == protocolFiberId_`, an injectable seam for host
tests) instead of `motionOwner_`'s value, so a second fiber calling
`tickDrive()` during a job never runs `serviceOnce()` again, full stop.
**Decision**: `motionOwner_` gains a fourth value, `kBlock`, taken by
the block-motion entry points (`startMove`/`startGoTo`/`driveTwist`/
`startDrive`) rather than refusing them outright — test.ts's existing
button-triggered tours are a real, working, idle-time use case that a
blanket refusal would regress. A wire verb arriving while
`motionOwner_ == kBlock` is refused the same `kBusy` a job-held
drivetrain already answers with. `motionOwner_`/`jobOwnsMotion_`'s
pre-existing duplication (CM-14) folds into this one field as a
byproduct.

**3. Motion-obligation clearing + TLM NOW** (SUC-003, ticket 003) —
`hasLiveMotionObligation()` (the one check `protocol.cpp`'s `run()`
loop already makes every pass) calls `resolvePendingIfDue()` first, so
a finished-but-unpolled obligation clears on the very next fiber pass
instead of only when a host happens to call `lastDone()`/
`lastDoneReason()`/`STATUS`. Additive to sprint 016 ticket 003's fix,
not a replacement — that fix still resolves eagerly for a host that
polls; this closes the case where nothing does. `TLM NOW` gets a real
one-shot path (`oneShotDue_`, checked in `serviceOnce()` alongside
`telemetryEnabled()`, emitting exactly one `thdr`+`t` pair without
touching `mode_`) rather than acking `kOk` and doing nothing.

**4. Glitch armor: explicit raw-zero rejection + staged stop**
(SUC-004, ticket 004) — `EncoderGlitchArmor::evaluate()` gains a
condition ahead of the existing magnitude check: `raw == 0 &&
lastGoodRaw_ != 0` returns `kRejectPending` unconditionally, closing the
~40 cm post-power-up window where a destroyed zero read sat within
`kMaxDeltaCounts` of a small `lastGoodRaw` and was silently accepted.
Separately, `deliverStopNow()`/the watchdog now stage a stop (a
`pendingStop_` flag delivered by the busy fiber itself, at the same
point `tickDrive()` already delivers a post-move settle stop) rather
than writing the motor register across a held `BusGuard` — the
not-busy case (the overwhelming majority of stops) is unchanged, an
immediate write.

**5. Protocol-fiber stack margin** (SUC-005, ticket 005) —
`execRun()`'s `sanitized`/`buf` locals move below the early returns
they already follow textually but not stack-allocation-wise; `result`
moves to a member if that alone doesn't shrink the pre-refusal
high-water mark enough. This is unconditional — it ships regardless of
what the paired hardware measurement (a `DIFFDRIVE_FAULT_SPIN`
stack-canary build, one `RUN:tour` plus a radio `RUN x #1` mid-tour,
high-water mark read by pyOCD) finds. That measurement is
hardware-only, budgeted as a single team-lead-run scripted bench
session, not a programmer-agent dispatch cycle — established team
practice for on-robot acceptance (no checked-in rule file states this;
it is carried forward from how prior sprints' hardware-only tickets
were actually run) — see ticket 005's own split between its
host-completable code change and its hardware-only measurement step.

### Design Rationale

See the `design/` overlay's own Design Rationale content (embedded in
each edited section rather than a separate subsection, matching
`src/DESIGN.md`'s existing per-section prose style) for the
Decision/Context/Alternatives/Consequences reasoning behind: promoting
`stepBusy` to a host-portable `BusGuard` rather than leaving it an
inline `Rig` field; choosing `kBlock` ownership over a blanket refusal
for the block program's fiber; making `hasLiveMotionObligation()`
self-resolving rather than adding a new poll site to `run()`'s loop;
and rejecting raw-zero unconditionally rather than only when it is
ALSO the larger of two candidate magnitudes.

### Migration Concerns

- **No data migration** — every change is in-memory control-flow/state-
  machine behavior; no persisted state changes shape.
- **Kernel stays byte-identical** — none of the five fixes touch
  `src/core/diffdrive.{h,cpp}`; verify `git diff` on those two files is
  empty at every ticket's close, same standing check sprint 028's
  Migration Concerns established.
- **Sequencing**: tickets 001 and 004 both touch `shims.cpp`'s Rig
  struct and `tickDrive()`'s immediate vicinity (the guard, and the
  staged-stop flag) — 004 is sequenced after 001 so the staged-stop
  fix is written against the guard's final shape, not against the bare
  `stepBusy` bool it replaces. Ticket 002 touches `protocol.cpp`'s
  `run()`/`serviceHookEntry()` and `blocks/motion.ts`'s `startDrive` —
  both also touched by ticket 001 (OTOS ownership inside that same
  loop) — sequenced after 001 for the same reason. Ticket 003 touches
  the same `run()` loop's `hasLiveMotionObligation()` call site ticket
  002 already edited; sequenced after 002. Ticket 005 is fully
  independent (wire_handler.cpp stack layout only) and is sequenced
  last because it is Low priority (issue triage #17) and its own
  measurement step is a separate, team-lead-run hardware session that
  should not gate or be confounded with the other four.
- **Host-testability split**: tickets 001, 003, 004, 005's code half are
  host-testable (new host-portable headers, or existing
  `WireAdapter`/`WireMockAdapter`/`WireHandler` seams). Ticket 002 is
  **not** host-testable end to end — `protocol.cpp` includes `pxt.h` —
  though the fiber-identity seam is designed to be injectable so its
  *decision logic* can still get a host test; full verification is
  hardware-only. See Test Strategy below.
- **No cross-repo impact** — nothing here touches `radio-robot-lib`'s
  wire grammar (no new verb, no new field name) or the vendored kernel.

## Use Cases

Substantial sizing (see Architecture above) — five use cases, one per
independently-closable defect, the same category sprint 026's
SUC-001-003, sprint 027's SUC-001-002, and sprint 028's SUC-001-003
used: internal firmware execution-model/bus-discipline/wire guarantees,
not student-facing block API behavior. None has a parent in
`docs/design/usecases.md` — that document's sixteen UCs describe what a
student's block program can do, not which fiber safely does the I2C
transaction underneath it.

### SUC-001: Every OTOS transaction is serialized against the kernel tick
Parent: None — internal I2C bus-discipline invariant; no existing UC
covers fiber/bus ownership underneath the student-facing pose blocks
(UC-009 "Read Robot Pose" describes the block-level contract this
protects, but says nothing about the bus).

- **Actor**: Any fiber that can reach an OTOS entry point — the
  protocol fiber (`SET rebase`), a job's tick loop, a background
  sampler fiber, or the main/block fiber (`readWorld()`/`seedPose()`/
  `calibrateWorldSensor()`).
- **Preconditions**: `tickDrive()` is mid-`kernel.step()`, inside one of
  the two settle sleeps between the Nezha encoder's select and read.
- **Main Flow**:
  1. A second fiber calls any OTOS entry point (`otosBegin/Read/Zero/
     Calibrate/SetOffset`, `seedPose`) or triggers `SET rebase`'s OTOS
     write.
  2. `BusGuard::acquire()` finds the guard held and sleeps (via the
     VFP-safe sleeper) in a short timed poll rather than issuing I2C.
  3. `tickDrive()` finishes its step, releases the guard.
  4. The waiting fiber's OTOS transaction proceeds, now guaranteed not
     to land inside the encoder's settle window.
- **Postconditions**: No encoder sample is ever destroyed by a
  concurrent OTOS transaction, regardless of which fiber or code path
  issued it — the invariant `src/DESIGN.md` §7 has documented since
  sprint 013 is now enforced at every entry point, not assumed.
- **Acceptance Criteria**:
  - [ ] A host test with `FakeSleeper::onSleep` scripting an OTOS entry
        inside the settle window shows the entry waits until the guard
        clears.
  - [ ] A source-pin test asserts every `otos_port.cpp` I2C caller and
        every `shims.cpp` OTOS entry point reaches the bus through
        `BusGuard::acquire()`/`release()`.
  - [ ] `test.ts` has no `control.inBackground` block that touches the
        OTOS.
  - [ ] Hardware: a bench run with a wire-issued OTOS read scripted to
        fire during a live drive shows no encoder-sample corruption
        (`i2cf` does not climb) where the unfixed build reproduces it.

### SUC-002: A wire dispatch in flight is never run on two fibers at once
Parent: None — internal firmware concurrency guarantee; no existing UC
covers which fiber executes the wire dispatcher.

- **Actor**: The protocol fiber, mid-`serviceOnce()`/`dispatch()`
  (yielding on an ack write) while a `RUN:tour` job is live; a
  button-handler (MessageBus) fiber calling `tickDrive()` concurrently;
  a block program directly calling `startMove()`/`driveTwist()`/
  `startDrive()` while a wire motion obligation is live.
- **Preconditions**: A `RUN` job or a wire motion verb currently holds
  `motionOwner_`.
- **Main Flow**:
  1. A second fiber (a button handler, or the block program's own top-
     level code) calls `tickDrive()` or a block-motion entry point.
  2. `serviceHookEntry()` checks `currentFiber() ==
     protocolFiberId_` — false for this caller — and returns without
     calling `serviceOnce()`, regardless of what `motionOwner_` says.
  3. If the caller is a block-motion entry point, `motionOwner_` is
     checked before it takes effect: `kNone` — it takes `kBlock`
     ownership and proceeds; `kWire`/`kJob` — it is refused/reported,
     never silently superseding the live motion.
- **Postconditions**: The wire dispatcher's shared `lineBuf_` is never
  touched by two fibers in the same window; a wire host's completion
  channel (`lastDone()`/`lastDoneReason()`) never silently resolves a
  motion it did not itself end.
- **Acceptance Criteria**:
  - [ ] A host test (decision-logic only, via the injectable
        current-fiber seam) confirms a non-protocol fiber's `tickDrive()`
        call never invokes `serviceOnce()`.
  - [ ] A host test confirms a block-side `startMove()` while
        `motionOwner_ == kWire` is refused or reported, never silently
        superseding.
  - [ ] Hardware: a button-handler tour running during a live
        `RUN:tour` no longer corrupts wire dispatch (MEASURED against
        the pre-fix reproduction and the fixed build, same board, same
        scenario).

### SUC-003: A finished motion clears its obligation without a host asking, and TLM NOW answers
Parent: None — internal wire-protocol completion-channel guarantee; no
existing UC covers what happens between a move finishing and the next
command being accepted.

- **Actor**: A host that sends a timed motion verb, observes completion
  by some means other than polling `STATUS`/`lastDone` (e.g. watching
  the robot, or a fixed sleep), then sends a cleartext `RUN:tour`; a
  host that wants one pose fix with telemetry off.
- **Preconditions**: A wire motion verb's own goal or lease has already
  been reached; no host has since called `lastDone()`/`lastDoneReason()`
  /`STATUS`.
- **Main Flow**:
  1. `protocol.cpp`'s `run()` loop calls `hasLiveMotionObligation()` on
     its next pass, as it already does every pass.
  2. `hasLiveMotionObligation()` calls `resolvePendingIfDue()` first;
     the already-finished motion resolves and `motionObligationActive_`
     clears.
  3. `motionOwner_` drops back to `kNone` on this same pass;
     `dispatchJob()`'s `motionOwner_ != kNone` gate no longer refuses
     the next `RUN:tour`.
  4. Separately, a host sends `TLM NOW #n` with telemetry off;
     `onTlm()` sets `oneShotDue_`; the next `serviceOnce()` pass emits
     exactly one `thdr`+`t` pair without changing `mode_`, then clears
     the flag.
- **Postconditions**: A finished motion never blocks a later command
  for longer than one fiber pass past its own completion; a host can
  get one pose fix without subscribing to a stream.
- **Acceptance Criteria**:
  - [ ] A host test arms a short-timeout verb, lets it finish, and
        confirms `hasLiveMotionObligation()` reads false on the next
        call with no intervening `lastDone()`/`lastDoneReason()` call.
  - [ ] A host test confirms `TLM NOW #n` produces exactly one frame
        pair (or an honest `kUnimplemented` refusal) and does not alter
        `mode_`.
  - [ ] Hardware: a `MOVE_X ... #7` that completes early, followed by a
        cleartext `RUN:tour` with no intervening `STATUS`/`lastDone`
        poll, is accepted rather than refused for the remainder of the
        original verb's declared duration.

### SUC-004: A destroyed zero-count encoder read never teleports odometry
Parent: None — internal control-loop correctness guarantee; no existing
UC covers raw-encoder-counts plausibility.

- **Actor**: `NezhaMotorPort::collect()`'s caller (the kernel's
  `refreshSample()`) consuming `EncoderGlitchArmor::evaluate()`'s
  decision; a bench host reading position/velocity off telemetry in the
  first ~40 cm after a brick power-up.
- **Preconditions**: The encoder counter has never been device-reset
  (measured behavior); a bus collision or power-up glitch produces a
  raw `0` read while `lastGoodRaw_` is still small (within
  `kMaxDeltaCounts` of 0).
- **Main Flow**:
  1. `evaluate(0)` is called with `lastGoodRaw_` nonzero and small.
  2. The new `raw == 0 && lastGoodRaw_ != 0` check fires ahead of the
     magnitude comparison and returns `kRejectPending` unconditionally.
  3. The caller holds position/velocity at the last known-good value
     for this tick, exactly as any other `kRejectPending` outcome
     already does.
  4. A genuine counter restart (two consistent implausible readings)
     still reaches `kAcceptAsRebaseline` through the unchanged
     two-strike path.
- **Postconditions**: Odometry never jumps toward 0 and back from a
  destroyed zero read during the vulnerable post-power-up window; a
  real two-reading-consistent restart still rebaselines correctly.
- **Acceptance Criteria**:
  - [ ] `test_encoder_glitch_armor.py`: a raw 0 after a nonzero good
        value is rejected (`kRejectPending`), regardless of magnitude.
  - [ ] `test_encoder_glitch_armor.py`: the existing two-strike
        rebaseline case (two consistent implausible non-zero readings)
        is unaffected.
  - [ ] Hardware: a cold-power-up bench run shows no position jump in
        the first ~40 cm of travel (MEASURED against the pre-fix
        reproduction).

### SUC-005: The protocol fiber's stack margin under the sprint 028 call chain is known and its worst locals are minimized
Parent: None — internal firmware resource-safety guarantee; no existing
UC covers stack margin (the closest documented precedent is the
radio-transport scratch-buffer overflow `src/DESIGN.md` §6 already
records as measured, pre-sprint-004).

- **Actor**: The protocol fiber itself, executing the full sprint-028
  call chain (`run()` → `serviceOnce()` → `dispatchJob()` →
  `runAction0()` → student handler → `tickDrive()` → service hook →
  `serviceOnce()` → `drainEmitQueue()` → `emitLineNow()` →
  `sendLine()`) with a `RUN` verb's `execRun()` locals live partway
  through it; the team-lead running the paired hardware measurement.
- **Preconditions**: A `DIFFDRIVE_FAULT_SPIN` stack-canary build is
  flashed; pyOCD is attached.
- **Main Flow**:
  1. `execRun()`'s `sanitized`/`buf` locals are moved below the
     `outcome != kOk`/`!hasResult` early returns they textually follow;
     `result` moves to a member if needed to further shrink the
     pre-refusal footprint.
  2. The team-lead runs one full `RUN:tour` plus a `RUN x #1` sent over
     radio mid-tour on the canary build.
  3. pyOCD reads the stack high-water mark.
- **Postconditions**: The relocation ships regardless of the
  measurement's outcome; the measurement is recorded as MEASURED (with
  its capture artifact, board, and date) or explicitly UNVERIFIED with
  what was tried — never silently omitted.
- **Acceptance Criteria**:
  - [ ] `execRun()`'s locals are below its early returns (or moved to
        members); the existing wire-grammar host suite still passes
        unchanged.
  - [ ] Hardware (team-lead session): the high-water mark under the
        tour-plus-radio-`RUN` scenario is measured and recorded with a
        MEASURED citation, or the ticket explicitly states UNVERIFIED
        and what was tried.

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
| 001 | Bus-ownership guard on every OTOS entry point | — |
| 002 | Fiber-identity check on the tick service hook; kBlock motion owner | 001 |
| 003 | Self-resolving motion obligation and a real TLM NOW | 002 |
| 004 | Glitch armor: explicit raw-zero rejection and staged cross-fiber stop | 001 |
| 005 | execRun buffer relocation and protocol-fiber stack high-water mark | — |

Tickets execute serially in the order listed.

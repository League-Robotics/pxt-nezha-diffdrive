---
id: '030'
title: Bus discipline and fiber safety
status: roadmap
branch: sprint/030-bus-discipline-and-fiber-safety
use-cases: []
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

(Describe the overall testing approach for this sprint: what types of tests,
what areas need coverage, any integration or system-level testing needed.)

## Architecture

Not yet written — this sprint is in Roadmap Mode. Architecture (sized
per the effort decision) is produced when this sprint is detail-planned.

### Architecture Overview

(High-level structure and component relationships, if applicable.)

### Design Rationale

(Significant decisions with alternatives considered and reasoning, if
applicable.)

### Migration Concerns

(Data migration, backward compatibility, deployment sequencing — or
"None" if not applicable.)

## Use Cases

Not yet written — produced at detail-planning time, sized to the
change.

### SUC-001: (Title)
Parent: UC-XXX

- **Actor**: (Who)
- **Preconditions**: (What must be true before)
- **Main Flow**:
  1. (Step)
- **Postconditions**: (What is true after)
- **Acceptance Criteria**:
  - [ ] (Criterion)

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

Tickets execute serially in the order listed.

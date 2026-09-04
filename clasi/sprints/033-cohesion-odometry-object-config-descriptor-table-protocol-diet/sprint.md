---
id: '033'
title: 'Cohesion: odometry object, config descriptor table, Protocol diet'
status: roadmap
branch: sprint/033-cohesion-odometry-object-config-descriptor-table-protocol-diet
use-cases: []
issues:
- code-review/odometry-object-and-kernel-rearm-references.md
- code-review/config-descriptor-table-softstop-goto-deadline.md
- code-review/protocol-diet-runbridge-radio-enable-routeline.md
- code-review/wire-minors-telemetry-terminator-rx-counters-seq-wrap.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 033: Cohesion: odometry object, config descriptor table, Protocol diet

## Goals

Close the three biggest cohesion losses the last two sprints introduced.
Odometry becomes one object (`Odometry`, host-portable) that directly
implements `PoseSource` instead of being spread across `Rig`'s
`x/y/heading`/`odomPos*`/`odomPrimed`/two epochs, a free `odomUpdate()`
function, and `EncoderPoseSource`'s 45-line lifetime essay holding
`const float&` into `Rig`; the kernel gains `rearmReferences()` so the
engine's rebase-epoch guard (written three times today) collapses to
one. The config surface — five hand-synchronised ordinal tables
(`setKernelValue`, `getConfigValue`, `WireAdapter::kFields`,
`ConfigField`, `diagValue`) — becomes one descriptor table the switches
and `kFields` read from, `Rig::softStop()` replaces four copies of the
soft-stop triplet, and the go-to timeout becomes an ordinary config
field instead of per-call singleton state dodging PXT's 4-argument
shim limit. `Protocol` goes on a diet: the cleartext RUN bridge becomes
a separable, host-tested `RunBridge`; the three scattered radio-enable
gates move onto `RadioTransport` itself; `routeLine()` replaces the
copy-pair serial/radio poll branches and the two identical
strip-a-trailing-byte sinks; `motionOwner_`/`jobOwnsMotion_` collapse
to one flag; the vestigial two-writer guards and retries (dead since
the emit ring made the protocol fiber the sole producer) are deleted.
Alongside these three, the wire-protocol minors: the telemetry
terminator/strip-check bug that can silently truncate a plausible
number, the single-line-per-pass RX drain with dead counters, an
uncounted `handleRun()` refusal path, the sequence-id wrap guard, and
`GET rebase` answering "unknown name" for an advertised field.

## Problem

`Rig` holds pose state directly; `odomUpdate()` is a free function over
it; `EncoderPoseSource` holds `const float&` references into `Rig` with
a lifetime essay explaining why that's safe; `resetPose()`, `seedPose()`,
and `SET rebase` are three writers with three different pre-steps;
`poseX()` mutates state as a side effect of reading. The rebase-epoch
guard this forces is written in `odomUpdate()`, `serviceMove()`, and
`progress()` — three copies of one fact. The config surface's five
tables must be hand-kept in sync; `protocol.h:281`'s "ordinal 30"
comment error is the direct cost of that duplication (the true count is
28; 30 is a different field entirely). The soft-stop triplet
(`engine.endMove` + `kernel.neutral` + `deliverStopNow`) is written out
in `stopAll`, `endMove`, the watchdog, and `updateMove` — four places
that must agree. `pendingGoToDeadlineMs_` lives on the singleton purely
to dodge a 4-argument shim limit. `Protocol` has grown a RUN bridge, a
motion arbiter, and three radio gates that belong on `RadioTransport`
(which already self-enables lazily); both transports carry two-writer
guards and retries whose comments still describe a TS-fiber writer that
hasn't existed since the emit ring shipped. Smaller: `emitHeader()`/
`emitFrame()` drop their trailing `\n` at exactly 239 bytes and both
sinks strip the last byte blind regardless, turning a plausible number
wrong; only one inbound line is drained per transport per pass with
silent overflow/drop and dead RX counters; `handleRun()`'s refusals
(overlong/non-printable/empty payloads) are uncounted and the 400 ms
dedupe eats a repeated `abort`; `expectedNext_` wraps at `UINT32_MAX`
with no guard; `GET rebase` has no read path.

## Solution

`Odometry` class (`src/motion/` or `src/platform/`) with `update(const
Output&)`, `reset()`, `seed(x, y, h)`, implementing `PoseSource`
directly — retiring `EncoderPoseSource`, its lifetime essay, and the
`Rig` pose fields; `odomUpdate()`'s math moves unchanged into
`Odometry::update()` with a host test that integrates a known wheel
path; one epoch guard lives inside `Odometry`, and the engine's two
copies go away as a byproduct of sprint A's lazy-origin-capture design
(this sprint's `Odometry` work depends on that having landed, per the
issue's own dependency note) plus the kernel's new `rearmReferences()`.
Decide once whether pose reads advance odometry (today three call
sites disagree). For config: one descriptor table `{name, ordinal, get,
set, unit}` in `shims.cpp` that both switches and `kFields` read from;
`ConfigField` generated from it where PXT can't import directly (a
script plus a drift test); `Rig::softStop()` replacing the four soft-stop
copies; the go-to timeout as an ordinary field in the same table. For
`Protocol`: `RunBridge` (host-portable like `RunQueue`) with `offer()`,
`dispatchOne()`, `currentText()`, dedupe and bypass rules host-tested
in isolation; `RadioTransport::enable()/enabled()` with `sendLine`/
`tryReceiveLine` returning false while disabled, retiring the three
scattered gates; `routeLine(handler, buf, len)` and one `TransportSink`
so both transports hand off an already-terminated line without a
strip-and-re-append round trip; one `nowMs()`; one owner flag replacing
`motionOwner_`/`jobOwnsMotion_`; deletion of `sending_` and the
transports' vestigial retries, with drop counters kept and the four
comment blocks rewritten to state the single-writer reality. For the
wire minors: bound the frame append at `sizeof - 2` and write `\n`
last, with both sinks checking the terminator before stripping (extend
the pathological-239-byte-frame test); drain up to N lines per
transport per pass and wire or delete the dead RX counters; one
`runMalformed_` counter with bypass names exempted from the dedupe;
guard the sequence-id wrap; give `GET rebase` a real read path or a
documented write-only refusal code.

## Success Criteria

- `grep -n positionEpoch src/motion src/shims.cpp` finds one reader.
- Every wire config name round-trips through SET/GET in a host test;
  every ordinal has exactly one definition; `grep -c 'deliverStopNow'
  src/shims.cpp` is 1.
- `Protocol` is composition plus `run()`; `RunBridge` has its own host
  tests independent of `Protocol`.
- The extended pathological-239-byte-frame test asserts the terminator
  survives; RX drop/accept counters actually increment; the sequence-id
  wrap is guarded; `GET rebase` answers correctly or with a documented
  refusal code instead of "unknown name".

## Scope

### In Scope

- `Odometry` object, `EncoderPoseSource` retirement (`src/motion/` or
  `src/platform/`, `src/core/rig.*`).
- Kernel `rearmReferences()` (`src/core/diffdrive.*`) — coordinate with
  sprint A since both touch the kernel; if sprint A's K4 already lands
  `rearmReferences()`, this sprint consumes it rather than re-adding it.
- Config descriptor table, `Rig::softStop()`, go-to deadline as a
  config field (`shims.cpp`, `wire_adapter.cpp`, `blocks/*.ts`
  `ConfigField`).
- `Protocol` diet: `RunBridge`, `RadioTransport` enable/enabled,
  `routeLine()`, one sink, one owner flag, vestigial guard deletion
  (`comms/protocol.*`, `comms/radio_transport.*`,
  `comms/serial_transport.*`, `comms/run_bridge.*` new).
- Wire minors: terminator/strip-check, RX drain and counters,
  `handleRun()` refusal counter, sequence-id wrap guard, `GET rebase`
  (`comms/wire_adapter.*`).

### Out of Scope

- Everything in sprints A (motion profile — including the kernel patches
  K1-K5, which this sprint's `rearmReferences()` work depends on having
  landed or landing concurrently), B (bus/fiber safety — the
  bus-ownership guard and fiber-identity check are separate from this
  sprint's `Protocol` diet, though both touch `protocol.cpp`), C (test
  program/blocks/simulator), E (bench tools), and F (comment work
  order).
- The one-fiber I2C invariant and the tick-service-hook fiber check —
  sprint B.

## Related Issues

- [`code-review/odometry-object-and-kernel-rearm-references.md`](../../issues/code-review/odometry-object-and-kernel-rearm-references.md)
- [`code-review/config-descriptor-table-softstop-goto-deadline.md`](../../issues/code-review/config-descriptor-table-softstop-goto-deadline.md)
- [`code-review/protocol-diet-runbridge-radio-enable-routeline.md`](../../issues/code-review/protocol-diet-runbridge-radio-enable-routeline.md)
- [`code-review/wire-minors-telemetry-terminator-rx-counters-seq-wrap.md`](../../issues/code-review/wire-minors-telemetry-terminator-rx-counters-seq-wrap.md)

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

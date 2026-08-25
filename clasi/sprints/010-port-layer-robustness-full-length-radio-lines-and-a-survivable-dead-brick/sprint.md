---
id: '010'
title: 'Port-layer robustness: full-length radio lines and a survivable dead brick'
status: roadmap
branch: sprint/010-port-layer-robustness-full-length-radio-lines-and-a-survivable-dead-brick
use-cases: []
issues:
- radio-rx-capacity-fragmentation.md
- unpowered-nezha-brick-wedges-program-at-boot.md
- get-full-duty-velocity-returns-garbage.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 010: Port-layer robustness: full-length radio lines and a survivable dead brick

> **Arc position.** Sixth planned sprint out of the 2026-08-23 code
> review (`docs/code-review/2026-08-23/review.md`), after sprint 004
> (radio/wire transport, ticketing), sprint 005 (bench tooling, roadmap),
> sprint 006 (motion correctness, roadmap), sprint 007 (student API,
> roadmap), sprint 008 (wire hardening, roadmap), and sprint 009
> (hygiene, roadmap). Numbering is not a recommendation to run this
> sprint's radio-capacity half last: `radio-rx-capacity-fragmentation.md`
> is the deferred remainder of sprint 004's own goal — sprint 004's Out
> of Scope entry states plainly that Phase A "changes the GRAMMAR radio
> speaks, not how much of it fits in one fragment," and that a v6 line
> whose formatted length exceeds the single 64-byte fragment "does not
> fail cleanly today." Put differently, "radio speaks full v6" is not
> actually true in practice until a line over ~64 bytes is either
> reachable or loudly refused, so this half wants to run soon after 004,
> not wherever its sprint number happens to place it. It also shares
> `radio_transport.h`'s capacity-constant lines (`kMaxPayloadBytes`, the
> false parity comment) with sprint 008's
> `wire-constants-single-source.md`, which unifies those same lines into
> one shared constant with drift protection — a different concern (the
> *values* staying in sync) from this sprint's (the RX *capacity model*
> itself), but the same lines of code. Whichever of the two sprints
> actually executes second must re-read those lines against what the
> first one left there before touching them again. The dead-brick half
> (`unpowered-nezha-brick-wedges-program-at-boot.md`) has no file or
> code-path overlap with any other sprint in this arc — kernel/port
> degradation on a wedged I2C bus is independent of the wire-protocol and
> motion work above and below it. The two halves are grouped into one
> sprint by *kind* — a hardware port boundary that silently lies instead
> of failing loudly, in firmware, verifiable only on a real bench — the
> same way sprint 006 grouped five independent kernel/odometry findings
> by theme rather than by shared code path.

## Goals

Two hardware port boundaries currently do something other than what they
were asked, without saying so. This sprint's job is to make each one
either do the thing or refuse it loudly:

- **Radio carries a full-length v6 line, or explicitly refuses one it
  can't.** Decide and implement one of the two directions
  `radio-rx-capacity-fragmentation.md` lays out — multi-fragment RX
  reassembly, or explicit loud rejection at the fragment boundary — so a
  v6 command over radio longer than `RadioTransport`'s current 64-byte
  single-fragment slot (`radio_transport.h:139`) never again clamps to a
  parseable *prefix* that can execute as a different, shorter, legal
  command. This choice is the central open decision this sprint hands to
  detail planning — see Solution; nothing here preordains it.
- **An unreachable Nezha brick degrades instead of hanging the program.**
  Per `unpowered-nezha-brick-wedges-program-at-boot.md`: when the brick
  is unpowered or otherwise unreachable at its first I2C touch — today,
  `kernel.begin()`'s encoder-priming reads inside the lazy `ensure()` in
  `src/shims.cpp` — the robot must come up with `connected=false`,
  `i2cFaultCount` climbing, and protocol/TLM/DIAG alive, with motion
  blocks becoming no-ops instead of the whole program hanging. Not just
  at boot: the kernel's own steady-state tick also touches I2C every
  24 ms (`cfg.cyclePeriod`), so whatever fix ships has to survive the
  brick going away *mid-session*, not only before the first move — a
  boot-only guard is not a fix.

## Problem

Both issues are the same shape of defect at two different hardware port
boundaries, which is why they are one sprint rather than two: a
`Transport`/`Motor` port that is supposed to report failure instead
silently does the wrong thing, or nothing at all, while every API above
it keeps reporting success. Concretely:

- **Radio RX** (`src/radio_transport.h`/`.cpp`): a single 64-byte
  `rxLine_` slot with no continuation framing means a v6 line encoded
  past 64 bytes either clamps to whatever prefix fits — which can parse
  as a *different*, shorter, legal command and execute it — or is
  silently dropped (`tryReceiveLine()`'s own header comment: "MORE-
  flagged fragments are dropped"). Today's short `RUN:` lines and bench
  verbs never reach this; the v6 telemetry frame, `GET`/`SET` replies,
  and `HELP` output will. Sprint 004 made radio speak the v6 *grammar*
  and explicitly declared this capacity gap out of scope, filing it as
  this issue precisely so it would not vanish along with that sprint.
- **Dead brick at the I2C boundary**: `DifferentialDrive::begin()` calls
  `left_.begin()`/`right_.begin()` (`src/diffdrive.cpp:264-265`), each of
  which runs `NezhaMotorPort::begin()`'s three-sample encoder-priming
  loop — `writeFrame()`/`readEncoderRaw()` over `uBit.i2c`
  (`src/nezha_port.cpp:48-72`). codal's NRF52 I2C driver busy-spins
  (never yields) against a bus with nothing answering, so that call
  never returns. Because CODAL's scheduler is cooperative and
  single-core, a fiber that never yields doesn't just fail its own
  caller — it stops every other fiber in the program, including the
  starvation watchdog `ensure()` launches on the very next line and
  never reaches. The kernel already has a working degrade path for a
  *fast-failing* read: `i2cFaultCount_` increments
  (`src/diffdrive.cpp:509`) whenever a tick's `refreshSample()` doesn't
  get a fresh sample. The actual defect is narrower and nastier than "no
  fault counter exists" — the counter is fine; the problem is a truly
  wedged bus never returns control to let anything, counter included,
  run at all.

Both are port-layer robustness problems at a hardware boundary, both are
firmware-only fixes, and both need a real bench check because no host
test double has ever exercised the failing path: `RadioTransport` (like
`SerialTransport`) `#include`s `pxt.h` directly with no host shim, per
sprint 004's own precedent, and `tests/host/fake_ports.h`'s `FakeMotor`
models a motor that cleanly reports `connected()==false` — not one whose
`begin()` call never returns at all. In both cases the robot currently
looks "silently not doing what you asked" rather than visibly broken: a
truncated radio command executing as something else, or a program that
never gets past the boot banner with no error anywhere in sight.

## Solution

**Radio RX — one decision, two directions, made at detail-planning
time, not here:**

1. *Multi-fragment RX reassembly* — sequence/continuation framing on top
   of the existing RadioRelay fragment format, a partial-line timeout so
   a lost middle fragment can't wedge the reassembler forever, and a
   bounded reassembly buffer. Makes radio a genuine capacity peer of
   serial; costs RAM (the protocol fiber is already documented elsewhere
   as 2 KB-tight) and adds new protocol surface — a timeout, a discard
   path — that today's grammar doesn't have.
2. *Explicit, loud rejection* — keep the single 64-byte fragment, but
   detect an over-length line at the fragment boundary and answer a
   defined `err` rather than ever clamping to a parseable prefix. Cheap
   and honest, but a real capability cut, not just better error
   handling: a radio host genuinely cannot send a `SET`/`HELP`-shaped
   line that overflows 64 bytes, full stop, by contract.

This sprint does not preordain which one ships — that tradeoff (protocol
surface and RAM vs. a hard capability ceiling) is exactly the kind of
call detail planning exists to make with fuller information. Whichever
is chosen must also resolve the issue's three-numbers question: radio RX
(64 bytes), radio TX (`kMaxPayloadBytes`, 200 bytes), and wire
(`kMaxLineBytes`, 240 bytes) end up either equal, or documented as
deliberately unequal with the consequence stated at each site — not left
as an unexplained mismatch.

**Dead brick — investigate before assuming a fix.** The issue names
three candidate directions — a codal I2C timeout option; a pre-flight
bus probe with a bounded wait before `begin()`'s priming reads; guarding
the priming path so a dead bus marks the wheel disconnected instead of
blocking — and is explicit that none is confirmed yet; this is an
investigation, not a known fix waiting to be typed in. Whichever
mechanism bounds the wait, it has to cover two call sites, not one: the
one-time `kernel.begin()` priming path `ensure()` runs on first
block/TLM use, and the steady-state `requestSample()`/`tick()` →
`collect()` I2C read that recurs every ~24 ms thereafter
(`src/shims.cpp`'s `Rig::ensure()` and tick path; `src/diffdrive.cpp`;
`src/nezha_port.cpp`). A guard that only covers boot priming leaves the
robot exposed to the identical hang the moment the brick goes away
mid-session — that would be a narrower version of the same bug, not a
fix. Detail planning should budget a dedicated investigation ticket
(confirm which of the three directions codal actually supports on this
target before committing to an implementation ticket) rather than assume
the remedy walking in.

## Success Criteria

- Radio RX has one decided, implemented behavior for an over-length v6
  line: either reassembled whole, or answered with a defined `err` —
  never executed as a truncated, different command, and never silently
  dropped with no signal. A host test drives an over-length line into
  the RX path and asserts the chosen behavior.
- The three capacity numbers (radio RX, radio TX, wire) are equal, or
  their inequality is documented with the consequence stated at each
  site.
- A bench check sends a real v6 line over 64 bytes over radio and
  confirms the chosen behavior against actual hardware, not just the
  host double.
- An unreachable/unpowered Nezha brick no longer hangs the program at
  first I2C touch: `connected=false`, `i2cFaultCount` climbing,
  protocol/TLM/DIAG alive, motion blocks no-op.
- The same degrade behavior holds when the brick goes away mid-session
  (the steady-state tick path), not only at boot.
- A bench check physically powers down or disconnects a brick on a real
  robot, both before first motion and mid-drive, and confirms the robot
  stays observable and does not hang either time.
- All new/changed host tests pass; no regression in existing
  `tests/host` coverage.

## Scope

### In Scope

- `src/radio_transport.{h,cpp}`: whichever RX capacity model detail
  planning selects (reassembly or rejection), and reconciling the three
  capacity numbers' relationship per the issue — this sprint owns that
  reconciliation, not just the chosen mechanism.
- `src/nezha_port.{h,cpp}`: the actual bus-hang guard/probe/timeout,
  whichever direction the investigation lands on.
- `src/shims.cpp` (`Rig::ensure()`'s `kernel.begin()` call, and
  `tickDrive()`'s steady-state per-cycle I2C path): whatever call-site
  plumbing the chosen remedy needs to cover both the boot-priming and
  steady-state cases.
- `src/diffdrive.{h,cpp}`: only if the chosen remedy needs a kernel-level
  contract change (e.g., `Motor::begin()`/`tick()` gaining a
  bounded-wait contract) — to be confirmed by investigation, not assumed
  here.
- Host tests: an over-length-line RX test per the issue's own
  verification note; a test that a `Motor` reporting
  `connected()==false` (via the existing `FakeMotor` double in
  `tests/host/fake_ports.h`) drives the kernel's already-existing
  no-op/`i2cFaultCount_` degrade path correctly — proving the *consumer*
  side of the fix works even though the *producer* side (an actual I2C
  hang) is bench-only.
- Two bench checks: a real >64-byte v6 line sent over radio; a physically
  unpowered or disconnected Nezha brick, exercised both before first
  motion and mid-drive.

### Out of Scope

- The line-cap **constant** unification — one shared line-capacity
  constant, drift tests, and the false `radio_transport.h` parity comment
  fix. That is sprint 008's `wire-constants-single-source.md`. This
  sprint changes the RX **capacity model**; sprint 008 changes how the
  **values** stay in sync. Whichever of the two sprints executes second
  must re-read `radio_transport.h`'s capacity-constant lines against what
  the first one left there.
- Anything in `tools/` bench tooling — sprint 005's domain.
- Any motion-behavior change (goTo geometry, stop timing, odometry) not
  caused by a disconnected motor port — sprint 006's domain.
- Any student-facing API or simulator change — sprint 007's domain.
- Detail planning, architecture, use cases, and tickets — this is a
  roadmap-phase sprint; those are produced when this sprint is
  detail-promoted.

## Test Strategy

Mostly host-testable on the radio-capacity half, mostly bench-only on the
dead-brick half — for the same underlying reason in both cases: the
actual hardware call sits beneath a seam nothing in `tests/host` shims
today. `RadioTransport`/`SerialTransport` `#include "pxt.h"` directly
(per sprint 004's precedent); `NezhaMotorPort`'s bus primitives call
`uBit.i2c` directly, and `FakeMotor` stands in only for the
already-abstract `Motor` interface, not for the I2C driver underneath
it.

- A host test constructs an over-length v6 line at the RX fragment
  boundary and asserts the chosen behavior (reassembled whole, or
  rejected with the defined error) — never "executed as a shorter
  command."
- A host test sets `FakeMotor::connectedValue = false` (or otherwise
  forces a stale `sampleTime`) and asserts the kernel's existing
  `i2cFaultCount_`/no-op path behaves as expected — proving the consumer
  side of the dead-brick fix without needing a real hang.
- **Not host-testable, by construction**: the actual I2C bus-hang guard
  itself (whatever mechanism the investigation picks) and the real
  over-64-byte radio RX behavior in the air, both requiring hardware —
  first exercised live at this sprint's two bench checks.
- Bench check 1: a real >64-byte v6 line sent over radio, confirming the
  chosen RX behavior against actual hardware, not just the host
  double — precisely the case no host test has ever exercised.
- Bench check 2: a physically unpowered or I2C-disconnected Nezha brick,
  exercised twice — once before any motion (the boot-priming path) and
  once mid-drive (the steady-state tick path) — confirming the robot
  stays observable (`connected=false`, `i2cFaultCount` climbing,
  TLM/DIAG alive) and does not hang either time.

## Architecture

(Architecture for this sprint's change, sized to the change — a
one-paragraph note for a trivial sprint, a fuller write-up with
component/data-model detail for a substantial one. May read "N/A —
trivial" when the change has no architectural impact.)

### Architecture Overview

(High-level structure and component relationships, if applicable.)

### Design Rationale

(Significant decisions with alternatives considered and reasoning, if
applicable.)

### Migration Concerns

(Data migration, backward compatibility, deployment sequencing — or
"None" if not applicable.)

## Use Cases

(Use cases sized to the change — may read "N/A — trivial" for small
sprints that don't warrant new or updated use cases.)

None of `docs/design/usecases.md`'s UC-001..016 cover hardware-port
degradation or radio line capacity — both are bench/host-tooling scope,
following sprint 004's own precedent of `Parent: N/A` SUCs for
wire-protocol/firmware-robustness work. Detail planning will likely need
at least two new SUCs: one for a radio host sending or receiving a
full-length v6 line (covering whichever of reassembly or rejection is
chosen), and one for a bench operator observing a degraded-but-alive
robot after an unreachable brick, at both boot and mid-session. Not
written out here — this is a roadmap-phase sprint.

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

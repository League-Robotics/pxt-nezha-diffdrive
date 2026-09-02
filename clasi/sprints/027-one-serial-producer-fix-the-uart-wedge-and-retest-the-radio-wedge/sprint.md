---
id: '027'
title: 'One serial producer: fix the UART wedge and retest the radio wedge'
status: executing
branch: sprint/027-one-serial-producer-fix-the-uart-wedge-and-retest-the-radio-wedge
use-cases:
- SUC-001
- SUC-002
- SUC-003
issues:
- concurrent-serial-writers-wedge-the-uarte-in-both-directions.md
- cleartext-run-hangs-the-link-under-active-telemetry.md
- fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md
- camlink-mounts-table-is-stale-for-tigez.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 027: One serial producer: fix the UART wedge and retest the radio wedge

## Goals

Close the hardware-proven UART wedge — two fibers writing the nRF52
UARTE concurrently permanently kill the serial link, in both
directions, on the first `RUN:` command carrying a payload — by making
the protocol fiber the single producer for both serial and radio
output. This is the small, already-hardware-verified first ticket that
`clasi/issues/single-executor-for-command-dispatch.md`'s 2026-09-02
triage note split out from the full executor-inversion design; the
full inversion is deliberately deferred to the following sprint.

Piggyback two small, independent items that fit the same bench
session: retest the radio-traffic wedge
(`fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`) now that
sprint 026's VFP yield guard has landed, since it shares an identical
`CFSR 0x8200` fault signature and was never re-tested after the guard;
and a ten-line `tools/camlink.py` documentation/data fix
(`camlink-mounts-table-is-stale-for-tigez.md`) that costs a field
session's worth of time every time it's skipped.

## Problem

`Protocol::emitLine` and `RadioTransport::sendLine` are each called
from more than one fiber — the protocol fiber's own telemetry/reply
path, and the MessageBus-forked fiber a `RUN:` handler with a non-empty
payload spawns. CODAL's `NRF52Serial` driver is not safe against two
concurrent producers: `putc()` spins on a non-atomically-set
`is_tx_in_progress_` flag with interrupts enabled and DMAs from a
`putc()` stack local, so two near-simultaneous `STARTTX` triggers can
leave the UARTE stopped in both directions with no fault, no reset, and
no self-recovery — only a debugger halt/resume clears it. This was
measured on tigez 2026-09-02 with pyOCD: `RUN:z` (an unbound name, one
payload byte) wedges the board 100% of the time on locally-built
firmware; `RUN:` with zero payload never does. It is the confirmed root
cause of the older, previously-unexplained
`cleartext-run-hangs-the-link-under-active-telemetry.md` symptom, and
it is separate from — and must not be confused with — sprint 026's VFP
fault (opposite signature on every axis: no fault, no reset, motion not
required, cleared by halt/go rather than a reboot).

Separately, `fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`
root-caused a hard fault (`CFSR 0x8200`, `PRECISERR|BFARVALID`, radio
payload bytes landing on a live `this` pointer inside
`DifferentialDrive::controlStep()`) that sprint 026 ticket 001's VFP
yield guard is the leading candidate fix for, but the radio-traffic
retest that would confirm or rule that out was never run — sprint 026
closed having only retested the non-radio kill tests. That issue still
reads "critical — do not drive over radio" and needs one bench session
to close or re-attribute it.

## Solution

**Serial fix**: `Protocol::emitLine()` stops touching a transport
directly. It clips the line, copies it into a `Protocol`-owned ring,
and returns. `Protocol::run()` gains a `drainEmitQueue()` call at the
top of its loop that calls the (now-private) old emit body —
`uBit.serial.send` plus the radio mirror. This gives `uBit.serial.send`
and `RadioTransport::sendLine` exactly one caller each, by
construction, removing the concurrent-producer window entirely. This
exact change was already implemented and hardware-verified on tigez
(`RUN:z`, `RUN:ping`, `RUN:spin:10` all answer; a 10-command soak
produced 0 reboots, port alive at end) — this sprint lands it as
production firmware with tests and docs, it does not re-derive it.

Expose the ring's drop count via `diagValue()` at the next free ordinal
(026/002 used ordinal 28 for the RUN queue's drop counter; this sprint
uses the next one). Add a docs line stating that student code inside an
event handler must call `diffDrive.emitLine`, not PXT's own
`serial.writeLine`/`serial.writeString` — this extension cannot lock a
path that goes straight to `uBit.serial` from an arbitrary fiber.

**Radio retest**: with the VFP-guarded firmware (sprint 026's fix,
already merged), drive `MOVE_X` over USB on tigez (farm node meili —
sprint 026's own hardware caveat is that magni's USB was dropping
boards) while hammering `PING` over the radio relay, many trials,
mirroring the original reproducer in
`captures/tigez-cal-20260830/`. Report the result either way: if the
fault no longer reproduces, close
`fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md` as fixed by
026/001; if it still reproduces, re-attribute it as a separate,
still-open defect rather than letting the guard become an unproven
explanation.

**camlink fix**: correct the stale "not persisted" docstring in
`tools/camlink.py` and add tigez's tag 57 to `MOUNTS` with its already-
measured mount offset and yaw, per the issue.

## Success Criteria

- Baseline reproduces the UART wedge on tigez (`RUN:z` wedges the port
  both directions, confirmed before judging the fix).
- Fixed firmware survives `RUN:z`, `RUN:ping`, and a 10+ command soak
  with 0 wedges, port alive and answering `HELLO` throughout.
- With `TLM` subscribed, a cleartext `RUN:` command no longer hangs the
  link — closing `cleartext-run-hangs-the-link-under-active-telemetry.md`
  as the same defect.
- The emit ring's drop count is readable via `diagValue()` and the docs
  state `diffDrive.emitLine` is required inside event handlers.
- The radio-traffic retest runs on tigez (meili) with many `MOVE_X` +
  `PING`-hammer trials and reports a definitive result — either
  `fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md` closes, or
  it is re-attributed with fresh evidence. Either outcome satisfies this
  sprint; an inconclusive session does not.
- `tools/camlink.py`'s docstring is corrected and tag 57 (tigez) is in
  `MOUNTS`.
- `uv run pytest` passes throughout, in full at `close_sprint`.

## Scope

### In Scope

- `Protocol::emitLine()` / `Protocol::run()`'s emit-queue restructuring
  (single serial+radio producer on the protocol fiber), per
  `concurrent-serial-writers-wedge-the-uarte-in-both-directions.md` and
  the single-serial-producer piece of
  `single-executor-for-command-dispatch.md`.
- The new emit ring's drop counter, exposed via `diagValue()`.
- A docs line on `diffDrive.emitLine` vs `serial.writeLine`.
- Hardware acceptance on tigez over USB with pyOCD: baseline wedge
  reproduction, then the fix's soak test, then a `TLM`-subscribed
  cleartext `RUN:` check closing the telemetry-hang issue.
- The radio-traffic wedge retest on the VFP-guarded firmware
  (tigez/meili), reported either way.
- The `tools/camlink.py` docstring and `MOUNTS` fix for tigez (tag 57).

### Out of Scope

- **The full executor inversion** (single executor on the protocol
  fiber for RUN *dispatch*, `motionOwner_` arbitration, inverting the
  tour's tick loop) — this is
  `single-executor-for-command-dispatch.md`'s second, larger piece,
  explicitly deferred to the following sprint per its own 2026-09-02
  triage note. This sprint fixes the serial *transport's* concurrent-
  producer hazard only; it does not restructure who dispatches a RUN
  command or ticks motion.
- Any other `next`-triaged issue not named above
  (`frozen-encoder-read-becomes-a-phantom-zero-velocity-and-the-pid-overreacts`,
  `no-wire-verb-reaches-rebaseposition-so-tours-cannot-zero-their-frame`)
  — left for a later sprint per `clasi/TRIAGE-20260902.md`.
- Any `high`- or `low`-triaged issue.
- Upstream CODAL fixes for the underlying `NRF52Serial` driver hazard
  (the write-up worth filing with Lancaster, documented in the serial-
  wedge issue) — out of bounds, vendored toolchain.

## Test Strategy

Two of the four issues this sprint closes are host-testable; two are
hardware-only.

- **Host-testable (`comms/emit_queue.h`, ticket 001).** The queue
  logic itself — enqueue/drain FIFO order, saturating drop counting,
  clip-to-`kMaxPayloadBytes` behavior — is a pure, `pxt.h`-free header
  in the same style as `run_queue.h` (sprint 026 ticket 002), so it
  gets a host test under `tests/host/` with no CODAL toolchain
  involved. `protocol.cpp`/`protocol.h` themselves stay untestable
  host-side (they include `pxt.h` transitively), same limitation every
  prior `Protocol` ticket has lived with — verified by code review plus
  the hardware acceptance ticket below, not a host unit test.
- **Hardware-only (tickets 002, 003).** The UART wedge is a timing
  race that a cloud-built or host-run test cannot reproduce (see the
  serial-wedge issue's "why local builds and not cloud builds" note),
  and the radio hard-fault is a hardware memory-corruption symptom.
  Both require the local docker toolchain build, pyOCD on the SWD
  port, and tigez specifically (farm node meili). Every claim from
  these two tickets must be a `MEASURED` comment naming its capture
  file under `captures/`, per `.claude/rules/measurement-citations.md`
  — an unrun trial is written as `UNVERIFIED`, never invented.
- **Doc/data-only (ticket 004).** `tools/camlink.py`'s fix has no
  behavior to test beyond the existing `MOUNTS`-table shape a host
  test may already pin (if one exists, extend it to cover tag 57; if
  none does, this ticket does not need to add one for a pure data/doc
  correction — see the ticket's own acceptance criteria).
- **Regression floor.** `uv run pytest` (full host suite) passes
  throughout ticket work and once more, in full, at `close_sprint`,
  per `.claude/rules/source-code.md`. `test_archaeology_marker_budget.py`
  (zero slack) and `test_vfp_guard_source_pin.py` apply to any new
  `.h`/`.cpp` this sprint adds or touches, same as every prior sprint.

## Architecture

**Compact** — this sprint's only architecturally-relevant change is
one new host-portable module (`comms/emit_queue.h`, a small
`Protocol`-owned outbound-line ring) plus a restructuring of one
existing module (`Protocol`'s composition, `comms/protocol.h/.cpp`) so
that `uBit.serial.send` and `RadioTransport::sendLine` each keep
exactly one caller, by construction. No new cross-module dependency
(`Protocol` already owned both transports it now queues through), no
dependency-direction change, no data-model change. Diagrams are
therefore omitted — a two-node "Protocol owns EmitQueue" picture would
not clarify anything a sentence doesn't already say. The sprint's other
two items sit outside architecture's scope entirely: the radio-traffic
retest (ticket 003) is measurement-only, producing either a closed
issue or a re-attributed one with fresh evidence, not new structure;
and the `tools/camlink.py` fix (ticket 004) is a docstring correction
plus one data-table row in an already-existing, unrelated tool module.

### Architecture Overview

**What changed.**

- **New module: `comms/emit_queue.h` (`diffDrive::EmitQueue<Slots,
  Bytes>`).** A header-only, `pxt.h`-free ring of NUL-terminated
  outbound lines, same shape and precedent as sprint 026 ticket 002's
  `run_queue.h`/`RunQueue` (fixed slot array, FIFO enqueue/dequeue, a
  saturating `dropped` counter) but holding line *text* to be written,
  not a MessageBus slot index to be read back. `Protocol` is its only
  owner and only caller.
- **Changed module: `Protocol` (`comms/protocol.h/.cpp`).**
  `Protocol::emitLine()` — the one entry point every fiber other than
  the protocol fiber itself reaches (via `shims.cpp`'s free-function
  `emitLine` shim, called from TS test code on whatever fiber a
  MessageBus RUN dispatch runs it on) — stops touching `transport_`/
  `radioTransport_` directly. It clips the line to
  `RadioTransport::kMaxPayloadBytes` exactly as before, copies it into
  a new `emitQueue_` member, and returns. The old body (serial write,
  then the radio mirror with its existing fiber_sleep(2)-and-retry-once
  policy) becomes a private `emitLineNow()`, called only from a new
  private `drainEmitQueue()`. `Protocol::run()`'s fiber loop calls
  `drainEmitQueue()` once at the top of every pass, before polling
  serial/radio RX, draining every currently-queued line in FIFO order.
  `SerialSink::write()`/`RadioSink::write()` — the v6 wire stack's own
  reply/telemetry path — are **unchanged**: they already ran only on
  the protocol fiber, so they were never part of this race and gain no
  new indirection.
- **`shims.cpp`: one new `diagValue()` ordinal (29).** Returns the new
  ring's `dropped()` count, same shape as ordinal 28's
  `protocolRunDropCount()` (sprint 026 ticket 002) — a saturating
  counter, readable via `probe(29)`, that should stay 0 across a normal
  session.
- **`src/blocks/sim.ts`: one added sentence in `emitLine()`'s existing
  doc comment.** States plainly that student code inside an event
  handler must call `diffDrive.emitLine`, never PXT's own
  `serial.writeLine`/`serial.writeString` — those go straight to
  `uBit.serial` from whatever fiber calls them, a path this extension
  cannot route through the new queue from the inside. This is a
  documented limit of the fix, not a defect in it (see the serial-wedge
  issue's own "Limit of the fix" section).

**Why.** `NRF52Serial`'s UARTE driver (codal-nrf52) is not safe against
two concurrent producers: `putc()` spins on a non-atomically-set
`is_tx_in_progress_` flag with interrupts enabled and DMAs from a
stack-local buffer, so two near-simultaneous `STARTTX` triggers can
leave the UARTE stopped in both directions, permanently, with no fault
and no self-recovery (measured on tigez 2026-09-02, full mechanism in
`clasi/issues/concurrent-serial-writers-wedge-the-uarte-in-both-directions.md`).
The two producers were `Protocol::run()` itself and whatever fiber a
`RUN:`-with-payload dispatch runs `emitLine()` on. `SerialTransport`'s
existing two-writer guard (a bounded-retry bool, sprint 004 ticket 006)
is a software lock one layer above where the actual race lives — inside
`putc()`'s own check-and-set — so it cannot close this gap no matter
how it's tuned; only removing the second producer can. Queuing and
draining from one fiber is a structural fix, not a tighter lock: after
this change there is exactly one call site in the whole binary that can
ever invoke `uBit.serial.send`, and exactly one that can ever invoke
`RadioTransport::sendLine()`, so the race is eliminated by construction
rather than made merely less likely. This same restructuring was
already implemented ad hoc and hardware-verified on tigez before this
sprint (soak test: 10 alternating commands, 0 reboots, port alive
throughout) — this sprint lands it as reviewed, tested, documented
production firmware; it does not re-derive the fix.

**Impact on Existing Components.** Additive to `Protocol`'s own state
(one more member, two more private methods) with no change to
`emitLine()`'s public signature or clip behavior — every existing
caller (`run.ts`'s `DBG:`/result lines, test.ts's own result reporting)
is unaffected. Latency grows by at most one loop pass
(`kPollIntervalMs`, 5 ms) before a queued line reaches the wire — the
same bound sprint 026 ticket 002 accepted for RUN command dispatch
through `run_queue.h`. Loss becomes possible where it was not before:
a line is dropped only if the ring is full when `emitLine()` is called,
countable via ordinal 29 — strictly preferable to the failure it
replaces (the port wedging permanently and losing everything
afterward, uncounted). `SerialTransport`'s own two-writer guard and
`RadioTransport::sendLine()`'s `sending_` re-entrancy guard are left in
place unchanged; they become structurally redundant for the
`emitLine()` path specifically but still guard `wireHandlerRadio_`'s
own sink against any future second producer — removing them is not
this ticket's scope and would only give back a safety margin for free.

### Design Rationale

**Decision: queue-and-drain-on-one-fiber, not a stronger lock around
the existing direct-write path.**

- **Context.** Two fibers can call into the serial/radio write path
  concurrently; something has to serialize them, and the codebase
  already has one lock-shaped attempt (`SerialTransport`'s two-writer
  guard) that does not work.
- **Alternatives considered.** (a) A mutex or critical section around
  `transport_.writeLine()`/`radioTransport_.sendLine()` — rejected:
  the demonstrated race lives inside codal's own `NRF52Serial::putc()`
  (a non-atomic check-and-set, an unconditional `ENDTX` clear that can
  consume the ISR's own completion event), below any lock this
  extension could add without patching the vendored driver; a lock
  one layer up cannot reach a race one layer down. (b) Route every
  write — including the v6 reply/telemetry path already running
  solely on the protocol fiber — through the same queue for
  uniformity — rejected as unneeded scope: that path was never racing,
  and queuing it would add a full loop-pass of latency to every ack,
  which the reliability layer (protocol.md's own "an ack or a nack is
  only a response to a message, not a beacon" design) never needed.
- **Why this choice.** Queuing only the actually-racing entry point
  gives `uBit.serial.send`/`RadioTransport::sendLine()` exactly one
  caller each by construction — verifiable by inspection (a call-site
  census), not merely asserted safe under a lock that hardware has
  already shown to be insufficient.
- **Consequences.** `emitLine()` callers can no longer assume the line
  is physically on the wire by the time the call returns (previously
  true for the serial half; now only "queued for the next drain,"
  ≤5 ms later) — no existing caller depends on that stronger guarantee.
  A full ring drops the newest line and counts it (ordinal 29) rather
  than blocking the calling fiber — an explicit, bounded, and countable
  tradeoff against the permanent, silent wedge it replaces.

### Migration Concerns

None. No persisted state, no wire-protocol-visible change — a
subscriber sees identical reply/telemetry ordering and content, only
drained from one more level of indirection inside the firmware — and
no deployment-sequencing concern beyond the normal per-robot reflash
(`tools/make_deploy.py --robot tigez`, pyOCD on the farm, not DAPLink
MSD). The only externally-observable behavior change is strictly a
reliability improvement: a burst that used to wedge the port
permanently can now, at worst, drop a line and count it.

## Use Cases

Compact sizing — three brief use cases, one per closable issue; the
fourth ticket (camlink.py) is a data/doc fix with no use-case-shaped
behavior of its own and is covered by SUC-003 only insofar as it is
tracked by a ticket, not because it changes a use case.

### SUC-001: A cleartext `RUN:` command with a payload never wedges the serial link
Parent: None — internal firmware transport-safety guarantee;
`docs/design/usecases.md` covers the extension's block-level API, not
the wire/RUN protocol's internal transport discipline, so no existing
UC applies.

- **Actor**: A bench host (or relay) sending `RUN:<name>[:<arg>]` over
  serial or radio while the protocol fiber may itself be emitting a
  reply or telemetry frame.
- **Preconditions**: The robot has booted; a host sends a `RUN:` line
  with a non-empty payload (the one case, per the issue's own bisect,
  that spawns a second writer).
- **Main Flow**:
  1. The host sends `RUN:z` (or any named/unnamed test) with a
     payload.
  2. The dispatch that follows no longer calls `uBit.serial.send`/
     `RadioTransport::sendLine` from any fiber but the protocol fiber
     — any line it needs to emit goes into `emitQueue_` and waits for
     `drainEmitQueue()`.
  3. The protocol fiber keeps answering `HELLO`/`PING`/`STATUS`
     throughout.
- **Postconditions**: The serial port never stops accepting or
  emitting bytes for the rest of the boot; no debugger halt/resume is
  ever needed to recover it.
- **Acceptance Criteria**:
  - [ ] Baseline (current firmware, before the fix): `RUN:z` wedges
        the port in both directions on tigez, reproduced before the
        fix is judged.
  - [ ] Fixed firmware: `RUN:z`, `RUN:ping`, and a 10+ command soak
        produce 0 wedges; `HELLO` answers throughout.
  - [ ] With `TLM` subscribed, a cleartext `RUN:` command no longer
        hangs the link or stalls telemetry — closing
        `cleartext-run-hangs-the-link-under-active-telemetry.md` as
        the same defect.
  - [ ] `emitQueue_`'s drop count is readable via `diagValue(29)`/
        `probe(29)`.

### SUC-002: The radio-traffic hard fault is confirmed fixed, or freshly re-attributed
Parent: None — internal firmware fault-attribution guarantee; no
existing UC covers a hardware fault-mechanism investigation.

- **Actor**: A bench operator driving `MOVE_X` over USB on tigez while
  hammering `PING` over the radio relay, on the VFP-guarded firmware
  (sprint 026 ticket 001, already merged).
- **Preconditions**: tigez on farm node meili, relay tuned to
  `!CG 55 114`, many trials planned (a single survival proves
  nothing — the fault is probabilistic).
- **Main Flow**:
  1. Run the reproducer many times, mirroring
     `captures/tigez-cal-20260830/`.
  2. Record every trial's outcome with a `MEASURED`-cited capture file.
  3. If no fault reproduces, close
     `fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md` as
     fixed by 026/001 and correct the still-open corruption attribution
     in `src/platform/nezha_port.cpp`'s comment and any doc referencing
     it.
  4. If the fault still reproduces, capture CFSR/BFAR with pyOCD on the
     wedged chip and re-attribute the issue with the fresh evidence,
     leaving it open rather than letting the guard stand as an unproven
     explanation.
- **Postconditions**: The issue reads either "closed, fixed by 026/001,
  evidence attached" or "open, re-attributed, evidence attached" — never
  "inconclusive."
- **Acceptance Criteria**:
  - [ ] Many-trial results are reported either way, each MEASURED claim
        naming its capture file.
  - [ ] The issue file and any affected source comment reflect the
        actual outcome.

### SUC-003: `tools/camlink.py` is current for the on-field robot
Parent: None — internal tooling accuracy guarantee; no existing UC
covers bench-tooling data currency.

- **Actor**: An agent or operator starting a field session with tigez.
- **Preconditions**: `tools/camlink.py`'s `MOUNTS` table and module
  docstring are read before deciding whether a mount-offset probe is
  needed.
- **Main Flow**:
  1. The docstring correctly states that AprilCam mount registrations
     persist and reload at daemon startup (only annotations are
     per-session).
  2. `MOUNTS` includes tag 57 (tigez) with its measured mount offset
     and yaw, plus a comment splitting the −90° convention term from
     the sub-degree physical residual.
- **Postconditions**: A tigez session finds a known mount and skips
  the probe ritual.
- **Acceptance Criteria**:
  - [ ] Docstring corrected per the issue's Defect 1.
  - [ ] Tag 57 added to `MOUNTS` with `mount_yaw_rad = -math.pi/2` plus
        the measured sub-degree residual, per the issue's Defect 2 and
        Fix step 3.

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

| # | Title | Depends On | Issue |
|---|-------|------------|-------|
| 001 | Single serial/radio producer: Protocol-owned emit queue | — | `concurrent-serial-writers-wedge-the-uarte-in-both-directions.md` |
| 002 | Hardware acceptance on tigez: UART wedge baseline, fix soak, and TLM-subscribed cleartext RUN | 001 | `cleartext-run-hangs-the-link-under-active-telemetry.md` |
| 003 | Radio-traffic wedge retest on VFP-guarded firmware | — (no code dependency; sequenced after 002 to reuse the same tigez/meili bench session) | `fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md` |
| 004 | camlink.py: correct mount-persistence docstring and add tigez (tag 57) | — (fully independent) | `camlink-mounts-table-is-stale-for-tigez.md` |

Tickets execute serially in the order listed.

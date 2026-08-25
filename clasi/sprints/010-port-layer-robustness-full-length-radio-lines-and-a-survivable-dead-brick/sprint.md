---
id: '010'
title: 'Port-layer robustness: full-length radio lines and a survivable dead brick'
status: ticketing
branch: sprint/010-port-layer-robustness-full-length-radio-lines-and-a-survivable-dead-brick
use-cases: ['SUC-001', 'SUC-002', 'SUC-003']
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

**Sizing: Substantial.** Three modules are touched with real behavioral
changes — `radio_transport.{h,cpp}`, `wire_handler.{h,cpp}` (two
independent fixes: STATUS's new `cyc=` field and the GET-path scaling
defect), `wire_adapter.cpp`, plus `nezha_port.{h,cpp}`/`shims.cpp` for
the dead-brick investigation — clearing the substantial-tier module-count
signal on its own. No new module is introduced and, as established
below, no new cross-module dependency is introduced either: every change
in this sprint lands on an edge that already exists (or is fully
self-contained within one file). That second fact is what drives the
diagram decision in Step 4.

### Step 1 — Understand the problem

Two hardware port boundaries silently do something other than what they
were asked, and one wire boundary silently reports something other than
what the firmware actually holds. All three are read in full above
(Problem, and this sprint's own linked issues); the load-bearing facts
carried into design:

- Radio's inbound 64-byte `rxLine_` slot is an arbitrary implementation
  choice, not a physical or protocol ceiling — the fleet's own physical
  radio packet size (`microbit_radio_max_packet_size: 250` in this
  project's `pxt.json`) already carries the wire grammar's full 240-byte
  line in **one** physical fragment, both directions. `radio_transport.h`
  and `radio_transport.cpp` already say so in their own header comments
  ("with the 250-byte fleet packet size every relay-forwarded command
  line qualifies" as a single-fragment message).
- The dead-brick bench session proved the *documented* failure
  (`kernel.begin()`'s priming loop never returning, freezing the
  cooperative scheduler) did not reproduce on a powered, healthy brick —
  what actually reproduced was a *different*, quieter defect: a kernel
  nothing has ticked reports the identical STATUS line to a kernel that
  is genuinely wedged (`ready=0 connL=0 connR=0 i2cf=0` either way),
  because `active_`/`connected_`/`i2cFaultCount_` are all written only
  inside `step()`/`collect()`, which run only when something ticks.
- `GET full_duty_velocity`'s wrong reply is not a `fullDutyVelocity`-
  specific bug — reading `wire_handler.cpp`'s `formatConfigValue()`
  (the single function both GET code paths call) shows a `uint32_t`
  intermediate that silently overflows for **any** config field whose
  real magnitude reaches roughly 4295, clamping to the same fixed wrong
  constant (`4294.967040`) every time. `fullDutyVelocity` (10795.0,
  `shims.cpp::ensure()`) is simply the only field in today's 18-entry
  table whose real value crosses that line — confirmed by reading every
  seeded `Config` value in `ensure()` and finding none of the other 17
  fields exceeds it.

### Step 2 — Identify responsibilities

Four independently-changing responsibilities, none of which shares a
root cause with another (this is a themed grouping, same as sprint 006's
five independent kernel/odometry findings and sprint 010's own
Problem section explaining why the two issues share a sprint):

1. **Radio line capacity** (RX and TX) — a transport-layer buffer-sizing
   and accept/reject decision. Owned by `RadioTransport`.
2. **"Has this kernel ever ticked?" observability** — a wire-adapter-
   level readback problem: an existing, already-correct kernel counter
   (`cycleCount`) is not surfaced anywhere STATUS-level. Owned by
   `WireAdapter`/`WireHandler`'s STATUS path.
3. **The actual I2C bus-hang guard** — a hardware-port-layer question
   that depends on facts about the target's I2C driver this sprint does
   not yet have confirmed. Owned by `NezhaMotorPort`, with `shims.cpp`
   as the only caller of its `begin()`/tick path.
4. **GET-path float-to-wire-text scaling** — a wire-grammar formatting
   defect, entirely inside one pure function. Owned by `WireHandler`.

### Step 3 — Define subsystems and modules

- **`RadioTransport`** (`radio_transport.h/.cpp`) — purpose: fragments
  and carries wire lines over the fleet's radio link. Boundary:
  knows bytes and on-air framing only, nothing about verbs or grammar
  (unchanged this sprint). Serves SUC-001.
- **`WireHandler`** (`wire_handler.h/.cpp`) — purpose: protocol v6's
  line-grammar mechanics and reliability layer. Boundary: pure,
  host-portable, no adapter/transport knowledge beyond the `Adapter`/
  `Sink` seams (unchanged). Serves SUC-002 (STATUS's new field) and
  SUC-003 (GET formatting fix).
- **`WireAdapter`** (`wire_adapter.cpp`) — purpose: the concrete
  `Wire::Adapter` for this robot, translating wire verbs to `shims.cpp`
  calls. Boundary: forward-declares `shims.cpp` free functions, holds no
  Rig/kernel reference of its own (unchanged). Serves SUC-002 (reads the
  already-existing `kDiagCycleCount` ordinal into the new STATUS field).
- **`NezhaMotorPort`** (`nezha_port.h/.cpp`) — purpose: the `Motor` port
  over the Nezha brick's I2C interface. Boundary: knows I2C/CODAL,
  nothing about the wire or blocks (unchanged). Serves SUC-002's
  bus-hang half, pending investigation.

No new module is defined. Every module above already exists at its
current boundary; this sprint changes behavior inside existing
boundaries, not the boundaries themselves.

### Step 4 — Diagrams

**No component/module diagram.** Every edge this sprint's changes travel
already exists in `src/DESIGN.md` §1's layer map, and no new edge is
added: `WireAdapter`'s new STATUS field reads the already-existing
`diagValue(kDiagCycleCount)` forward declaration (no new
`WireAdapter → shims.cpp` call is introduced, only a new *use* of one
that ticket 004 of sprint 004 already wired for `i2cf`); `RadioTransport`
resizes two of its own member buffers and tightens its own accept/reject
decision, touching no other module; `WireHandler`'s GET-formatting fix
is entirely internal to one pure function; the dead-brick investigation
(§ below) reaches no further than the existing `shims.cpp → NezhaMotorPort
→ Motor::begin()/tick()` relationship. This is the same reasoning
sprint 008 and sprint 020 each used to omit their own diagrams under the
substantial tier: several independently-changing modules, zero new
composition between them. A diagram redrawing the current module graph
with no new nodes or edges would clarify nothing beyond what §1 of
`src/DESIGN.md` already shows.

**No entity-relationship diagram.** No persistent data model exists in
this embedded package (nothing survives a power cycle), unchanged by
this sprint, exactly as every prior sprint's architecture update has
found.

**No dependency-direction graph** beyond this one-line statement:
dependency direction is unchanged (Presentation/wire → MotionEngine →
Kernel/ports, kernel at the bottom); nothing in this sprint adds, removes,
or reverses an edge.

### Step 5 — What Changed / Why / Impact / Migration Concerns

**What Changed.**

1. **`radio_transport.h`/`.cpp` — RX capacity, enlarged and made honest.**
   `rxLine_` grows from `[64]` to `[Wire::WireHandler::kMaxLineBytes]`
   (240), matching the wire grammar's own ceiling instead of an
   arbitrary smaller one. `onDatagram()`'s current behavior —
   `if (len > sizeof(rxLine_)) len = sizeof(rxLine_);`, which silently
   truncates an over-length single-fragment datagram to whatever fits
   and still accepts it — is replaced with an outright reject: a frame
   whose declared `LEN` exceeds the (now 240-byte) buffer is dropped,
   exactly like an already-dropped MORE-flagged fragment, and counted on
   a new RX diagnostic (`rxOversizeDropped_`, alongside the existing
   `rxFrames_`/`rxAccepted_`). The accept/reject decision itself (given
   `len` and the buffer's capacity) is factored into a small, pure,
   `inline` function living in `radio_transport.h` — the header already
   includes only `<cstddef>`/`<cstdint>` (host-portable), so this needs
   no new file the way `heading_wrap.h`/`encoder_glitch_armor.h` did in
   sprint 006; a host test simply `#include`s the header and calls the
   function directly, without linking `radio_transport.cpp` (which still
   requires `pxt.h`) at all.
2. **`radio_transport.h` — TX capacity, raised to match.** `kMaxPayloadBytes`
   moves from 200 to 240 (`payloadBuf_` resizes with it; `frameBuf_[256]`
   already has headroom for a 240-byte payload plus its 3-byte fragment
   header and needs no change). `protocol.cpp::emitLine()` needs no code
   change — it already names `RadioTransport::kMaxPayloadBytes` by
   reference (sprint 008), so it inherits the new value automatically.
   `sendFragmented()`'s existing multi-fragment loop (already written,
   already correct, previously dead code in practice because every real
   payload fit in one fragment under the old 200-byte cap) needs no
   change either — it already handles a payload up to and beyond the MTU
   correctly should a future target ever configure a smaller
   `MICROBIT_RADIO_MAX_PACKET_SIZE`. A drift test asserts
   `RadioTransport::kMaxPayloadBytes == Wire::WireHandler::kMaxLineBytes
   == SerialTransport::kMaxLineBytes` (all 240) so the three numbers
   cannot silently diverge again, closing the issue's explicit
   three-numbers requirement with equality rather than a documented
   inequality. `tests/host/test_wire_telemetry_frame.py`'s pinned
   200-byte-boundary assertions move to the new 240-byte boundary; the
   previously-"39 B over" pathological 239-byte FULL frame now fits,
   with 1 byte of headroom (flagged in Open Questions below — this
   margin is thin, not comfortable).
3. **`wire_handler.h`/`.cpp`, `wire_adapter.cpp` — STATUS gains `cyc=`.**
   `Wire::StatusFields` gains a `uint32_t cyc` field.
   `WireAdapter::status()` sets it from the *already-existing*
   `diagValue(kDiagCycleCount)` call (ordinal 16, already read by
   telemetry's `cyc` column since sprint 004 ticket 004) — no `shims.cpp`
   change, no new forward declaration, no new kernel readback.
   `WireHandler::execStatus()`'s format string gains ` cyc=%lu`
   (buffer headroom re-verified; the line's previous worst case measured
   well under the 200-byte buffer). `tests/host`'s `WireMockAdapter` and
   the `WaHandle`/real-`WireAdapter` test surface are re-synced with the
   new field, the same re-sync discipline sprint 008 called out as
   required, not optional, whenever a real adapter method's shape
   changes.
4. **`nezha_port.h`/`.cpp` — dead-brick bus-hang guard: investigation,
   not a committed fix.** See the dedicated subsection below — this
   ticket's scope depends on a fact this sprint does not yet have
   confirmed (which codal-nrf52 release this project's build actually
   resolves, and whether it already includes upstream's own I2C
   transaction-timeout/hang-recovery work).
5. **`wire_handler.cpp` — `formatConfigValue()`'s scaling defect,
   fixed for every field.** The function's `magnitude * 1,000,000`
   intermediate, currently computed in `uint32_t`, is widened (a
   `double`/`uint64_t` intermediate) so the multiply cannot silently
   overflow for any field whose real magnitude the 18-entry `kFields`
   table could plausibly hold, and the *input* is bounded against an
   honest ceiling before scaling — the same shape as WIRE-08's inbound
   `kWireBoundaryCastCeiling` fix (sprint 007 ticket 007), applied here
   to the outbound mirror the issue itself identified. A new host test
   loops over all 18 `kFields` entries (not just `full_duty_velocity`)
   asserting each field's GET reply round-trips its real, configured
   value.

**Why.** Each of the five items above closes a case where a port
boundary (radio, the I2C bus, or the wire's own text formatting) either
executes something other than what was asked (item 1's truncated-prefix
hazard) or reports something other than what is actually true (items 3
and 5) — the same "silently does the wrong thing instead of saying so"
shape the sprint's Problem section names as the reason these belong in
one sprint. Item 2 (TX capacity) and the drift test are the
direct, symmetric completion of item 1's own capacity fix.

**Impact on Existing Components.** `WireHandler` and `WireAdapter` each
gain one new field/one new use of an existing readback — additive, no
existing verb or field's behavior changes. `RadioTransport`'s two
buffers grow (~176 B for RX, ~40 B for TX — both class members, not
stack, so the protocol fiber's 2 KB stack budget this project has
already measured as tight is untouched). `NezhaMotorPort` is unchanged
until ticket 004's investigation concludes; any resulting change is
additive/defensive by the sprint's own Success Criteria (a working robot
must not behave differently). No component gains a new caller or a new
callee.

**Migration Concerns.**

- Radio capacity: strictly a widening for any legally-encoded ≤240-byte
  v6 line (nothing that worked before stops working). The one real
  behavior change is that a >240-byte malformed/pathological inbound
  radio frame — today silently truncated to a prefix and *executed* as a
  different, shorter, legal command — is now dropped outright with no
  reply, matching `WireHandler::feed()`'s own long-established
  discard-whole-line contract for serial. No in-tree caller sends lines
  anywhere near this length today (bench `RUN:` lines and today's short
  verbs sit well under 64 bytes, per this sprint's own Goals).
- STATUS's new `cyc=` field: purely additive, following the exact
  precedent sprint 004 ticket 004 set adding `i2cf=` — any wire host
  parsing STATUS by `key=value` token (the wire grammar's own documented
  shape) is unaffected by a new key appearing in the line; a host doing
  fragile fixed-position parsing was already unsupported by the
  protocol's own design.
- GET formatting fix: a real, visible reply change for
  `full_duty_velocity` today, and for any future field whose real
  magnitude crosses ~4295 — the wire reply changes from a wrong,
  plausible-looking number to the actual configured value. This is the
  fix's entire point, not a regression; no host should have built logic
  around the previously-wrong value (it is transparently nonsensical —
  `4294.967040` on every affected field, always the same number).
- Dead-brick guard: no committed behavior change until ticket 004 lands;
  whatever ships is additive/defensive per this sprint's Success
  Criteria — a healthy robot's behavior must be unchanged.

### Step 6 — Design Rationale

**Decision: close the radio capacity gap by enlarging `RadioTransport`'s
own buffers to the wire's existing 240-byte ceiling and rejecting the
(now narrow) residual overflow, not by building multi-fragment RX
reassembly.** Context: sprint.md's Requirements frame this as "the
central open decision," with two directions — reassembly (Direction 1)
or loud rejection (Direction 2) — each carrying a stated cost
(reassembly: RAM plus new protocol surface, a partial-line timeout, a
discard path; rejection: "a real capability cut... a radio host
genuinely cannot send a SET/HELP-shaped line that overflows 64 bytes").
Reading `radio_transport.h`'s own header comments and this project's
`pxt.json` (`microbit_radio_max_packet_size: 250`) changes the premise
both directions assumed: the physical single-fragment MTU (≈247 bytes
of payload) already exceeds the wire grammar's 240-byte line cap, on
both TX and RX — `onDatagram()` already only accepts a complete
single-fragment (`START|END`) message, and the header's own comment
already states "with the 250-byte fleet packet size every relay-
forwarded command line qualifies." So a v6 line up to 240 bytes will
*always* arrive as one physical radio packet; reassembly across multiple
packets is solving a problem that does not exist at this MTU. Rejection
is therefore not "a real capability cut" as Direction 2 originally
worried — it applies only to the narrow band above the wire's own
240-byte ceiling (241–247 bytes), which is either malformed or
adversarial input under the wire grammar's own rules, never a legally
encoded v6 line. Alternatives: (a) build true multi-fragment reassembly
[rejected — solves a problem the MTU already makes moot, at real RAM and
protocol-surface cost]; (b) raise the RX buffer only partway (e.g. to
128) [rejected — an arbitrary partial number re-creates the exact
"unexplained mismatch" the issue asks this sprint to close]; (c)
enlarge to 240 and reject above it [chosen]. Consequence: radio becomes
a full capacity peer of the wire grammar (including the previously-tight
239-byte pathological FULL telemetry frame) with no new protocol state,
no timeout logic, and a RAM cost (≈216 B total, both buffers) far below
reassembly's.

**Decision: STATUS's new `cyc=` field reuses the existing
`kDiagCycleCount` readback rather than inventing a new tri-state
"motor health" signal.** Alternatives: (a) a new explicit enum/bitmask
distinguishing never-ticked / ticked-and-healthy / ticked-and-faulted
[rejected — this signal is already fully derivable today from two
already-exposed numbers (`cyc` and `i2cf`/`connL`/`connR`) once `cyc` is
visible in STATUS itself rather than only in FULL telemetry; inventing a
new enum before that combination is even tried is the speculative
generality this project's own architecture principles warn against]; (b)
expose `cyc` in STATUS [chosen] — minimal, reuses an already-tested
readback (the same one FULL telemetry's `cyc` column already reads), zero
new kernel-facing state. Consequence: an operator reading STATUS alone
(no TLM subscription needed) sees `cyc=0` as "nothing has ticked yet —
`ready=0`/`connL=0`/`i2cf=0` are not evidence of a fault," and `cyc>0`
with `connL=0`/`i2cf` climbing as "genuinely not connected" — exactly the
distinction this sprint's Goals require, at the cost of one new
`key=value` pair on one reply line.

**Decision: the dead-brick bus-hang guard is an investigation ticket,
not a committed implementation.** Context: this sprint's own Requirements
already say the issue "needs investigation" and name three candidate
directions with none confirmed. Web research performed during this
planning pass sharpens why: codal-nrf52's own changelog records
"NRF52I2C: Introduce transaction timeout" (v0.2.33) and
"NRF52I2C::waitForStop: recover from hang" (v0.2.58), and
codal-microbit-v2's changelog records "Stabilize I2C communications
between NRF52 and KL27 DAPLINK chip when running on battery power (#130)"
(v0.2.32) — [Changelog](https://github.com/lancaster-university/codal-microbit-v2/blob/master/Changelog.md).
This project's `pxt.json` carries no explicit codal version pin (MakeCode
resolves the target build), so it is not yet known whether the resolved
build already includes this upstream work. If it does, the "permanent
hang" premise may already be platform-bounded (to some multi-second
delay, not infinite), which changes ticket 004's job from "add a
timeout" to "confirm the existing platform bound is adequate and make
the resulting delay graceful rather than a silent freeze"; if it does
not, a software-side guard is still needed, and the candidate
"pre-flight bus probe" direction is weaker than it looks — a probe would
use the *same* blocking I2C primitive `begin()`'s own priming reads use,
so on a true clock-stretch bus lockup it would hang exactly as long.
Alternatives: (a) commit to one of the three candidate directions now
[rejected — sprint.md's own Requirements already reject this, and the
platform-level finding above means committing now risks either
duplicating a fix the platform already ships or missing that the fix
does not cover this project's specific hang shape]; (b) a dedicated
investigation ticket, output a written finding plus any code change the
finding can justify without hardware [chosen]. Consequence: ticket 004
is scoped as research-plus-optional-low-risk-change; the actual
degrade-gracefully guarantee is proven only at the bench (ticket 005),
per this sprint's own Test Strategy.

**Decision: fix `formatConfigValue()` by widening its intermediate
arithmetic and bounding the input, not by raising the post-scale clamp
or special-casing `fullDutyVelocity`.** Context: the function's
`kMaxScaled = 4294967040.0f` clamp already exists and already prevents
undefined behavior (the cast to `uint32_t` is well-defined at the clamp
boundary) — the bug is not UB, it is that the clamp fires far too early
in real-world terms and substitutes a fixed wrong number. Alternatives:
(a) special-case `fullDutyVelocity` [rejected — the issue explicitly
asks for a sweep, not a one-field patch, and the defect is systemic to
any field whose real magnitude reaches ~4295, not to this field
specifically — confirmed by reading every seeded `Config` value and
finding the threshold is generic]; (b) raise `kMaxScaled` to a larger
value still inside `uint32_t` [rejected — insufficient: `uint32_t`
itself cannot represent `real_value × 1,000,000` for any real value much
past ~4295 no matter where the clamp is set inside its range; the type,
not the clamp threshold, is the actual ceiling]; (c) widen the
intermediate to `double`/`uint64_t` and bound the *input* value instead,
mirroring `kWireBoundaryCastCeiling`'s inbound pattern [chosen] — the
only option that removes the ceiling rather than relocating it.
Consequence: every field in the 18-entry table, present and future,
round-trips its real value through GET as long as it stays under the new
input-side ceiling; a host reading `full_duty_velocity` to decide whether
the robot is calibrated (this issue's own stated safety concern) sees
the truth.

### Step 7 — Open Questions

- Which codal-nrf52/codal-microbit-v2 release this project's MakeCode
  build actually resolves, and whether it already includes the upstream
  I2C transaction-timeout/`waitForStop` hang-recovery work cited above —
  ticket 004's first action item, and the single biggest unknown gating
  any further dead-brick implementation work.
- Whether `Motor::begin()`/`tick()` should eventually gain an explicit
  bounded-wait/status-returning contract (a kernel-level change to the
  vendored, cross-repo-synced `diffdrive.{h,cpp}`) — deliberately
  deferred out of this sprint's Scope pending ticket 004's findings; not
  to be assumed or implemented here.
- The bench session that surfaced the dead-brick correction also
  observed a wire-native `WHEELS_X 100 -100 100 2000` command accepted
  with no error while `cyc` stayed at 0 for the command's own duration —
  distinct from the `RUN:`-bridged block command that did tick the
  kernel. This is not one of this sprint's three claimed issues and is
  not fixed here, but STATUS's new `cyc=` field (item 3 above) will make
  this oddity trivially reproducible if a stakeholder re-tests it —
  flagged for a future investigation, not ticketed in this sprint.
- The widest pathological FULL telemetry frame (239 B, pinned by
  `tests/host/test_wire_telemetry_frame.py`) now fits the raised 240-byte
  radio TX ceiling with exactly 1 byte of headroom — legal, but thin. A
  future FULL column addition should re-measure against this margin
  before assuming it still fits.

## Use Cases

None of `docs/design/usecases.md`'s UC-001..016 cover hardware-port
degradation, radio line capacity, or wire-formatting correctness — all
three are bench/host-tooling scope, following sprint 004's own precedent
of `Parent: N/A` SUCs for wire-protocol/firmware-robustness work.

### SUC-001: Radio host sends or receives a full-length v6 line
Parent: N/A

- **Actor**: A bench host (or the fleet's RADIOBRIDGE relay) speaking v6
  over radio.
- **Preconditions**: The robot's radio is enabled; the host sends a
  legally-encoded v6 line whose formatted length is anywhere up to
  `WireHandler::kMaxLineBytes` (240 bytes) — e.g. a `HELP` reply, a
  pathological `FULL`-mode telemetry frame, or a long `GET`/`SET`
  exchange.
- **Main Flow**:
  1. The host's line arrives as one physical radio fragment (the fleet's
     250-byte packet size always carries a ≤240-byte line in one
     fragment).
  2. `RadioTransport` accepts the complete, untruncated line into its
     (now 240-byte) `rxLine_` buffer.
  3. The full line is fed to `wireHandlerRadio_`, which parses and
     dispatches it exactly as it would over serial.
  4. The robot's reply (also up to 240 bytes) is carried back over radio
     in one fragment, using the raised `kMaxPayloadBytes`.
- **Postconditions**: The command the host sent is the command the
  robot executed — never a truncated prefix parsed as a different,
  shorter, legal command. A line whose declared length exceeds 240 bytes
  is dropped outright, with no reply, and counted on a diagnostic.
- **Acceptance Criteria**:
  - [ ] A host test exercising `RadioTransport`'s host-portable
        accept/reject predicate confirms a ≤240-byte line is accepted
        and a >240-byte line is rejected, never truncated-and-accepted.
  - [ ] A host test confirms `RadioTransport::kMaxPayloadBytes`,
        `Wire::WireHandler::kMaxLineBytes`, and
        `SerialTransport::kMaxLineBytes` are equal (240) and fail
        together if any one drifts.
  - [ ] A bench check sends a real >64-byte v6 line over radio and
        confirms it executes correctly, not as a truncated command.

### SUC-002: Bench operator distinguishes "never ticked" from "brick unreachable"
Parent: N/A

- **Actor**: A bench operator or diagnostic host reading `STATUS` after
  a robot reports `ready=0`.
- **Preconditions**: The robot has booted; no caller has necessarily
  ticked the kernel yet (no `driveTick()` loop, no live wire motion
  obligation).
- **Main Flow**:
  1. The operator sends `STATUS`.
  2. The reply's new `cyc=` field reads 0: nothing has ticked yet, so
     `ready=0`/`connL=0`/`connR=0`/`i2cf=0` are not evidence of a fault.
  3. The operator issues a command that ticks the kernel (a block-path
     `RUN:` command, or a wire motion verb that arms a live obligation).
  4. The operator re-sends `STATUS`. `cyc` is now nonzero. If `connL`/
     `connR` are now `1` and `i2cf` stays low, the brick is healthy. If
     `connL`/`connR` stay `0` and `i2cf` climbs, the brick is genuinely
     unreachable.
  5. (Bench-only) The operator physically disconnects the brick, before
     first motion and again mid-drive, and confirms the robot stays
     observable (protocol/TLM/DIAG alive, motion blocks no-op) rather
     than hanging, in both cases.
- **Postconditions**: An operator can tell "nothing has ticked yet" from
  "the brick is genuinely unreachable" using `STATUS` alone, without
  subscribing to telemetry or guessing from `ready=0` in isolation.
- **Acceptance Criteria**:
  - [ ] A host test with a mock adapter at `cyc=0` confirms STATUS reads
        as "never ticked."
  - [ ] A host test with a mock adapter at `cyc>0`, `connLeft=false`
        confirms STATUS reads as "ticked and genuinely not connected."
  - [ ] A host test drives `FakeMotor::connectedValue = false` and
        confirms the kernel's existing `i2cFaultCount_`/no-op degrade
        path behaves correctly (the consumer side of the fix).
  - [ ] (Bench-only, ticket 005) A physically unreachable brick, both
        before first motion and mid-drive, leaves the robot observable
        and non-hanging; the investigation from ticket 004 informs
        whether any additional guard is in place by the time this check
        runs.

### SUC-003: Wire host reads a configured field's real value via GET
Parent: N/A

- **Actor**: A bench host or diagnostic tool issuing `GET` to inspect or
  verify calibration state (e.g., "is `full_duty_velocity` configured,
  per the `0 = uncalibrated → VELOCITY refused` contract?").
- **Preconditions**: The kernel holds some configured value for a field
  in the 18-entry `kFields` table, including one whose real magnitude is
  large (e.g. `full_duty_velocity` at 10795.0).
- **Main Flow**:
  1. The host sends `GET full_duty_velocity` (or a bare `GET`).
  2. `WireAdapter::onGet()` reads the real, correctly-scaled value.
  3. `WireHandler::formatConfigValue()` formats it without silent
     overflow, for any field's real magnitude the table can hold.
  4. The host receives the true configured value, not a fixed,
     plausible-looking wrong constant.
- **Postconditions**: A host's calibration/safety decisions based on a
  GET reply are based on the robot's real state.
- **Acceptance Criteria**:
  - [ ] A host test loops over all 18 `kFields` entries, sets each to a
        representative (including deliberately large) value, and asserts
        the GET reply round-trips it correctly.
  - [ ] A host test specifically covers `full_duty_velocity` at its real
        seeded value (10795.0) and confirms the reply is `10795.000000`,
        not `4294.967040`.

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

| # | Title | Issue | Depends On |
|---|-------|-------|------------|
| 001 | RadioTransport RX capacity: enlarge `rxLine_` to 240 bytes and reject (not truncate) an over-length fragment | radio-rx-capacity-fragmentation.md | — |
| 002 | RadioTransport TX capacity: raise `kMaxPayloadBytes` to 240 and drift-test the three line-capacity constants | radio-rx-capacity-fragmentation.md | 001 |
| 003 | STATUS gains a `cyc` field so never-ticked is distinguishable from brick-unreachable | unpowered-nezha-brick-wedges-program-at-boot.md | — |
| 004 | Nezha I2C bus-hang guard: investigation and best-effort implementation | unpowered-nezha-brick-wedges-program-at-boot.md | — |
| 005 | Bench verification checklist: unreachable brick at boot and mid-session | unpowered-nezha-brick-wedges-program-at-boot.md | 003, 004 |
| 006 | GET-path float-to-wire scaling: fix `formatConfigValue` overflow and sweep every config field | get-full-duty-velocity-returns-garbage.md | — |
| 007 | Build checkpoint: flashable hex from this sprint's final state | — | 001, 002, 003, 004, 005, 006 |

Tickets execute serially in the order listed. 001/002 (radio capacity),
003/004/005 (dead-brick), and 006 (GET-path fix) are three independent
clusters with no cross-cluster dependency — the listed order groups
them by issue for readability, not because 003 must follow 002. 007 is
always last, per the standing build-checkpoint convention.

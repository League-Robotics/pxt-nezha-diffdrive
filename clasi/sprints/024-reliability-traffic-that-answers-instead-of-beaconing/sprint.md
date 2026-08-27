---
id: '024'
title: Reliability traffic that answers instead of beaconing
status: executing
branch: sprint/024-reliability-traffic-that-answers-instead-of-beaconing
use-cases:
- SUC-001
- SUC-002
issues:
- reliability-line-free-runs-at-20-hz-on-the-radio-with-no-host.md
- radio-link-wedges-on-a-sequence-gap-and-reconnect-cannot-heal-it.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 024: Reliability traffic that answers instead of beaconing

## Goals

- Make the reliability line (`ack`/`nack`) a pure response: exactly one
  per inbound line, and none from a transport nobody has spoken to. No
  beacon, no rate limit, no configurable cadence — silence is the
  requirement, stated directly by the stakeholder and reaffirmed three
  times.
- Make a host able to actually recover a stalled radio link: fix the
  two `tools/robotlink.py` bugs that currently prevent `HELLO` — the
  protocol's own designated reconnect-resync — from ever being sent.
- Leave the wire grammar itself untouched: per-line `ack`/`nack`
  dispatch, decode-failure-is-NAK, and the telemetry piggyback are
  already correct and stay exactly as they are. This sprint removes one
  unconditional caller in the protocol fiber loop and fixes two host
  bugs around it — it is not a protocol revision.

## Problem

Two related defects, one on each side of the wire, both surfaced while
diagnosing a live radio connect on 2026-08-26:

1. **Firmware free-runs the reliability line.** `Protocol::run()`'s
   fiber loop (`src/comms/protocol.cpp:346-369`) calls
   `emitReliability()` on both `wireHandler_` (serial) and
   `wireHandlerRadio_` (radio) every `kReliabilityEmitPeriodMs` (50 ms)
   whenever telemetry is off — the boot default, and therefore the
   normal case. `ack`/`nack` is a response by definition; this call has
   no "has anyone spoken on this transport" gate at all, so an idle
   robot broadcasts 20 packets/sec on its own radio channel, addressed
   to nobody, forever. Sprint 022 made the cost of this worse than when
   it was written: the radio channel is now shared, per-robot, across
   the fleet at deploy time, so every powered robot on a channel now
   contributes its own 20 Hz beacon to that air. The RX path gives good
   reason to suspect — not yet proven — that this is a contributing
   cause of the sequence gaps the second defect can't recover from: the
   nRF radio can't receive while transmitting, and a beacon firing
   20x/sec is competing with every inbound command for the same
   half-duplex channel. The original periodic-emission design (sprint
   003 ticket 003) was scoped narrowly, as a **telemetry-piggybacked**
   self-heal for a lost `nack` — sprint 004 split `emitTelemetry()` from
   `emitReliability()` and left the `else` branch calling the latter
   unconditionally, which is the drift this sprint corrects.

2. **The host can't clear a stall once one opens.** A radio handler that
   stalls on a sequence gap streams `nack 1 0 none` at the reliability
   cadence forever, and nothing in `tools/` can clear it short of a
   robot reboot. `WireHandler::handleHello()`
   (`src/comms/wire_handler.cpp:640-652`) is the protocol's own
   designated escape hatch — it resets `expectedNext_` to 1 and clears
   `gapOutstanding_` without touching motion-completion state — but
   `tools/robotlink.py`'s `open_link()` (lines 208-244) never sends it.
   Worse, `sync_seq()` (lines 123-142), meant to adopt the robot's
   sequence state from a keepalive line, has an off-by-one on the `nack`
   case: `nack N` means "send me N next," not "N was accepted," so
   `sync_seq()` setting `_seq = N` on a `nack` allocates `#(N+1)` next —
   a fresh gap on the same wound. Even a host that stumbles onto a
   stalled robot's `nack` line re-wedges itself on reconnect, which is
   why the stall looks permanent.

## Solution

**Firmware** (`src/comms/protocol.cpp`): remove the unconditional
`else` branch that calls `emitReliability()` on both handlers every 50
ms. The conditional already distinguishes "telemetry subscribed" from
"not" (`wireAdapter_.telemetryEnabled()`); when it's false, the fix is
to do nothing periodic at all, not call a lighter-weight version of the
same thing. Two facts make this a narrow, low-risk change:

- Per-line `ack`/`nack` is **already** the entire reliability plane for
  a non-subscribed transport — `WireHandler::dispatch()`
  (`wire_handler.cpp:450`) calls `replyAck()`/`replyNack()` on every
  received line already, completely independent of the periodic call
  this sprint removes. Nothing needs to be added to `WireHandler` for
  "exactly one reliability line per inbound line" to hold; it already
  holds.
- The telemetry piggyback is untouched: `emitTelemetry()` still calls
  `emitReliability()` internally as its own third write
  (`wire_handler.cpp:1231`), so a host that has subscribed via `TLM`
  keeps getting the reliability line exactly as before — that stream is
  itself a host request, so it stays a response.

**Host** (`tools/robotlink.py`): fix `sync_seq()`'s ack/nack branch (set
`_seq = N` for an `ack`, `_seq = N - 1` for a `nack`), and make
`open_link()` send `HELLO` and consume its banner reply before doing
anything else, on both the USB and radio paths. See Architecture →
Design Rationale for how these two fixes compose once the beacon is
gone — the naive "keep calling `sync_seq()` right after `HELLO`" reading
of the fix needs one clarification to stay correct.

**Cleanup** (`tools/arc_capture.py`, `tools/tlm.py`,
`tools/tour_capture.py`, and the affected files under `tests/`): revisit
the `ack `/`nack ` filtering `arc_capture.py:161` needed only because
the beacon false-positived its firmware-identity check, and correct
comments elsewhere that describe the free-running emission as current,
expected behavior (several exist — see Test Strategy).

## Success Criteria

- A robot fresh off boot, with nothing sent to it on a given transport,
  emits zero bytes on that transport indefinitely — bench-verified: open
  a link, send nothing, observe for a window well past 50 ms (the old
  period) with no `ack`/`nack` line appearing.
- A robot subscribed via `TLM` continues to receive the piggybacked
  reliability line exactly as before — a regression check, not new
  behavior.
- Every sequenced command still draws exactly one `ack`/`nack`
  (unchanged; already true today).
- `open_link()` sends `HELLO` and reaches a correct sequence state on
  both USB and radio; a fake link that replies `nack 5` produces `#5` as
  the next allocated command id, not `#6` (pinned by a new test).
- A radio handler with a synthetic stalled gap recovers via a reconnect
  that sends `HELLO`, without a robot reboot.
- Full suite (`tests/host/`, `tests/tools/`) passes; per-transport
  isolation (`test_wire_per_transport_isolation.py`) still holds
  unchanged.

## Scope

### In Scope

- `src/comms/protocol.cpp`: remove the periodic `emitReliability()`
  calls in the telemetry-off branch of `Protocol::run()`'s fiber loop;
  correct the surrounding rationale comment (lines ~332-356), which
  currently documents the now-removed unconditional behavior as
  intentional.
- `tools/robotlink.py`: `sync_seq()`'s ack/nack branch fix; `open_link()`
  sends `HELLO` before establishing sequence state, on both carriers;
  new `tests/tools/test_robotlink.py`.
- `tools/arc_capture.py`, `tools/tlm.py`, `tools/tour_capture.py`:
  revisit/update beacon-era filtering and doc comments.
- `tests/host/test_wire_grammar.py`, `test_wire_telemetry_frame.py`,
  `test_wire_per_transport_isolation.py`, `test_wire_motion_verbs.py`,
  `test_wire_reliability.py`: correct stale prose describing
  `protocol.cpp`'s periodic emission as unconditional current behavior;
  re-run as a regression gate (no assertion changes expected — see Test
  Strategy for why).
- `tests/tools/test_tlm.py`, `test_run_verbs.py`: same review, per the
  brief's explicit instruction to check them.

### Out of Scope

- Any change to `WireHandler`'s public behavior (`dispatch()`,
  `emitReliability()`, `emitTelemetry()`) — already correct; this sprint
  only removes an unconditional caller in `protocol.cpp`.
- Measuring the suspected radio TX/RX self-jamming feedback loop (RX
  success rate with the beacon on vs. off). Real, but explicitly flagged
  in the issue as "needs measuring, not assuming" — not required to
  satisfy the stakeholder's silence requirement, which holds regardless
  of whether the feedback loop is real. A natural follow-up, not this
  sprint's work.
- Any rate-limiting, host-side filtering, or configurable-cadence
  approach — explicitly rejected by the stakeholder in favor of pure
  silence.
- Rotation/motion accuracy work, or anything in sprint 020/021's scope.
- `radio-robot-lib`'s own `protocol.md` spec text (a different repo;
  S8.5 there still describes a periodic emission, and this sprint's
  narrower reading of it — piggyback-only — is a local conformance
  clarification, not a spec change this repo can make).
- Whether the one-time unsolicited boot banner (`protocol.cpp:267`,
  `wireHandler_.sendBanner()`, fired once at fiber startup) reaches
  radio as well as serial — unchanged by this sprint, per the brief
  ("the boot banner is separate and stays").

## Test Strategy

**What changes at the `WireHandler` level: nothing.** `dispatch()`'s
per-line ack/nack and `emitReliability()`/`emitTelemetry()`'s piggyback
behavior are untouched by this sprint — the entire firmware fix is
deleting one unconditional caller in `protocol.cpp`. Every host test
file listed as "asserts on ack/nack byte sequences" (`test_wire_grammar
.py`, `test_wire_telemetry_frame.py`, `test_wire_per_transport_isolation
.py`, `test_wire_motion_verbs.py`, `test_wire_reliability.py`) drives
`WireHandler` directly through the `wire_grammar_shim.cpp` ctypes
binding, never through `Protocol`'s fiber loop — so their assertions
(built on `_ack()`/`_nack()` golden bytes) remain correct as-is. What
*does* need updating in these files is prose: several docstrings and
comments (e.g. `test_wire_grammar.py:274-276`,
`test_wire_reliability.py`'s own module docstring citing S8.5,
`test_wire_motion_verbs.py:654`) describe `protocol.cpp`'s periodic
emission as an unconditional fact about production behavior, which
stops being true. Same category of staleness in `tests/tools/test_tlm
.py` (lines ~54-61, ~101-105) and `tools/tlm.py` (its own "streams
continuously at 50 ms" doc comment). `test_run_verbs.py` was checked
per the brief's instruction and has no beacon dependency — it tests
`RUN:` string-keyed dispatch, unrelated to the reliability plane; no
change expected there beyond confirming that.

**What is genuinely NOT host-testable: the firmware removal itself.**
`Protocol` is CODAL-bound and has no host shim — established precedent
in this exact area, stated by `test_wire_per_transport_isolation.py`'s
own docstring about `wireHandler_`/`wireHandlerRadio_`'s composition in
`protocol.h`: "that specific pair can only be verified by code review."
The same is true of the periodic-call removal. Verification is (a) code
review of the diff, and (b) a bench check: open a link, send nothing,
confirm silence past 50 ms; then send `TLM POSE #1` and confirm the
piggyback resumes. Do this on USB at minimum; radio via the zavaz relay
if convenient, since both handlers are driven by the same loop and the
fix is symmetric.

**New coverage**: `tests/tools/test_robotlink.py` (new file — none
exists today) with a fake serial port, proving `sync_seq()` maps `nack
N` to `_seq = N - 1` and `ack N` to `_seq = N` distinctly (not the same
line, per the bug), and that `open_link()` sends `HELLO` before
anything else on both the USB and radio paths.

**Per-transport isolation**: unaffected by this sprint — no code path
touched here reads or writes both handlers' state together (there is no
shared state; `expectedNext_`/`gapOutstanding_`/`malformedCount_` are
plain per-instance members). `test_wire_per_transport_isolation.py` is
re-run as a regression gate, not given new assertions, because the
property it proves doesn't change.

**Verification commands**: `uv run pytest tests/host/ tests/tools/`;
`uvx ruff check tools tests`.

## Architecture

**Sizing: Substantial**, by module count rather than inherent per-change
complexity. This sprint touches two modules with an existing
relationship (`src/comms/` firmware and `tools/` host tooling talk to
each other over the wire protocol today) plus a documentation-hygiene
pass across several test files — more than the compact tier's literal
"one module" test, even though no individual change here introduces a
new module, a new or changed cross-module dependency, a
dependency-direction change, or a data-model change. Per the "prefer the
heavier tier when borderline" guidance, this is classified substantial
and reviewed at full depth; no diagram is included (see What Changed's
closing paragraph for why).

### What Changed

**`src/comms/protocol.cpp` (protocol fiber loop)** — `Protocol::run()`'s
periodic block (lines 346-369) currently reads:

```cpp
if (nowMs - lastEmitMs >= kReliabilityEmitPeriodMs) {
  if (wireAdapter_.telemetryEnabled()) {
    ... emitTelemetry(snapshot) on both handlers  // unchanged
  } else {
    wireHandler_.emitReliability();       // REMOVED
    wireHandlerRadio_.emitReliability();  // REMOVED
  }
  lastEmitMs = nowMs;
}
```

The `else` branch is deleted outright — not replaced with a gated or
rate-limited version. `kReliabilityEmitPeriodMs` (50 ms) and the `if`
itself stay, since they still govern the telemetry-on cadence. The
comment block immediately above this code (lines 332-356) currently
documents the unconditional call as deliberate, citing sprint 003
ticket 003's self-heal rationale; it is rewritten to state the new
behavior and cite this sprint in its place, so a future reader doesn't
find code that contradicts its own neighboring comment.

**`tools/robotlink.py` (host link layer)** — two independent bug fixes
in the same file, both inside `Link`/`open_link()`:

- `sync_seq()` (lines 123-142) currently sets `self._seq =
  int(m.group(1))` for both an `ack` and a `nack` match. The fix
  distinguishes them in the same regex match — `ack N` → `_seq = N`
  (next id to allocate is N+1); `nack N` → `_seq = N - 1` (next id to
  allocate is N, matching what the robot is actually waiting for).
- `open_link()` (lines 208-244) never sends `HELLO`. The fix sends it
  and consumes the banner reply before anything else, on both the
  zavaz-radio branch and the plain-USB branch.

**`tools/arc_capture.py`, `tools/tlm.py`, `tools/tour_capture.py`
(cleanup)** — `arc_capture.py:161`'s firmware-identity check filters
`ack `/`nack ` lines specifically because the beacon used to
false-positive it; `tlm.py`'s module docstring and `TlmStream`
documentation describe the keepalive as streaming "continuously at 50
ms." Both are corrected to describe post-fix reality (a reply only ever
follows a request); `tour_capture.py` was checked and needs no
functional change, only confirmation it carries no equivalent
assumption.

No component/module diagram is included: none of these changes compose
with each other in a new way, or add an edge to the existing
firmware↔host wire-protocol relationship — `protocol.cpp` stops calling
a function it used to call unconditionally, `robotlink.py` starts
calling a wire verb (`HELLO`) that already existed and was already
documented as the reconnect primitive, and the cleanup items are prose.
A diagram would show the same two boxes and one edge that already
exist today, with nothing new to label (same reasoning sprints 020 and
023 used to omit theirs).

### Design Rationale

**Decision: delete the periodic emission outright rather than rate-limit
or gate it more finely.**
- *Context*: the stakeholder considered and explicitly rejected two
  intermediate positions — "reduce the rate" and "bound the repeats" —
  before stating the requirement as unconditional silence. `ack`/`nack`
  is defined as a response; a response with no corresponding request is
  a contradiction in terms, not a tuning parameter.
- *Alternatives considered*: (a) reduce the cadence (e.g. 500 ms instead
  of 50 ms) — rejected, still beacons, just slower; (b) emit only when
  `gapOutstanding_` is true (stall-only re-nacking) — rejected, still
  broadcasts unconditionally to an idle robot the instant any command is
  lost, which is exactly the case a shared radio channel makes common;
  (c) host-side filtering (ignore beacon lines in `tools/`) — rejected
  by the stakeholder outright, it does nothing for airtime; (d) delete
  the branch entirely — chosen, matches the stated requirement exactly
  and needs no new state or configuration.
- *Consequences*: the one case sprint 003 ticket 003's periodic emission
  was written to cover — a **lost** `ack`/`nack` reply — no longer
  self-heals via a passive re-emission. See the next decision for why
  this is an acceptable, understood trade, not an oversight.

**Decision: the lost-reply case moves from a firmware-side timer to the
host's own retransmit loop, and that is a feature, not a regression.**
- *Context*: sprint 003 ticket 003 specified the periodic emission
  narrowly — a lost `nack` "self-heals via the next
  telemetry-piggybacked reliability line ... without any new timer."
  Sprint 004 then made that emission unconditional instead of
  piggyback-only, which is the actual drift this sprint fixes; the
  original design intent was never "beacon regardless of subscription."
- *Alternatives considered*: (a) keep some periodic re-emission as a
  narrower self-heal (e.g. only while `gapOutstanding_`) — rejected, see
  the previous decision; (b) accept the loss of self-healing as a real
  capability regression the sprint must compensate for elsewhere (e.g.
  a new host-side polling loop) — rejected as unnecessary, because the
  compensating mechanism already exists; (c) rely on
  `robotlink.py`'s existing `send_until()` (`tools/robotlink.py:162`,
  which resends the *same* id until it sees the expected reply prefix)
  as the sole recovery path for a lost reply — chosen, no new code
  needed.
- *Consequences*: under pure request/response, a lost `ack`/`nack` still
  heals — one round trip later, driven by the host's own retransmit,
  which is where retransmit responsibility belongs on a lossy link. The
  **only** case genuinely given up is a host that sends a command, loses
  the reply, and then goes quiet forever without ever retrying — a host
  bug, not a transport failure, and not something a robot should
  broadcast at 20 Hz to cover for. **A future reader must not "restore"
  the periodic emission as a fix for a perceived regression** — the
  self-heal path changed shape, it did not disappear, and restoring the
  beacon to patch around a host that fails to retry would reintroduce
  exactly the defect this sprint removes.

**Decision: `open_link()` sends `HELLO` and then treats the connection
as reset, rather than calling the old `sync_seq()` and trusting whatever
it reads.**
- *Context*: `sync_seq()`'s original design assumed a passive keepalive
  line would always be available to read shortly after connecting — a
  fair assumption while the beacon existed, but no longer, once
  firmware ticket 1 lands. `HELLO`'s own contract
  (`wire_handler.cpp:640-652`) is stronger than "produces a line worth
  parsing for state": it deterministically resets the robot to
  `expectedNext_ = 1`, `gapOutstanding_ = false`, unconditionally, on
  whichever handler received it. A freshly constructed `Link` already
  initializes `self._seq = 0` (`robotlink.py:105`), which is exactly the
  correct host-side counterpart to a robot at `expectedNext_ = 1`.
- *Alternatives considered*: (a) implement the issue's proposed fix
  literally — send `HELLO`, then call the existing (bug-fixed)
  `sync_seq()` expecting it to read a line — rejected as the sole
  mechanism, because once the beacon is gone there is normally nothing
  for it to read at that point in the connection sequence, so this would
  silently degrade into a 1.5 s dead wait on every connect for no
  benefit; (b) drop `sync_seq()` entirely — rejected, its bug fix (the
  ack/nack branch) is still correct and worth having for any future
  caller that legitimately reads a live `ack`/`nack` line outside the
  connect path; (c) send `HELLO`, consume its banner, and rely on the
  deterministic post-`HELLO` state (`self._seq = 0`, matching a fresh
  `Link`) rather than blocking on a read that no longer has anything
  to answer it — chosen.
- *Consequences*: `open_link()`'s post-`HELLO` behavior does not need to
  read anything further to know the connection is in a known-good state
  — `HELLO`'s own guarantee **is** the resync, not a side effect
  `sync_seq()` needs to separately observe. `sync_seq()`'s bug fix
  stands as a correctness fix in its own right (it is still wrong today,
  independent of the beacon), but the ticket implementing this must not
  wire it into `open_link()` in a way that blocks on a reply that no
  longer arrives. Ticket 002 documents this explicitly so the two fixes
  compose correctly rather than one silently defeating the other's
  benefit.

### Migration Concerns

- **No data migration.** No persisted or wire-format state changes
  shape — `ack`/`nack`'s field layout is untouched; only when it is
  emitted changes.
- **Deployment sequencing, host/firmware pairing.** An **unpatched**
  host (old `robotlink.py`, no `HELLO`, buggy `sync_seq()`) connecting
  to a **patched** robot (no beacon) is a real, if narrow, compatibility
  gap: the old `sync_seq()` will find nothing to read immediately after
  connecting (nothing streams passively anymore) and will simply time
  out, silently leaving `_seq` at its constructor default of `0`. That
  happens to be correct for a robot that has processed nothing yet, but
  is **wrong** for a host reconnecting mid-session to a robot that has
  already advanced past `expectedNext_ = 1` — the resulting guess opens
  a fresh gap immediately. This is a real degradation versus today's
  behavior (where the beacon almost always provided a line for the old
  `sync_seq()` to read, even if it mishandled the `nack` case). Ticket
  002 should ship before field use of a beacon-free robot build, not
  after — recorded here so this isn't discovered as a surprise on the
  playfield.
- **Per-transport isolation is structurally unaffected** — see Test
  Strategy; no shared state exists for this sprint's changes to
  perturb.
- **`radio-robot-lib`'s own `protocol.md` S8.5** still describes a
  periodic emission at the spec level; this sprint narrows this repo's
  own conformance to "piggyback-only," which is consistent with S8.5's
  own wording (piggybacked on telemetry) but not with the unconditional
  reading sprint 004 drifted into. No change to the spec itself is in
  this repo's power to make (different repo) — flagged, not fixed, same
  disposition as sprint 023's own cross-repo drift note.

### Open Questions

1. The suspected radio TX/RX self-jamming feedback loop (issue's own
   "needs measuring, not assuming") is not validated in this sprint.
   Recommended follow-up: a fixed command-burst RX-success-rate
   measurement with the beacon on vs. off, once both are available to
   compare (the "on" case requires temporarily running pre-sprint
   firmware). Not required to ship this fix — the stakeholder's silence
   requirement holds regardless of whether the loop is real.
2. Does the one-time unsolicited boot banner (`protocol.cpp:267`) fire
   on the radio handler as well as serial? Out of scope for this sprint
   per the brief, but adjacent enough to "an idle robot should be
   silent until spoken to" that it may be worth a future look — this
   sprint does not touch it and takes no position on whether it should
   change.

## Use Cases

### SUC-001: An idle robot is silent on both carriers until spoken to
Parent: None — this is an internal wire-protocol traffic guarantee;
`docs/design/usecases.md` covers the PXT extension's block-level API,
not the wire protocol's own reliability-plane behavior, so no existing
UC applies.

- **Actor**: Any host (or absence of one) on either transport; every
  other robot sharing the same radio channel.
- **Preconditions**: A robot has booted (or last received `HELLO`) and
  no line has been received on the transport in question since.
- **Main Flow**:
  1. The robot's protocol fiber runs its normal loop.
  2. On the transport that has received nothing, the fiber emits no
     `ack`/`nack` line, ever, regardless of elapsed time.
  3. A host sends exactly one sequenced line on that transport.
  4. The robot replies with exactly one `ack` or `nack` for that line,
     via `WireHandler::dispatch()`'s existing per-line reply path
     (unchanged by this sprint).
  5. No further reply follows until the next inbound line.
- **Postconditions**: Total reliability-line traffic on an unaddressed
  transport is zero bytes, indefinitely. Traffic on an addressed
  transport is exactly one reply per inbound line, except while a host
  is subscribed via `TLM`, in which case the reliability line
  piggybacks on each telemetry frame (itself a response to the `TLM`
  subscription).
- **Acceptance Criteria**:
  - [ ] Bench-verified: a link opened with nothing sent produces zero
        `ack`/`nack` lines over an observation window well past the old
        50 ms period.
  - [ ] A `TLM`-subscribed host continues to receive the piggybacked
        reliability line unchanged.
  - [ ] `tests/host/test_wire_per_transport_isolation.py` continues to
        pass unchanged — a gap on one carrier still cannot affect the
        other's reply stream.

### SUC-002: A reconnecting host clears a stalled sequence gap via HELLO, without a reboot
Parent: None — internal wire-protocol reconnect/recovery behavior; no
existing UC in `docs/design/usecases.md` covers host-tooling reconnect
semantics.

- **Actor**: A host reconnecting `tools/robotlink.py`'s `Link` to a
  robot whose radio (or serial) handler has a stalled sequence gap
  (`gapOutstanding_ = true`).
- **Preconditions**: The robot's handler for the transport being
  (re)connected is stalled — every well-formed command is being nacked
  identically, regardless of content, because a numeric gap is
  outstanding.
- **Main Flow**:
  1. The host calls `open_link()`.
  2. `open_link()` sends `HELLO` and consumes the banner reply before
     anything else, on whichever carrier it is opening.
  3. The robot's `handleHello()` resets that handler's `expectedNext_`
     to 1 and clears `gapOutstanding_`, without touching motion-
     completion state.
  4. `open_link()` establishes `self._seq = 0` to match the
     now-known-reset robot state — no blocking read is needed to
     "learn" this, since `HELLO`'s own contract guarantees it.
  5. The host's next sequenced command (`#1`) is accepted normally.
- **Postconditions**: The previously stalled handler now accepts
  commands again, with no robot reboot involved. A `sync_seq()` call
  made against a live `nack N` line (outside the `open_link()` path)
  correctly computes `_seq = N - 1`, not `N`.
- **Acceptance Criteria**:
  - [ ] `tests/tools/test_robotlink.py` (new) proves `sync_seq()`'s
        `ack`/`nack` branches distinctly, against a fake link.
  - [ ] `tests/tools/test_robotlink.py` proves `open_link()` sends
        `HELLO` before any sequenced command, on both the USB and radio
        paths.
  - [ ] A fake link replying `nack 5` yields `#5` as the next allocated
        command id, not `#6`.

## GitHub Issues

(None — this sprint's two issues are local CLASI issues in
`clasi/issues/`, not GitHub issues.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [x] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [x] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | Firmware: stop the free-running reliability emission in protocol.cpp | — |
| 002 | Host: open_link() resyncs via HELLO, and sync_seq() fixes its ack/nack asymmetry | — |
| 003 | Cleanup: retire beacon-era filtering and stale prose across tools/ and tests/ | 001, 002 |

Tickets execute serially in the order listed.

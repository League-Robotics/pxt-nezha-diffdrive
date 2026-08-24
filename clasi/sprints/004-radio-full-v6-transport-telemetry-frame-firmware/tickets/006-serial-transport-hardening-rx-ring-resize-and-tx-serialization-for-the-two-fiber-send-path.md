---
id: '006'
title: 'Serial transport hardening: RX ring resize and TX serialization for the two-fiber
  send path'
status: open
use-cases: [SUC-007]
depends-on: ["001", "002"]
github-issue: ''
issue: serial-transport-rx-ring-and-tx-serialization.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Serial transport hardening: RX ring resize and TX serialization for the two-fiber send path

## Description

Code review 2026-08-23 (R-19 + R-20, WIRE-03 + WIRE-04, both CONFIRMED)
found two `SerialTransport` defects that ticket 002's original
acceptance criteria wrongly implied did not exist on the serial side
(that wrong assertion has been corrected in ticket 002's own file —
see its amended AC). This ticket does the actual serial-side work:

1. **RX ring is v5-sized (R-19).** `serial_transport.cpp:24`
   (`SerialTransport::begin()`) still calls
   `uBit.serial.setRxBufferSize(128)`, unchanged since before v6 raised
   `kMaxLineBytes` to 240 (`serial_transport.h:32`, sprint 003 ticket
   005). During wire-driven motion the protocol fiber drains the ring
   only every ~24 ms (`shims.cpp:526-542`'s self-pacing tick), which at
   115200 baud is ~276 bytes of RX capacity needed per window — a
   near-max-length line plus anything else arriving in the same window
   (a keepalive ack, a reliability-layer resend) overflows a 128-byte
   ring before the fiber next drains it, and CODAL's ring drops the
   overflow silently. A resend re-enters the exact same window, so this
   is not a one-off: it is a deterministic-enough drop under sustained
   motion traffic. **Fix**: raise `setRxBufferSize()` (and, for
   symmetry, `setTxBufferSize()`, currently also 128) to >= 2x
   `kMaxLineBytes` (480 B), mirroring the issue's own stated remedy.

2. **TX is unserialized (R-20, serial half).** `emitLine()` (the TS
   fiber's result-line path, reached via `SerialTransport::writeLine()`)
   and the serial `WireHandler`'s own replies/keepalives (reached the
   same way, since ticket 001 keeps one serial `WireHandler` — this
   part of R-20 is NOT new as of this sprint, it predates ticket 001)
   both call `writeLine()`, which issues two back-to-back
   `uBit.serial.send(..., SYNC_SLEEP)` calls (content, then the `0x0A`
   delimiter) with no guard between callers and no check of either
   call's return value. `SYNC_SLEEP` blocks and yields the calling
   fiber, which is exactly the window the other fiber can interleave
   into — the two writers can garble each other's line, or one can
   silently drop depending on CODAL's internal buffering state at the
   time (the issue's own phrasing: "drop-vs-block depends on CODAL
   mode; both are failures"). **Fix**: serialize the two writers and
   stop discarding `send()`'s return.

This ticket is the serial counterpart to ticket 002's radio guard, but
the right amount of machinery is NOT identical — see Design Rationale
in Implementation Plan below for why serial gets a bounded retry
instead of radio's accept-the-drop-for-telemetry asymmetry.

## Acceptance Criteria

- [ ] `SerialTransport::begin()` sizes both the RX and TX ring to
      `>= 2 * kMaxLineBytes` (i.e. >= 480 B for RX; the ticket may use
      the existing named constant rather than a bare literal) —
      replacing the current `128`.
- [ ] `SerialTransport::writeLine()` is guarded so two fibers calling it
      concurrently cannot interleave their bytes into the wire: a
      `sending_`-style bool (mirroring ticket 002's `RadioTransport`
      pattern) around the guarded body, OR an equivalent minimal
      construct — implementer's choice, but the guard must cover BOTH
      `uBit.serial.send()` calls inside `writeLine()` (content AND the
      delimiter), not just the first.
- [ ] Unlike ticket 002's radio guard (where the second caller drops
      immediately and only `emitLine()` retries once), the serial guard
      uses a **bounded retry** on BOTH callers — `fiber_sleep(2)` and
      retry, capped at a small fixed attempt count (e.g. 5) — because
      serial has no caller whose loss is "fine": both the TS fiber's
      result lines and the `WireHandler`'s protocol replies/keepalives
      are host-visible traffic with no self-healing `seq`-gap signal
      the way telemetry has. If the cap is exhausted, the call gives up
      silently but the drop is counted (next bullet), not retried
      forever.
- [ ] `writeLine()`'s two `uBit.serial.send()` return values are
      checked; a non-OK result (or exhausting the retry cap above)
      increments a drop counter exposed as a new `diagValue()` ordinal
      (next available: 26) so a bench operator can see it via `probe(26)`
      the same way the existing counters (`i2cFaultCount`,
      `cycleOverrunCount`, etc.) are already read — mirrors the issue's
      own stated remedy ("count drops in a DIAG ordinal").
- [ ] `RadioTransport`'s existing guard (ticket 002) and its
      `sending_` member are untouched by this ticket — this ticket adds
      an analogous but separately-scoped guard on `SerialTransport`,
      not a shared abstraction between the two (see Design Rationale:
      the two guards' retry policies are deliberately different, so a
      shared base class would either need a policy parameter or would
      force one transport's policy onto the other).
- [ ] A host test exists IF expressible; if not, this ticket states
      explicitly why not, following ticket 002's own precedent for its
      un-host-testable radio guard (see Testing Plan below — the
      answer here is "the ring resize and the real CODAL guard are not
      host-testable, for the same `#include "pxt.h"`-with-no-host-shim
      reason ticket 002 gives for `radio_transport.cpp`").

## Implementation Plan

**Approach**: Mirror ticket 002's `sending_`-guard shape for the
serialization mechanism, but with a bounded-retry-on-both-callers
policy instead of radio's asymmetric drop-vs-retry-once, and add the
ring resize as an independent one-line-per-call change in `begin()`.

**Design Rationale — why serial's retry policy differs from radio's
(ticket 002)**: *Context*: both transports now have two fibers writing
through one guarded send path. *Alternatives considered*: (a) copy
ticket 002's policy verbatim (second caller drops immediately, only one
caller retries once); (b) a bounded retry on every caller, capped and
counted. *Why (b)*: radio's asymmetry works because telemetry
self-heals via the `seq` gap and only `emitLine()`'s result lines are
irreplaceable — serial has no such split; a `STATUS` reply lost to a
race is just as bad as an `OCAL:` result lost to one, so treating every
serial caller the way `emitLine()` is treated on radio is the more
honest match for serial's actual stakes. *Consequences*: a fiber can
now block slightly longer under contention (up to the retry cap) than
it would with radio's instant-drop policy — acceptable, since serial
traffic volume/contention is lower than radio's (one host, not a fleet)
and the existing 50 ms emission cadence has headroom for a few extra
`fiber_sleep(2)` calls.

**Files to modify**:
- `src/serial_transport.h`: raise the ring-size constant/literal used
  by `begin()`; add a `sending_` bool member (private, next to any
  existing flags) and a drop-counter member (or route the counter
  through `shims.cpp`'s existing kernel-output pattern if that reads
  more consistent with how `diagValue()`'s other counters are sourced —
  implementer's call, but it must end up reachable from `diagValue()`).
- `src/serial_transport.cpp`: `begin()`'s two `setRxBufferSize`/
  `setTxBufferSize` calls; guard `writeLine()`'s body with the bounded
  retry described above; check both `uBit.serial.send()` return values.
- `src/shims.cpp`: add `case 26:` to `diagValue()`'s switch, returning
  the new serial-drop counter.
- `src/protocol.h`/`.cpp`: no expected change — `Protocol::emitLine()`
  already calls into `SerialTransport::writeLine()` (or the equivalent
  serial sink path) without needing to know about the new internal
  guard, unless the implementer finds `emitLine()` needs its own
  retry-on-false the way ticket 002 added for radio (in which case,
  mirror that shape here too — implementer's judgment once the actual
  call signature is in front of them).

**Testing plan**:
- **No host test is possible for the ring resize or the real
  concurrency guard's behavior**, for the same reason ticket 002 gives
  for `RadioTransport`: `src/serial_transport.cpp` `#include`s `pxt.h`
  directly (`uBit.serial`) and has no host shim in `tests/host/` —
  building one would mean simulating CODAL's serial ring and fiber
  scheduler, well beyond this ticket's scope. State this explicitly
  rather than fabricating a test that doesn't exercise the real hazard.
  Verify by code review: confirm the ring size constant changed,
  confirm `sending_` (or equivalent) is set/cleared on every path
  including the retry-cap-exhausted path, confirm both `send()` return
  values are checked, confirm the new `diagValue(26)` ordinal reads the
  counter correctly (this last part CAN be host-tested via the existing
  `diagValue()` test-double pattern in `tests/host/wire_motion_verb_shim.cpp`
  if the counter is threaded through a location the shim already
  models — check whether it needs a new settable double there).
- Ticket 005's Phase C bench checkpoint should add a line to its
  handoff checklist (a small edit to ticket 005, made alongside this
  one) noting this guard's first live exercise is at the bench, same as
  it already does for ticket 002's radio guard.
- **Verification command**: `uv run pytest tests/host/` (scoped run;
  no test file is expected to change unless the `diagValue(26)` counter
  turns out to be host-testable per the note above, in which case scope
  to that new/extended test file specifically).

**Documentation updates**: `serial_transport.h`'s file header (and
`begin()`'s own comment, which currently explains the 128-byte choice
in v5 terms) should be updated to state the new ring size and the
reason (v6's 240-byte `kMaxLineBytes`, not v5's ~27-byte binary frame,
is now the sizing driver). `writeLine()`'s doc comment should describe
the new two-caller-with-a-guard reality, mirroring the update ticket
002 makes to `radio_transport.h`'s equivalent comment.

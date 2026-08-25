---
id: '002'
title: 'RadioTransport TX capacity: raise kMaxPayloadBytes to 240 and drift-test the
  three line-capacity constants'
status: open
use-cases: ['SUC-001']
depends-on: ['001']
github-issue: ''
issue: radio-rx-capacity-fragmentation.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# RadioTransport TX capacity: raise kMaxPayloadBytes to 240 and drift-test the three line-capacity constants

## Description

`RadioTransport::kMaxPayloadBytes` (`src/radio_transport.h:119`) is 200,
unchanged since before sprint 003 raised the wire grammar's own ceiling
(`Wire::WireHandler::kMaxLineBytes`, `SerialTransport::kMaxLineBytes`) to
240. `protocol.cpp::emitLine()` already clips to this constant **by
name** (sprint 008), so raising the constant's value is the only change
needed at that call site — no code there changes.

Per sprint.md's Architecture (Step 6): `sendFragmented()`'s existing
multi-fragment TX loop is already correct and needs no change either —
raising the cap to 240 (241 with the trailing delimiter byte) still
comfortably fits in one physical fragment under this project's
`microbit_radio_max_packet_size: 250` (`kMtu` ≈ 247), so the loop
continues to run its single-iteration path for every real payload,
exactly as it does today at 200. `frameBuf_[256]` already has headroom
for a 240-byte payload plus its 3-byte fragment header and needs no
change.

Depends on ticket 001 only to avoid two tickets touching
`radio_transport.h` in the same sprint out of sequence — there is no
functional dependency between the RX buffer/predicate change and this
TX constant raise.

**Pinned-test reconciliation.** `tests/host/test_wire_telemetry_frame.py`
(sprint 004 ticket 003) pins the widest-frame measurements against the
**old** 200-byte TX ceiling, including
`test_widest_pathological_int32_min_frame_confirms_open_question_2`,
which documents the 239-byte pathological FULL frame as "39 B over" 200.
Against the new 240-byte ceiling that same frame fits, with exactly 1
byte of headroom — thin, not comfortable (flagged in sprint.md's Open
Questions). Update this test's assertions to the new boundary; do not
delete the pathological-frame measurement itself, since it remains the
project's only pinned evidence of the FULL column set's true worst case.

## Acceptance Criteria

- [ ] `RadioTransport::kMaxPayloadBytes` is 240; `payloadBuf_` resizes
      with it (`kMaxPayloadBytes + 1`, unchanged formula).
- [ ] `protocol.cpp::emitLine()` requires no code change (already
      references the constant by name) — confirmed by reading the call
      site, not assumed.
- [ ] A new host test asserts
      `RadioTransport::kMaxPayloadBytes == Wire::WireHandler::kMaxLineBytes
      == SerialTransport::kMaxLineBytes` (all 240), and — via a
      compile-time or runtime check against ticket 001's own local
      constant — that `RadioTransport`'s RX buffer capacity equals the
      same value, so a future edit to any one of these four numbers
      fails a test rather than silently reintroducing an inequality.
- [ ] `tests/host/test_wire_telemetry_frame.py`'s pinned boundary
      assertions are updated to the 240-byte ceiling; the 239-byte
      pathological-frame measurement itself is preserved (not deleted),
      with a comment noting the 1-byte headroom against the new cap.
- [ ] `tests/host/test_wire_telemetry_projection.py` (the realistic-value
      projection, 138 B) is re-run to confirm it is unaffected (it
      already had headroom under 200 and gains more under 240).

## Implementation Plan

**Approach.** A one-constant change in `radio_transport.h`, a new drift
test, and reconciling one pinned pathological-frame test's boundary
values. No other file's code changes (`protocol.cpp` already
references the constant by name, per sprint 008).

**Files to modify:**
- `src/radio_transport.h` — `kMaxPayloadBytes` 200 → 240; update the doc
  comment above it (sprint 008 already corrected it to state the true
  "deliberately the tighter cap" relationship — re-verify that statement
  still reads correctly once the value changes, since "tighter" no
  longer applies once RX/TX/wire are all equal at 240; state equality
  explicitly instead).
- `tests/host/test_wire_telemetry_frame.py` — boundary assertions moved
  to 240; pathological-frame headroom comment added.
- A new or extended host test file adds the three/four-way drift
  assertion described above.

**C++11 gate coverage.** `radio_transport.h`/`.cpp` are **out** of the
`-std=c++11` syntax gate (transport layer, `.cpp` includes `pxt.h` —
`src/DESIGN.md` §11). The new drift test itself is host-test tooling,
not gated code.

**Testing plan.**
- New drift test (host-only, no hardware dependency): asserts the four
  capacity numbers agree.
- Update `test_wire_telemetry_frame.py`'s pinned boundary values.
- Run the full `tests/host` suite to confirm no other test depended on
  the old 200-byte value.

**Documentation updates.** None beyond this ticket and the sprint's
design overlay, which already states the "equal, not deliberately
unequal" resolution.

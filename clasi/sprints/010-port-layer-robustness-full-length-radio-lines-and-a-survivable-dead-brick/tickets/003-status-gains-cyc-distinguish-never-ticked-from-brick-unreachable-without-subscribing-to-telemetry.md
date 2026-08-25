---
id: '003'
title: STATUS gains a cyc field so never-ticked is distinguishable from brick-unreachable
status: open
use-cases: ['SUC-002']
depends-on: []
github-issue: ''
issue: unpowered-nezha-brick-wedges-program-at-boot.md
completes_issue: false  # This closes only the observability half of the
  # issue (never-ticked vs. unreachable is now distinguishable). The
  # actual bus-hang guard (ticket 004) and its bench confirmation
  # (ticket 005) are still open; the issue stays open past this sprint
  # pending those.
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# STATUS gains a cyc field so never-ticked is distinguishable from brick-unreachable

## Description

Bench evidence (`unpowered-nezha-brick-wedges-program-at-boot.md`'s
2026-08-24 correction) established that a healthy robot nothing has ever
ticked and a robot with a genuinely unreachable brick report the
**identical** `STATUS` line: `ready=0 connL=0 connR=0 i2cf=0`. Root
cause: `active_` is only promoted from `staged_` inside `step()`
(`snapshotConfig()`, `src/diffdrive.cpp:403`), `out_.ready` reads
`active_` (`:799`), and `connected_`/`i2cFaultCount_` are only refreshed
inside `collect()`/`publishOutput()` — all of which run only when some
caller ticks the kernel. `STATUS` currently exposes no readback of
"has this kernel ever stepped," so an operator cannot tell the two
apart from the wire without first issuing a motion command and hoping it
ticks.

**The fix needs no new kernel state.** `DifferentialDrive::Output`
already carries `cycleCount` (`src/diffdrive.h:118`), already surfaced
via `diagValue(kDiagCycleCount)` (ordinal 16,
`src/wire_adapter.cpp:207`, `src/shims.cpp:854`), already read by FULL
telemetry's `cyc` column (`src/wire_adapter.cpp:625`). The only gap is
that `STATUS` (unlike FULL telemetry) never surfaces it, and STATUS is
the reply a bench operator reads without first subscribing to telemetry.

## Acceptance Criteria

- [ ] `Wire::StatusFields` (`src/wire_handler.h`) gains a `uint32_t cyc`
      field.
- [ ] `WireAdapter::status()` (`src/wire_adapter.cpp:298`) sets
      `out.cyc = static_cast<uint32_t>(diagValue(kDiagCycleCount));` —
      no `shims.cpp` change, no new forward declaration.
- [ ] `WireHandler::execStatus()`'s format string
      (`src/wire_handler.cpp:705-707`) gains ` cyc=%lu`, placed after
      `i2cf=` (both are kernel-health-cousin fields); the 200-byte
      `buf` headroom is re-verified against the longer line.
- [ ] `tests/host/wire_mock_adapter.h`'s `WireMockAdapter` gains a
      settable `cyc` field feeding `status()`.
- [ ] A host test with the mock adapter at `cyc=0` asserts STATUS's
      reply contains `cyc=0`.
- [ ] A host test with the mock adapter at `cyc>0` and `connLeft=false`
      asserts STATUS's reply shows the ticked-and-not-connected shape
      (`cyc` nonzero, `connL=0`).
- [ ] A host test against the **real** `WireAdapter` (via `WaHandle` or
      equivalent, stepping a real kernel with `FakeMotor`/`FakeClock`)
      confirms `status().cyc` equals `diagValue(kDiagCycleCount)` at
      that same instant — mirroring the same-source guarantee sprint 004
      ticket 004 established for `i2cf` ("the two can never disagree").
- [ ] No existing STATUS field's meaning or position changes; this is
      purely additive.

## Implementation Plan

**Approach.** Reuse an already-correct, already-tested kernel readback
(`cycleCount` via `diagValue(kDiagCycleCount)`) in a new place
(`STATUS`), exactly the way sprint 004 ticket 004 added `i2cf=` to
`STATUS` from the same `diagValue()` seam. No new kernel-facing state,
no new module, no new cross-module dependency.

**Files to modify:**
- `src/wire_handler.h` — `Wire::StatusFields` gains `uint32_t cyc`.
- `src/wire_handler.cpp` — `execStatus()`'s `snprintf` format string and
  argument list.
- `src/wire_adapter.cpp` — `WireAdapter::status()` populates the new
  field.
- `tests/host/wire_mock_adapter.h` — `WireMockAdapter` re-synced with
  the new `StatusFields` member (this project's standing "test doubles
  must be updated in the same ticket that changes the real shape"
  discipline, sprint 007's own highest-risk-item callout).

**C++11 gate coverage — IN gate.** `wire_handler.h`/`.cpp` and
`wire_adapter.cpp` are three of the four files the `-std=c++11
-fsyntax-only` syntax gate already covers
(`tests/host/test_cxx11_syntax_gate.py`, `src/DESIGN.md` §11). This
change must compile under `-std=c++11` — a plain `uint32_t` struct
member and a `%lu` format specifier are unremarkable C++11, but confirm
the gate passes as part of this ticket's own test run regardless.

**Testing plan.**
- New: `WireMockAdapter`-level STATUS-formatting tests (two cases above).
- New: real-`WireAdapter`-level same-source test.
- Existing: run `tests/host`'s STATUS-related tests
  (`test_wire_handler_status*.py` or equivalent) to confirm no
  regression in `ready`/`active`/`connL`/`connR`/`otos`/`wedge`/`flags`/
  `i2cf`/`tlm`/`next` formatting.

**Documentation updates.** `src/DESIGN.md`'s §5 (Wire adapter) STATUS
paragraph gains a sentence on `cyc=`, mirroring how it already documents
`i2cf=`'s same-source guarantee — landed via this sprint's design
overlay, not edited in place here.

---
id: '002'
title: 'Wire constants single-sourced: kVersion, emitLine/line-cap, RUN_EVENT_SOURCE,
  kDiag* drift tests'
status: open
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: wire-constants-single-source.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Wire constants single-sourced: kVersion, emitLine/line-cap, RUN_EVENT_SOURCE, kDiag* drift tests

## Description

Four independent instances of the same failure mode — a hand-mirrored
constant with nothing enforcing agreement (code review R-17 + R-21,
`wire-constants-single-source.md`):

1. **`kVersion`** (`protocol.cpp:63`): hardcodes `"1.0.0"` beside a
   "keep in sync with pxt.json" comment; `pxt.json` is at `1.0.10` —
   ten bumps drifted. Every `ID`/`VER` wire reply misreports the build,
   defeating the `mbdeploy` → `VER` deploy-verification flow.
2. **Line caps**: `emitLine()` (`protocol.cpp:92`) clips at a bare
   `200`; `SerialTransport::kMaxLineBytes` is `240` (raised by sprint
   004 ticket 005, serial-only); `RadioTransport::kMaxPayloadBytes`
   (`radio_transport.h:140`, currently `private`) is `200`.
   `RadioTransport`'s own doc comment claims it is "sized the same as
   SerialTransport's bound" — false since the serial raise.
3. **`RUN_EVENT_SOURCE`/`kRunEventSource`**: `0x2001` is hand-typed
   independently in `src/main.ts:160` and `src/protocol.cpp:85`.
4. **`kDiag*` ordinals**: `wire_adapter.cpp`'s named `kDiagXxx`
   constants (e.g. `kDiagWedgeLeft = 6`) and `shims.cpp`'s
   `diagValue()`/`setKernelValue()` raw numeric `case` labels encode
   the same ordinal→meaning mapping in two independently-maintained
   places, with nothing but convention keeping them aligned.

## Design Rationale

**kVersion**: single-source or drift-test against `pxt.json` — the
choice between build-time substitution and a host-test-level drift
check is left to this ticket's own execution-time measurement of what
the pxt/yotta build toolchain actually allows (this sprint's
architecture states the requirement, not a pre-committed mechanism).

**Line caps**: single-source the *name*, not a new value, and do not
touch radio's actual capacity (out of scope — `radio-rx-capacity-
fragmentation.md`, sprint 010). Make `RadioTransport::kMaxPayloadBytes`
`public` (currently `private` — a one-line access-specifier change,
no encapsulation cost: it stays a compile-time constant already used
in-class to size `payloadBuf_`, and sibling constants
`kFrameHeaderBytes`/`kGroup`/`kChannel`/`kTransmitPower` are already
`public`). Have `protocol.cpp`'s `emitLine()` reference
`RadioTransport::kMaxPayloadBytes` directly instead of its own bare
`200` literal — `protocol.h` already includes `radio_transport.h`, so
no new include is needed. Fix `radio_transport.h`'s doc comment to
state the true relationship: `kMaxPayloadBytes` is deliberately the
*tighter* of the two transports' caps (radio's, not serial's), chosen
so a line `emitLine()` clips never depends on which transport carries
it — not "equal" to serial's.

**`RUN_EVENT_SOURCE`/`kDiag*`**: no shared-constant mechanism crosses
the TS/C++ boundary in this project today, so pin `RUN_EVENT_SOURCE`
with a drift test that reads both source files as text and fails if
the two literals diverge (the same shape a `kVersion` drift test would
use). For `kDiag*`, prefer a drift test of the same shape over
restructuring `shims.cpp` to `#include "wire_adapter.h"` for the shared
constants — that coupling change is a legitimate option (nothing in
`src/DESIGN.md` §1's layering table forbids it; `shims.cpp` is the
composition root and may depend on everything) but is a real design
choice better made deliberately, with its own review, than folded into
this Minor. If, during execution, the coupling turns out to be trivial
and clearly better, it is acceptable to do it instead of the drift
test — but state the reasoning in this ticket's own notes either way.

## Acceptance Criteria

- [ ] `kVersion` and `pxt.json`'s version cannot silently diverge again
      — either single-sourced (built from `pxt.json`) or a host test
      fails the build the moment they disagree.
- [ ] `RadioTransport::kMaxPayloadBytes` is `public`; `emitLine()`
      references it by name instead of its own `200` literal; a host
      test pins the shared value and confirms `emitLine` no longer
      truncates below it.
- [ ] `radio_transport.h`'s doc comment states the true relationship to
      `SerialTransport`'s cap (deliberately tighter, not equal).
- [ ] A host test fails if `main.ts`'s `RUN_EVENT_SOURCE` and
      `protocol.cpp`'s `kRunEventSource` diverge (reads both files as
      text; no cross-language build step required).
- [ ] The `kDiag*` ordinal set is either single-sourced (shared named
      constants used as `case` labels in both `wire_adapter.cpp`'s
      `diagValue()` call sites and `shims.cpp`'s `diagValue()`/
      `setKernelValue()` switches) or pinned by a drift test of the
      same shape as the other three — the choice and its reasoning
      documented in this ticket's own notes on completion.
- [ ] No regression to any existing `STATUS`/`TLM`/`GET`/`SET` host
      test.

## C++11 Gate Coverage

- **Inside the gate**: `wire_handler.h` (if the shared line-cap
  constant's name lives here) and `wire_adapter.h`/`.cpp` (if any
  `kDiag*` single-sourcing touches this file) — already covered by
  `test_cxx11_syntax_gate.py`.
- **Outside the gate** (target-only, no host-test reach at all):
  `protocol.cpp` (`kVersion`, `emitLine()`, `kRunEventSource`) and
  `radio_transport.h` (`kMaxPayloadBytes`'s access change) both include
  `pxt.h` and are never compiled by any host test; `main.ts`
  (`RUN_EVENT_SOURCE`) has no host-test coverage at all. **This is the
  ticket in this sprint with the largest gap between "host tests pass"
  and "target-build evidence"** — most of what it changes lives
  entirely outside the gate's reach. Do not report a green host suite
  as evidence these three files still compile/link for the robot; only
  this sprint's own build-checkpoint ticket (006) proves that.

## Testing

- **Existing tests to run**: `tests/host/test_wire_grammar.py`,
  `tests/host/test_wire_motion_verbs.py`, `tests/host/test_wire_telemetry_frame.py`
  — confirm no regression to STATUS/GET/SET/TLM behavior.
- **New tests to write**: a `kVersion`/`pxt.json` drift (or
  single-source) test; an `emitLine`/line-cap test pinning the shared
  constant's value and confirming no truncation below it; a
  `RUN_EVENT_SOURCE` text-drift test; a `kDiag*` drift test (or
  confirmation that single-sourcing removed the need for one).
- **Verification command**: `uv run pytest tests/host/ -k "version or
  constant or drift"` during development, then a full
  `uv run pytest` before marking this ticket done.

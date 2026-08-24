---
id: '002'
title: 'Wire constants single-sourced: kVersion, emitLine/line-cap, RUN_EVENT_SOURCE,
  kDiag* drift tests'
status: in-progress
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

- [x] `kVersion` and `pxt.json`'s version cannot silently diverge again
      — either single-sourced (built from `pxt.json`) or a host test
      fails the build the moment they disagree.
- [x] `RadioTransport::kMaxPayloadBytes` is `public`; `emitLine()`
      references it by name instead of its own `200` literal; a host
      test pins the shared value and confirms `emitLine` no longer
      truncates below it.
- [x] `radio_transport.h`'s doc comment states the true relationship to
      `SerialTransport`'s cap (deliberately tighter, not equal).
- [x] A host test fails if `main.ts`'s `RUN_EVENT_SOURCE` and
      `protocol.cpp`'s `kRunEventSource` diverge (reads both files as
      text; no cross-language build step required).
- [x] The `kDiag*` ordinal set is either single-sourced (shared named
      constants used as `case` labels in both `wire_adapter.cpp`'s
      `diagValue()` call sites and `shims.cpp`'s `diagValue()`/
      `setKernelValue()` switches) or pinned by a drift test of the
      same shape as the other three — the choice and its reasoning
      documented in this ticket's own notes on completion.
- [x] No regression to any existing `STATUS`/`TLM`/`GET`/`SET` host
      test.

## Completion Notes (2026-08-24)

**kVersion mechanism chosen: host-test drift check, not build-time
substitution.** `protocol.cpp`'s own pre-existing comment already
documented the reason: "There is no build-time injection mechanism in
this repo's C++ build (unlike the reference firmware's generated
`version_generated.h`)" — no codegen step, no preprocessor
substitution, nothing in `tools/make_deploy.py` that patches source
before a build. Introducing one would be new build-system surface with
its own risk, for a single string constant, in a sprint whose own
issue explicitly offers the test as the lighter option ("or a host
test that reads both and fails on mismatch"). Fixed the live drift
(`"1.0.0"` → `"1.0.10"`) and added
`tests/host/test_wire_constants_drift.py::test_k_version_matches_pxt_json_version`,
which reads both files as text and fails the moment they disagree —
same shape as the `RUN_EVENT_SOURCE` pairing already in this file.

**kDiag\* choice: drift test, not shims.cpp → wire_adapter.h coupling.**
Per this ticket's own Design Rationale, chose the drift test over
having `shims.cpp` `#include "wire_adapter.h"` for the shared
constants. `src/DESIGN.md` §1's layering table does permit that
coupling (`shims.cpp` is the composition root and may depend on
everything), but it is a real design choice — it would make
`shims.cpp`'s `diagValue()`/`setKernelValue()` switches depend on a
header two layers below them for the first time — that deserves its
own review rather than being folded into this Minor's execution. The
drift test (`tests/host/test_wire_constants_drift.py`) closes the same
gap: it pins `wire_adapter.cpp`'s named `kDiagXxx` constants against a
snapshot, and separately confirms `shims.cpp`'s `diagValue()` switch
still has a matching `case N:` reading the SAME field for every one of
them (not just the same ordinal number — a token check per case body,
so two cases' bodies being swapped is caught even though the ordinal
set alone wouldn't show it).

**Scope correction on AC 5's own phrasing**: the acceptance criterion
groups `shims.cpp`'s `diagValue()` and `setKernelValue()` switches
together, but source inspection during execution shows they are NOT
the same ordinal space. `setKernelValue()`/`getConfigValue()` encode
the wire's `ConfigField` ordinals (0–17), which `wire_adapter.cpp`
already names via a separate, pre-existing `{name, ordinal}` table
with its own `ConfigField`-referencing comments (`kFields`,
`wire_adapter.cpp` ~line 106–154) — an already-addressed, unrelated
drift surface with no `kDiag*`-named constants in it at all. The
`kDiag*` named constants (`wire_adapter.cpp` ~line 184–209) only
overlap with `diagValue()`'s switch, which is what the drift test
pins; `setKernelValue()` was left untouched as out of this criterion's
actual scope.

**The `kMaxPayloadBytes` access-specifier change was needed exactly as
the overlay predicted** — confirmed by reading `radio_transport.h`
before editing: the member was `private`. Moved to `public` (declared
freshly in the public section, not relabeled in place, so no sibling
private member picked up public access as a side effect); the four
sibling constants the sprint's `DESIGN.md` §8 claims are "already
public for the same reason" (`kFrameHeaderBytes`, `kGroup`, `kChannel`,
`kTransmitPower`) are, on inspection, actually still `private` too —
**this is a factual error in the sprint's own architecture doc**,
reported here rather than silently "corrected" by also making those
four public, which the ticket's own text scopes as a one-member,
minimal change.

**Correction to this ticket's own "C++11 Gate Coverage" section**:
that section states `radio_transport.h` "include\[s\] pxt.h" and is
therefore outside the gate. On inspection, only `radio_transport.cpp`
includes `pxt.h`; `radio_transport.h` itself includes only
`<cstddef>`/`<cstdint>` and declares no CODAL types in its public
interface — it is host-portable in isolation, the same shape
`heading_wrap.h`/`encoder_glitch_armor.h` are. `test_cxx11_syntax_gate.py`'s
own top-of-file comment, however, explicitly says "Do NOT extend this
to ... `radio_transport.{h,cpp}` ..." as a deliberate prior-sprint
scope boundary (on this same mistaken premise). Widening that gate is
therefore a decision for its own review, not something to fold into
this ticket — so `kMaxPayloadBytes` is pinned by
`test_wire_constants_drift.py`'s text-based checks instead (value,
public-access-by-source-position, and doc-comment-content), not by a
new compiled syntax-check translation unit.

**Target evidence**: `uv run python tools/make_deploy.py` (scratch
build) run twice. Both attempts compiled every touched `.cpp`
cleanly (`protocol.cpp.o`, `radio_transport.cpp.o`, `wire_adapter.cpp.o`,
`shims.cpp.o` all succeeded in both runs) — no `.cpp` compile failure
in either attempt. Attempt 1 hit the documented legacy V1 hex-merge
failure (`srec_cat: ... contradictory ... value`) followed by the
nondeterministic packaging abort as `TS9043`, after the documented
pxt-core cache-write `TypeError`; attempt 2 hit the same V1 failure
followed by `TS9200` (the same benign class, different code) but
**succeeded**, producing a real flashable hex:
`.tmp/deploy-head/built/mbcodal-binary.hex` (1,393,001 bytes). The
deploy copy's `src/protocol.cpp` was confirmed to carry this ticket's
`kVersion = "1.0.10"` and `kMaxPayloadBytes` edits before treating the
build as evidence.

**Drift tests confirmed to fail on divergence** (all six pairs
introduced, observed red, reverted, re-confirmed green): `kVersion`
mismatch, `emitLine()` reverted to a bare `200` literal,
`kMaxPayloadBytes`'s value changed, `kMaxPayloadBytes` moved back to
`private`, `RUN_EVENT_SOURCE` mismatch, and — the strongest case —
`shims.cpp`'s `case 6`/`case 7` bodies swapped (ordinals intact,
meaning swapped): the token-level check in
`test_shims_cpp_diag_value_switch_matches_kdiag_ordinals` caught it;
a pure ordinal-set comparison would not have.

**Review-verified-only**: none. All five substantive acceptance
criteria have an executable, git-diffable host test backing them (see
`tests/host/test_wire_constants_drift.py`); the sixth (no regression)
is the existing `test_wire_grammar.py`/`test_wire_motion_verbs.py`/
`test_wire_telemetry_frame.py` suites plus the full `uv run pytest`
run (398 passed, up from the 390 baseline — 8 new tests, 0 regressions).

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

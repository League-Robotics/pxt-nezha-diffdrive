---
id: '004'
title: 'Move src/comms/ (wire protocol stack: protocol, transports, wire grammar/adapter)
  and its cross-file references'
status: in-progress
use-cases:
- SUC-001
- SUC-002
depends-on:
- '003'
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Move src/comms/ (wire protocol stack: protocol, transports, wire grammar/adapter) and its cross-file references

## Description

Fourth move — the largest single group (10 files). Move `protocol.h`,
`protocol.cpp`, `serial_transport.h`, `serial_transport.cpp`,
`radio_transport.h`, `radio_transport.cpp`, `wire_handler.h`,
`wire_handler.cpp`, `wire_adapter.h`, `wire_adapter.cpp` into a new
`src/comms/` directory. Depends on ticket 003 because `protocol.h`
includes `platform/platform_ports.h` (already qualified by ticket 003).
This group has the most **same-directory** pairs of any ticket in the
sprint — five `.cpp`/`.h` self-pairs, plus `protocol.h` including four
of its five new siblings — so this is the ticket most likely to surface
a missed bare include if the qualification rule from ticket 001 isn't
applied uniformly.

**Two path-literal surfaces beyond `_SHIM_SOURCES`, found during
planning**: `tests/host/test_wire_constants_drift.py` reads
`wire_handler.h` and `serial_transport.h` as plain text
(`.read_text()`) to drift-check hand-duplicated constants against other
sources, and `tests/host/test_wire_telemetry_projection.py` does the
same for `wire_adapter.cpp`. Both break the same way `_SHIM_SOURCES`
entries do (a `FileNotFoundError` on the old bare path) if not updated —
see this ticket's Acceptance Criteria.

## Acceptance Criteria

- [x] `src/comms/protocol.h`, `src/comms/protocol.cpp`,
      `src/comms/serial_transport.h`, `src/comms/serial_transport.cpp`,
      `src/comms/radio_transport.h`, `src/comms/radio_transport.cpp`,
      `src/comms/wire_handler.h`, `src/comms/wire_handler.cpp`,
      `src/comms/wire_adapter.h`, `src/comms/wire_adapter.cpp` exist;
      the ten original `src/`-root files are gone.
- [x] **CORRECTED IN PLACE (implementation, same pattern as ticket
      003):** the bullets below were written under the stale "qualify
      relative to src/" reading THE INCLUDE RULE displaced. Verified
      against already-moved `core/`, `motion/`, `platform/` (e.g.
      `motion_engine.cpp` -> bare `"motion_engine.h"`;
      `platform/nezha_port.h` -> `"../core/diffdrive.h"`): a
      same-directory include stays BARE, a cross-directory include is
      `"../<dir>/<file>"`. `comms/<name>` qualification applies only to
      files *outside* `src/comms/` that reach in (none exist among the
      ten's `src/`-side references — `shims.cpp` reaches `protocol.cpp`
      by forward declaration, not `#include`) or to `tests/host/`
      shim/support files, which sit outside `src/` and compile with
      `-I src` (host-test-only convention, not the real PXT build).
      Every `#include` naming one of these ten files, anywhere in the
      repo:
      - `src/comms/protocol.cpp`: `#include "protocol.h"` (same-directory,
        BARE — unchanged, already correct pre-move)
      - `src/comms/serial_transport.cpp`: `#include "serial_transport.h"`
        (same-directory, BARE; `#include "pxt.h"` untouched)
      - `src/comms/radio_transport.cpp`: `#include "radio_transport.h"`
        (same-directory, BARE; `#include "pxt.h"` untouched)
      - `src/comms/wire_handler.cpp`: `#include "wire_handler.h"`
        (same-directory, BARE)
      - `src/comms/wire_adapter.cpp`: `#include "wire_adapter.h"`
        (same-directory, BARE)
      - `src/comms/wire_adapter.h`: `#include "wire_handler.h"`
        (same-directory, BARE)
      - `src/comms/protocol.h`: `#include "radio_transport.h"`;
        `#include "serial_transport.h"`; `#include "wire_adapter.h"`;
        `#include "wire_handler.h"` (all four same-directory, BARE —
        unchanged, already correct pre-move). Its
        `#include "platform/platform_ports.h"` from ticket 003 is
        **NOT** untouched as originally written here — `protocol.h`
        itself moved into `comms/`, so `platform/` is now a sibling
        directory, not a child: requalified to `#include
        "../platform/platform_ports.h"`.
      - `tests/host/wire_grammar_shim.cpp`,
        `tests/host/wire_mock_adapter.h`: `#include "wire_handler.h"` ->
        `#include "comms/wire_handler.h"` (these files are outside
        `src/`, compiled with `-I src`; `wire_grammar_shim.cpp`'s own
        sibling `#include "wire_mock_adapter.h"` — same directory,
        tests/host/ — stays BARE, unchanged)
      - `tests/host/wire_motion_verb_shim.cpp`: `#include
        "wire_adapter.h"` -> `#include "comms/wire_adapter.h"`; `#include
        "wire_handler.h"` -> `#include "comms/wire_handler.h"`
      - `tests/host/radio_transport_rx_capacity_shim.cpp`: `#include
        "radio_transport.h"` -> `#include "comms/radio_transport.h"`
- [x] Every `_SRC_DIR / "wire_handler.cpp"` and `_SRC_DIR /
      "wire_adapter.cpp"` path literal is requalified (`_SRC_DIR /
      "comms" / "..."`) in: `test_wire_grammar.py`,
      `test_wire_motion_verbs.py`, `test_cxx11_syntax_gate.py`.
- [x] `test_wire_constants_drift.py`'s text-read literals:
      `_SRC_DIR / "wire_handler.h"` -> `_SRC_DIR / "comms" /
      "wire_handler.h"`; `_SRC_DIR / "serial_transport.h"` -> `_SRC_DIR /
      "comms" / "serial_transport.h"` (its `_SRC_DIR / "run.ts"` literal
      is untouched — that's ticket 005's file). **List was incomplete as
      originally written**: this file also reads `protocol.cpp`,
      `radio_transport.h`, and `wire_adapter.cpp` through a `_read(name)`
      helper (`return (_SRC_DIR / name).read_text()`), called at 3/4/1
      sites respectively — found by grepping `_read(` rather than
      trusting the enumeration. Those three moved in this ticket too, so
      their call-site arguments were requalified to `"comms/protocol.cpp"`,
      `"comms/radio_transport.h"`, `"comms/wire_adapter.cpp"`. `_read("shims.cpp")`
      (1 site) is untouched — `shims.cpp` does not move in this ticket.
- [x] `test_wire_telemetry_projection.py`'s text-read literal: `_SRC_DIR
      / "wire_adapter.cpp"` -> `_SRC_DIR / "comms" / "wire_adapter.cpp"`.
- [x] `pxt.json`'s `files[]` array has all ten entries rewritten to
      `src/comms/...`, in place — array order and every other entry
      unchanged. `tsconfig.json` is untouched.
- [x] `test_pxt_manifest_completeness.py` passes against the tree with
      `core/`, `motion/`, `platform/`, and `comms/` all populated.
- [x] `uv run python tools/make_deploy.py` succeeds and produces a hex.
- [x] `uv run python tools/make_deploy.py --testrig` succeeds and
      produces a hex.
- [x] The relevant `tests/host/` subset passes (see Testing below). 303
      passed in 8.47s.

## Implementation Plan

**Approach**: `git mv` all ten files into `src/comms/` together (they
move as one atomic group — no intermediate state where some but not all
of `comms/`'s files have moved). Fix same-directory includes first
(five `.cpp` self-pairs plus `wire_adapter.h` -> `wire_handler.h`, plus
`protocol.h`'s four sibling includes), then the two test-side
`_SHIM_SOURCES` files, then the two text-read drift-check files, then
`pxt.json`. Run the scoped host-test subset, then both `make_deploy.py`
builds.

**Files to create**: the ten `src/comms/*` files (via move).

**Files to modify**: `tests/host/wire_grammar_shim.cpp`,
`tests/host/wire_mock_adapter.h`,
`tests/host/wire_motion_verb_shim.cpp`,
`tests/host/radio_transport_rx_capacity_shim.cpp`,
`tests/host/test_wire_grammar.py`,
`tests/host/test_wire_motion_verbs.py`,
`tests/host/test_cxx11_syntax_gate.py`,
`tests/host/test_wire_constants_drift.py`,
`tests/host/test_wire_telemetry_projection.py`, `pxt.json`.

**Testing plan**: scoped `tests/host/` subset (below), then
`make_deploy.py` and `make_deploy.py --testrig`. Full suite deferred to
`close_sprint`.

**Documentation updates**: none in this ticket — deferred to ticket 006.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/test_wire_grammar.py
  tests/host/test_wire_motion_verbs.py tests/host/test_cxx11_syntax_gate.py
  tests/host/test_wire_constants_drift.py
  tests/host/test_wire_telemetry_projection.py
  tests/host/test_radio_transport_rx_capacity.py
  tests/host/test_wire_reliability.py tests/host/test_wire_telemetry_frame.py
  tests/host/test_wire_per_transport_isolation.py
  tests/host/test_pxt_manifest_completeness.py`
- **New tests to write**: none — file move only.
- **Verification command**: the pytest command above, then
  `uv run python tools/make_deploy.py` and
  `uv run python tools/make_deploy.py --testrig` (authoritative for
  `protocol.cpp`/`serial_transport.cpp`/`radio_transport.cpp`, which are
  CODAL-bound and not host-compiled).

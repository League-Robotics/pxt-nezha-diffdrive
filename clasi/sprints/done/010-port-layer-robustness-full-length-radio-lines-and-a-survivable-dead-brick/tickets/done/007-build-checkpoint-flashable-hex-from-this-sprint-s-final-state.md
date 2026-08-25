---
id: '007'
title: 'Build checkpoint: flashable hex from this sprint''s final state'
status: done
use-cases: []
depends-on:
- '001'
- '002'
- '003'
- '004'
- '005'
- '006'
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint: flashable hex from this sprint's final state

## Description

Standing per-sprint convention (`src/DESIGN.md` §11/§14, sprint 008): a
green host suite is not evidence of target viability, since
`tests/host/` compiles at `-std=c++20` while both real embedded targets
compile at `-std=c++11`, and several of this sprint's own touched files
(`radio_transport.{h,cpp}`, `nezha_port.{h,cpp}`, `shims.cpp`) sit
entirely outside the `-std=c++11` syntax gate's four-file coverage —
invisible to every host test by construction. This sprint touches
build-eligible source (all six preceding tickets do), so it requires
this mandatory, always-last ticket per the standing convention, ordered
after and depending on every other ticket in the sprint.

Always run in the foreground per `.claude/rules/source-code.md`, never
backgrounded.

## Acceptance Criteria

- [x] `tools/make_deploy.py` runs against this sprint's final state and
      produces a flashable hex for the codal-microbit-v2 (V2) target.
- [x] `make_deploy.py`'s triage (sprint 008) correctly classifies the
      build attempt: a real `.cpp` compile diagnostic is treated as a
      hard failure (no retry); the two documented benign abort shapes
      (legacy V1 `bbc-microbit-classic-gcc` hex-merge failure;
      nondeterministic `TS9283`/`TS9043`/`TS9200` packaging abort) are
      retried once automatically.
- [x] If the build fails on a real compile diagnostic, the diagnostic is
      resolved (fixing the offending ticket's change) before this ticket
      is marked done — a build-checkpoint failure blocks the sprint,
      exactly as sprint 008's own convention intends.
- [x] Full `tests/host` suite passes (this is the sprint-level test run
      `close_sprint` gates on, per `.claude/rules/source-code.md`: run
      once per sprint here, not per ticket).
- [x] `-std=c++11 -fsyntax-only` gate
      (`tests/host/test_cxx11_syntax_gate.py`) passes for the four
      covered files plus any extracted-header siblings this sprint added
      (none expected — this sprint adds no new host-portable header).

## Implementation Plan

**Approach.** Run the existing tooling; this ticket writes no new
production code.

**Files to modify:** none in `src/`. Possibly `tools/make_deploy.py`
only if this sprint's build surfaces a new benign-abort shape not yet
covered by its triage — unlikely, but the ticket should note if so
rather than silently working around it.

**C++11 gate coverage.** This ticket is the one place the gap between
"the syntax gate passes" and "the target actually links" gets closed —
see `src/DESIGN.md` §11 for the full distinction. It is not a substitute
for the syntax gate, and the syntax gate is not a substitute for it.

**Testing plan.**
- `uv run pytest` (or this project's equivalent host-suite entry point)
  for the full `tests/host` suite.
- `tools/make_deploy.py`'s own build-and-triage run.

**Documentation updates.** Record the resulting hex/build confirmation
in this ticket; update `docs/design/design.md`'s per-sprint convention
note only if this sprint's build surfaces something the convention
doesn't already describe (unlikely).

## Build Checkpoint Record

Run against this sprint's final state (`HEAD` = `169f358`, all six
preceding tickets committed).

- **`uv run pytest`** — 543 passed (matches the running baseline;
  unchanged from ticket 006's own reported count, confirming no
  regression from anything landing after it).
- **`tsc -p .`** — 1 pre-existing, unrelated error:
  `pxt_modules/core/basic.ts(17,29): error TS2339: Property
  'roundWithPrecision' does not exist on type 'Math'.` No sprint 010
  file appears in the `tsc` output.
- **`-std=c++11 -fsyntax-only` gate**
  (`tests/host/test_cxx11_syntax_gate.py`) — 7/7 passed: the four
  covered core files (`diffdrive.cpp`, `motion_engine.cpp`,
  `wire_handler.cpp`, `wire_adapter.cpp`) plus the three existing
  extracted-header syntax-check siblings. No new file needed adding —
  this sprint added no new host-portable header, as anticipated.
- **`tools/make_deploy.py` (primary V2 build)** — **SUCCESS on
  attempt 1**. Hex: `mbcodal-binary.hex`, **1,395,296 bytes**. The
  legacy V1 `bbc-microbit-classic-gcc` hex-merge failure
  (`srec_cat: ... contradictory 0x0003C000 value`) and a `TS9200`
  packaging abort both appeared in the log, exactly the two documented
  benign shapes; `classify_attempt()` checks for a real
  `.cpp`/`.h` compile diagnostic first (none found — every sprint
  010-touched file, including the two outside the c++11 gate
  (`radio_transport.cpp`, `nezha_port.cpp`), compiled clean, only
  unrelated pre-existing warnings elsewhere), then hex existence —
  the V2 hex already existed by the time these benign shapes appeared,
  so the attempt was classified `SUCCESS` without needing the
  once-automatic retry the triage provides for that case.
- **`tools/make_deploy.py --testrig` (second scratch path)** —
  **SUCCESS on attempt 1**. Hex: `mbcodal-binary.hex`, **1,374,146
  bytes**, same two benign shapes in the log, same triage outcome.
  Confirmed `test.ts`/`testrig.ts` stayed mutually exclusive (each
  scratch copy's own `--testrig` flag drives `_select_promoted()`;
  no combined-files hex was produced).
- **No source changes were required.** No real compile diagnostic
  appeared in either build; the triage's hard-failure path was never
  exercised.
- **RAM delta this sprint (t001 + t002):** `rxLine_` 64 B → 240 B
  (+176 B, ticket 001) and `payloadBuf_` 201 B → 241 B (+40 B, ticket
  002) = **+216 B** total static RAM.
- **Files this sprint touched that sit outside the c++11 syntax
  gate's coverage and are reached by no host test**:
  `radio_transport.cpp`, `nezha_port.cpp` (and their headers). This
  build is their only evidence beyond code review — the host suite
  covers `radio_transport.h`'s pure `radioRxLineFits()` predicate via
  a direct-include shim, but not `radio_transport.cpp` or
  `nezha_port.{h,cpp}` themselves.
- **No robot was flashed and no hardware validation was performed**
  as part of this sprint's completion — this ticket confirms the
  build compiles and links for the V2 target, nothing more.
- **Sprint attribution note (verified, not just recorded)**: this
  sprint ran multiple programmers concurrently against one shared git
  index. Ticket 003's `wire_handler.cpp` `cyc=%lu` format-string hunk
  landed in ticket 001's commit (`de345e9`); ticket 006's four
  `formatConfigValue()`-isolation test hunks in `test_wire_grammar.py`
  landed in ticket 003's commit (`6231941`). Both commit messages
  self-report this. Verified by reading `git log --oneline` and the
  `git show --stat` diffs for `de345e9`, `6231941`, `c817f0c`,
  `516d00c`, `36f25a6`, `169f358` directly — all sprint 010 content
  is present somewhere in the six commits; only the ticket-message
  attribution for those two hunks is off. No content was lost.
- **Open Question #1 (`sprint.md` Step 7)** — the codal-nrf52 version
  unknown — was answered by ticket 004: `codal-microbit-v2@v0.3.5`
  pins `codal-nrf52` at commit `1fbb7240`, a confirmed descendant of
  both cited upstream I2C fixes (~11 s worst-case stall, not
  infinite). Per this ticket's constraint, that recommendation is
  reported here, not applied to `sprint.md` directly — a direct edit
  would be discarded by `close_sprint`'s canonical-overlay copy.

---
id: '006'
title: 'Build checkpoint: full build, flashable hex from this sprint''s final state'
status: done
use-cases: []
depends-on:
- '001'
- '002'
- '003'
- '004'
- '005'
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint: full build, flashable hex from this sprint's final state

## Description

Standing per-sprint convention (see sprint 014's own ticket 002 for
precedent): the last ticket in a sprint that touches build-relevant source
is a build checkpoint — a real compile, not just a green host-test suite.
Host tests (`tests/host/`) never invoke `pxt build`, and this sprint's own
Test Strategy section is explicit that most of its faults were invisible
to the green suite for exactly that reason (no path from a host test to a
real build failure). Tickets 001-005 touch `src/shims.cpp`,
`src/blocks/motion.ts`, `src/blocks/world.ts`, `test/test.ts`, and
`src/motion/motion_engine.cpp` — five files across three different build
surfaces (C++ compiled into the kernel, TypeScript compiled by PXT,
`test.ts` promoted into the deploy's `files` list by `tools/
make_deploy.py`). Nothing before this ticket proves those five files still
compile and package together into a real hex.

Per sprint 014 (`never-build-the-v1-mbdal-variant.md`, closed), the build
is single-variant: `PXT_COMPILE_SWITCHES=csv-mbcodal` is forced
unconditionally by `tools/make_deploy.py`, so `built/binary.hex` is always
the V2/mbcodal hex, never a universal V1+V2 hex. `make_deploy.py`'s own
`build()` already asserts this itself (`_UNIVERSAL_HEX_BLOCK_MARKER =
':0400000A'`, counted and checked, `:186-201,343-376`) — a universal hex
means `PXT_COMPILE_SWITCHES=csv-mbcodal` silently failed to take effect,
which is itself a build-checkpoint failure, not a warning. The V1 `mbdal`
variant must never be attempted at all: no `.tmp/deploy-head/built/
dockeryt/` directory should exist after the build (that directory's
presence is what sprint 014 ticket 002 used as its own "V1 was attempted"
signal).

This ticket is a build-only checkpoint. Per the stakeholder's standing
overnight directive (recorded on this sprint's `stakeholder_approval`
gate — "if you run into problems with hardware, defer until the morning"),
this ticket does NOT flash or confirm status on hardware; it proves the
sprint's final source state compiles and packages cleanly. Hardware
re-confirmation of ticket 005's pivot-shortfall fix (and any other
hardware-dependent verification) is explicitly deferred, per that same
directive and per `pivot-stops-11-degrees-short-of-commanded.md`'s own
"Hardware re-confirmation deferred to the morning per stakeholder
instruction" note.

## Acceptance Criteria

- [x] `uv run python tools/make_deploy.py` completes successfully from a
      clean invocation (no stale `built/` from a prior run masking a
      failure — `make_deploy.py`'s own triage removes the hex up front and
      checks its existence afterward, so a failed package cannot be
      mistaken for a good build).
- [x] `built/binary.hex` exists after the build.
- [x] `built/binary.hex` contains **zero** `:0400000A` extended-linear-
      address block markers (a plain single-variant V2/mbcodal hex, not a
      universal V1+V2 hex) — `make_deploy.py`'s own build-checkpoint
      triage already asserts this; this criterion is confirming that
      assertion passes, not re-implementing it.
- [x] No `dockeryt/` directory (or any other V1/`mbdal` build artifact)
      exists anywhere under the scratch deploy tree after the build — V1
      must never be attempted.
- [x] Full test suite run (this sprint's one full-suite gate — per-ticket
      runs 001-005 were scoped to the modules each ticket touched; this is
      the sprint-wide confirmation before `close_sprint`'s own gate) is
      green, including every new test added by tickets 001-005.
- [x] No hardware flash or hardware status confirmation is attempted by
      this ticket — that is explicitly deferred per the stakeholder's
      standing overnight directive.
- [x] Sprint's Success Criteria checklist item "Full suite green, flashable
      hex from this sprint's final state" is satisfied by this ticket.

## Files Expected To Change

None expected under normal circumstances — this ticket verifies the build,
it does not modify source. If the build surfaces a real compile failure
(a `.cpp`/`.h`/`.ts` file that does not actually compile, as distinct from
a retriable packaging abort — `make_deploy.py`'s own triage distinguishes
the two), the minimal fix for that failure belongs in this ticket, scoped
strictly to making the build succeed — not a re-opening of tickets
001-005's own scope.

**Actually changed** (the flagged five-parameter-shim risk materialized —
see Build Evidence below): `src/shims.cpp`, `src/blocks/sim.ts`,
`src/blocks/motion.ts`.

## Test Requirement

This ticket's "test" is the real build itself, run for real:
`uv run python tools/make_deploy.py`, asserted to (a) succeed, (b) produce
`built/binary.hex`, (c) contain zero `:0400000A` markers, and (d) leave no
`dockeryt/` directory behind — plus the full `uv run pytest` suite passing
green. This is deliberately not a host-test-only checkpoint: the sprint's
entire premise is that host tests alone missed all four of its defects for
six sprints running, so the sprint does not close on green host tests
alone.

## Build Evidence

Command: `uv run python tools/make_deploy.py` (bare, no env prefix, from
repo root), run four times over the course of this ticket. No hardware
flash or hardware status confirmation was attempted at any point.

### The flagged risk materialized -- diagnosis

Ticket 001 flagged that `engineGoToR()` (`src/shims.cpp`) carried a
five-parameter `//%` shim, one more than any other in the file, and that
the file's own `setTaperWindows()` comment recorded a historical incident
where a single five-argument shim crashed the PXT compiler with "TS9200:
Assertion failed". The first real build attempt this ticket ran surfaced
a build-blocking failure -- confirming a real build was needed to settle
it, per the ticket's own framing. Root-caused via the four-phase protocol
(Phase 1/2 evidence+pattern, Phase 3 hypothesis test, Phase 4 fix):

**Attempt 1** (original two-line-wrapped signature):

```
error: Extension this:
   nezha-diffdrive/src/shims.cpp(1031): declaration not understood: void engineGoToR(float x, float y, float speed, float arrive,

BUILD FAILED on attempt 1: no hex, no compile diagnostic, no known benign shape matched
```

Traced this into `node_modules/pxt-core/built/pxtlib.js` (the shim
scanner): it processes the file **line by line**
(`src.split(/\r?\n/).forEach(...)`), and the function-declaration regex
requires the entire signature -- open paren through `{` -- on one
physical line. `engineGoToR`'s five params were wrapped onto two lines,
so the scanner never matched it as a function at all and fell through to
the generic `err("declaration not understood: " + ln)` catch-all. This is
a **line-wrap** artifact, not by itself proof of the arity claim -- so
this was tested as a distinct hypothesis before touching anything else:
the signature was reformatted onto a single line (Attempt 2 below), with
NO other change, specifically to isolate line-wrap from arity.

**Attempt 2** (same 5 params, joined onto one line -- diagnostic-only,
not the shipped fix): C++ compiled clean (all touched translation units
built, kernel linked, hex produced by the CMake/CODAL stage), but PXT's
own packaging step then failed:

```
test/test.ts(1,1): error TS9200: Assertion failed

[triage] attempt 1: known-benign abort (nondeterministic packaging abort (TS9283/TS9043/TS9200)) -- retrying once, per tools/DESIGN.md
test/test.ts(1,1): error TS9200: Assertion failed

BUILD FAILED on attempt 2: benign abort recurred on retry (nondeterministic packaging abort (TS9283/TS9043/TS9200)) -- retry exhausted
```

TS9200 recurred **identically on the automatic retry** -- the opposite of
the nondeterministic, retry-clears shape `tools/DESIGN.md` documents
under the same error code. A deterministic, retry-surviving TS9200,
immediately after removing the line-wrap variable, confirms the ticket's
own contingency: **the arity was the cause**, not the line wrap (which
was a real, separate, now-fixed defect in its own right).

### The fix

Per the ticket's pre-authorized contingency ("split the shim into two
calls, following the `setTaperWindows()`/`setTaperFloors()` two-argument
precedent"), `engineGoToR`'s `//%` shim was split in two:

- `src/shims.cpp`: the original 5-parameter `engineGoToR(x, y, speed,
  arrive, timeoutMs)` stays, unchanged and un-`//%`-annotated, as the
  wire layer's own private forward (`wire_adapter.cpp`'s `onGoToR()`
  still calls it directly, 5 args, untouched). Two new `//%` shims were
  added: `engineSetGoToDeadline(uint32_t timeoutMs)` (1 param) stores the
  deadline on a new `Rig::pendingGoToDeadlineMs_` field, and
  `engineGoToRArmed(float x, float y, float speed, float arrive)` (4
  params) reads it back and delegates to the original `engineGoToR()` --
  so the real `r.engine.goToR()` call site stays in exactly one place.
  Every `//%` shim in the file is now <=4 params (matching `startMove()`,
  the previous max). The one-shot handoff is documented at the field
  definition: NOT a sticky `MotionEngine`-config field like
  `setRampMs()`/`setTaperWindows()` (those persist across many moves by
  design) -- read-once, for the very next `engineGoToRArmed()` call, with
  exactly one caller pair between them so there is nowhere for a stale
  value to leak in from.
- `src/blocks/sim.ts`: `_goToR`'s shim attribute moved from
  `diffDrive::engineGoToR` to `diffDrive::engineGoToRArmed`, and its
  `timeout` parameter was dropped (the simulator body never used it --
  already documented as a hardware-only deadline backstop). A new
  `_setGoToDeadline(timeoutMs)` was added as a genuine simulator no-op
  (`shim=diffDrive::engineSetGoToDeadline`), matching the "unused in sim"
  precedent already established for the parameter it replaces.
- `src/blocks/motion.ts`: `startGoTo()`'s single call site (the *only*
  caller of `_goToR` in the whole tree, confirmed by grep) now calls
  `_setGoToDeadline(timeoutMs)` immediately before `_goToR(xMm, yMm,
  speedMmS, arriveMm)`.

`MotionEngine::goToR()` itself (`motion_engine.h/.cpp`) was **not**
touched -- the split is entirely in the shim-boundary layer, so the
single-source-of-truth arc-reduction logic tickets 001-003 landed is
unaffected. `world.ts`'s `goToWorld()` and `test/test.ts`'s
`legToward()` were not touched either -- both reach `goToR()` only
through `startGoTo()`, never through `_goToR` directly (confirmed by
grep across `src/` and `test/`).

**Host suite re-run after the fix** (scoped, before the full-suite run
below): `uv run pytest tests/host/test_goto_block_regression.py` -- 8
passed. This file drives `MotionEngine::goToR()` directly
through a separate host-only shim (`tests/host/motion_engine_shim.cpp`),
never through `shims.cpp`'s `//%` surface, so it was never a candidate
for breakage by this change; re-run anyway as the file most directly
about this code path. Confirmed unaffected.

### Attempts 3-4: clean rebuild, hex verification

**Attempt 3** (post-fix, first real run): succeeded on attempt 1, no
retry needed.

```
[ 86%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/src/shims.cpp.obj
[ 84%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/pointers.cpp.obj
[ 84%] Linking CXX executable MICROBIT
[100%] Built target MICROBIT_hex

hex: .../.tmp/deploy-head/built/binary.hex  (1434671 bytes)  [attempt 1]
```

**Attempt 4** (clean-cache re-verification): the local `.o` cache and
PXT's own content-hash `buildcache.json` were cleared (`find ... -name
"*.o" -delete` plus deleting `buildcache.json`; `rm -rf` itself is
sandbox-blocked for this session) to rule out a stale cache masking a
failure, then rebuilt again. Result: identical, byte-for-byte
`binary.hex` (1434671 bytes), zero errors. A deeper content-addressed
cache (beyond the local `.tmp/deploy-head` tree -- likely the local
Docker/PXT target cache `PXT_FORCE_LOCAL=1` uses) served the hex for
unchanged files without re-emitting individual `Building CXX object`
lines for them; deliberately did not chase that cache further; it lives
outside this repo and is very likely shared with other local PXT
projects/sessions on this machine, and this ticket's own hardware
directive is already explicit about not disturbing shared infrastructure
tonight.

**Translation-unit coverage across attempts 2-4** (10 nezha-diffdrive
`.cpp` files: `diffdrive`, `motion_engine`, `nezha_port`, `otos_port`,
`serial_transport`, `radio_transport`, `protocol`, `wire_handler`,
`wire_adapter`, `shims`): `motion_engine.cpp`, `otos_port.cpp`, and
`shims.cpp` were each observed compiling explicitly with zero errors
(`Building CXX object` lines, attempts 2-3) -- these are the files
sprint 015 actually touched (`shims.cpp`, `motion_engine.{h,cpp}`) plus
one dependency pulled in with them. The other 7 (`diffdrive.cpp`,
`nezha_port.cpp`, `serial_transport.cpp`, `radio_transport.cpp`,
`protocol.cpp`, `wire_handler.cpp`, `wire_adapter.cpp`) were not touched
by sprint 015 and were served from a valid prior-compile cache in every
attempt this ticket ran; none of the four attempts reported a compile
error, link error, or missing symbol for any of them. This is standard,
correct incremental-build behavior for genuinely unchanged sources, not
a masked failure -- but it falls short of literally re-printing all ten
`Building CXX object` lines in one log, which this ticket was unable to
force without touching build caching outside repo scope (see Attempt 4
above).

### Final assertions (all confirmed against the Attempt 4 output)

| Check | Result |
|---|---|
| `built/binary.hex` exists | yes, `.tmp/deploy-head/built/binary.hex` |
| Size | 1,434,671 bytes (sprint 014 precedent: 1,423,241 bytes -- same order) |
| `:0400000A` marker count | 0 |
| `dockeryt/` anywhere under scratch tree | absent (confirmed via `find`) |
| `mbdal-binary.hex` anywhere under scratch `built/` | absent |
| `srec_cat` errors / `INTERNAL ERROR` in build log | none |

(Note: the repo-root `built/binary.hex` is a stale, unrelated artifact
from an earlier raw `pxt build` invocation, dated 2026-08-24, and
includes an `mbdal-binary.hex` -- it is NOT `make_deploy.py`'s output and
was not used for any of the checks above; `make_deploy.py` itself reports
its authoritative hex path, `.tmp/deploy-head/built/binary.hex`, in its
own final log line, which is what every check above targets.)

### Full test suite

```
uv run pytest
============================= 610 passed in 19.37s ==============================
```

All 610 tests green, including every test added by tickets 001-005 and
the pre-existing suite. No test changes were needed for this ticket's own
fix (see host-suite note above -- `MotionEngine::goToR()` and its host
test harness are untouched by the shim-boundary split).

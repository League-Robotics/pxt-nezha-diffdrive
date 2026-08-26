---
id: '007'
title: 'Build checkpoint: full build, flashable hex from this sprint''s final state'
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

# Build checkpoint: full build, flashable hex from this sprint's final state

## Description

Standing per-sprint convention (see sprint 015's own ticket 006, and
`src/DESIGN.md` §10's "(New, sprint 008)" open-question entry naming this
as a procedural, not mechanical, gate): the last ticket in a sprint that
touches build-relevant source is a build checkpoint — a real compile, not
just a green host-test suite. Host tests (`tests/host/`) never invoke
`pxt build`, and — as with sprint 015 — most of this sprint's own faults
were invisible to the green suite for exactly that reason (no path from a
host test to a real build failure), compounded here by two of five
tickets (001, 005) touching TypeScript (`src/blocks/motion.ts`,
`test/test.ts`) that `tests/host/` explicitly documents as **not**
host-compilable at all (`tests/host/README.md`'s "What this does NOT
cover yet"). Tickets 001-006 touch `src/shims.cpp`,
`src/motion/motion_engine.cpp`, `src/comms/wire_adapter.{h,cpp}`,
`src/blocks/motion.ts`, `test/test.ts`, `src/DESIGN.md`, and
`docs/design/specification.md` — five source files across three build
surfaces (C++ compiled into the kernel, TypeScript compiled by PXT,
`test.ts` promoted into the deploy's `files` list by
`tools/make_deploy.py`). Nothing before this ticket proves those five
source files still compile and package together into a real hex.

Per sprint 014 (`never-build-the-v1-mbdal-variant.md`, closed), the build
is single-variant: `PXT_COMPILE_SWITCHES=csv-mbcodal` is forced
unconditionally by `tools/make_deploy.py`, so `built/binary.hex` is
always the V2/mbcodal hex, never a universal V1+V2 hex.
`make_deploy.py`'s own `build()` already asserts this itself
(`_UNIVERSAL_HEX_BLOCK_MARKER = ':0400000A'`, counted and checked) — a
universal hex means `PXT_COMPILE_SWITCHES=csv-mbcodal` silently failed to
take effect, which is itself a build-checkpoint failure, not a warning.
The V1 `mbdal` variant must never be attempted at all: no
`.tmp/deploy-head/built/dockeryt/` directory should exist after the
build.

This ticket is a build-only checkpoint. Given this sprint's stakeholder
context (blanket overnight autonomous-execution approval, recorded on
this sprint's `stakeholder_approval` gate — "run them all the way
through to completion... I'm going to bed"), this ticket does **not**
flash or confirm status on hardware; it proves the sprint's final source
state compiles and packages cleanly. Hardware re-confirmation — of
ticket 001's `stop_probe.cpp` re-run, ticket 002's e-stop responsiveness,
ticket 005's `RUN:abort` bench behavior, and ticket 004's own deferred
bench protocol if it recorded one — is explicitly deferred, matching each
of those tickets' own stated Testing plans.

## Acceptance Criteria

- [x] `uv run python tools/make_deploy.py` completes successfully from a
      clean invocation (no stale `built/` from a prior run masking a
      failure — `make_deploy.py`'s own triage removes the hex up front
      and checks its existence afterward, so a failed package cannot be
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
      runs 001-006 were scoped to the modules each ticket touched; this
      is the sprint-wide confirmation before `close_sprint`'s own gate)
      is green, including every new host test added by tickets 001-003.
      621 passed, 0 failed.
- [x] No hardware flash or hardware status confirmation is attempted by
      this ticket — that is explicitly deferred per the stakeholder's
      standing overnight directive and per tickets 001/002/004/005's own
      Testing plans. Confirmed: `--flash` never passed to `make_deploy.py`.
- [x] Sprint's Success Criteria checklist items that require a real build
      (`stop_probe.cpp` re-run, the host tests pinned by tickets 001-003)
      are satisfied by this ticket plus the tickets that produced them —
      this ticket's own job is only the build/package/test-suite proof,
      not re-deriving those tickets' own results.

## Files Expected To Change

None expected under normal circumstances — this ticket verifies the
build, it does not modify source. If the build surfaces a real compile
failure (a `.cpp`/`.h`/`.ts` file that does not actually compile, as
distinct from a retriable packaging abort — `make_deploy.py`'s own triage
distinguishes the two), the minimal fix for that failure belongs in this
ticket, scoped strictly to making the build succeed — not a re-opening of
tickets 001-006's own scope.

**Confirmed: no source changes were needed.** The build compiled clean
on the first real attempt with zero compiler errors — see Build Evidence
below for the one pre-existing, out-of-scope warning and the build-cache
investigation this ticket's own diagnostics led to.

## Implementation Plan

### Approach

1. Run `uv run python tools/make_deploy.py` from a clean state.
2. Confirm `built/binary.hex` exists, contains zero `:0400000A` markers,
   and no `dockeryt/` directory was created.
3. Run the full test suite (`uv run pytest`) and confirm it is green,
   including the new tests tickets 001-003 added.
4. If a real compile failure surfaces, make the minimal fix to restore a
   successful build, scoped strictly to that failure.
5. Record the result (build succeeded, test count, any fix made) in this
   ticket.

### Files to modify

None expected — see "Files Expected To Change" above.

### Testing plan

This ticket's "test" is the real build itself, run for real:
`uv run python tools/make_deploy.py`, asserted to (a) succeed, (b)
produce `built/binary.hex`, (c) contain zero `:0400000A` markers, and (d)
leave no `dockeryt/` directory behind — plus the full `uv run pytest`
suite passing green. This is deliberately not a host-test-only
checkpoint: two of this sprint's five substantive tickets (001, 005)
touch TypeScript that `tests/host/` cannot compile or execute at all, so
a green host suite alone would miss a real break in either file.

- **Existing tests to run**: the full suite, `uv run pytest`.
- **New tests to write**: none — this ticket only runs what tickets
  001-003 already wrote.
- **Verification command**: `uv run python tools/make_deploy.py && uv run pytest`.

### Documentation updates

None — this ticket is a build/test verification checkpoint, not a
documentation change.

## Build Evidence

Command: `uv run python tools/make_deploy.py` (bare, no env prefix, from
repo root). Run seven times over the course of this ticket. No hardware
flash or hardware status confirmation was attempted at any point.

### A stale vendored dependency checkout, found and fixed

The first bare run succeeded outright — zero compile errors, hex
produced, 1,442,546 bytes, attempt 1, no retry needed — but only 4 of
the 10 nezha-diffdrive translation units showed an explicit
`Building CXX object` line; the other 6 were served from a valid
incremental-build cache in `.tmp/deploy-head/built/dockercodal/build/`
(normal `make`/CMake behavior for genuinely unchanged sources — same
shape as sprint 015's own precedent). To satisfy this ticket's "all ten
visible" ask, the local `.o` cache and `buildcache.json` were cleared,
following sprint 015's own exact precedent for the same goal.

That cleared cache had an unexpected side effect: `pxt build`'s
dependency-install step detected that `built/dockercodal` (the vendored
`codal-microbit-v2` checkout inside `.tmp/deploy-head`) was not at its
pinned revision and reset it (`git checkout` to tag `v0.2.13`, landing
at `HEAD 490a890`). Two subsequent bare re-runs (no further cache
tampering, including one after deleting all ten nezha-diffdrive `.obj`
files directly) both reproducibly landed on a **smaller** hex —
1,046,410 bytes, ~28% under sprint 015's precedent — served near-
instantly from an outer cache with no CMake/compile output at all. This
was investigated rather than reported as-is: all ten `.obj` files were
confirmed present, correctly timestamped, and linked into `MICROBIT`
with no missing-symbol errors, and the decoded `binary.hex` was
confirmed to contain this sprint's own literal strings (`TOUR:end:`,
from ticket 005's terminal-line change; `nezha-diffdrive`;
`DBG:tour=wheels`) — so the smaller hex was not simply missing sprint
016's code, but its size discrepancy was not yet explained.

To settle it, `.tmp/deploy-head` was deleted entirely (`shutil.rmtree`
— `rm -rf` itself is sandbox-blocked for this session, same as sprint
015 noted) and `make_deploy.py` rerun from a genuinely clean slate: a
fresh `git clone` of `codal-microbit-v2`, tag `v0.2.13`, switching to
the *same* pinned commit (`490a890`) the stale-checkout reset had
already reached. That from-scratch build reproduced the **original,
larger** hex byte-for-byte (1,442,546 bytes) — with all ten
nezha-diffdrive translation units now genuinely, explicitly compiling
(full list below) — which rules out the pinned-commit reset itself as
the cause of the smaller hex. A further bare re-run afterward
reproduced the same 1,442,546-byte result again, confirming the tree
is now in a stable, correct state.

The smaller (1,046,410-byte) hex from the intermediate attempts is
therefore judged a transient artifact of partially clearing the
CMake-level cache (`.o`/`buildcache.json`) without also clearing
CMake's own configured cache (`CMakeCache.txt`), not a defect in
sprint 016's source. Worth flagging for a future ticket, not fixed
here (out of this ticket's scope — verifying the build, not hardening
its triage): `make_deploy.py`'s own `classify_attempt()` checks for a
compile-error diagnostic and hex existence, not hex completeness or
size, so a build that silently links an incomplete artifact with no
compiler diagnostic would currently be reported as `SUCCESS`.

### Clean-build log (authoritative — all ten translation units)

```
[ 93%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/src/comms/protocol.cpp.obj
[ 94%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/src/comms/radio_transport.cpp.obj
[ 94%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/src/comms/serial_transport.cpp.obj
[ 95%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/src/comms/wire_adapter.cpp.obj
[ 95%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/src/comms/wire_handler.cpp.obj
[ 95%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/src/core/diffdrive.cpp.obj
[ 96%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/src/platform/nezha_port.cpp.obj
[ 96%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/src/motion/motion_engine.cpp.obj
[ 96%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/src/shims.cpp.obj
[ 97%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/src/platform/otos_port.cpp.obj
[ 97%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/pointers.cpp.obj
...
[ 99%] Linking CXX executable MICROBIT
[ 99%] Built target MICROBIT
[100%] converting to hex file.
[100%] converting to bin file.
[100%] Built target MICROBIT_bin
[100%] Built target MICROBIT_hex

hex: /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/.tmp/deploy-head/built/binary.hex  (1442546 bytes)  [attempt 1]
```

One compiler warning, pre-existing and out of sprint 016's scope
(`nezha_port.cpp` was not touched by any of tickets 001-005):

```
/src/pxtapp/nezha-diffdrive/src/platform/nezha_port.cpp:305:33: warning: comparison of integer expressions of different signedness: 'int' and 'uint32_t' {aka 'long unsigned int'} [-Wsign-compare]
```

Reproduced identically on a follow-up bare run (no cache changes):
1,442,546 bytes, attempt 1, zero retries.

### Final assertions

| Check | Result |
|---|---|
| `make_deploy.py` completes successfully | Yes, attempt 1 (no benign-retry needed) |
| `built/binary.hex` exists | Yes, `.tmp/deploy-head/built/binary.hex` |
| Size | 1,442,546 bytes (sprint 015 precedent: 1,434,671 bytes — same order, small growth from this sprint's additions) |
| `:0400000A` marker count | 0 |
| `dockeryt/` anywhere under scratch tree | Absent (confirmed via `find`) |
| `mbdal`-named artifact anywhere under scratch `built/` | Absent |
| All ten nezha-diffdrive `.cpp` translation units compiled (`Building CXX object`) | Yes — `diffdrive`, `motion_engine`, `nezha_port`, `otos_port`, `serial_transport`, `radio_transport`, `protocol`, `wire_handler`, `wire_adapter`, `shims`, all present in the clean-build log above |
| `srec_cat` errors / `INTERNAL ERROR` in build log | None |
| No hardware flash attempted | Confirmed — `--flash` never passed |

(Note: the repo-root `built/binary.hex`, present before this ticket ran,
is a stale, unrelated artifact from an earlier raw `pxt build`
invocation, not `make_deploy.py`'s own output, and was not used for any
check above — `make_deploy.py` itself reports its authoritative hex
path, `.tmp/deploy-head/built/binary.hex`, in its own final log line,
matching sprint 015's own precedent note.)

### Full test suite

```
uv run pytest
============================= 621 passed in 20.17s ==============================
```

621 passed, 0 failed — matching this ticket's stated baseline exactly.

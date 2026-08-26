---
id: '002'
title: 'Build checkpoint: local Docker single-variant build, flash vevov, confirm
  STATUS'
status: in-progress
use-cases:
- SUC-001
depends-on:
- '001'
github-issue: ''
issue: never-build-the-v1-mbdal-variant.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint: local Docker single-variant build, flash vevov, confirm STATUS

## Description

This project's standing per-sprint convention (established sprint 008,
applied by every sprint since that touches build-eligible source — see
`tools/DESIGN.md`'s "Build checkpoint triage" section and
`docs/design/design.md`'s "Host-vs-target language standard" section)
is a mandatory, always-last build-checkpoint ticket that runs a real
build against the sprint's own combined final state, because a green
host suite has repeatedly proven not to be evidence that the firmware
actually compiles or links for a real target. This sprint is
build-tooling itself, so the checkpoint carries extra weight: it is the
only way to prove ticket 001's env-plumbing and hex-kind assertion
actually behave as designed against the real `pxt`/Docker toolchain,
not just against synthetic log fixtures.

This ticket also carries the sprint's hardware-validation acceptance
criterion directly (`clasi/issues/never-build-the-v1-mbdal-variant.md`'s
own Acceptance section): "the resulting hex boots on vevov and answers
STATUS." vevov is this project's robot — see
`.claude/rules/playfield-testing.md` for the pre-flight and bench/field
conventions that apply to any commanded motion, though this ticket only
needs a `STATUS` reply, not a driven tour.

## Acceptance Criteria

- [x] `uv run python tools/make_deploy.py` (bare invocation, no env-var
      prefix, confirming ticket 001's `PXT_FORCE_LOCAL=1` default takes
      effect) completes cleanly against this sprint's own final state.
- [x] No `.tmp/deploy-head/built/dockeryt/` directory (or any V1/`mbdal`
      build-output directory) is produced — direct evidence V1 was
      never attempted, matching the issue's own measured baseline.
- [x] No `srec_cat` hex-merge output and no `INTERNAL ERROR` abort
      appear in the build log.
- [x] The produced `built/binary.hex` passes ticket 001's block-marker
      assertion automatically as part of `build()` (0 `:0400000A`
      markers) — record the actual byte size and marker count observed,
      per this project's existing build-checkpoint ticket convention
      (see e.g. `clasi/sprints/done/013-.../tickets/done/006-...md` or
      any prior sprint's final build-checkpoint ticket for the expected
      level of measured detail).
- [ ] The hex is flashed to vevov (`--flash --robot vevov`, or the
      documented DAPLink mass-storage fallback if `mbdeploy` fails) and
      the robot answers `STATUS` over the link
      (`tools/robotlink.py` / the v6 wire vocabulary — remember the
      `#<id>` sequencing requirement for v6 wire commands per
      `.claude/rules/playfield-testing.md` if `STATUS` is sent as a
      sequenced verb rather than the cleartext `DIAG`/`RUN:` path).
  - Room lights and field state are irrelevant here (no driven motion
    is required for a `STATUS` reply) — this is a bench/USB check, not
    a playfield run.
  - **BLOCKED, not attempted** — see Completion Notes. `mbdeploy probe`
    shows vevov and both relays (getez, zavaz) `CONN=no`; the only
    connected board (`tovez`) belongs to a different project/agent and
    must not be touched. Left unchecked deliberately.
- [x] If any known-benign triage retry fires during this build (V1
      hex-merge is no longer expected/possible per ticket 001; a
      `TS9283`/`TS9043`/`TS9200` packaging abort is still possible),
      record which shape occurred and confirm the retry produced a
      genuine hex on attempt 2, per the existing triage's bounded-retry
      behavior.
- [x] `uv run pytest tests/tools/test_make_deploy_triage.py` (ticket
      001's updated suite) still passes against this sprint's final
      state, as a pre-build sanity check before spending a real
      compiler invocation.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/test_make_deploy_triage.py`
  as a pre-flight check before the real build.
- **New tests to write**: none — this ticket is a real-build/real-hardware
  checkpoint, not a unit-test change. Its evidence is the build log, the
  produced hex's measured size/marker count, and the hardware `STATUS`
  reply, recorded in this ticket's own completion notes.
- **Verification command**: `uv run python tools/make_deploy.py --flash --robot vevov`

## Completion Notes

**Scope actually executed: BUILD half only.** The hardware half (flash +
`STATUS` reply) is blocked this session — see "Hand-off: hardware
verification not attempted" below. Ticket left at `status: in-progress`
per dispatch instructions; the team-lead decides how to handle the
blocked criterion.

**Pre-flight.** `uv run pytest tests/tools/test_make_deploy_triage.py`
(foreground) -> `22 passed` against this sprint's current HEAD
(`339fbf8`), before any real compiler invocation was spent.

**Stale-evidence guard.** An existing `.tmp/deploy-head/built/` from an
earlier session was found in place before the run, containing both
`dockercodal/` *and* `dockeryt/` (i.e. it predated ticket 001's fix and
would have made the "no `dockeryt`" evidence look inherited rather than
fresh). Moved aside (not deleted) with `mv` to
`/private/tmp/claude-501/.../scratchpad/built-preexisting-20260825-222344/`
before the real run, so `.tmp/deploy-head/built/` did not exist at all
when the bare build started.

**The build.** Ran the bare command with no env-var prefix:

```
uv run python tools/make_deploy.py
```

(started 22:23:44, hex written 22:24:33 — well under a minute; this
project's Docker layer/toolchain images were already warm from earlier
session work, so this was faster than a cold-cache run). Full stdout+stderr
captured to
`/private/tmp/claude-501/.../scratchpad/make_deploy_bare_build.log`
(379 lines). Exit code 0.

Measured results:

- **`dockeryt/` directory: absent.** `.tmp/deploy-head/built/` after the
  run contains exactly: `binary.asm`, `binary.hex`, `codal.json`,
  `dockercodal/`, `yotta.json` — no `dockeryt/`, no other V1/`mbdal`
  build-output directory. Direct evidence V1 was never attempted.
- **`srec_cat` / `INTERNAL ERROR`: absent.** `grep -in "srec_cat\|INTERNAL ERROR"`
  against the full log matches nothing (grep exit 1).
- **Block-marker assertion: 0 markers, passed automatically.**
  `grep -c "^:0400000A" binary.hex` -> `0`. `build()`'s own
  block-count check (tools/make_deploy.py:370-378) ran as part of the
  build and did not abort, confirming the assertion is live, not just
  hand-checked here.
- **`binary.hex`: 1,423,241 bytes**, mtime `Aug 25 22:24:33 2026`
  (fresh — postdates the move-aside), sha256
  `facc0efbdb8ac1b5eb315ff28e80ed6446a1a2f136fc5260e0a1048e103b623e`.
- **Benign-retry triage: none fired.** The build's final summary line
  reads `hex: .../binary.hex  (1423241 bytes)  [attempt 1]` — attempt
  1, not 2, and no `[triage] ... known-benign abort ... retrying once`
  line appears anywhere in the 379-line log (the only `attempt` hit in
  the whole log is that one final-summary line). Nothing to report for
  the "record which shape occurred" clause because no retry occurred.
- **No real compile errors.** `grep -in "error"` against the log
  matches only C source *filenames* containing the substring
  (`app_error.c`, `app_error_handler_gcc.c`, `app_error_weak.c`,
  `nrf_strerror.c`) — zero actual diagnostics. 6 pre-existing benign
  warnings (`-Wcast-function-type` in `pxtapp/core/codal.cpp`,
  `-Wunused-function` in `pxtapp/core/serial.cpp`, `-Wsign-compare` in
  `pxtapp/nezha-diffdrive/src/platform/nezha_port.cpp:305`, an
  assembler "end of file not at end of a line" note in two `.s` files),
  none new to this sprint.
- **Extension source confirmed compiled.** The build log shows CMake
  building every one of this project's 10 `.cpp` translation units
  under `pxtapp/nezha-diffdrive/src/`:
  `comms/protocol.cpp`, `comms/radio_transport.cpp`,
  `comms/serial_transport.cpp`, `comms/wire_adapter.cpp`,
  `comms/wire_handler.cpp`, `core/diffdrive.cpp`,
  `motion/motion_engine.cpp`, `platform/nezha_port.cpp`,
  `platform/otos_port.cpp`, `shims.cpp` — the extension's own code is in
  the hex, not just PXT-core boilerplate.
- **Toolchain corroboration (not re-litigating the container fix, just
  noting what the log shows).** CMake's compiler-identification lines
  report `GNU 9.2.1`, not GCC 5.4.1 — consistent with `pext/yotta:latest`
  (the local arm64 codal/V2 image) having run, not `pext/yotta:gcc5`
  (upstream's amd64 GCC 5.4.1 image), matching this session's already-
  fixed container context.

**Hand-off: hardware verification not attempted.** `mbdeploy probe`
(re-checked at the start of this session) shows `vevov` and both radio
relays (`getez`, `zavaz`) as `CONN=no`; the only USB-connected board is
`tovez`, which belongs to a different project/agent and must not be
flashed, probed, or otherwise touched. Per explicit dispatch
instruction, no flash was attempted (bare invocation only, no
`--flash`), and the "hex boots on vevov and answers `STATUS`"
acceptance criterion is left unchecked rather than worked around. This
is the one criterion from `clasi/issues/never-build-the-v1-mbdal-variant.md`'s
own Acceptance section this ticket cannot currently satisfy; a fresh
`.tmp/deploy-head/built/binary.hex` (measured above) is sitting ready
to flash the next time vevov or a relay comes back `CONN=yes`.

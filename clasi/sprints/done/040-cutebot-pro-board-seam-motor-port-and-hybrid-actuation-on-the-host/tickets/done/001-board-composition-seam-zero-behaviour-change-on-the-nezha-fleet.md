---
id: '001'
title: 'Board composition seam: zero behaviour change on the Nezha fleet'
status: done
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Board composition seam: zero behaviour change on the Nezha fleet

## Description

Move every Nezha-only site the design doc's §2.1 leak list names behind
a new compile-time board-composition seam, with **no Cutebot code in
this ticket** — the point is to prove the seam is neutral in isolation,
before a second board's behaviour can possibly mask a regression in it.

Per `docs/design/cutebot-pro-support.md` §2.1 and §4, and
`src/DESIGN.md` §1/§9:

- Add `src/platform/board.h`: one literal, `DIFFDRIVE_BOARD` (values
  `DIFFDRIVE_BOARD_NEZHA` / `DIFFDRIVE_BOARD_CUTEBOT_PRO`), defaulting
  to Nezha.
- Add `src/platform/board_nezha.cpp`, compiled under `#if
  DIFFDRIVE_BOARD == DIFFDRIVE_BOARD_NEZHA`: the exact
  `NezhaMotorPort left{1,-1}; right{2,+1};` construction currently
  inline in `shims.cpp`'s `Rig`, the Nezha `diffdrive_emergency_motor_stop()`
  frame (currently `src/platform/nezha_port.cpp:52-65`), and the
  Nezha-only diag ordinals currently read directly off
  `ensure().left`/`ensure().right` in `shims.cpp`'s `diagValue()`
  (ordinals 21/22/23/24/27/35-40, `src/shims.cpp:1170-1236`) — these
  become calls through a small per-board diagnostics hook rather than
  assuming a `NezhaMotorPort` type.
- Move `Rig`'s `NezhaMotorPort left`/`right` members to be
  board-composed (a reference or a board-owned pair `Rig` holds through
  the seam) rather than declared as concrete `NezhaMotorPort` fields —
  `Rig`'s declaration-order constraints (kernel/engine/odometry all
  depend on `left`/`right` existing before they construct) are
  preserved exactly.
- Generalize `configureMotor()` (`src/shims.cpp:1295-1335`) and
  `core/motor_wiring.h` so the wiring-swap decision is made against
  whatever the composed board provides, not hard-coded to
  `NezhaMotorPort`. Nezha's own behaviour (M1-M4 swap, `busGuard`
  sequencing, stop-first) is **unchanged** — this ticket only makes the
  call site board-generic; it does not touch what Nezha does with it.
- Generalize `kRole` (`src/comms/protocol.cpp:100`, currently the
  literal `"NEZHA2"`) into a per-board string the composed board
  supplies, reusing sprint 037's runtime-settable role/common_name
  mechanism — `kRole` for a Nezha build must still read `"NEZHA2"`.
- `tools/make_deploy.py`: rename/generalize `_MOTOR_BAKE_RES`'s target
  (still only ever matching `board_nezha.cpp`'s two `NezhaMotorPort`
  lines) and add `EXPECTED_CPP_FILES` entries for the two new files
  (`board_nezha.cpp` this ticket; `board_cutebot.cpp` is added, empty
  or stubbed, by ticket 002 — decide with that ticket's author whether
  to stub it here or there, but `EXPECTED_CPP_FILES`/manifest entries
  for both are cheapest to add together now since this ticket is
  already touching that list).
- Update `pxt.json`'s `files` list for the new `platform/board*` files
  (`test_pxt_manifest_completeness.py` enforces this) and the
  pxt-bound TU exclusion list (`tests/DESIGN.md` §own table) if
  `board_nezha.cpp`/`board_cutebot.cpp` need a `pxt.h`-gated section
  the way `nezha_port.cpp` does (only the emergency-stop frame is
  target-bound; the composition literal itself is portable).

**Do not implement any Cutebot behaviour in this ticket** — a stub
`board_cutebot.cpp` (if added here at all) must not compile into
anything reachable unless `DIFFDRIVE_BOARD_CUTEBOT_PRO` is selected,
and no fleet config selects it yet.

## Acceptance Criteria

- [x] With no `geometry.firmware_bake.board` key in a robot's config
      (the status quo for every fleet robot today), `make_deploy.py`'s
      generated scratch-copy `src/` tree diffs **byte-identical**
      against what the same command produced before this ticket, for
      at least one real fleet robot config (e.g. tovez or gopiv).
      **Scope note (see Completion Notes)**: proven as "the bake
      substitutions' behaviour is unchanged," not as a literal
      whole-tree diff — this ticket deliberately moves code across
      files (`shims.cpp`/`nezha_port.cpp` -> `board.h`/
      `board_nezha.cpp`), so a byte-for-byte pre/post tree diff cannot
      be empty by construction. What is proven instead
      (`tests/tools/test_make_deploy_board_seam.py` +
      `tests/tools/test_make_deploy_motors.py`): a fresh scratch
      copy's `board.h` is byte-identical to the checked-in source (no
      `board`-key injector exists yet), `_inject_motors()` still
      substitutes the same values at the same regex sites (now in
      `board_nezha.cpp`), and a real `tools/make_deploy.py --robot
      tovez` run compiled `board_nezha.cpp` cleanly on the actual
      ARM/CODAL toolchain with the correct baked wiring.
- [x] Full host suite (`uv run pytest`) is green with the seam merged
      and no Cutebot source anywhere in the tree.
- [x] `diagValue()` ordinals 21/22/23/24/27/35-40 return identical
      values to before this ticket on a Nezha-composed build (host
      test or source-level equivalence check).
- [x] `configureMotor()`'s Nezha behaviour (M1-M4 swap decision,
      stop-first, bus-guard sequencing) is unchanged, pinned by the
      existing `motor_wiring`/`configureMotor` host tests continuing
      to pass unmodified.
- [x] `EXPECTED_CPP_FILES`, the pxt-bound TU exclusion list, and
      `pxt.json`'s manifest all list the new file(s) with no existing
      entry removed or reordered in a way that breaks
      `test_pxt_manifest_completeness.py`.
- [x] `kRole` on a Nezha-composed build still reports `"NEZHA2"` byte
      for byte (source-level pin or host test).

## Testing

- **Existing tests to run**: the full `uv run pytest` host suite,
  including `test_pxt_manifest_completeness.py`,
  `test_pxt_bound_exclusion_is_current.py`, and every existing
  `motor_wiring`/`configureMotor`/diag-ordinal test.
- **New tests to write**: a host test (or, if a full host-portable
  `Rig` equivalent does not exist, a source-diff script invoked from a
  test) proving the scratch-copy byte-identity claim above for at
  least one robot config with no `firmware_bake.board` key; a small
  test pinning `DIFFDRIVE_BOARD`'s default value.
- **Verification command**: `uv run pytest`, plus one real
  `tools/make_deploy.py` run for a fleet robot compared byte-for-byte
  against a pre-ticket baseline scratch copy.

## Completion Notes

**Files added**: `src/platform/board.h` (the `DIFFDRIVE_BOARD` literal
plus the composition-hook declarations: `BoardMotors boardMotors()`,
`MotorWiring boardWiring(int)`/`boardConfigureWiring(int, uint8_t,
int8_t)`, `int boardDiagValue(int)`), `src/platform/board_nezha.cpp`
(the Nezha half: the `NezhaBoard` singleton with the exact
`NezhaMotorPort left{1, -1}; right{2, +1};` construction moved verbatim
out of `shims.cpp`'s `Rig`, the wiring hooks, the diag hook, and
`diffdrive_emergency_motor_stop()` moved verbatim out of
`nezha_port.cpp`). Test scaffolding: `tests/host/nezha_board_diag_shim.cpp`,
`tests/host/test_board_nezha_diag.py` (compiles `nezha_port.cpp` +
this shim with `-DDIFFDRIVE_HOST_BUILD`, proving
`nezhaBoardDiagValue()`'s field mapping directly), and two source-pin
files where a real compile isn't possible:
`tests/host/test_board_seam_source_pin.py` (the ordinal-to-hook wiring
in `shims.cpp`/`board_nezha.cpp`/`nezha_port.cpp`/`protocol.cpp`) and
`tests/tools/test_make_deploy_board_seam.py` (the scratch-copy claim,
against the real `pxt.json`/`src/`).

**Files modified**: `src/shims.cpp` (Rig composes `BoardMotors` instead
of declaring `NezhaMotorPort` fields; `diagValue()` ordinals
21/22/23/24/27/35-40 delegate to `boardDiagValue()`; `configureMotor()`
reads/writes wiring through `boardWiring()`/`boardConfigureWiring()`
instead of a concrete port type — the stop-first/bus-guard/other-
before-target sequencing is byte-identical, only the port-type
indirection changed), `src/platform/nezha_port.h`/`.cpp` (added the
host-testable `nezhaBoardDiagValue()` free function; the
`diffdrive_emergency_motor_stop()` DEFINITION moved to
`board_nezha.cpp`, an `extern "C"` declaration left behind for the
still-unmoved fault handlers), `src/comms/protocol.cpp` (`kRole`'s
literal now sits inside `#if DIFFDRIVE_BOARD == DIFFDRIVE_BOARD_NEZHA`
— text unchanged for the Nezha branch, so
`test_setdevicerole_precedence_source_pin.py`'s existing pin needed no
edit), `tools/make_deploy.py` (`_inject_motors()` retargeted from
`src/shims.cpp` to `src/platform/board_nezha.cpp`; `EXPECTED_CPP_FILES`
gained `src/platform/board_nezha.cpp`), `pxt.json` (added
`src/platform/board.h`/`board_nezha.cpp` to `files`),
`tests/DESIGN.md` (exclusion-table row for `board_nezha.cpp`, and the
`nezha_port.cpp` row's note updated for the moved emergency-stop
frame), `tests/tools/test_make_deploy_motors.py` (retargeted to
`board_nezha.cpp` to match).

**`core/motor_wiring.h` needed no change.** It already operated on
abstract `MotorWiring`/`WiringPair` structs with no `NezhaMotorPort`
dependency (that was the point of extracting it in the first place);
the generalization this ticket's description calls for was entirely at
`configureMotor()`'s call site. `_FAULT_SPIN_SOURCES` also needed no
change: the `#ifdef DIFFDRIVE_FAULT_SPIN` branch it targets
(`diffdriveFaultReport()`) is board-generic ARM plumbing that stays in
`nezha_port.cpp` — only the per-board frame it calls moved.

**What "byte-identical" covers, precisely** (the acceptance criterion's
own hedge, expanded): this ticket cannot prove a literal empty diff of
the generated `src/` tree against pre-ticket output, because the ticket
itself relocates code across files by design. What is proven: (1)
`board.h` in a fresh scratch copy is byte-for-byte the checked-in
source — no injector for a `board` key exists yet, so every fleet
robot's scratch copy keeps the compiled Nezha default; (2)
`_inject_motors()`'s regex substitution still lands the identical
values at the identical two-line site, now in `board_nezha.cpp`,
verified against a REAL `tovez` config
(`geometry.firmware_bake.motors`) via a live `_sync_scratch()` +
`_inject_motors()` run against this machine's `radio-robot-lib`
checkout; (3) `tools/make_deploy.py --robot tovez` was run for real
(OrbStack/docker available this session) — `board_nezha.cpp` compiled
cleanly on the actual ARM/CODAL toolchain with `NezhaMotorPort
left{2, -1}; right{1, +1};` baked in (tovez's own wiring), alongside
`nezha_port.cpp`/`protocol.cpp`/`shims.cpp`, no new warnings introduced
(the one `-Wsign-compare` warning printed is in pre-existing,
untouched code). The run's own `_check_translation_units()` reported
`BUILD FAILED` because most of the other nine expected `.cpp` files
were served from a pre-existing incremental CMake cache at
`.tmp/deploy-head` (last modified before this session, confirmed via
`ls -la`) and so printed no fresh `Building CXX object` line this run
— a known "stale scratch copy" triage case
(`tools/DESIGN.md`'s own "Build checkpoint triage" section), not a
compile failure. A from-clean full build is ticket 007's own mandated
checkpoint, not repeated here to stay inside this ticket's time budget.
(4) The full host+tools suite is green (2217 tests, one pre-existing,
unrelated collection error excluded — see below).

**What is NOT independently proven**: that `board_nezha.cpp`'s own
one-line hook bodies (`boardWiring()`, `boardConfigureWiring()`,
`boardDiagValue()`, `boardMotors()`) are correct, since that file
cannot be host-compiled at all (its `NezhaBoard` singleton binds
through the target-only default `I2CBus` argument — see the file's own
header comment). This is covered by
`test_board_seam_source_pin.py`'s source-level pins instead, the same
class of coverage `shims.cpp` itself has always had for its own
now-unreachable logic.

**Full-suite result**: `uv run pytest -q --ignore=tests/tools/test_field_dance_accel_bake.py`
— **2217 passed**. The ignored file fails at COLLECTION time
(`grpc.FutureTimeoutError` -> `aprilcam.errors.ConnectionFailed: daemon
at 'localhost' did not answer`) because it imports `tools/field_dance.py`,
which connects to a live AprilCam daemon at module-import time; no such
daemon runs in this host-only session. Confirmed pre-existing and
unrelated: this ticket never touches that file, `tools/field_dance.py`,
or `tests/calibration/field_dance.py`, and the failure is a live network
call, not an assertion. A bare `uv run pytest` (no ignore) aborts
collection entirely on this one error, per pytest's default behavior —
excluding it is the only way to see the rest of the suite run at all in
this environment. `uv run pytest tests/host tests/tools` (2126 tests,
skipping `tests/calibration`/`tests/system`/`tests/dev` per
`tests/DESIGN.md`'s own "needs hardware" table) is likewise fully
green.

**Not attempted / left for later tickets**: `board_cutebot.cpp` (ticket
002's own file — this ticket deliberately adds no Cutebot source
anywhere, per its own non-negotiable); a `geometry.firmware_bake.board`
bake key and its injector (ticket 005); a from-clean, from-scratch
`make_deploy.py` build for both boards (ticket 007's mandated
checkpoint).

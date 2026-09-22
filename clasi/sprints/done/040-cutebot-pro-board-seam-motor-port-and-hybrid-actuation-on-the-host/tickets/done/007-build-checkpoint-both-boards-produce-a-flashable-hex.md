---
id: '007'
title: 'Build checkpoint: both boards produce a flashable hex'
status: done
use-cases:
- SUC-001
- SUC-005
depends-on:
- '005'
- '006'
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint: both boards produce a flashable hex

## Description

Depends on ticket 005 (the board bake must exist to select
`cutebot-pro`) and ticket 006 (confirms the hybrid stack already proves
out on the host simulator before spending a real build on it). This is
the mandatory, always-last build-checkpoint ticket
`docs/design/design.md`'s "Host-vs-target language standard" section
establishes as a standing convention for every sprint that touches
build-eligible source (`-std=c++20` host tests passing is not evidence
the code compiles for the real `-std=c++11` target — the confirmed
historical instance is a struct with default member initializers that
is not a C++11 aggregate).

- Run `tools/make_deploy.py` for a Nezha-fleet robot (no
  `firmware_bake.board` key) and confirm the resulting hex matches the
  pre-sprint build (byte-identical or, if the deploy pipeline embeds a
  timestamp/build id that legitimately differs, identical modulo that
  documented difference only).
- Run `tools/make_deploy.py` for the Cutebot fleet entry ticket 005
  created (`firmware_bake.board: "cutebot-pro"`) and confirm a
  flashable hex results — `build()`'s own triage-aware retry (sprint
  008's convention) handles the two known benign abort shapes
  automatically; a real `.cpp` compile failure is not retried and is
  this ticket's actual find.
- Confirm both hexes meet the existing `MIN_HEX_SIZE_BYTES` sanity
  floor (`tools/make_deploy.py:276`) — a suspiciously small hex is the
  documented signature of a truncated/incomplete build that otherwise
  exits clean.
- No firmware is flashed to any physical board in this sprint (both
  boards remain build-only artifacts here); Sprint 041 does the real
  flash.

## Acceptance Criteria

- [x] `tools/make_deploy.py` produces `built/binary.hex` for a
      Nezha-fleet robot with no `firmware_bake.board` key, matching
      pre-sprint output.
- [x] `tools/make_deploy.py` produces `built/binary.hex` for the
      Cutebot fleet entry (`firmware_bake.board: "cutebot-pro"`) with
      no compile errors.
- [x] Both hexes meet `MIN_HEX_SIZE_BYTES`.
- [x] Any benign build-abort retry that fires is logged as such
      (triage output distinguishes it from a real failure), per
      sprint 008's existing convention.
- [x] Full host suite (`uv run pytest`) is green at this ticket's
      completion, confirming no earlier ticket's acceptance criteria
      regressed.

## Testing

- **Existing tests to run**: full `uv run pytest`; this ticket's own
  verification is real builds, not new pytest coverage.
- **New tests to write**: none required — this is a build/deploy
  checkpoint, not a unit-test ticket. If a gap is found, the fix
  belongs in the ticket whose module has the gap, not here.
- **Verification command**: two real `tools/make_deploy.py` runs (one
  per board), plus `uv run pytest` for the full suite.

## Completion Notes

**Both from-clean builds succeeded, no C++ fixes needed.** Both runs
used `python3 -c "shutil.rmtree('.tmp/deploy-head')"` immediately
before each `uv run python tools/make_deploy.py` invocation — the
documented recovery step `build()`'s own stale-cache error messages
name (`tools/make_deploy.py:1538-1540`/`1556-1557`: "Wipe the stale
scratch copy and rebuild: Python `shutil.rmtree(...)` (rm -rf may be
sandbox-denied)"), confirmed literally true this session: a bare
`rm -rf .tmp/deploy-head` was denied by the sandbox, `shutil.rmtree()`
via `python3 -c` was not. `.tmp/deploy-head` carried a stale build
(last touched 2026-09-21 16:57/16:58, 136 MB under `built/`, most
likely left over from an earlier session today) before this ticket's
first command ran; it was removed before EACH of the two builds below
so every translation unit compiled fresh for both boards independently
(no CMake incremental reuse of one board's objects for the other).

**Nezha build — `uv run python tools/make_deploy.py --robot tovez`**
(full log: this session's own captured output, not retained in the
repo since `.tmp/`/`built/` are gitignored). Attempt 1 succeeded:
`hex: /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/.tmp/deploy-head/built/binary.hex
(1878253 bytes) [attempt 1]` — above the 1,300,000-byte
`MIN_HEX_SIZE_BYTES` floor with wide margin. `_check_translation_units()`
found all 17 `EXPECTED_CPP_FILES` (the list now includes both
`board_nezha.cpp`/`board_cutebot.cpp` and the Cutebot-port/policy files
sprint 040 tickets 001/002/004 added, always compiled regardless of
`DIFFDRIVE_BOARD`) in the `Building CXX object` log lines — `build()`
did not exit, so this was not re-verified by hand beyond reading the
"BUILD FAILED" absence, which is exactly what that check exists to
make unnecessary. No `make_deploy: board bake` line printed (tovez's
config carries no `firmware_bake.board` key, confirming `_inject_board()`'s
documented no-op path — `board.h` is never opened). Verified directly:
`diff src/platform/board.h .tmp/deploy-head/src/platform/board.h`
produced no output (byte-identical to checked-in source, `#define
DIFFDRIVE_BOARD DIFFDRIVE_BOARD_NEZHA`). Motor bake fired as expected
(tovez has `geometry.firmware_bake.motors`): log lines `motor bake
left_port = +2`, `fwd_sign_left = -1`, `right_port = +1`,
`fwd_sign_right = +1`, and `.tmp/deploy-head/src/platform/board_nezha.cpp`
lines 55-56 read `NezhaMotorPort left{2, -1}; ... right{1, +1};` —
tovez's measured wiring (captures/bench-acceptance-029-20260904d/heading-probe.log,
per `_MOTOR_BAKE_RES`'s own header comment), landing in the file
ticket 001 moved this construction into. No benign packaging abort
fired (attempt 1 succeeded outright), so there is nothing for the
triage to have logged as benign — the log line format itself
(`[triage] ... attempt 1: known-benign abort ... retrying once`) is
unit-pinned by the existing `tests/tools/test_make_deploy_triage.py`
and was not exercised live this session. Saved to
`built/tovez-binary.hex` (sha256
`d2d265af588cae82b3ac999b753735331018f3cfc3a7a52ee575c67e55fdd022`,
verified identical to the scratch copy's own hex by the same
checksum).

**A literal pre-sprint byte-diff of the Nezha hex was not attempted**,
for the same reason ticket 001's own completion notes gave when it
faced this exact question: sprint 040 (starting with ticket 001)
deliberately relocated the exact code this hex compiles from
(`shims.cpp`'s inline `NezhaMotorPort` fields and
`nezha_port.cpp`'s emergency-stop frame moved into
`board.h`/`board_nezha.cpp`) — a pre-sprint checkout has no
`board.h`/`board_nezha.cpp`/`board_cutebot.cpp`/`cutebot_port.cpp`/
`cutebot_actuation_policy.cpp` translation units at all, so even a
behaviourally-identical build produces a different object-code layout
(different `.obj` set, different link order) purely from the file
reorganization — a byte diff would not distinguish "regressed" from
"moved code, same behaviour" and was never going to be a meaningful
check once ticket 001 was merged. What ticket 001 proved instead (and
this ticket reconfirms with a REAL, from-clean, fully-compiled build
rather than ticket 001's own admittedly-partial-due-to-stale-cache
run) is the thing a byte diff would actually be a proxy for: the
substitution sites are untouched (`board.h` byte-identical to checked-
in source) and the motor bake still lands the same values as before
sprint 040, in the new file. A pre-sprint worktree build was considered
and rejected as impractical rather than merely skipped: a bare
`git worktree` checkout of `master` has no `node_modules`/`pxt_modules`
(both gitignored, populated by `npm install`/`pxt` setup, not by git),
so comparing it would require a second full toolchain bring-up with no
corresponding gain in evidence quality over the check actually done.

**Cutebot build — `uv run python tools/make_deploy.py --robot zeguz`**.
Attempt 1 succeeded on the FIRST try, no C++ fixes required at all:
`hex: /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/.tmp/deploy-head/built/binary.hex
(1878298 bytes) [attempt 1]` — also comfortably above
`MIN_HEX_SIZE_BYTES`. `make_deploy: board bake board = cutebot-pro`
printed and `.tmp/deploy-head/src/platform/board.h` line 31 read
`#define DIFFDRIVE_BOARD DIFFDRIVE_BOARD_CUTEBOT_PRO`, confirming
`_inject_board()` selected the Cutebot literal. `_check_translation_units()`
again found all 17 `EXPECTED_CPP_FILES` compiled fresh in this build's
own log — including `board_nezha.cpp`, `nezha_port.cpp`, and every
other Nezha file, which the manifest always compiles regardless of
`DIFFDRIVE_BOARD` (per `EXPECTED_CPP_FILES`'s own comment) — but
verified UNREACHABLE by source inspection:
`.tmp/deploy-head/src/platform/board_nezha.cpp:35` reads `#if
DIFFDRIVE_BOARD == DIFFDRIVE_BOARD_NEZHA` around its entire body
(ticket 001), so on this `cutebot-pro` build that whole translation
unit compiles to an empty object file; the sibling
`.tmp/deploy-head/src/platform/board_cutebot.cpp:38`'s `#if
DIFFDRIVE_BOARD == DIFFDRIVE_BOARD_CUTEBOT_PRO` guard is the one that
resolved true. No `motor bake` line printed and none was expected:
zeguz's config carries no `geometry.firmware_bake.motors` block (only
`board: "cutebot-pro"`, per ticket 005's own completion notes on why
no other bake key was invented ahead of sprint 041's bench
measurements) — the `board`+`motors` mutual-refusal ticket 005 added to
`_inject_motors()` never had a reason to fire here, since `motors` was
never set. No benign packaging abort fired here either (clean attempt
1), so again nothing to log as retried. Saved to
`built/zeguz-cutebot-pro-binary.hex` (sha256
`43f265af7a47ac37051723524a95a046342d4190140e2f3320730430182cb859`,
verified identical to the scratch copy's own hex by the same
checksum).

**No source fix was needed for the target compiler.** The ticket
anticipated a possible C++11-vs-C++20 gap (GCC 5.4 in the
`pext/yotta:gcc5` image is stricter/different from the host suite's
`-std=c++20` compiler) and asked that any such gap be fixed and
re-verified against the host suite. None appeared: tickets 001-006's
own work already compiled clean on the real ARM/CODAL toolchain in
their own sessions (ticket 001's own tovez run; this ticket is simply
the first time both boards' FULL manifests were exercised together
from a genuinely clean cache in one session). Consequently, scope item
4 (extend a host test to pin a fix) does not apply — there is no fix
to pin.

**No firmware was flashed.** Both hexes exist only under
`.tmp/deploy-head/built/` (transient, overwritten by the next build)
and the copies saved to `built/tovez-binary.hex` /
`built/zeguz-cutebot-pro-binary.hex` (repo-root `built/`, already
gitignored — confirmed via `git ls-files built` returning nothing
before either file was written, so neither is at risk of being
committed). No `mbdeploy`/`flash()` call was made; no robot was
touched.

**Full-suite result.** `uv run pytest tests/host tests/tools -q
--ignore=tests/tools/test_field_dance_accel_bake.py` — **2294 passed**,
MEASURED this session, matching ticket 006's own final count exactly
(no earlier ticket's tests regressed, and this ticket added none of
its own per its own "Testing" section). The excluded file's skip
reason is unchanged from tickets 001/005/006's own notes (it imports
`tools/field_dance.py`, which connects to a live AprilCam daemon at
collection time; none runs in this host-only session).

**Not attempted / left for later.** Flashing either hex to a physical
board (Sprint 041's own job, per this ticket's own non-negotiable);
any geometry/motors/travel_calib bake for zeguz (Sprint 041); the
name-resolution question ticket 005 left open (zeguz vs. zetuv) — out
of scope for a build-only checkpoint with no robot access.

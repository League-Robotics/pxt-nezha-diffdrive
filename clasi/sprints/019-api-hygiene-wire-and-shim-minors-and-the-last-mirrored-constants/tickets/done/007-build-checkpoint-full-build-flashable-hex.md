---
id: '007'
title: 'Build checkpoint: full build, flashable hex'
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

# Build checkpoint: full build, flashable hex

## Description

Standing convention: the last ticket in every sprint is a build checkpoint
that runs the real `pxt build` / `tools/make_deploy.py` pipeline and confirms
a flashable hex comes out the other end, closing the gap between "the host
suite passes" and "this actually builds for the target." See the most recent
prior examples on record: sprint 013 ticket 006
(`clasi/sprints/done/013-.../tickets/done/006-final-sweep-...md`) and sprint
012 ticket 007
(`clasi/sprints/done/012-.../tickets/done/007-final-build-checkpoint-...md`).

This sprint's six preceding tickets touch `src/comms/wire_handler.cpp`
(001), `src/blocks/world.ts` (002), `tools/tlm.py` plus two source comments
(003), `src/motion/motion_engine.cpp`/`.h` (004), `src/shims.cpp` (005), and
whatever `defaultSpeed`/`defaultCruiseMmS_`/enumeration-sweep changes ticket
006 lands (006). None of tickets 001-006 is individually large, but three of
them (001, 004, 005) touch files reached by the real on-target compile in
ways the host-only test harness cannot fully substitute for -- a
`static_assert` (ticket 001) is a compile-time check the host harness may
model differently than the actual CODAL toolchain, and a degenerate-command
kernel call (ticket 004) exercises the same `kernel_.neutral()` path already
proven correct by `endMove()`, but only a real build confirms nothing about
its usage broke compilation for the actual target.

**Depends on tickets 001-006** -- this ticket must run last, after every
other change in the sprint, since its whole job is confirming the combined
result of all six still builds and still passes the full suite.

`src/core/diffdrive.{h,cpp}` is vendored and byte-stable; none of this
sprint's tickets touch it, and this checkpoint's job includes confirming that
remains true (no accidental edit slipped into the vendored kernel across six
tickets).

## What to do

1. Run the full host test suite first (`uv run pytest tests/host/
   tests/tools/`, or `uv run pytest` for the whole repo) and confirm it's
   green -- this is the pre-condition, not the checkpoint itself. Confirm the
   new drift tests from tickets 005 and 006, and the new host tests from
   tickets 001, 002, and 004, are present and passing (not merely that the
   suite as a whole is green -- verify by name that each ticket's stated new
   test(s) actually ran).
2. Run the real build pipeline exactly as prior sprints' build-checkpoint
   tickets have: `tools/make_deploy.py` for the primary target, and again
   with `--testrig` for the second scratch path. `make_deploy.py`'s own
   triage (`classify_attempt()`) distinguishes a real compile diagnostic
   (hard failure, no retry) from the known benign shapes (legacy V1
   `bbc-microbit-classic-gcc` hex-merge failure; nondeterministic
   `TS9283`/`TS9043`/`TS9200` packaging aborts, retried once automatically)
   -- trust that triage rather than re-deriving it.
3. Confirm a flashable hex is produced with no errors for the primary target
   (record the hex filename, byte size, and sha256, as prior build-checkpoint
   tickets have).
4. Specifically confirm ticket 001's `static_assert` (or equivalent
   compile-time guard) compiles cleanly under the real toolchain, not just
   the host harness -- this is exactly the class of check a host-only
   `pytest` run can model subtly wrong.
5. Specifically confirm `src/blocks/world.ts`'s rewritten
   `startWorldTracking()` (ticket 002) and any TypeScript changes from ticket
   006 (if the `defaultSpeed`/`motion.ts` comment or code was touched)
   type-check under the real `pxt build` -- the review's own Q-07 finding
   notes that `tsc`/`pxt build` is the only thing that executes/type-checks
   the block-facing TypeScript at all in this repo.
6. If the build fails, the failure is diagnostic information about tickets
   001-006, not a new bug to silently patch around -- report which prior
   ticket's change is implicated and coordinate the fix back into that
   ticket's scope (reopening it if already closed) rather than making an ad
   hoc fix in this ticket that isn't traceable to a ticket with acceptance
   criteria covering it.
7. Do not flash a real robot for this checkpoint -- follow the established
   convention (build success and hex output, not an on-hardware smoke test;
   see the prior build-checkpoint tickets cited above). This sprint changes
   no student-visible behavior beyond `startWorldTracking()` becoming correct
   for a future sensor revision and the degenerate-motion contract being made
   honest (per sprint.md's own Use Cases section), so a hardware flash is not
   a meaningful additional check here.

## Acceptance Criteria

- [x] Full host suite (`uv run pytest`) passes, including the new tests
      tickets 001, 002, 004, 005, and 006 each add.
- [x] The real build pipeline (`tools/make_deploy.py`, primary target and
      `--testrig`) completes and produces a flashable hex with no errors.
- [x] `src/core/diffdrive.{h,cpp}` is confirmed unmodified by this sprint
      (e.g. `git diff` against the sprint's base for those two files is
      empty).
- [x] If the build surfaces a failure traceable to a specific ticket
      001-006, that failure is fixed within the scope of the responsible
      ticket (reopened if already closed) rather than patched ad hoc here.
- [x] All of this sprint's Success Criteria from `sprint.md` are satisfied:
      HELP cannot lose its terminator; `0x5F` appears once, in
      `otos_port.h`; `dutl`/`dutr` units documented in `tlm.py` and both
      source comments; the degenerate motion command either stops prior
      motion or plainly documents that it does not; `kCdegToRad`/
      `kRadToCdeg` defined once, seven (or more, per ticket 005's own
      verification) open-coded sites retired; every remaining mirrored
      constant enumerated with a drift test or a merge.

## Build Evidence

**Pre-condition -- full test suite (foreground):** `uv run pytest` --
**677 passed**, 0 failed. Ran twice (once before the build pipeline,
once after) with identical results. By-name verification that each
prior ticket's own new tests actually ran (not just an aggregate
green count):

- Ticket 001: `tests/host/test_wire_grammar.py::
  test_build_help_line_terminator_survives_synthetic_overflow`,
  `::test_build_help_line_terminator_survives_at_every_tight_capacity`
  -- collected and passed.
- Ticket 002: `tests/host/test_otos_product_id_single_source.py::
  test_start_world_tracking_delegates_to_world_tracking_ready` --
  collected and passed.
- Ticket 003: `tests/tools/test_tlm.py::
  test_duty_pct_undoes_the_wire_double_x100_scale`,
  `::test_duty_pct_10000_is_full_duty` -- collected and passed.
- Ticket 004: `tests/host/test_motion_engine_primitives.py::
  test_wheels_x_zero_magnitude_stops_a_live_wheels_v_hold`,
  `::test_wheels_x_non_positive_cruise_stops_a_live_wheels_v_hold`,
  `tests/host/test_motion_engine_reductions.py::
  test_move_x_zero_magnitude_stops_a_live_wheels_v_hold`,
  `::test_move_x_non_positive_cruise_stops_a_live_wheels_v_hold` --
  collected and passed.
- Tickets 005/006: `tests/host/test_wire_constants_drift.py` -- 19
  passed (10 pre-existing + 9 new: the kCdegToRad merge guard from
  ticket 005, and ticket 006's defaultCruiseMmS_-comment,
  24 ms-cadence, trackWidth/rotationalSlip, and ConfigField-ordinal
  guards).

`ruff check tools tests` -- all checks passed. `clasi design validate`
-- `ok: true`, no messages (three non-subsystem docs noted as
informational, not orphan-checked, as before this sprint).

**Real build pipeline.** `.tmp/deploy-head` and `.tmp/deploy-testrig`
both pre-existed from earlier work in an INCOMPLETE state (each was
missing 4 of the 10 `nezha-diffdrive` translation units from its
`Building CXX object` log -- an incremental build silently reusing
stale `.o` files, the same class of risk
`make-deploy-accepts-a-silently-incomplete-hex.md` (sprint 016) warns
about, though here the resulting hex sizes happened to already be
correct). Wiped both directories with Python `shutil.rmtree` (not
`rm -rf`, per this ticket's own instruction) and rebuilt each from
scratch before recording final evidence.

*Primary target* (`uv run python tools/make_deploy.py`, exit code 0):

- `hex: .tmp/deploy-head/built/binary.hex (1445876 bytes)` -- ~1.44 MB,
  consistent with sprint 017's measured 1,442,996 bytes (small
  increase expected: this sprint added source, comments, and no
  vendored-kernel changes).
- sha256: `e11c0178998d8048ef5b8c048230b93f4b097365e5497ebad4e0393ba5bd95d9`
- All **ten** `nezha-diffdrive` translation units present as `Building
  CXX object` lines: `comms/wire_adapter.cpp`, `comms/protocol.cpp`,
  `comms/wire_handler.cpp`, `comms/radio_transport.cpp`,
  `comms/serial_transport.cpp`, `core/diffdrive.cpp`,
  `motion/motion_engine.cpp`, `platform/nezha_port.cpp`,
  `platform/otos_port.cpp`, `shims.cpp`.
- Zero `:0400000A` markers in the hex; no `.tmp/deploy-head/built/
  dockeryt/`; no `srec_cat` error text; no `INTERNAL ERROR`; no
  compiler `error:` lines (two pre-existing, unrelated compiler
  warnings only: an unused-function warning in `core/serial.cpp` and a
  signed/unsigned comparison warning in `nezha_port.cpp`, both outside
  this sprint's diff). `[attempt 1]` -- no retry needed.
- `wire_handler.cpp` (ticket 001's `static_assert(sizeof(kCommandTable)
  / sizeof(kCommandTable[0]) == 18, ...)`) compiled cleanly under the
  real CODAL/GCC toolchain, not just the host harness's own C++11
  syntax gate.
- `src/blocks/world.ts` (ticket 002) and `src/blocks/motion.ts`
  (referenced by ticket 006's enumeration, unmodified in content) were
  in the file set `pxt build` type-checked before generating the C++
  glue the CMake step then compiled -- the build reaching hex output
  with zero `error TS####` anywhere in the log confirms this succeeded
  (a TS type error aborts before the native compile phase is ever
  reached).
- Re-ran after recording evidence (now incremental, using the freshly
  rebuilt cache) to confirm exit code 0 explicitly: identical hex size
  and `[attempt 1]`, confirming determinism.

*`--testrig` target* (`uv run python tools/make_deploy.py --testrig`,
exit code 0):

- `testrig hex: .tmp/deploy-testrig/built/binary.hex (1419146 bytes)`.
- sha256: `5bfeb5008d532e713438a771b9381079eaa74f0cdba7a9dac26d351666d3d6b1`
- All ten `nezha-diffdrive` translation units present (confirmed after
  the wipe+rebuild); zero `:0400000A` markers; no `dockeryt/`; no
  `srec_cat`/`INTERNAL ERROR`/compiler `error:` lines. `[attempt 1]`.
  Re-ran to confirm exit code 0 and identical hex size/sha256.
- No hardware flash performed (`--flash` never passed), per this
  ticket's own instruction and this sprint's `sprint.md` Use Cases
  section -- no student-visible behavior changed beyond
  `startWorldTracking()` (ticket 002) and the degenerate-motion
  contract (ticket 004).

**Vendored kernel.** `git diff <sprint-019-base> HEAD -- src/core/
diffdrive.h src/core/diffdrive.cpp` is empty -- confirmed byte-stable
across every ticket in this sprint, including this checkpoint.

**No failures traceable to tickets 001-006 surfaced** -- both builds
succeeded on the first attempt after the scratch-directory wipe;
nothing needed reopening.

## Testing

- **Existing tests to run**: the full suite -- `uv run pytest`.
- **New tests to write**: none -- this ticket verifies the six tickets'
  own new coverage and the real build, it doesn't add new pytest coverage
  of its own.
- **Verification command**: `uv run pytest && python tools/make_deploy.py
  && python tools/make_deploy.py --testrig`.

---
id: '006'
title: 'Build checkpoint: full build, flashable hex'
status: in-progress
use-cases: []
depends-on:
- '001'
- '002'
- '003'
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint: full build, flashable hex

## Description

Standing convention: the last ticket in every sprint is a build
checkpoint that runs the real `pxt build` / `tools/make_deploy.py`
pipeline and confirms a flashable hex comes out the other end. See the
most recent prior examples: sprint 019 ticket 007
(`clasi/sprints/done/019-.../tickets/done/007-build-checkpoint-full-build-flashable-hex.md`)
and sprint 014 ticket 002.

**Depends on tickets 001, 002, and 003** -- the three tickets in this
sprint that actually change files (`test/test.ts` in 001 and 003,
`tools/field.py` in 002). Tickets 004 and 005 are deferred
(`status: exception`, blocked on hardware availability) and touch no
files, so this checkpoint has nothing of theirs to verify.

This checkpoint carries extra weight for ticket 001 specifically:
`test/test.ts` is TypeScript type-checked by `pxt build`/`tsc` and has
no host-side unit harness in this repo (per sprint 019's own
build-checkpoint findings) -- this is the ONLY thing that proves
ticket 001's refactor (and ticket 003's new `RUN:arc` verb) still
compile correctly for the real target.

## What to do

1. Run the full host test suite (`uv run pytest`) and confirm it is
   green, including ticket 002's new `tests/tools/test_field.py`
   coverage and ticket 001/003's `tests/tools/test_run_verbs.py`
   sanity checks (verify by name that these ran, not just that the
   aggregate count is green).
2. `ruff check tools tests`.
3. Run the real build pipeline: `uv run python tools/make_deploy.py`
   (primary target). `make_deploy.py`'s own triage (`classify_attempt()`)
   distinguishes a real compile diagnostic (hard failure) from the two
   documented benign shapes (legacy V1 hex-merge failure; nondeterministic
   `TS9283`/`TS9043`/`TS9200` packaging aborts, retried once) from
   success -- trust that triage rather than re-deriving it by hand.
4. **Assert the hex is not silently short**, per
   `clasi/issues/make-deploy-accepts-a-silently-incomplete-hex.md`: a
   clean build log is not sufficient evidence on its own -- a 27%-short
   hex has passed one before. Confirm explicitly:
   - `binary.hex` byte size is in the expected band -- recent
     checkpoints measured 1,423,241 (014), 1,434,671 (015), 1,442,546
     (016), and 1,445,876 (019) bytes, i.e. ~1.44 MB and slowly
     growing. Treat anything well below that band (order 1.2 MB or
     less) as a signal of a stale/incomplete vendored `dockercodal`
     checkout, not a clean pass -- wipe `.tmp/deploy-head` and rebuild
     from scratch if so, per sprint 019's own build-evidence precedent.
   - Zero `:0400000A` markers.
   - All **ten** `nezha-diffdrive` translation units present as
     `Building CXX object` lines: `comms/wire_adapter.cpp`,
     `comms/protocol.cpp`, `comms/wire_handler.cpp`,
     `comms/radio_transport.cpp`, `comms/serial_transport.cpp`,
     `core/diffdrive.cpp`, `motion/motion_engine.cpp`,
     `platform/nezha_port.cpp`, `platform/otos_port.cpp`,
     `shims.cpp`.
   - No `dockeryt/` directory, no `srec_cat` text, no `INTERNAL ERROR`.
5. Confirm no real `error:` lines in the build log beyond known
   pre-existing benign warnings (unused-function in `core/serial.cpp`,
   signed/unsigned comparison in `nezha_port.cpp`).
6. If the build surfaces a failure traceable to ticket 001, 002, or
   003, that is diagnostic information about that ticket, not a new
   bug to patch around here -- report which ticket is implicated and
   fix it within that ticket's scope (reopening it if already closed).
7. This checkpoint does not need to repeat ticket 003's hardware flash
   or heading-trajectory capture -- that is ticket 003's own
   acceptance criteria, already verified there against a build from
   the same sprint state. A hardware flash here is optional, at the
   implementer's discretion, only as an additional confirmation that
   the FINAL combined sprint state (001+002+003 together) still
   flashes and answers `STATUS` -- not a repeat of ticket 003's
   heading measurement.

## Acceptance Criteria

- [x] Full host suite (`uv run pytest`) passes, including tickets
      001/002/003's new/updated tests, verified by name.
- [x] `ruff check tools tests` passes.
- [x] The real build pipeline (`tools/make_deploy.py`) completes and
      produces a flashable hex with no real compile errors.
- [x] Hex byte size recorded and confirmed in the expected ~1.44 MB
      band (not a silent short build); zero `:0400000A` markers; no
      `dockeryt/`; all ten translation units confirmed present by
      name.
- [x] If a failure traces to ticket 001, 002, or 003, it is fixed
      within that ticket's scope (reopened if needed) rather than
      patched ad hoc here. **N/A** -- no failure occurred; nothing to
      trace or fix.
- [ ] All of this sprint's applicable Success Criteria from
      `sprint.md` are addressed: every `RUN:` handler sets one named
      shaping profile with the profile recorded in the capture
      (ticket 001); `tools/field.py` knows the field limits and margin
      with a pre-flight path check, or the rule is corrected (ticket
      002); the phase-handoff fix is confirmed on hardware (ticket
      003). The `goToWorld` and leg-vs-pivot rotation criteria remain
      unmet, by design, per tickets 004/005's recorded exceptions.
      **Left unchecked, deliberately**: 001 and 002's criteria ARE
      met (both tickets `done`). 003's is NOT -- ticket 003's own
      Acceptance Criteria and Verdict record the phase-handoff fix as
      **NOT FORMALLY CONFIRMED** (trajectory capture blocked this
      session by a newly-discovered `src/comms/` link-hang defect,
      filed separately; only weaker endpoint-only data was collected).
      This checkpoint does not repeat or substitute for that capture
      (see ticket's own item 7) and cannot check this box on 003's
      behalf. This is a genuine, open gap carried forward on ticket
      003, not a defect of this build checkpoint -- see Build
      Evidence below.

## Testing

- **Existing tests to run**: the full suite -- `uv run pytest`.
- **New tests to write**: none -- this ticket verifies tickets
  001-003's own new coverage and the real build; it doesn't add new
  pytest coverage of its own.
- **Verification command**: `uv run pytest && ruff check tools tests && uv run python tools/make_deploy.py`.

## Build Evidence

Run 2026-08-26, repo root, on branch
`sprint/018-bench-truth-re-measure-accuracy-on-corrected-motion`. No
flash attempted (tovez was already flashed with this sprint's exact
build during ticket 003's own hardware session; reflashing here would
verify nothing new).

### 1. Full host suite -- `uv run pytest`

```
687 passed in 22.25s
```

Ticket-specific coverage confirmed present **by name**, not just by
aggregate count:
- `tests/tools/test_field.py .................................  [ 82%]`
  (33 passed) -- ticket 002's field-limits/pre-flight-path-check
  coverage.
- `tests/tools/test_run_verbs.py ......................  [ 95%]`
  (22 passed) -- tickets 001/003's RUN-verb sanity checks (named
  shaping profile per handler, `RUN:arc` string).

### 2. `uvx ruff check tools tests`

```
All checks passed!
```

### 3. `node_modules/.bin/tsc --noEmit -p tsconfig.json`

Exit code 0, no output -- `test/test.ts`'s ticket 001/003 changes
(profile discipline, new `RUN:arc:<deg>` handler) type-check cleanly.

### 4. `clasi design validate`

```
{"ok": true, "messages": []}
```
(three informational-only notices about non-subsystem docs
`overview.md`/`specification.md`/`usecases.md` not being
orphan-checked -- pre-existing, not a failure.)

### 5. `uv run python tools/make_deploy.py`

**First attempt** reused a codal build cache left over from ticket
003's own build minutes earlier: the hex came out at the correct size
(1,448,621 bytes, matching ticket 003's own measurement exactly) but
the log contained **zero** `Building CXX object` lines for anything --
an incremental relink, not independent evidence that this checkpoint's
own invocation actually recompiled the ten `nezha-diffdrive`
translation units. Per this ticket's own instruction ("fewer than ten
... translation units compile -> wipe `.tmp/deploy-head` entirely and
rebuild before concluding anything"), treated this as insufficient
evidence (not as a failure) and wiped `.tmp/deploy-head`
(`shutil.rmtree`, Python) to force a fully clean rebuild, per
`clasi/issues/make-deploy-accepts-a-silently-incomplete-hex.md`.

**Clean rebuild** (full local Docker `codal` compile, `.tmp/deploy-head`
removed first):

```
hex: /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/.tmp/deploy-head/built/binary.hex  (1448621 bytes)  [attempt 1]
```

Assertions, checked explicitly against this clean-rebuild log:

- **Byte size**: 1,448,621 bytes -- in the healthy ~1.44 MB band
  (references: 1,423,241 (014), 1,434,671 (015), 1,442,546 (016),
  1,445,876 (019)), and matches ticket 003's own from-scratch flash
  build exactly.
- **All ten `nezha-diffdrive` translation units** present as
  `Building CXX object` lines (count: 10/10):
  `comms/protocol.cpp`, `comms/radio_transport.cpp`,
  `comms/serial_transport.cpp`, `comms/wire_adapter.cpp`,
  `comms/wire_handler.cpp`, `core/diffdrive.cpp`,
  `motion/motion_engine.cpp`, `platform/nezha_port.cpp`,
  `platform/otos_port.cpp`, `shims.cpp`.
- **`:0400000A` markers**: 0 (plain V2 hex, not a universal V1+V2
  one -- `PXT_COMPILE_SWITCHES=csv-mbcodal` took effect).
- **`dockeryt/` directory**: none found under `.tmp/deploy-head/built`.
- **`srec_cat` errors**: none.
- **`INTERNAL ERROR`**: none.
- **`BUILD FAILED`**: none.
- **`error:` lines**: none.
- **`warning:` lines**: five total, all pre-existing and benign --
  `core/serial.cpp:275` unused-function (`sendString`),
  `platform/nezha_port.cpp:305` signed/unsigned comparison (both named
  in this ticket as known pre-existing), plus `core/codal.cpp:143`
  function-pointer-cast and two assembler "end of file not at end of a
  line" notices in vendored `pxtapp/core` `.s` files -- none touch
  `nezha-diffdrive` logic and none are new.

### Conclusion

Build is clean by every check this ticket specifies. Tickets 001 and
002's source changes (`test/test.ts` profile discipline, new
`RUN:arc:<deg>` handler; `tools/field.py` field limits/pre-flight path
check) compile and pass their full host coverage. No failure traces to
any of tickets 001, 002, or 003 -- the one open item (ticket 003's
on-hardware phase-handoff trajectory capture) is a recorded,
in-progress gap on ticket 003 itself, not a build defect surfaced
here.

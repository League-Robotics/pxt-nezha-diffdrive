---
id: '001'
title: "VFP yield guard \u2014 verify and hardware-confirm"
status: in-progress
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: fiber-safety-and-command-dispatch.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# VFP yield guard — verify and hardware-confirm

## Description

`RUN:straight:20`, `RUN:pivot:90` and `RUN:square:20` hard-fault the
board 3/3 (MEASURED gopiv 2026-09-01, pyOCD +
`DIFFDRIVE_FAULT_SPIN`). Root cause: CODAL's fiber context switch
(`codal-nrf52/asm/CortexContextSwitch.s`) saves R0-R12/SP/LR and no VFP
registers, while this firmware builds with the hardware FPU on
(`-mfpu=fpv4-sp-d16 -mfloat-abi=softfp`), so GCC spills pointers as
well as floats into the callee-saved bank s16-s31 (= d8-d15). A fiber
parked at a yield while holding a pointer there loses it the instant
another fiber runs float code. Full forensics:
`docs/knowledge/2026-09-01-codal-does-not-save-fpu-registers-across-fibers.md`;
raw measurement: `clasi/issues/run-fiber-motion-resets-the-board-on-fw-1-20260829-1.md`;
design: `clasi/issues/fiber-safety-and-command-dispatch.md` §1.

**The implementation for this ticket already exists, uncommitted, in
the working tree — this ticket is honest that it is written but
UNVERIFIED, not that it needs to be written.** What is present:

- `src/platform/vfp_guard.{h,cpp}` — `noinline` `vfpSafeSleep(ms)` /
  `vfpSafeYield()` wrapping `fiber_sleep`/`schedule`, each followed by
  an inline-asm clobber of `d8`-`d15`, gated
  `#if defined(__arm__) && defined(__ARM_FP)`.
- Every direct yield in this extension's own code rerouted through it:
  `src/platform/platform_ports.h` (`CodalSleeper::sleepMillis`/
  `yield()` — this alone covers the vendored kernel's two encoder
  settle sleeps transitively, since `DifferentialDrive::step` reaches
  the sleeper by indirect virtual call), `src/comms/protocol.cpp`
  (`emitLine()`'s retry sleep and the measured crash site in `run()`),
  `src/comms/serial_transport.cpp` (the retry sleep, plus a
  `guardedSerialSend()` local helper wrapping `uBit.serial.send(...,
  SYNC_SLEEP)` — a yield that hides inside a call that looks
  synchronous and that no `fiber_sleep` grep would find),
  `src/platform/nezha_port.cpp` (encoder probe settle),
  `src/platform/otos_port.cpp` (`busGap()` and the begin sleep).
- `pxt.json`'s `files[]` and `tools/make_deploy.py`'s
  `EXPECTED_CPP_FILES` both list the two new files (confirm both stay
  in sync — this is exactly what `test_pxt_manifest_completeness.py`
  and `test_make_deploy_triage.py` check).
- Guardrails already shipped alongside the fix: `.claude/rules/fiber-yield-safety.md`
  (scoped to `src/**/*.cpp`/`src/**/*.h`), a "Yield discipline (system
  invariant)" section in `src/DESIGN.md` beside the existing I2C
  bus-discipline invariant, in-header rationale in `vfp_guard.h` itself,
  and `tests/host/test_vfp_guard_source_pin.py` with teaching-oriented
  failure messages.
- The full host suite (890 tests) passes.

**What is NOT done and is this ticket's actual scope:**

1. A successful firmware build (`--robot gopiv` explicitly —
   `DEFAULT_ROBOT` is vevov).
2. The codegen check that `vfpSafeSleep`/`vfpSafeYield` really compile
   to `vpush.64 {d8-d15}` ... `vldm sp!, {d8-d15}` around a `bl` (a
   `b.w` would mean the tail call survived and the guard is inert).
3. The disassembly census: after the guard, exactly **three** direct
   yield-primitive call sites may remain across our symbols (the two
   wrappers plus the serial-send helper) — baseline was 17 across 13
   symbols.
4. The hardware kill test on gopiv: baseline 3/3 resets on *current*
   (unfixed) firmware first — without this the fixed run proves
   nothing — then 0/10 `RUN:straight:20`, 0/10 `RUN:pivot:90`, 0/5
   `RUN:square:20` on the fixed firmware, in the same pyOCD session.

This ticket is a **prerequisite gate for ticket 003**: ticket 003
restructures the very fiber this guard protects, and must not start
until this ticket's hardware acceptance has actually passed — starting
it against an unconfirmed guard would make any ticket-003 test failure
ambiguous between "the guard doesn't work" and "the restructuring is
wrong."

## Acceptance Criteria

- [ ] `arm-none-eabi-gdb` disassembly of the flashed ELF
      (`.tmp/deploy-head/built/dockercodal/build/MICROBIT` — the
      repo-root `built/` copy is stale; `arm-none-eabi-objdump` is not
      installed on the dev machine) confirms both `vfpSafeSleep` and
      `vfpSafeYield` contain a `vpush` naming all eight of `d8`-`d15`,
      a matching `vldm`/`vpop`, and a `bl` to the wrapped primitive
      (not a `b.w`).
- [ ] Disassemble `.text`, grep for
      `fiber_sleep|codal8scheduleEv|fiber_wait_for_event` filtered to
      `diffDrive|DiffDrive|Wire`, and confirm exactly **three** direct
      call sites remain (the two guard wrappers and the
      `guardedSerialSend()` helper) — anything else is an unguarded
      yield. Note in the ticket's own notes that this census finds only
      *direct* calls inside our own symbols, not a yield two frames
      deep inside a vendored call (that is how `SYNC_SLEEP` was found
      in the first place — by reading CODAL source, not by grepping).
- [ ] A firmware build succeeds with `--robot gopiv` explicitly.
- [ ] `uv run pytest tests/host/test_vfp_guard_source_pin.py` and the
      full host suite pass.
- [ ] **Hardware acceptance on gopiv, farm node magni, pyOCD only.**
      DAPLink mass storage times out mid-write on that host and blanks
      the board (measured, `FAIL.TXT`: "The transfer timed out"); use
      `pyocd erase --mass` followed by `pyocd flash -t nrf52833` for
      every flash in this ticket, never the MSD drag-and-drop path.
      1. **Baseline first, same session, same board**: flash *current*
         (unfixed) firmware, send `RUN:straight:20` x3, confirm 3/3
         resets (a second `device NEZHA2 ...` banner on an established
         link *is* a reset — no further probing needed).
      2. Flash the fix; confirm `VER` changed.
      3. **PASS = 0/10 `RUN:straight:20`, 0/10 `RUN:pivot:90`, 0/5
         `RUN:square:20`.**
      4. Stress the race harder than the original repro: subscribe
         `TLM` so the protocol fiber is busy, and interleave `MOVE_X`
         during a `RUN:square:20`.
      5. Re-test the radio-traffic wedge
         (`fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`)
         and the tigez wedge (identical `CFSR 0x8200`, previously
         attributed to heap corruption) and **report either way** in
         this ticket's completion notes. If they clear, correct that
         attribution (do not silently leave the old attribution
         standing). If they persist, they are a separate fault — say so
         explicitly, and do not let this guard become their
         explanation by default.
      6. If anything still faults, `#define DIFFDRIVE_FAULT_SPIN 1`
         (`src/platform/nezha_port.cpp:77`) parks the chip for pyOCD
         instead of resetting, for further diagnosis.
- [ ] `uv run pytest tests/host/test_pxt_manifest_completeness.py
      tests/tools/test_make_deploy_triage.py` pass (both directions of
      the `pxt.json`/`EXPECTED_CPP_FILES` sync).
- [ ] Confirm `vfp_guard.cpp` is **not** in
      `_CXX11_PORTABLE_SOURCES` — it includes `pxt.h`, and the host
      build is `-std=c++11`.
- [ ] Re-run `tests/system/run_tour.py` (the host-driven `.tour` suite)
      once the fix is flashed, to confirm the wire-driven path is
      unaffected.
- [ ] No new comment names a sprint, a ticket, an `R-NN` code, or any
      `.md` filename anywhere under `src/` — the archaeology marker
      budget is at 388/388 with **zero** slack
      (`test_archaeology_marker_budget.py`). Issue/ticket references
      belong in the commit message only. The uncommitted `vfp_guard.{h,cpp}`
      and `test_vfp_guard_source_pin.py` were already written clean of
      such references — verify they stay that way if touched.

## Implementation Plan

**Approach**: This ticket is primarily verification, not authorship —
the source changes already exist uncommitted (see Description). Work
through the acceptance criteria in order: codegen census first (cheap,
no hardware needed), then the firmware build, then the hardware
acceptance sequence on gopiv. If the codegen or disassembly census
finds a gap (e.g. a yield site the original pass missed), fix it in
the existing uncommitted files rather than restarting the design — the
architecture (guard shape, call-site list, guardrails) is already
reviewed and is not in question; only its completeness and hardware
behavior are.

**Files to verify/modify** (already touched, uncommitted):
`src/platform/vfp_guard.h`, `src/platform/vfp_guard.cpp`,
`src/platform/platform_ports.h`, `src/comms/protocol.cpp`,
`src/comms/serial_transport.cpp`, `src/platform/nezha_port.cpp`,
`src/platform/otos_port.cpp`, `pxt.json`, `tools/make_deploy.py`,
`tests/host/test_vfp_guard_source_pin.py`,
`tests/tools/test_make_deploy_triage.py`, `.claude/rules/fiber-yield-safety.md`,
`src/DESIGN.md`.

**Files NOT to modify**: `src/core/diffdrive.{h,cpp}` (vendored,
byte-identical — the guard covers it transitively through
`CodalSleeper` without editing it), `src/shims.cpp`,
`src/comms/radio_transport.cpp` (audited, no yield in its call graph),
`src/motion/motion_engine.*`.

## Testing

- **Existing tests to run**: full `uv run pytest` (host suite, 890
  tests at time of writing) — confirm it still passes unmodified from
  the uncommitted working tree.
- **New tests to write**: none expected beyond what
  `test_vfp_guard_source_pin.py` already covers, unless the codegen or
  disassembly census surfaces a gap.
- **Verification commands**:
  `uv run pytest tests/host/test_vfp_guard_source_pin.py tests/host/test_pxt_manifest_completeness.py tests/tools/test_make_deploy_triage.py`,
  a firmware build with `--robot gopiv`, the `arm-none-eabi-gdb`
  disassembly census, and the gopiv hardware acceptance sequence above.

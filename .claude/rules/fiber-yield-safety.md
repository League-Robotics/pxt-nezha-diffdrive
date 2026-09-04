---
paths:
  - "src/**/*.cpp"
  - "src/**/*.h"
---

# Never yield without the VFP guard

You are editing firmware C++ that runs under CODAL's fiber scheduler.

**Do not call `fiber_sleep()` or `schedule()` directly.** Route every
yield through `diffDrive::vfpSafeSleep()` / `diffDrive::vfpSafeYield()`
in `src/platform/vfp_guard.h`. `tests/host/test_vfp_guard_source_pin.py`
fails the build if you don't.

## Why

The build enables the hardware FPU (`-mfpu=fpv4-sp-d16
-mfloat-abi=softfp`) and **CODAL's context switch does not save the FPU
registers** — `swap_context` in `codal-nrf52/asm/CortexContextSwitch.s`
stores R0-R12, SP and LR, and contains no VFP instructions at all.

GCC allocates the callee-saved half of that bank, s16-s31 (= d8-d15),
as ordinary spill space — **for pointers, not just for floats**. So a
fiber parked at a yield can have its local variables silently replaced
by whatever another fiber's arithmetic left in those registers.

MEASURED gopiv 2026-09-01 (pyOCD, `DIFFDRIVE_FAULT_SPIN` build):
`Protocol::run()` parked `&radioTransport_` in s17 across its
`fiber_sleep(5)`; a tour fiber's PID wrote a wheel speed over it; the
protocol fiber woke, restored float -25.0f as `this`, and dereferenced
it. `CFSR 0x8200`, `BFAR` = the float's bit pattern + the member offset.
The board hard-faulted and reset. Full write-up in the knowledge
directory under `docs/`.

The guard is a `noinline` wrapper whose inline-asm clobber of d8-d15
forces AAPCS to `vpush`/`vldm` the bank around the yield, on the calling
fiber's own stack — the save CODAL omits. Because the save is per-frame
it is also per-fiber: a guarded fiber is safe no matter what any
unguarded fiber does.

## The trap that grep will not catch

**A yield can hide inside a call that looks synchronous.** Searching for
`fiber_sleep` is not an audit — you have to know whether the CODAL API
you are calling blocks internally.

The worked example: `uBit.serial.send(..., SYNC_SLEEP)` blocks on
`fiber_wait_for_event()` when the 255-byte TX ring fills, which is
reachable with 240-byte lines at 20 Hz telemetry. It is wrapped for that
reason.

Audited and cleared — these do **not** yield, so do not wrap them:
`uBit.i2c` (`NRF52I2C` spin-waits), `uBit.radio.datagram.send`, async
serial read, and `MessageBus::send` (queues only; it does not dispatch).

**If you call a CODAL API that is not on that cleared list, read its
source before assuming it does not yield.** If it does, wrap it in a
`noinline` local helper carrying `DIFFDRIVE_VFP_BANK_CLOBBER()`, the
same way `serial_transport.cpp` does.

## Related invariants

- `src/core/diffdrive.{h,cpp}` is the vendored kernel. **Do not edit
  it** -- except via a paired upstream PR, see
  `clasi/sprints/029-motion-profile-unification-one-shaper-one-floor-predictive-arrival/issues/decide-the-kernel-fork.md`. Sprint 029 ticket 001
  (K1-K4: post-floor twist-hold reference, stale-tick freeze,
  anti-windup, `rearmReferences()`) is the first change to land under
  that carve-out: the same four patches were written against this
  repo's copy and staged as a diff for
  `radio-robot-elite/src/firm/diffdrive/` (see
  `docs/code-review/2026-09-02/raw/kernel-patches-k1-k4.upstream.patch`
  for the exact diff and how to apply it there); the upstream PR was
  not yet opened as of that ticket's own close. Any further kernel edit
  follows the same shape -- implement in both trees, or get an explicit
  stakeholder decision to drop byte-identity in favor of a local fork
  with its own behavioral fidelity test (`decide-the-kernel-fork.md`
  covers both regimes). Its two encoder settle sleeps are already
  covered, because it reaches the sleeper through a true indirect
  virtual call and `CodalSleeper`'s methods are guarded.
- Every OTOS transaction must run on the same fiber that ticks the
  kernel. An OTOS read landing inside the encoder select-to-read window
  destroys that encoder sample.

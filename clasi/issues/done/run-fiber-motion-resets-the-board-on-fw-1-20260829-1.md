---
status: done
---
# RUN: motion resets the board — CODAL does not save the FPU registers across a fiber switch

**Severity: high, and wider than the RUN verbs.** Opened 2026-09-01,
**root-caused the same day** on gopiv with pyOCD.

## Root cause

**CODAL's fiber context switch saves R0–R12, SP and LR. It saves no VFP
registers at all.** The firmware is built `-mfpu=fpv4-sp-d16
-mfloat-abi=softfp`, so GCC allocates the *callee-saved* FPU registers
s16–s31 freely — 899 sites in the binary reference them.

A value parked in s16–s31 across a `fiber_sleep()` is therefore
silently destroyed if any other fiber runs float code in the gap. When
the parked value is a **pointer**, the next dereference faults.

That is exactly what happens:

| | |
|---|---|
| `codal-nrf52/asm/CortexContextSwitch.s` | `swap_context` / `restore_register_context` touch R0–R12, SP, LR only — no `vstm`/`vldm`/`vpush` anywhere in the file |
| `DifferentialDrive::drive(float left, float right)` @ 0x296ce | `vmov s16, r1` / `vmov s17, r2` — **both wheel speeds go into s16/s17** |
| `Protocol::run()` @ 0x26a4c | `vmov r1, s16` / `vmov r0, s17` — **reads the line buffer and `this` back out of s16/s17**, then calls `RadioTransport::tryReceiveLine` |

So the protocol fiber parks `&radioTransport_` in s17, sleeps, the tour
fiber's PID writes a wheel speed over s17, the protocol fiber wakes and
dereferences a float as an object pointer.

## The measurement

MEASURED gopiv 2026-09-01, `DIFFDRIVE_FAULT_SPIN` debug build (the
hook `nezha_port.cpp` already carries), pyOCD halt on the parked chip
after a single `RUN:straight:20`:

```
CFSR  0x00008200     BFARVALID | PRECISERR  -- precise data bus error
HFSR  0x40000000     FORCED     -- escalated to HardFault
BFAR  0xC1C801F3     the faulting address
xPSR  0x61030003     IPSR = 3  -- in the HardFault handler
```

Stacked exception frame at 0x2001FE20:

```
r0  0xC1C80000   <- float -25.0    (s17: right wheel, cm/s)
r1  0x41C80000   <- float +25.0    (s16: left wheel, cm/s)
r2  0x00000040   r3 0x2001FEB8   r12 0x0000A35D
LR  0x00026A61   PC 0x00026EF4   xPSR 0x21030200  (thread mode)
```

`addr2line` on the build's own ELF:

```
0x00026EF4  RadioTransport::tryReceiveLine   radio_transport.cpp:31
0x00026A61  Protocol::run                    protocol.cpp:350
```

`radio_transport.cpp:31` is `if (radioReady_) return;`. The
instruction is `ldrb.w r7, [r0, #499]`, and **BFAR = 0xC1C80000 + 0x1F3
= r0 + 499** — `this` is the float, and `radioReady_` sits at offset
499. The two register values are not garbage: they are exactly ±25.0f,
a 250 mm/s pivot, still sitting in the registers the motor path put
them in.

**Note the reset itself is diagnostic.** `NVIC_SystemReset()` in
`diffdriveFaultReport()` (added b2305e8) is the ONLY reset path in this
firmware, so "the board rebooted" already meant "the board faulted".

## Why RUN: faults and host-driven MOVE_X does not

Not the RUN dispatch, and not the motions:

| what was sent | resets? | why |
|---|---|---|
| `RUN:turnrate`, `RUN:abort`, `RUN:gap` | no | no float work on a second fiber |
| `MOVE_X` straight + pivot, host-driven | no | **`tickDrive()` runs on the protocol fiber itself** (`protocol.cpp`: `if (hasLiveMotionObligation()) tickDrive();`) — one fiber, so the ordinary ABI preserves s16–s31 correctly |
| `RUN:straight`, `RUN:pivot`, `RUN:square` | **yes, 3/3** | `tickToCompletion()` ticks on the **handler's own fiber** while the protocol fiber sleeps holding pointers in s16/s17 |

The reset lands at or just after move completion, where the float work
is heaviest and the yields most frequent.

## This is not only a RUN: bug

Any two fibers where one holds a pointer in s16–s31 and the other runs
float code can do this. In particular **a student program that calls
`control.inBackground()` and does any floating-point work is exposed**,
and so is the watchdog fiber's own `appliedDutyLeft != 0.0f`.

It is very likely the same fault as
`fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md` and the
tigez wedge written up in `nezha_port.cpp` — that one recorded the
**identical CFSR 0x8200** and was attributed to heap corruption
("a pointer holding the ASCII bytes PING"). A pointer restored from a
clobbered FPU register explains that observation without needing heap
corruption, and explains why radio traffic *concurrent with the motor
kernel* is the trigger: the radio poll is the code that parks `this` in
s17. That attribution should be revisited.

## Fixing it

**Not available:** the clean global fix is `-ffixed-s16 … -ffixed-s31`
(or `-mfloat-abi=soft`), which would stop GCC using the callee-saved
FPU registers anywhere. `codal.json` exposes preprocessor
`definitions` only — no compiler-flag knob — so this would mean editing
the vendored toolchain cmake, which is out of bounds. Patching CODAL's
`swap_context` to save s16–s31 is the textbook fix and is out of bounds
for the same reason. Both are worth raising **upstream**: CODAL
enabling the FPU without saving it across fibers is a defect in CODAL,
not in this extension.

**Available, and the recommended fix:** stop running motion on a second
fiber. Wire-issued moves already tick on the protocol fiber and are
provably safe; TS-issued moves should do the same. That means an
obligation-arming shim callable from TypeScript, and `tickedMove()`
becoming `startMove(...)` + wait, instead of
`while (diffDrive.driveTick())` on the handler's fiber. The tour then
runs with exactly one fiber doing float work, which is the condition
that makes the host-driven path safe today.

This does not remove the underlying hazard for student
`control.inBackground()` programs — only the upstream fix does — so the
hazard should be documented for students regardless.

## Impact while it stands

`RUN:square` / `RUN:infinity` / `RUN:spline` (and the pre-existing
`RUN:straight` / `RUN:pivot` / `RUN:tour`) cannot be driven. The five
bench tools that use those verbs — `otos_levercal.py`, `pivot_truth.py`,
`truth_check.py`, `rotation_check.py`, `turn_sweep.py` — will reset the
board mid-measurement.

Host-driven `MOVE_X` is unaffected: `tests/system/run_tour.py` and the
whole `.tour` suite are the working path.

## Reproducing

1. Add `#define DIFFDRIVE_FAULT_SPIN 1` above the fault-handler section
   in `src/platform/nezha_port.cpp` (the hook is already there); build
   and flash.
2. Send `RUN:straight:20`. The board goes silent instead of resetting.
3. `pyocd commander -t nrf52833 -c halt -c "reg r0 r1 pc lr sp"
   -c "read32 0xE000ED28 4" -c "read32 0xE000ED38 4"`, and dump the
   stack around MSP for the exception frame.
4. `arm-none-eabi-addr2line -f -C -e built/dockercodal/build/MICROBIT <pc>`.

**Flash gopiv with pyOCD, not DAPLink mass storage** — MSD timed out
mid-write twice on magni (`FAIL.TXT`: "The transfer timed out"),
leaving the board blank both times. `pyocd erase --mass` then
`pyocd flash -t nrf52833` recovered it cleanly.

---

## Triage 2026-09-02 — DONE

Fixed by sprint 026 ticket 001 (commit 6907222, VFP yield guard).
MEASURED gopiv 2026-09-01, `reports/run-tours-20260901`: 0/10
`RUN:straight:20`, 0/10 `RUN:pivot:90`, 0/5 `RUN:square:20` resets on
the board that reset 3/3 the same morning. The radio-traffic wedge
retest this issue asked for is still open — tracked in
`next/fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`.

## gopiv acceptance, sprint 028, 2026-09-02

MEASURED gopiv 2026-09-02, sprint 028's own hardware-acceptance
session, old firmware `ver 0.20260901.1` (the baseline before sprint
028's executor-inversion ticket landed, i.e. the same VFP-guard-fixed
generation this issue's own 2026-09-02 triage covers, not a regression
target): `RUN:pivot:90` sent alone produced **no reset** — `PIVOT:end`
at t=1.280s, `cyc` monotonic 2199->2253, no unsolicited `device
NEZHA2` boot banner. Consistent with this issue's own "DONE" triage
above; re-confirmed here as a byproduct of sprint 028's baseline step,
not a new investigation.
`captures/gopiv-acceptance-028-20260902/step_a_transcript.txt`.

Separately (not a `RUN:`-reset finding, noted here only because it
surfaced in the same baseline step): `RUN:abort` sent mid-`RUN:square:20`
on this same old firmware did not stop the tour quickly — `STATUS`
stayed `active=1`/`reason=timeout` for several seconds after the abort
before settling. This is the pre-028 "`RUN:abort` works by accident"
architecture issue (`single-executor-for-command-dispatch.md`,
resolved by sprint 028 ticket 003, hardware-confirmed fixed at ~40 ms
on the same board — see that ticket's own Hardware acceptance
section), not a recurrence of this issue's reset defect.

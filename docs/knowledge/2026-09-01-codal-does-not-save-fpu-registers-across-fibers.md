---
date: 2026-09-01
tags: [codal, fibers, fpu, vfp, hardfault, concurrency, firmware, pyocd]
related-tickets: []
---

# CODAL does not save the FPU registers across a fiber switch

## Problem

Any `RUN:` program that drives the motors resets the board on
fw 1.20260829.1. `RUN:straight:20`, `RUN:pivot:90` and `RUN:square:20`
fail 3/3. The same motions issued by the host as `MOVE_X` are fine.

The real problem is larger than the RUN verbs, and that is the point of
this article: **the firmware enables the hardware FPU, and CODAL's fiber
scheduler does not save the FPU registers.** GCC uses the callee-saved
half of that register bank as ordinary spill space — for pointers, not
just for floats — so any fiber that is parked at a yield can have its
local variables silently replaced by another fiber's arithmetic.

## Symptoms

- The board emits its `DBG:` banner, drives roughly one move, then the
  **boot banner reappears** on the wire, `PING`'s uptime counter
  restarts from ~0, and `cyc` returns to 0 and stays there.
- No panic text, no fault code, no LED error pattern. A silent reset.
- Non-motion `RUN:` verbs are unaffected. Host-driven `MOVE_X` is
  unaffected. Telemetry flows normally right up to the instant it stops.

Two things made this hard to read. First, "the board rebooted" looks
like a power or watchdog problem, not a memory-safety problem. Second,
the failure moves with the build: whether a given function keeps a
pointer in the affected registers is a register-allocation decision, so
it tracks binary layout rather than semantics and can appear to come and
go across unrelated changes.

## What was tried

**Blaming the RUN dispatch path.** Reasonable — RUN was the only failing
verb. Killed by measurement: three non-motion RUN verbs
(`RUN:turnrate`, `RUN:abort`, `RUN:gap`) never reset, and host-issued
`MOVE_X` performing the *identical* straight and pivot never reset. The
common factor of the failures was not RUN and not the motions; it was
`tickToCompletion()` running the control loop on the handler's own
fiber.

**Blaming heap corruption.** An earlier wedge on tigez with the
*identical* `CFSR 0x8200` had been attributed to CODAL's radio
`queueRxBuf` allocating over the live Rig, because BFAR happened to hold
bytes that read as ASCII `"PING"`. Plausible, and wrong — or at least
unproven. A pointer restored from a clobbered FPU register explains that
observation with no heap corruption at all.

**Assuming a reboot meant a watchdog.** It did not. `NVIC_SystemReset()`
inside `diffdriveFaultReport()` is the *only* reset path in this
firmware, so "the board rebooted" already meant "the board took a CPU
fault" — the fault handlers had been installed a few days earlier
precisely so a fault would stop the motors instead of leaving them
running. The reset was diagnostic information that went unread for
several rounds.

## What worked

The firmware already carried the tool: `DIFFDRIVE_FAULT_SPIN` in
`src/platform/nezha_port.cpp` builds a variant whose fault handler stops
the motors and then **spins**, holding the fault state for a debugger
instead of resetting.

MEASURED gopiv 2026-09-01, `DIFFDRIVE_FAULT_SPIN` build, pyOCD halt
after a single `RUN:straight:20`:

```
CFSR  0x00008200     BFARVALID | PRECISERR   (precise data bus error)
HFSR  0x40000000     FORCED                  (escalated to HardFault)
BFAR  0xC1C801F3     the faulting address
xPSR  0x61030003     IPSR = 3, i.e. in the HardFault handler
```

Stacked exception frame at 0x2001FE20:

```
r0  0xC1C80000   <- float -25.0
r1  0x41C80000   <- float +25.0
PC  0x00026EF4   LR 0x00026A61   xPSR 0x21030200  (thread mode)
```

`addr2line` against the build's own ELF:

```
0x00026EF4  RadioTransport::tryReceiveLine   radio_transport.cpp:31
0x00026A61  Protocol::run                    protocol.cpp:350
```

`radio_transport.cpp:31` is `if (radioReady_) return;`, compiled as
`ldrb.w r7, [r0, #499]`. And **BFAR = 0xC1C80000 + 0x1F3 = r0 + 499**:
`this` was the float. The two register values are not garbage — they are
exactly the two wheel speeds of a 250 mm/s pivot, still sitting where
the motor code left them.

Three facts from the binary close the loop:

| where | what |
|---|---|
| `codal-nrf52/asm/CortexContextSwitch.s` | `swap_context` / `save_context` / `restore_register_context` touch R0-R12, SP, LR. **Zero VFP instructions in the entire file.** |
| build flags | `-mfpu=fpv4-sp-d16 -mfloat-abi=softfp` — the FPU is on, and GCC allocates s16-s31 freely. 899 sites in the image reference them. |
| `DifferentialDrive::drive(float,float)` @0x296ce | `vmov s16, r1` / `vmov s17, r2` — both wheel speeds go into the unsaved bank |
| `Protocol::run()` @0x26a4c | `vmov r1, s16` / `vmov r0, s17` — reads the line buffer and `this` back **out of** that same bank |

The protocol fiber parks `&radioTransport_` in s17, sleeps, the tour
fiber's PID writes a wheel speed over s17, the protocol fiber wakes and
dereferences a float.

**The fix is a source-only save/restore at every yield point we own.** A
`noinline` wrapper containing the yielding call plus an inline-asm
clobber of `d8`-`d15`:

```c
__attribute__((noinline)) void vfpSafeSleep(uint32_t ms) {
  fiber_sleep(ms);
  __asm__ volatile("" ::: "d8","d9","d10","d11","d12","d13","d14","d15");
}
```

compiles to

```
	push	{r3, lr}
	vpush.64	{d8, d9, d10, d11, d12, d13, d14, d15}
	bl	fiber_sleep
	vldm	sp!, {d8-d15}
	pop	{r3, pc}
```

Compile-verified against the real target flags. **Not yet confirmed on
hardware** at the time of writing — the hardware acceptance (0 resets in
10x `RUN:straight:20`, 10x `RUN:pivot:90`, 5x `RUN:square:20`, against a
3/3 failure baseline taken in the same session) is still to be run.

## Why it works

The clobber does not work by being a compiler barrier. It works because
declaring `d8`-`d15` clobbered marks them **used by this function**, and
AAPCS then obliges the compiler to save and restore them in the
prologue and epilogue. That save lands on the **calling fiber's own
stack**, before the context switch, and the restore runs after the fiber
resumes — which is precisely the work `swap_context` omits.

Three properties follow, and each one matters:

1. **It protects every ancestor frame.** The whole bank is saved
   unconditionally, so it covers whatever any caller further up that
   fiber's stack had parked there — at any depth. This is why guarding
   `CodalSleeper::sleepMillis` covers the vendored kernel's two encoder
   settle sleeps without editing the vendored kernel at all.

2. **Coverage is monotonic.** The save area is per-frame and therefore
   per-fiber. A fiber that yields through an unguarded path can lose its
   *own* values, but it can never corrupt a guarded fiber. There is no
   ordering requirement and no interaction hazard, so partial coverage
   is strictly better than none.

3. **It is sufficient, not merely a mitigation — because CODAL is
   non-preemptive.** Context switches happen only at explicit yields, so
   the set of dangerous moments is finite and enumerable. Guard all of
   them in our code and the class is closed for our code.

`noinline` is load-bearing for cost and verifiability rather than
correctness. Inlined, the guard is still correct, but GCC hoists the
save into the enclosing function's prologue and then refuses to allocate
d8-d15 anywhere across the asm — degrading register allocation through
the whole enclosing function, and leaving no single symbol to verify.

## Future guidance

**Never call `fiber_sleep()` or `schedule()` directly in this
extension's C++.** Route every yield through the guard. This is enforced
by `tests/host/test_vfp_guard_source_pin.py`.

**A yield can hide inside a call that looks synchronous.** Grepping for
`fiber_sleep` is not an audit. `uBit.serial.send(..., SYNC_SLEEP)`
blocks on `fiber_wait_for_event()` when the 255-byte TX ring fills —
reachable with 240-byte lines at 20 Hz telemetry — and was found only by
reading CODAL's `Serial.cpp`. Audited and cleared so far: `uBit.i2c`
(spin-waits only), `uBit.radio.datagram.send`, async serial read, and
`MessageBus::send` (queues only). Anything else needs reading before it
is trusted.

**A silent reset means a CPU fault, not a watchdog.** Reach for
`DIFFDRIVE_FAULT_SPIN` plus pyOCD early. Read CFSR/HFSR/BFAR and the
stacked frame at MSP, then `addr2line` the PC against the ELF that
matches the flashed hex — `.tmp/deploy-head/built/dockercodal/build/MICROBIT`,
not the stale repo-root copy.

**Register values in a fault frame are evidence, not noise.** `r0` and
`r1` here were exactly -25.0f and +25.0f. Recognising them as a pivot's
wheel speeds is what turned "corrupted pointer" into "corrupted by
*what*". Decode fault addresses as floats and as ASCII before calling
them garbage.

**Do not conflate this with a scheduling redesign.** Moving work to a
single executor fiber does *not* fix it: the surviving fiber still parks
pointers in the bank across its own yields, and any other float-running
context still clobbers them. The two are separate pieces of work.

**Do not fix it in vendored code.** The genuine upstream fix is CODAL
saving s16-s31 in `swap_context`, or building `-mfloat-abi=soft` /
`-ffixed-s16...s31`. `codal.json` carries preprocessor definitions only
and exposes no supported hook for compiler flags, so both routes mean
editing vendored files. Report it upstream; contain it locally.

**Flash gopiv with pyOCD, not DAPLink mass storage.** MSD timed out
mid-write twice on the farm node and left the board blank both times
(`FAIL.TXT`: "The transfer timed out"). `pyocd erase --mass` followed by
`pyocd flash -t nrf52833` recovered it cleanly.

**One claim to keep narrow.** Student TypeScript is *not* exposed: PXT's
Thumb backend emits zero `vpush`/`vldm` in the generated program, so
pure-TS `control.inBackground` code has nothing in the bank to lose. The
exposure is confined to C++ frames beneath a student's fiber.

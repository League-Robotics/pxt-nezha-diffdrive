---
status: in-progress
sprint: '026'
tickets:
- 026-001
- 026-002
- 026-003
---

# Fiber safety and command dispatch

## Description

Two defects with one origin: commands are executed on whatever fiber
happens to pick them up, and fibers are not safe to switch away from.

1. **`RUN:` programs that drive the motors hard-fault the board.**
   MEASURED gopiv 2026-09-01 with pyOCD and the `DIFFDRIVE_FAULT_SPIN`
   hook: `RUN:straight:20`, `RUN:pivot:90` and `RUN:square:20` fault
   3/3. Host-driven `MOVE_X` does not. Non-motion RUN verbs do not.
   This blocks every on-robot tour program and the five bench tools that
   drive through RUN verbs (`otos_levercal.py`, `pivot_truth.py`,
   `truth_check.py`, `rotation_check.py`, `turn_sweep.py`).

2. **RUN payloads are destroyed silently.** `runSlots_[4][48]` +
   `nextRunSlot_` (`src/comms/protocol.h:142-145`) is a write cursor
   with no read cursor, no occupancy and no overflow signal. A burst
   arriving during a long tour overwrites text a pending handler has not
   read yet — the exact failure the ring's own comment claims to
   prevent. The 3 s same-text dedupe (`protocol.cpp:222-229`) is a
   workaround for the missing occupancy, and it makes the same command
   twice inside 3 s *silently impossible* — which is the shape
   `tools/turn_sweep.py` sends.

3. **Three execution models coexist**: wire motion ticks on the protocol
   fiber (`protocol.cpp:434-441`), `RUN:` motion ticks on a forked
   MessageBus fiber, and student blocks tick on the calling fiber. Only
   the third is deliberate.

## Cause

**CODAL's fiber context switch saves R0–R12/SP/LR and no VFP
registers** (`codal-nrf52/asm/CortexContextSwitch.s` — `swap_context`,
`save_context`, `restore_register_context` contain zero VFP
instructions). The firmware is built `-mfpu=fpv4-sp-d16
-mfloat-abi=softfp`, so GCC 9.2.1 allocates the callee-saved bank
s16–s31 (= d8–d15) freely, **including as spill slots for pointers**.

Any fiber holding a value in that bank across a yield loses it if
another fiber runs code using those registers. Measured instance:
`Protocol::run()` parks `&radioTransport_` in s17 across its
`fiber_sleep(5)`; a RUN handler fiber's PID (`DifferentialDrive::drive`
does `vmov s16,r1` / `vmov s17,r2`) overwrites it; the protocol fiber
resumes, restores float −25.0f as `this`, and dereferences it. CFSR
0x8200 (BFARVALID|PRECISERR), BFAR = float bits + 0x1F3 = the offset of
`radioReady_`.

Victims are wider than the RUN path. From the flashed ELF, functions
that `vpush {d8...}` **and** yield within their extent:
`Protocol::run`, `OtosPort::read`, `OtosPort::setPose`,
`MotionEngine::settleToRest`.

CODAL is **non-preemptive** (`CodalFiber.h:28`) — context switches
happen only at explicit yields. That is the load-bearing fact: guarding
every yield in our own code is *sufficient*, not merely a mitigation.

## Proposed fix

Three steps, in order. Step 1 must land and be hardware-confirmed
before step 3 begins.

### 1. VFP yield guard — the crash fix

New `src/platform/vfp_guard.{h,cpp}`: `noinline` `vfpSafeSleep(ms)` /
`vfpSafeYield()` wrapping `fiber_sleep` / `schedule`, each followed by
`__asm__ volatile("" ::: "d8"…"d15")`, behind
`#if defined(__arm__) && defined(__ARM_FP)` (`__ARM_FP` alone is also
defined on arm64 macOS).

`noinline` is what creates the frame: the clobber marks the bank used,
so AAPCS forces `vpush.64 {d8-d15}` before the `bl` and
`vldm sp!, {d8-d15}` after, on the **calling fiber's own stack**. The
whole bank is saved, so it protects every ancestor frame at any depth on
that fiber. Coverage is monotonic — an unguarded fiber can lose its own
values but can never corrupt a guarded one.

Route every yield in our code through it:

| File | Note |
|---|---|
| `src/platform/platform_ports.h:22,25` | **Covers the vendored kernel transitively.** `DifferentialDrive::step` reaches the sleeper by true indirect virtual call (`blx r9`), so `src/core/diffdrive.cpp`'s two settle sleeps are guarded without editing it. Also covers all of `shims.cpp`, which already goes through `r.sleeper`. |
| `src/comms/protocol.cpp:153,437` | 437 is the measured crash victim |
| `src/comms/serial_transport.cpp:53` | retry sleep |
| `src/comms/serial_transport.cpp:64-65,70` | **A yield no grep for `fiber_sleep` finds**: `uBit.serial.send(…, SYNC_SLEEP)` blocks on `fiber_wait_for_event` when the TX ring fills — reachable with 240-byte lines at 20 Hz telemetry. Needs a file-local `noinline` wrapper carrying the same clobber. |
| `src/platform/nezha_port.cpp:201` | encoder probe settle |
| `src/platform/otos_port.cpp:11,109` | `busGap()` and the begin sleep |
| `pxt.json` `files[]` | both new files, or the manifest test fails |

Unchanged: `src/core/diffdrive.{h,cpp}` (vendored), `src/shims.cpp`,
`src/comms/radio_transport.cpp` (no yield in its call graph),
`src/motion/motion_engine.*`.

Cost ≈ 200 cycles per yield at ~350 yields/s ≈ **0.11 % CPU**, under
500 bytes of extra fiber stack.

### 1b. Guardrails — the part that makes the fix durable

**There is currently nothing in the repo about any of this.** A search
of `src/`, `tests/`, `docs/`, `tools/` and `.claude/` for VFP, FPU,
`d8-d15`, `s16`, or floats-across-fibers returns nothing but the issue
files. Every existing `fiber_sleep` mention in `src/DESIGN.md` is
descriptive, not cautionary. A guard that lives only in `.cpp` files
gets quietly undone by the first person who adds a sleep, so ship these
with it:

1. **`.claude/rules/fiber-yield-safety.md`**, scoped
   `paths: ["src/**/*.cpp", "src/**/*.h"]`. The highest-leverage item:
   it fires automatically for any agent editing firmware C++. States the
   rule (never call `fiber_sleep`/`schedule` directly; route through the
   guard), why (CODAL saves no VFP registers; the bank holds *pointers*,
   not just floats), and the non-obvious part — that a yield can hide
   inside a CODAL call that looks synchronous, with
   `uBit.serial.send(..., SYNC_SLEEP)` as the worked example.
2. **A system-invariant section in `src/DESIGN.md`**, alongside the
   existing I2C bus-discipline invariant, since that document is where
   this codebase records "things that are true of the whole system".
   `src/DESIGN.md` is not counted by the archaeology marker budget.
3. **The explanation at the point of use** in `vfp_guard.h` — what the
   clobber does, why `noinline` is load-bearing, and why the save lands
   on the calling fiber's stack.
4. **A teaching failure message** in `test_vfp_guard_source_pin.py`. When
   it fails in six months the message is the only context the reader
   gets; it must say why a bare `fiber_sleep` is dangerous, not just
   that one was found.

### 2. A real RUN queue

Header-only ring in `src/comms/run_queue.h` — `head`/`tail`/`count`
plus a `dropped` counter, 8 slots — following the precedent
`src/core/heading_wrap.h` and `src/core/encoder_glitch_armor.h` set for
extracting a host-portable core out of a CODAL-bound file. `handleRun()`
enqueues instead of overwriting; `dropped` is surfaced through the
existing `diagValue()` ordinal table so overflow becomes visible. The
dedupe window can then shrink or go away. Fibers and dispatch unchanged
in this step. Host-testable.

### 3. Single executor on the protocol fiber

**Do not make the executor drive the tour** — that forces every tour
into a state machine and destroys the explicit `startMove` +
`driveTick()` shape `test/test.ts:19-21` calls deliberate. **Invert the
pump**: the tour keeps its own tick loop, that loop runs on the
executor's fiber, and the tick services the wire.

- Split `Protocol::run()` into `serviceOnce()` (one non-blocking pass:
  serial read, radio read, telemetry if due) and a loop that calls it,
  dispatches a queued job, then ticks or sleeps.
- `dispatchJob()` invokes the TS dispatcher via `runAction0()` on this
  fiber. Mechanically supported: `runAction3` pushes a per-fiber
  `ThreadContext` and `gcProcessStacks` walks it.
- `tickDrive()` gains one service hook, fired **after
  `r.stepBusy = false` (`shims.cpp:670`) and before the pacing sleep** —
  never inside `stepBusy`, because `step()` already yields twice inside
  the encoder select→read window. A function-pointer hook on the `Rig`
  keeps new CODAL surface out of `shims.cpp` and is host-testable with
  the `FakeSleeper::onSleep` injection at `kernel_shim.cpp:265-287`.
- Replace `control.onEvent(RUN_EVENT_SOURCE, …)` (`run.ts:44`) with a
  `_registerRunDispatch(cb)` shim; `onRun`/`onRunCommand` keep their
  public shape. The 0x2001 event leaves the RUN path.
- **`RUN:abort` and `RUN:clearestop` must bypass the queue.** Abort
  works *by accident* today — MessageBus forks a second fiber, so it
  runs concurrently with the tour. Under one executor a queued abort
  would arrive after the tour it was meant to stop.
- Add `motionOwner_ ∈ {none, wire, job}` **in `Protocol`, not
  `WireAdapter`** (a wire `MOVE_X` mid-tour currently overwrites the
  tour's move with no error to either side). Keeping it out of
  `WireAdapter` is what lets the wire-verb tests stay valid.
- Raise `device_stack_size` to 4096 via `pxt.json`'s yotta `config`
  seam; the default is 2048.
- Leave `hasLiveMotionObligation()` **wire-only**. Extending it to RUN
  jobs would make a wire motion report `kStop` where `kTimeout` is
  correct. A RUN job needs no obligation — its own tick loop runs.

### Superseded

An earlier writeup proposed arming the motion obligation from
TypeScript so the protocol fiber ticks TS-issued moves. **That is
wrong.** `tourWorld()` reads the OTOS on the handler's fiber between
moves; moving the tick elsewhere puts those reads inside the encoder
select→read window that `src/DESIGN.md:639-642` declares a system
invariant. It trades an FPU hazard for an I2C hazard.

## Verification

**Codegen census — the completeness proof.** `arm-none-eabi-objdump` is
not installed on the dev machine; use `arm-none-eabi-gdb`. The ELF
matching the flashed hex is
`.tmp/deploy-head/built/dockercodal/build/MICROBIT` (the repo-root
`built/` copy is stale).

Disassemble `vfpSafeSleep`/`vfpSafeYield` and assert each has a `vpush`
naming all eight of d8–d15, a `vldm`/`vpop`, and a `bl` (a `b.w` means
the tail call survived and the guard is inert). Then disassemble
`.text`, grep for `fiber_sleep|codal8scheduleEv|fiber_wait_for_event`
filtered to `diffDrive|DiffDrive|Wire`: the baseline is **17 direct
yield calls across 13 of our symbols**; after the guard exactly
**three** may remain (the two wrappers and the serial-send wrapper).
Anything else is an unguarded yield.

**The census is necessary but not sufficient.** It finds *direct* calls
to the yield primitives inside our own symbols; it cannot see a yield
two frames deep inside a vendored call. That is exactly how
`uBit.serial.send(..., SYNC_SLEEP)` was found -- by reading CODAL, not by
grepping. Audited and cleared so far: I2C (`NRF52I2C` spin-waits only),
`uBit.radio.datagram.send`, async serial read, and `MessageBus::send`
(queues only). Prefer walking the call graph from each of our symbols to
any yield primitive over checking our own frames alone -- that turns "we
audited carefully" into something mechanical.

**Permanent test** `tests/host/test_vfp_guard_source_pin.py` — pure
text, no toolchain, following `test_wire_constants_drift.py`: no file
under `src/` except `vfp_guard.cpp` contains a bare `fiber_sleep(`,
bare `schedule()`, or `SYNC_SLEEP` outside the wrapper; the header names
all eight registers; both definitions carry `noinline`. This is what
catches a bare `fiber_sleep` added later.

**Hardware acceptance** (gopiv on farm node magni). Flash with pyOCD —
DAPLink mass storage times out mid-write on that host and blanks the
board; recover with `pyocd erase --mass`.

1. Baseline first, same session, same board: flash *current* firmware,
   `RUN:straight:20` ×3, confirm 3/3 resets. Without this the fixed run
   proves nothing.
2. Flash the fix; confirm `VER` changed.
3. **PASS = 0/10 `RUN:straight:20`, 0/10 `RUN:pivot:90`, 0/5
   `RUN:square:20`.** A second `device NEZHA2 …` banner on an
   established link *is* a reset — no probing needed.
4. Stress the race harder than the original repro: subscribe `TLM` so
   the protocol fiber is busy, and interleave `MOVE_X` during a
   `RUN:square:20`.
5. Re-test the radio-traffic wedge and the tigez wedge (identical CFSR
   0x8200, previously attributed to heap corruption) and **report either
   way**. If they clear, correct that attribution. If they persist they
   are separate faults — say so, and do not let the guard become their
   explanation.
6. If anything still faults, `#define DIFFDRIVE_FAULT_SPIN 1`
   (`nezha_port.cpp:77`) parks the chip for pyOCD instead of resetting.

Then re-run the `.tour` suite (`tests/system/run_tour.py`) for the
host-driven path, and `uv run pytest` throughout.

## Traps

- **`test_archaeology_marker_budget.py` is at 388/388 with zero slack.**
  Any new comment line naming a sprint, a ticket, an `R-NN`-style code,
  or any `*.md` filename fails the build. Describe mechanisms in the new
  files; put issue references in the commit message.
- `test_pxt_manifest_completeness.py` checks `pxt.json` both directions.
- Do not add `vfp_guard.cpp` to `_CXX11_PORTABLE_SOURCES` — it includes
  `pxt.h`. The build is `-std=c++11`.
- `test_include_paths_match_target.py`: includes resolve relative to the
  including file.
- `test_wire_constants_drift.py` becomes meaningless at step 3 (it pins
  the 0x2001 literal pair); delete it with the code.
- `test_run_abort_source_pin.py` must be rewritten at step 3 — the pin
  moves from "an abort handler exists" to "abort bypasses the queue".
- A RUN handler may block only through `driveTick()`.
  `basic.showNumber` scrolls ~1 s per digit and would make the executor
  deaf; use `showIcon`/`plot`/`emitLine`.
- Waiting paths must poll `moving()` (`shims.cpp:788`), never
  `isMoving()`/`_updateMove()`, which runs `serviceMove()`'s float math
  on the waiting fiber.
- Build with `--robot gopiv` explicitly (`DEFAULT_ROBOT` is vevov).

## Related

- `run-fiber-motion-resets-the-board-on-fw-1-20260829-1.md` — the
  root-cause forensics this issue acts on. Its "stop running motion on a
  second fiber" recommendation is superseded (see above), and its claim
  that student `control.inBackground` code is exposed should be narrowed:
  PXT's TypeScript codegen emits zero `vpush`/`vldm`, so pure-TS student
  code has nothing in the bank to lose.
- `fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md` — identical
  CFSR 0x8200; may be the same fault. Re-test after step 1.
- `cleartext-run-hangs-the-link-under-active-telemetry.md` — step 3
  removes two of its three suspected causes structurally (one serial
  writer; RX drained every ~24 ms during a tour).
- `ensure-is-not-reentrant-two-rigs-can-be-constructed.md` — independent
  of this work; not fixed by it.

**Upstream:** enabling the FPU without saving s16–s31 across fibers is a
CODAL defect, not ours. The guard is containment for our own code; the
real fix (`swap_context` saving the bank, or `-ffixed-s16…s31`) belongs
upstream and should be filed there.

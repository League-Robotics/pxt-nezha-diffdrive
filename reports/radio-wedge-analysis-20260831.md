# Radio-during-motion wedge: what actually changed, and where the bug is

Written 2026-08-31 by the team-lead session, from a read of the "Vav to
Tygez swap" session transcript (`101bc174-61d3-4a1f-9484-e6f0a191f653`),
the working tree it left behind, and the vendored CODAL sources. Every
measured claim below cites the artifact that backs it; claims from my own
source reading are marked as such.

## TL;DR

- The wedge is **not** the encoder/I2C lockup family, and it is **not** a
  bug in the day's diffs. It is a **HardFault from heap corruption**: a
  radio receive buffer gets allocated *on top of the live Rig*, and the
  packet text ("PING", "MOVE") lands on a `NezhaMotorPort` vtable
  pointer. Proven with pyOCD fault registers, disassembly, and a hardware
  watchpoint (`captures/tigez-cal-20260830/notes.md`, "ROOT CAUSE" section).
- **Every semantic change in yesterday's window was individually falsified
  on hardware** the same night (see table below). What the day's changes
  actually did was reshuffle the binary's heap layout so a *latent*,
  layout-dependent corruption now lands on the motor port every time.
  v0.20260829.3 carries the same bug and survives by placement luck — the
  issue file (`clasi/issues/fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`)
  already records this retraction.
- The session's current direction — patching vendored
  `MicroBitRadio.cpp` — treats the *messenger*. CODAL's allocator is
  IRQ-masked (source reading, below), CODAL has allocated in its radio IRQ
  on every micro:bit for years, and the agent's own IRQ-masking
  experiments failed to stop the fault. The free list is almost certainly
  **already corrupt** by the time `queueRxBuf()` allocates. The open
  question is *what corrupts it* — and that writer is in our firmware,
  not CODAL.

## The critical question: it worked last night — what changed?

Last known-good radio driving: vevov square tours on fw 0.20260829.2
(2026-08-29, `captures/` baselines; memory note
`vevov-square-tour-baseline-20260829`). Fleet reflashed to 1.20260829.1 on
2026-08-30. The full window is `v0.20260829.3..master`:

| commit | what it changed on the board | verdict |
|---|---|---|
| 6d39109, 494fefa | docs/rules only | inert |
| 5b5a73b | version string from config (`pxt.json` version only) | inert semantically; **does** shift binary layout |
| ab796aa + 0039e3f (merge) | the real firmware delta, below | every piece falsified individually |
| 88b4c77 | `tools/make_deploy.py` injects `kGroup` per-robot alongside `kChannel` | build tooling; injection verified baked correctly (55/114 for tigez) |
| b2305e8 | HardFault fail-safe | landed *after* the failure started; a response, not a cause |

The firmware-visible delta inside ab796aa/0039e3f, line by line:

1. **Radio became opt-in and late.** `Protocol::setRadioGroup()` →
   `setupRadio(channel, group)` + `enableRadio()`, gated by a new
   `radioEnabled_ = false` member ([protocol.cpp](../src/comms/protocol.cpp)).
   The on-board program now calls `diffDrive.enableRadioLink()` at its top
   ([test/test.ts:49](../test/test.ts#L49)); measured effect: radio comes up
   once motion is already running instead of on the first loop pass.
2. **On-board name→address derivation deleted** (~100 lines,
   `deriveRadioAddress`/`selectRadioGroup` out of
   [radio_transport.h](../src/comms/radio_transport.h)); channel/group are
   now injected compile-time constants (`kChannel`/`kGroup`, defaults 4/10)
   plus a `setChannel()` runtime path.
3. Toolbox weights in `src/blocks/*.ts` — annotations only, inert.

**Each candidate was A/B-tested on tigez that night and each failed to
explain the death** (transcript 2026-08-30 21:05–23:11; recorded in the
issue file's "earlier attribution RETRACTED" section):

- master with the one-line change `radioEnabled_ = true` — gates become
  no-ops, `Protocol::run()` behaviorally identical to the good build —
  **still died on the first move**;
- eager radio bring-up on master — still died;
- 4 KB fiber stacks — still died;
- deferring datagram RX out of the event context — deferral provably
  fired, still died;
- settle delay after radio TX — still died;
- `microbit_radio_max_packet_size` reverted — still died (and the
  250-byte setting predates the window anyway: a5711dd, 2026-08-20).

Meanwhile v0.20260829.3 survived ~10 move-cycles under the same radio
hammering, 100% vs 0%. Two builds with (tested-)identical semantics and
opposite, fully deterministic outcomes is the signature of a
**layout-dependent memory-corruption bug**, not of a logic regression in
the diff. The heap allocator is deterministic first-fit; each binary aims
the corruption at a fixed victim; yesterday's binaries aimed it at
something harmless, today's aims it at the motor port vtable.

So the honest answer to "what changed?": **the reflash changed the
binary's memory layout, and the layout is the trigger. The bug itself is
older than the window and is still unidentified.** The same reasoning
says the *next* innocent rebuild could bring it back on any board — which
is why "roll back and move on" is not closure.

## What is proven, with artifacts

Chain of evidence in `captures/tigez-cal-20260830/notes.md` ("ROOT CAUSE,
named by hardware watchpoint") and the session scratchpad scripts
(`catch2.py`):

1. The board doesn't hang — it **hard-faults**: IPSR=3, HFSR FORCED,
   CFSR=PRECISERR|BFARVALID, BFAR=0x474E4988 (= "ING"+0x38 — ASCII).
2. Faulting site: virtual call in `DifferentialDrive::controlStep` —
   `this->right_->vptr` had been overwritten with 0x474E4950 = **"PING"**
   (a later capture read "MOVE" — whatever packet was in flight).
3. Hardware watchpoint on that vtable word caught the writer: the
   zero-fill of `new FrameBuffer()` inside
   `codal::MicroBitRadio::queueRxBuf()` — i.e. **the allocator returned a
   block overlapping the live Rig**.
4. The runaway wheels were the weak default `HardFault_Handler` (infinite
   loop, `gcc_startup_nrf52833.S`) with the last motor command latched in
   the brick. Fixed by b2305e8: emergency motor stop + `NVIC_SystemReset()`.
   MEASURED: 8/8 faults auto-recovered, ~1 s reboot.

## Why the vendor-patch direction is wrong

- **CODAL's heap is IRQ-safe by design.** `device_malloc_in`/`device_free`
  wrap every free-list walk in `target_disable_irq()` /
  `target_enable_irq()` (source reading:
  `built/dockercodal/libraries/codal-core/source/core/CodalHeapAllocator.cpp`,
  ~lines 208–272). An IRQ-time `new FrameBuffer()` cannot interleave with
  a fiber-side malloc/free. The stock radio driver has allocated in its
  IRQ on every micro:bit in the world; the code did not change — our
  binary did.
- **The agent's own data refutes the reentrancy theory.** Masking IRQs
  across the entire datagram receive+free (uncommitted guard in
  [radio_transport.cpp](../src/comms/radio_transport.cpp)) and across
  `new Rig()` (uncommitted guard in [shims.cpp](../src/shims.cpp)) did not
  stop the fault — the "MOVE" capture happened *with* the guard in place.
  If IRQ-vs-fiber allocator interleaving were the mechanism, those masks
  would have closed it.
- **The uncommitted guard is broken as coded anyway** (source reading):
  it uses raw `__disable_irq()`/`__enable_irq()`, but CODAL's
  `target_enable_irq()` is counter-based
  (`codal-nrf52/source/codal_target_hal_base.cpp:21`) with the counter at
  0 during normal running — so the *first* inner malloc/free (the
  `PacketBuffer` ctor/dtor) ends with counter 1→0 and **re-enables
  interrupts inside the guarded section**, before `~PacketBuffer()` runs.
  The guard's own comment claims a property the code doesn't have.
- Therefore: by the time `queueRxBuf()` allocates, the free list is
  already corrupt. A spare-buffer patch in the vendored driver relocates
  the victim; it cannot fix the corrupter. It also has to fight
  `checkgit()` (which rejects a dirty library checkout) and lives in a
  build cache that gets re-provisioned — the patch was already silently
  absent from one "fixed" build during the session.

## Where the real bug likely is — the hunt

For first-fit malloc to hand out memory inside a live allocation, a block
header (size / free bit) must already be wrong. Classic causes, in order
of suspicion here:

1. **A neighbor overflowing its heap block** — writes past the end of an
   allocation trample the next block's header; a later defrag/merge then
   swallows live memory. Radio-path buffers are the prime suspects
   because the failure needs radio traffic: audit every buffer the v6
   radio path touches against the **250-byte** payload
   (`microbit_radio_max_packet_size: 250`, pxt.json — set 2026-08-20;
   anything still assuming 32 overflows by 218). `appendByte` was audited
   clean; `sendFragmented`, the ack builder, and `rxLine_` sizing have not
   had the same treatment.
2. **A fiber stack overflow** — CODAL fiber stacks are heap blocks; the
   protocol fiber runs radio TX/RX + telemetry + `tickDrive()` with
   multi-hundred-byte locals. The 4 KB test was weak evidence (it also
   moves layout). Paint-and-check canaries decide it.
3. **Double-free / use-after-free in the FrameBuffer/PacketBuffer
   lifecycle** — verify against the *stock* vendored source.

Decisive instruments (all proven available on this rig):

- **Watchpoint the Rig's block header** (the word at `rig - 4`), not the
  vtable. The vtable watchpoint caught the overlap-memset — the header
  watchpoint catches the original corrupter red-handed. `catch2.py` in the
  session scratchpad needs a one-line change of address.
- **Heap-walk assert**: CODAL ships a heap validator/printer under
  `CODAL_DEBUG >= CODAL_DEBUG_HEAP`; alternatively a ~20-line walker
  called once per protocol loop turns "fault eventually" into "walk fails
  at cycle N", timestamping the corruption long before the fault.
- The A/B pair of builds (good .3 / bad master) already exists in the
  session worktrees (`wt-0829-3`, `wt-dbg`) — compare *heap layouts* (nm
  order, boot allocation trace), since layout, not semantics, is the
  discriminator.

## Addendum (2026-08-31 early AM): second static sweep — what else is now ruled out

A follow-up sweep (this session, source + ELF disassembly of the master
build in `.tmp/deploy-head`) eliminated the remaining cheap theories:

- **The 32-vs-250 packet split-brain: refuted by the binary.** Both
  `queueRxBuf()` and `enable()` pass 264 (= sizeof(FrameBuffer) at
  payload 250) to `operator new`; `.text` contains exactly one
  `PCNF1 = 0x020400FA` (MAXLEN=250) and zero `0x02040020` (MAXLEN=32).
  `codal_extra_definitions.h` carries 250 into every TU. No pxt `radio`
  package is compiled in. A maximal DMA write (251 bytes) cannot even
  reach the FrameBuffer's own `next` field (offset 256).
- **Allocator reentrancy: now ruled out at every layer.** `_Znwj`
  (operator new) calls `device_malloc` directly; `malloc` is only a weak
  alias of `device_malloc` — pxt's `GC_GET_HEAP_SIZE` malloc override is
  NOT in this build, so there is ONE heap and every malloc/free critical
  section is IRQ-masked (`CodalHeapAllocator.cpp`).
- **Our firmware writes are bounded, and it never frees.** Every
  `memcpy`/`snprintf` in `src/comms` and `src/platform` checks or
  truncates against its buffer (`rxLine_`, `frameBuf_[256]`,
  `payloadBuf_`, RUN slots, ack/pong/id builders); grep finds no
  `delete`/`free` in our source at all.
- **Stock CODAL radio queue discipline reads coherent** under CODAL's
  cooperative scheduler: the driver queue's fiber-side pop is
  NVIC-guarded; the datagram queue is touched only from fiber context
  (`idleCallback()` appends, the MessageBus handler pops), and neither
  critical section yields.

**Important correction to the evidence base:** the failed
`__disable_irq()` guard experiments must NOT be read as exonerating
IRQ-vs-fiber races. The guard self-unmasks at the first inner
malloc/free (CODAL's counter-based `target_enable_irq()` clears PRIMASK
it didn't set — `codal_target_hal_base.cpp:21`), so those runs tested
nothing. The races are exonerated by the source reading above instead.

Two incidental defects found (worth fixing, neither proven to be the
corrupter):

1. `ensure()` (`src/shims.cpp:188`) is not re-entrant: `rig` is assigned
   only after `new Rig()` returns, so if anything in the Rig
   construction path yields (the boot priming `fiber_sleep(4)`,
   `nezha_port.cpp:201`, if ctor-reachable), a concurrent shim call from
   the other transport's fiber constructs a SECOND Rig — leaked
   half-built object plus doubled I2C init.
2. `rxLineBuf_[64]` (`src/comms/protocol.h:269`) silently truncates any
   inbound radio line over 64 bytes even though the transport accepts
   up to ~247 — a correctness trap for long `SET`/`TLM` commands, not a
   memory-safety one.

Also confirmed why radio+motion is the trigger shape:
`src/core/diffdrive.cpp:497,501` — the control step yields
(`sleepMillis(4)`) between encoder select and read, twice per tick, so
during motion the entire radio path (queue dispatch, PacketBuffer
alloc/free, the 264-byte stack FrameBuffer in `datagram.send()`, the
busy-wait TX) runs NESTED inside the motor tick's settle windows. At
idle it runs standalone — a different interleave and a different heap
churn pattern.

**Where this leaves the hunt:** static analysis is exhausted; every
readable mechanism is either bounded, masked, or cooperative-safe, yet
the overlap is real and deterministic. What remains is not reachable by
reading: the DMA/PACKETPTR lifecycle under the exact TX/RX overlap of
an ack-during-motion, the fiber stack paging machinery
(`verify_stack_size` realloc on context switch), or a wild write that
only that interleave exposes. The decisive experiment is unchanged and
is now the ONLY next step worth hardware time: **watchpoint the Rig's
heap-block header** (the word at `rig - 4`; adapt `catch2.py`:
breakpoint after `ensure()`, read `rig`, watch `rig-4` for 4-byte
writes, run the radio kill-test) — it catches the original corrupter,
not the later overlap-memset. Prerequisite: revert the `#if 1`
fault-spin in `nezha_port.cpp` or build a coherent `DIFFDRIVE_FAULT_SPIN`
forensic hex so the on-board firmware matches the ELF being symbolized.

## Superseding update (2026-08-31 ~03:07): the kill is localized to protocol.{cpp,h}

The tigez session's clean-room bisect matrix (fresh worktrees, no
shared build caches, judged by full square tours on the same bench in
the same hour — its results table is in that session and in the issue
file) supersedes the pure "layout luck" conclusion above:

| build | square tour |
|---|---|
| v0.20260829.3 | 6/8 clean, zero faults (2 = ordinary radio loss) |
| master | dead on move one, every time |
| .3 + master's radio_transport only | survives — transport innocent |
| .3 + master's protocol.{cpp,h} | dead on move one |
| …with the old export surface restored | dead |
| …with the bool moved out of the class (layout identical to .3) | dead |

So the trigger IS carried by master's `src/comms/protocol.{cpp,h}` —
swapping just that pair into an otherwise-.3 build reproduces the death
— while the gates-forced-true test, the export surface, and the member
layout of `radioEnabled_` are each individually exonerated. The causal
lines are inside an "astonishingly small" remaining delta in that pair,
still being enumerated. The corruption MECHANISM (heap overlap onto the
Rig, watchpoint-proven) stands unchanged; what changed is that the
aiming is done by something in protocol.{cpp,h}, not by diffuse binary
layout. The working-tree hazards below were also cleared by that
session at ~03:06 (tree reset to exactly b2305e8; vendored library
reset to f5d1682).

## Hazards sitting in the working tree right now (cleared ~03:06, kept for the record)

- [nezha_port.cpp:77](../src/platform/nezha_port.cpp#L77) has
  `#if 1  // TEMP: DIFFDRIVE_FAULT_SPIN` — **any hex built from this tree
  parks in the fault handler instead of auto-recovering** (motors stopped,
  but the board stays down). Revert before building anything for a robot.
- tigez was last flashed (~02:15) with a forensic build (fault-spin +
  shims IRQ mask). Reflash from a clean tree before driving it.
- Uncommitted, measured-ineffective experiment code in
  `src/comms/radio_transport.cpp` and `src/shims.cpp` (see the guard
  defect above). Either drop them or re-land them as documented
  experiments — as written, their comments over-claim.
- The vendored-CODAL "LEAGUE PATCH" did **not** survive in
  `built/dockercodal/libraries/codal-microbit-v2` (stock file restored;
  the original is parked in the session scratchpad as
  `MicroBitRadio.cpp.orig`). Copies may exist in `.tmp/deploy-head`.
- `config/devices.json`, `tools/make_deploy.py`,
  `tests/tools/test_make_deploy_robot_channel.py` also carry uncommitted
  changes from the session — review before the next commit sweeps them in.

## File map for review

| file | why |
|---|---|
| `clasi/issues/fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md` | the issue, incl. the formally retracted bisect |
| `captures/tigez-cal-20260830/notes.md` | the full measured chain: markers, fault registers, watchpoint, fail-safe verification |
| `src/comms/radio_transport.cpp` / `.h` | uncommitted IRQ guard; window delta (injection constants, `setChannel`); rxLine/ack buffer audit target |
| `src/comms/protocol.cpp` / `.h` | `radioEnabled_` gates, radio bring-up ordering (falsified suspects, but the bring-up timing is where layout shifts) |
| `src/shims.cpp` (~`ensure()`, line 187) | Rig allocation — the corruption victim; uncommitted NVIC mask |
| `src/platform/nezha_port.cpp` / `.h` | committed fail-safe (keep) + the TEMP `#if 1` (revert) |
| `test/test.ts` (top) | `enableRadioLink()` opt-in — the one program-level change in the window |
| `built/dockercodal/libraries/codal-core/source/core/CodalHeapAllocator.cpp` | read-only: the IRQ-masked allocator that undermines the reentrancy theory |
| `built/dockercodal/libraries/codal-microbit-v2/source/MicroBitRadio.cpp` | read-only: stock `queueRxBuf()` — the messenger, not the culprit |
| session scratchpad `/private/tmp/claude-501/…/101bc174…/scratchpad/` | `catch2.py`, `patch_radio.py`, A/B worktrees, `MicroBitRadio.cpp.orig` |

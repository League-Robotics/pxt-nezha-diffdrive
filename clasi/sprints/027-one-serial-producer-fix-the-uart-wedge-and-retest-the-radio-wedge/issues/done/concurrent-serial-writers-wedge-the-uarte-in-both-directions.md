---
status: done
sprint: '027'
tickets:
- 027-001
---

# Two fibers writing the serial port wedge the nRF52 UARTE in both directions, permanently and without a fault

Priority: **High** — it is the confirmed root cause of
`cleartext-run-hangs-the-link-under-active-telemetry.md`, which has sat with an
unconfirmed mechanism since 2026-08-26. It kills the link on the **first**
`RUN:` command with a non-empty payload, needs no telemetry and no motion, and
never recovers. Sprint 026 ticket 003 (single executor on the protocol fiber)
already fixes it, and this issue supplies the hardware proof for that ticket.

Found 2026-09-02 on **tigez** (micro:bit V2, serial 3527777815), fw
`1.20260829.1`, codal-microbit-v2 `v0.3.5`, codal-nrf52 `1fbb7240`, over USB
serial with pyOCD on the SWD port.

## This is NOT the VFP fault

`fiber-safety-and-command-dispatch.md` root-causes a hard fault: CFSR 0x8200,
BFARVALID|PRECISERR, board resets, motion RUN verbs only, and it explicitly
records that **non-motion RUN verbs do not fault**. This defect is the
opposite signature on every axis:

| | VFP fault (026) | this defect |
|---|---|---|
| fault | CFSR 0x8200, hard fault | **none** — `IPSR = 0`, no fault, no panic |
| board | resets | **keeps running normally** |
| motion needed | yes | **no** — `RUN:z`, an unbound name, is enough |
| recovery | reboot | never self-recovers; a bare debugger halt/go fixes it |

They are two different bugs that both live on the `RUN:` path. Fixing the VFP
guard will not fix this.

## What happens

Send one cleartext `RUN:` line with a non-empty payload. **The UART stops, in
both directions, for the rest of the boot.** No reply to the command, no reply
to anything sent afterwards, and nothing the robot emits ever arrives.

Everything else keeps working. The scheduler is healthy, fibers keep cycling,
and **pressing button A still drives the robot** — student code and motors are
completely unaffected. Only the wire is gone. That is why this reads as "the
program hung" when nothing has hung at all.

## Measurements

All taken on the wedged board. `P = read32(0x200018c4)` is the `Protocol`
singleton; `uBit.serial` is at `0x20000b80`.

**The receiver is dead.** 17 bytes (`AAAAAAAAAAAAAAAA\n`) sent into the wedged
board, 2 s wait, then halt and read:

```
rxBuffSize = 0xFF    rxBuffHead = 0    rxBuffTail = 0     <- ring EMPTY, bytes never arrived
```

**The transmitter is idle, not stalled.**

```
txBuffHead = 56   txBuffTail = 56     <- head == tail, TX ring EMPTY
is_tx_in_progress_ = 0                <- not stuck
```

**No UART error, interrupts still enabled.** UARTE0 @ `0x40002000`:

```
ERRORSRC (0x480) = 0                  <- no framing / parity / overrun
INTEN    (0x300) = 0x004A0314         <- RXDRDY|ENDRX|ENDTX|ERROR|RXTO|RXSTARTED|TXSTOPPED
```

**The CPU and scheduler are fine.** `runQueue` empty, `waitQueue` empty, three
fibers, and the two on `sleepQueue` keep advancing their wake times with the
wall clock (12004 → 22680 → 33448 ms across my waits). `MessageBus`
`queueLength = 0`. The RUN listener is present and healthy: `id=0x2001`,
`flags=0x0011` (PARAMETERISED|QUEUE_IF_BUSY), no BUSY bit, empty private queue.

**It never self-recovers, and a bare halt/go always fixes it.** Probed with
`HELLO` eight times over 53 s — dead every time. Then:

```
pyocd cmd -c "halt" -c "go"     <- no reads, nothing else
HELLO -> device NEZHA2 robot tigez 3527777815    RECOVERED
```

A debug halt/resume restoring a peripheral that software cannot see or leave is
the signature of the UARTE being left in a state no code path exits.

## This rules out hypothesis 1 of the existing issue

`cleartext-run-hangs-the-link-under-active-telemetry.md` proposes measuring
`probe(26)` / `diagValue(26)` — the `SerialTransport::writeLine` drop counter —
as the cheap first test, on the theory that the RUN handler's `emitLine()` and
the protocol fiber's telemetry exhaust the retry cap.

**Measured directly, and it is not that:**

```
transport_.sending_   (P+0x4F8) = 0     <- guard not stuck
transport_.dropCount_ (P+0x4FC) = 0     <- writeLine has NEVER dropped a line
```

`writeLine` reports success every time. The bytes are accepted by the driver and
then never leave the chip. Hypothesis 2 (RX ring overflow) is also out — the RX
ring is *empty*, not overfull. Hypothesis 3 (fiber starvation) is out — the
fibers are demonstrably cycling.

## The trigger, bisected

Reset before each probe, then send `<probe>`, then `HELLO`:

```
RUNX       -> SURVIVES    prefix does not match; goes to wireHandler_
ZZZZ       -> SURVIVES    arbitrary junk; goes to wireHandler_
RUN:       -> SURVIVES    prefix matches, dataLen == 0
RUN:z      -> WEDGES      prefix matches, dataLen == 1
RUN:ping   -> WEDGES
```

`RUN:` surviving is the load-bearing case. `handleRun()` opens with
`if (data == nullptr || dataLen == 0) return;`, so an empty payload proves the
call happens and returns cleanly — and, critically, returns **before raising the
MessageBus event**. One payload byte is the whole difference, and what that byte
buys is a *second fiber*.

`RUN:z` also wedges with **no handler bound to that name**, so nothing in
TypeScript needs to run. Merely dispatching the event is sufficient.

## Cause

The first `RUN:` with a payload is the only moment this firmware has **two
fibers writing the serial port concurrently**: `Protocol::run` on the protocol
fiber, and the MessageBus handler fiber the RUN event spawns. That is the race
window, and it is why an empty payload is safe.

The nRF52 UARTE is **one peripheral for both directions**, and codal's
`NRF52Serial` drives it unsafely from a producer context:

```cpp
// NRF52Serial::enableInterrupt — the ONLY producer-side kick
} else if (t == TxInterrupt) {
    if (!is_tx_in_progress_ && txBufferedSize()) { ... putc(...); }
}
return DEVICE_OK;          // returns OK even when it did nothing

// NRF52Serial::putc
while (!target_get_irq_disabled() && is_tx_in_progress_);  // spin, IRQs ON
if (target_get_irq_disabled()) { clear ENDTX; clear TXSTOPPED; }
is_tx_in_progress_ = true;                                 // check-and-set NOT atomic
nrf_uarte_tx_buffer_set(p_uarte_, (const uint8_t*)&c, 1);   // EasyDMA -> a STACK LOCAL
nrf_uarte_task_trigger(p_uarte_, NRF_UARTE_TASK_STARTTX);
```

`putc()` is reachable both from the UARTE ISR (via `dataTransmitted()`) and from
any producer fiber (via `enableInterrupt`). The spin and the `= true` are
separated by a call, so two `STARTTX` triggers can be issued against one
in-flight transfer, and `putc()`'s unconditional `ENDTX` clear can consume the
completion event the ISR needed. Note also that
`NRF52Serial::disableInterrupt(TxInterrupt)` is a deliberate no-op on this port,
so `Serial::setTxInterrupt()`'s enable/disable pairing is illusory.

The observable end state — TX ring drained, RX ring empty, `ERRORSRC` clear,
`is_tx_in_progress_` back to 0, nothing blocked, only a debugger resume
recovering it — is consistent with the shared peripheral being left in a state
the driver has no path out of.

**Why local builds and not cloud builds.** This is a timing race, so it flips on
instruction scheduling. Firmware built with the local `yotta-compiler` Docker
image hits it on the first `RUN:` every time; the same source built through the
MakeCode cloud compile service does not, because its native runtime is ~8 KB
smaller and shifts the phase of the RUN line's arrival. **The cloud build has
the identical latent bug and simply never lands in the window** — it should not
be treated as unaffected.

## Fix — and it is sprint 026 ticket 003

Make the protocol fiber the **single producer**. `Protocol::emitLine` stops
touching a transport: it clips the line, copies it into a `Protocol`-owned ring,
and returns. `Protocol::run` calls a new `drainEmitQueue()` at the top of its
loop, which calls the old emit body (now private, `emitLineNow`) — serial write
plus radio mirror. `uBit.serial.send` then has exactly one caller by
construction, and so does `RadioTransport::sendLine`.

**Verified on hardware.** With that change, on the same board and the same local
toolchain that reproduced the wedge 100% of the time:

```
RUN:z    -> run rx name=z arg=0        HELLO afterwards -> banner
RUN:ping -> pong heading=46            RUN:spin:10 -> act spin done heading=11
soak: 10 alternating commands, 15 reply lines, 0 reboots, port alive at end
```

This is the same structural change ticket 003 already proposes, so the ticket
should land as designed — this issue supplies the measured justification and a
second, independent reason it is necessary.

Notes for whoever implements it:

- **Ordering is preserved exactly**, including relative to the protocol fiber's
  own replies and telemetry, because there is now one drainer. Latency grows by
  at most one loop pass (`kPollIntervalMs`, 5 ms).
- **Loss becomes possible but bounded and countable**: a line is dropped only if
  the ring is full when `emitLine` is called. The old code could not drop *here*
  — but it could wedge the port permanently and lose everything after, which is
  the worse failure. Expose the drop count.
- `serial_transport.cpp`'s `SYNC_SLEEP` lost-wakeup in codal's
  `Serial::setTxInterrupt`, and the fact that `sending_` is a plain bool rather
  than a `FiberLock` and is not self-healing, are **real defects found along the
  way but are not this bug**. Worth fixing on their own merits; do not ship them
  as the fix for this.

## Limit of the fix — needs a docs line

This covers `diffDrive.emitLine` only. PXT's own `serial.writeLine` /
`serial.writeString` goes straight to `uBit.serial` from whatever fiber calls
it, and this extension cannot lock that from the inside. **Student code calling
`serial.writeLine` inside an event handler can still reach the race.** That
should be stated in the extension's docs: *on this robot, use
`diffDrive.emitLine`, not `serial.writeLine`.* A complete fix needs
pxt-microbit's serial shim to route through the same queue, which is out of this
extension's reach.

## Upstream — worth filing with Lancaster

> **NRF52Serial: concurrent producers can wedge the UARTE in both directions.**
> `Serial::setTxInterrupt()` queues bytes and then calls
> `enableInterrupt(TxInterrupt)` as the only producer-side kick; on nRF52 that
> path gates on `if (!is_tx_in_progress_ && txBufferedSize())` and calls
> `putc()`. `putc()` spins on `is_tx_in_progress_` with interrupts enabled, sets
> it non-atomically, points EasyDMA at `&c` — a stack local of `putc` itself,
> dead the moment it returns — and triggers `STARTTX`. Because
> `enableInterrupt()` is callable from any fiber while the UARTE IRQ handler
> independently calls `dataTransmitted()` → `putc()`, two `STARTTX` triggers can
> be issued against one in-flight transfer, and `putc()`'s unconditional
> `nrf_uarte_event_clear(ENDTX)` can consume the completion event the ISR
> needed. Observed on a micro:bit V2 (codal-microbit-v2 v0.3.5, codal-nrf52
> `1fbb7240`) with two fibers writing the port: the UARTE stops **both**
> transmitting and receiving — TX ring empties normally, RX ring stays empty
> across 17 bytes physically delivered, `ERRORSRC` is 0, `INTEN` still has
> RXDRDY/ENDRX/ENDTX/ERROR/RXTO/RXSTARTED/TXSTOPPED enabled,
> `is_tx_in_progress_` reads 0, no fiber is blocked and the scheduler is
> healthy. It never self-recovers (53 s, 8 probes); a bare debugger `halt`/`go`
> with no other access restores it every time. Suggested fixes: make the
> `is_tx_in_progress_` check-and-set atomic under `target_disable_irq()`, DMA
> from a member buffer rather than a `putc()` stack local, and have
> `enableInterrupt(TxInterrupt)` latch a pending kick instead of silently
> returning `DEVICE_OK` when the flag is set. Note also that
> `NRF52Serial::disableInterrupt(TxInterrupt)` is a deliberate no-op, so
> `Serial::setTxInterrupt()`'s enable/disable pairing is illusory on this port.

## Closes

`cleartext-run-hangs-the-link-under-active-telemetry.md` — same defect. That
issue observed it only with telemetry streaming because telemetry guarantees a
second concurrent writer; it does not actually require telemetry, only a second
fiber. Its "Suspected mechanism, not yet confirmed" section can be replaced by
this one, and its hypotheses 1–3 are each ruled out above by direct measurement.

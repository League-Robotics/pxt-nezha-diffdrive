---
status: pending
sprint: '010'
---

# Unpowered Nezha brick wedges the whole program at first I2C touch

## Description

Bench-measured on vevov (2026-08-19): when the Nezha brick is
unpowered (battery off/dead) or otherwise unreachable on I2C, the
first I2C transaction — `kernel.begin()`'s encoder priming inside the
lazy `ensure()` on first block/TLM use — never returns. codal's
NRF52 I2C driver busy-spins on the wedged bus, which freezes the
entire cooperative fiber scheduler: the boot banner is the last serial
output (it precedes the first I2C touch), no TLM is ever emitted, PING
goes unanswered, and button handlers are dead. Externally this looks
like a total firmware hang; the DAPLink debug side stays alive.

Expected behavior: an unreachable brick should degrade gracefully —
`connected=false`, `i2cFaultCount` climbing, protocol/TLM/DIAG alive so
the failure is observable, blocks no-op instead of hanging.

Possible directions (needs investigation): codal I2C timeout options;
pre-flight bus probe with timeout before `begin()`'s priming reads;
guarding the priming path so a dead bus marks the wheel disconnected
instead of blocking. Note the constraint that the kernel's own
step()/tick() I2C also runs every 24 ms — a fix has to cover the
steady-state path, not only boot priming.

Diagnosis session context: DIAG verb (protocol) now exposes
conn/i2cf/stall/estop/lastError, which is how this was isolated.

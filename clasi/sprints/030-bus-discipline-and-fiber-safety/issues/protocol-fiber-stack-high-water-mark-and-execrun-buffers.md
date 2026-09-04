---
status: in-progress
sprint: '030'
tickets:
- 030-005
---

# Measure the protocol fiber's stack high-water mark under a tour; move execRun buffers below its early returns

Priority: **Low** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: RC-04 ([motion-and-kernel](../../../docs/code-review/2026-09-02/raw/motion-and-kernel.md)), CM-09 ([comms](../../../docs/code-review/2026-09-02/raw/comms.md)). Triage #17. UNVERIFIED.

## Description

Since sprint 028 the protocol fiber hosts the whole TS job call chain:
`run()` -> `serviceOnce()` -> `dispatchJob()` -> `runAction0()` -> handler ->
`tickDrive()` -> hook -> `serviceOnce()` -> `drainEmitQueue()` (241-byte
local) -> `emitLineNow()` -> `sendLine()`, and `execRun()` commits ~750 B
of locals (`argv[16]`, `result[224]`, `sanitized[224]`, `buf[241]`)
before the adapter can refuse. Every yield in that chain pays CODAL's
stack copy for the depth. `radio_transport.h:314-318` records this fiber
hard-faulting from ~450 B of locals before the buffers were moved to
members.

## What would settle it

A `DIFFDRIVE_FAULT_SPIN` build with a stack-canary fill, one full
`RUN:tour` plus a `RUN x #1` over radio mid-tour, and the high-water mark
read by pyOCD. Independently of the measurement, move `execRun()`'s three
buffers below the `outcome != kOk` early returns or make them members
like `emitBuf_`.

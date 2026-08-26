---
status: pending
---

# int32-typed sim fallback params break JS→Blocks conversion (TS9256)

## Problem

Every JS→Blocks conversion in a project that depends on this extension
fails in the MakeCode editor with

```
error TS9256: bit sizes are not supported for locals and parameters
```

pointing at `src/blocks/sim.ts` (pre-reorg measurements: lines 113 and
352). The decompiler's typecheck pass rejects sized-int (`int32`)
parameter types on functions that have bodies, and sim.ts's
shim-fallback functions (`//% shim=diffDrive::…` with TS bodies for
the simulator) declare their parameters `int32`. The student sees
"Oops, there is a problem converting your code" on every attempt. The
native build and the toolbox are unaffected — only conversion runs the
stricter check, which is why hardware builds never surfaced it.

## Verified (2026-08-25/26, local pxt serve, pxt-core 13.0.1 / pxt-microbit 9.1.1)

- Extension as-is: conversion always fails with TS9256.
- Scratch copy with a blanket `int32`→`number` in sim.ts: identical
  program converts to blocks correctly.
- A hex built from the patched copy (pxt CLI cloud compile) ran on
  tovez: `RUN:go` executed a commanded 200 mm move to 200.3 mm — the
  TS decl types do not govern the native shim ABI (the C++ signatures
  do), so the change is hardware-safe.

## Fix

Change parameter types on the sim-fallback functions in
`src/blocks/sim.ts` from `int32` to `number` (return types can stay).
A sprint-013-era audit found int32 params on ~10 functions
(`_setWheels`, `_driveTwist`, `_startMove`, `_cycleStat`,
`_setGeometry`, `runCommandText`, `setTaperWindows`, `setTaperFloors`,
plus others) — sweep the whole file, not just the two reported lines.
Verify: JS→Blocks converts cleanly in the local editor
(`http://localhost:3232/index.html?ws=fs`) for a project using the
extension. Related: [[simulator-crashes-at-on-start-startprotocol]]
(same file, same editing session).

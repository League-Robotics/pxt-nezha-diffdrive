---
status: in-progress
sprint: '013'
tickets:
- 013-001
---

# int32-typed sim fallback params break JS→Blocks conversion (TS9256)

## Problem

Every "switch to blocks" in a student project that depends on this
extension fails in the MakeCode editor with:

```
error TS9256: bit sizes are not supported for locals and parameters
  pxt_modules/nezha-diffdrive/src/sim.ts(113,21)
  pxt_modules/nezha-diffdrive/src/sim.ts(352,21)
```

The decompiler's typecheck pass rejects sized-int (`int32`) parameter
types on functions that have **bodies**. `src/sim.ts`'s shim-fallback
functions (`//% shim=diffDrive::...` with a TS body for the simulator)
declare their parameters as `int32`, so the JS→Blocks conversion
always aborts with the "Oops, there is a problem converting your
code" dialog. The normal native build and the toolbox are unaffected —
only the conversion path runs the stricter check, which is why this
was never seen in `make_deploy` builds.

Verified 2026-08-25 on a local `pxt serve` (pxt-core 13.0.1,
pxt-microbit 9.1.1):

- Extension as-is: conversion always fails with TS9256.
- Scratch copy with `int32` → `number` in sim.ts (blanket regex;
  `projects/nezha-diffdrive-patched` in the
  `blocks-local-codeserver-test` worktree): the same program converts
  to blocks correctly.
- A hex built from that patched copy (pxt CLI, cloud compile) was
  flashed to tovez and its `RUN:go` handler executed: pose telemetry
  showed the commanded 200 mm move, so number-typed params do **not**
  break the native build (the C++ shim signatures, not the TS decl
  types, govern the native ABI).

## Proposed fix

In `src/sim.ts`, change the parameter types of the shim-fallback
functions from `int32` to `number` (parameters at lines 83, 104,
113–114, 191, 271, 352 as of 447135a; return types can stay).
Then a normal build + flash + bench check.

## Secondary findings from the same session (for the record)

1. The extension has no `pxsim`-side simulator implementation, so the
   web simulator crashes at boot: `Cannot read properties of undefined
   (reading 'startProtocol')` from `motion.ts`'s top-level
   `_startProtocol()`. Cosmetic in the editor, but scary for students.
2. `pxt serve`'s fs workspace (`?ws=fs`) wedges into a memory
   workspace ("Project Auto-Save Disabled") after a 409 merge conflict
   on the editor-managed `_history` file (two clients, or a client
   with stale state). Recovery: delete the project's `_history` and
   reload the editor.
3. MakeCode's downloaded `.hex` is universal-hex format, which
   pyocd/mbdeploy cannot parse ("Record at line 2 has invalid record
   type") — flash `built/mbcodal-binary.hex` from a pxt CLI build
   instead. Also: a MakeCode editor tab with a WebUSB pairing grant
   holds the DAP interface, making mbdeploy fail with "Unable to claim
   interface" until the tab is navigated away.

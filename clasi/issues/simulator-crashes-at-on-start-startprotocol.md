---
status: pending
---

# Simulator crashes at on-start: "Cannot read properties of undefined (reading 'startProtocol')"

## Problem

Every project using this extension shows a Problems-pane error in the
MakeCode editor — `Cannot read properties of undefined (reading
'startProtocol') at the 'on start' block` — and the web simulator dies
at boot (`Simulator crashed, no error handler`). Eric hit this in the
local editor 2026-08-25 (screenshot in session transcript).

## Mechanism

`src/blocks/motion.ts` calls `_startProtocol()` at namespace load. Its
sim-side declaration in `src/blocks/sim.ts` is

```ts
//% shim=diffDrive::startProtocol
export function _startProtocol(): void { }
```

with an EMPTY body. pxt treats an empty-bodied shim function as
native-only and emits a `pxsim.diffDrive.startProtocol(...)` call in
the simulator build; no pxsim implementation exists, so the sim throws
at the first statement of `<main>`. Functions with real bodies run
their bodies in the sim and are fine. A sprint-013-era audit found ~8
more empty-bodied shims with the same latent problem (`_setGeometry`,
`_setKernelValue`, `probe`, `setTaperWindows`, `setTaperFloors`,
`setRampMs`, `otosSetOffset`, `otosZero`, `otosCalibrate`,
`_clearStallLatch`).

## Fix

Give every empty-bodied shim in `src/blocks/sim.ts` a real (if
trivial) simulator body — e.g. `_startProtocol` sets a module-level
`simProtocolStarted` flag — so pxt uses the TS body in the simulator.
Verify in the local editor: Problems pane clean, simulator boots and
shows the program's start icon for a bare project using the extension.
Related: [[int32-sim-params-break-blocks-conversion]] (same file).

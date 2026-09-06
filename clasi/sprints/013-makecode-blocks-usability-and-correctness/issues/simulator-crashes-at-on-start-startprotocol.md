---
status: in-progress
sprint: '013'
tickets:
- 013-001
---

# Simulator crashes at on-start: "Cannot read properties of undefined (reading 'startProtocol')"

## Problem

Every project using this extension shows a Problems entry in the
MakeCode editor — `Cannot read properties of undefined (reading
'startProtocol') at the 'on start' block` — and the simulator dies at
boot. Eric hit this in the local editor 2026-08-25 (screenshot in
session); the console shows `Simulator crashed, no error handler`.

## Mechanism

`motion.ts` calls `_startProtocol()` at namespace load. The sim-side
declaration (src/sim.ts:276-277) is

```ts
//% shim=diffDrive::startProtocol
export function _startProtocol(): void { }
```

with an EMPTY body — pxt treats an empty-bodied shim function as
native-only and emits a `pxsim.diffDrive.startProtocol(...)` call in
the simulator build; no such pxsim implementation exists, so the sim
throws at the first statement of `<main>`. Other sim.ts functions with
real bodies run their bodies in the sim and are fine; any other
empty-bodied shim reachable from sim code (e.g. `_setGeometry`,
line ~271) has the same latent problem.

## Fix direction

Give `_startProtocol` (and other empty-bodied shims) a real, if
trivial, simulator body — e.g. set a module-level `simProtocolStarted`
flag — so pxt uses the TS body in the simulator. Verify in the local
editor: the Problems pane is clean and the simulator boots (shows the
program's start icon) for a bare project using the extension.
Related: [[int32-sim-params-break-blocks-conversion]] (same file, same
editing session would cover both).

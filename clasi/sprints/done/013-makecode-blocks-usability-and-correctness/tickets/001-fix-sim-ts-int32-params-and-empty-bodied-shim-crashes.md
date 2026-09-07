---
id: '001'
title: Fix sim.ts int32 params and empty-bodied shim crashes
status: open
use-cases: []
depends-on: []
github-issue: ''
issue:
- int32-sim-params-break-blocks-conversion.md
- simulator-crashes-at-on-start-startprotocol.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Fix sim.ts int32 params and empty-bodied shim crashes

## Description

Two defects in `src/sim.ts`, same file and same editing pass:

1. **`int32-sim-params-break-blocks-conversion.md`**: shim-fallback
   functions use `int32` parameter types, which MakeCode's decompiler
   typecheck pass rejects with `TS9256` on any function that has a
   body — so every "switch to blocks" on a project using this
   extension fails. The native build is unaffected (the C++ shim
   signatures in `shims.cpp` govern the ABI, not the TS decl types) —
   already spot-verified on tovez with a scratch patch (`RUN:go`,
   pose telemetry matched the commanded 200 mm move).
2. **`simulator-crashes-at-on-start-startprotocol.md`**: several
   shim-fallback functions have empty (`{ }`) TS bodies. pxt treats an
   empty body as "native-only" and bundles an unimplemented
   `pxsim.diffDrive.*` call for the simulator; since this project ships
   no separate `pxsim`-side implementation, calling one of these
   crashes the browser simulator (`Cannot read properties of undefined
   (reading 'startProtocol')`). `_startProtocol()` is called
   unconditionally at namespace load (from `motion.ts`), so **every**
   project using this extension crashes at boot regardless of which
   blocks the student uses.

**Important — the issue files under-count both lists.** Planning-time
line-by-line read of `sim.ts` (as of commit 447135a) found more
functions affected than either issue's own audit named. Treat the
lists below as the authoritative, complete set for this ticket;
re-check against the current file in case anything shifted since
447135a.

### Complete int32 → number list (parameters only; return types stay
per the issue's own instruction — the decompiler only rejects
`int32` on locals/parameters)

- `_setWheels(left: int32, right: int32)` — line 83
- `_driveTwist(speed: int32, yawRate: int32)` — line 104
- `_startMove(distance: int32, yaw: int32, speed: int32, yawRate: int32)` — lines 113-114
- `_cycleStat(which: int32)` — line 191 (param only; return type stays `int32`)
- `_setGeometry(trackWidth: int32, calib: int32)` — line 271
- `_setKernelValue(field: int32, value: int32)` — line 274 (not named
  by the issue — found during planning)
- `probe(what: int32)` — line 292 (not named by the issue)
- `setTaperWindows(distCounts: int32, yawCounts: int32)` — line 300 (not named by the issue)
- `setTaperFloors(distPct: int32, turnPct: int32)` — line 303 (not named by the issue)
- `setRampMs(ms: int32)` — line 306 (not named by the issue)
- `otosSetOffset(x: int32, y: int32, yaw: int32)` — line 329 (not named by the issue)
- `runCommandText(slot: int32)` — line 352
- `_seedPose(x: int32, y: int32, heading: int32)` — line 357 (not named by the issue)

### Complete empty-bodied shim list (candidates for a real trivial body)

Reachable unconditionally at startup — **fix this one first, it's the
whole bug report**:
- `_startProtocol(): void { }` — line 277 (called at namespace load
  from `motion.ts`)

Reachable only if a program calls the corresponding block/API — fix
for defense-in-depth, lower priority, but each will crash the
simulator the moment a program calls it:
- `_setGeometry(trackWidth, calib): void { }` — line 271
- `_setKernelValue(field, value): void { }` — line 274
- `_clearStallLatch(): void { }` — line 239 (its own comment claims
  "no-ops in the simulator", but an empty TS body does NOT achieve a
  no-op in the sim — it triggers the exact same undefined-`pxsim.*`
  crash as `_startProtocol`. The comment's intent needs an actual
  statement, e.g. reading/discarding a no-op local, to be realized.)
- `setTaperWindows(distCounts, yawCounts): void { }` — line 300
- `setTaperFloors(distPct, turnPct): void { }` — line 303
- `setRampMs(ms): void { }` — line 306
- `otosSetOffset(x, y, yaw): void { }` — line 329
- `otosZero(): void { }` — line ~322-323
- `otosCalibrate(samples): void { }` — line ~325-326

Do NOT touch `runCommandText()` — it already has a body (`return ""`)
even though the return value is a no-op; not empty, not affected.

Each trivial body should follow the file's existing precedent (e.g.
`_estopClear()`'s `simEstopped = false` pattern) — a real assignment
or state update, not a comment-only body, since pxt's emptiness check
is structural, not semantic.

## Acceptance Criteria

- [ ] Every `int32` parameter listed above is changed to `number` in
      `src/sim.ts`; return types are left unchanged.
- [ ] `_startProtocol()` has a real (non-empty) trivial body.
- [ ] Every other empty-bodied shim function listed above has a real
      (non-empty) trivial body, or is documented in this ticket's
      completion notes as deliberately left as-is with a reason.
- [ ] In the local editor (`http://localhost:3232/index.html?ws=fs`),
      a project using this extension converts JS→Blocks with no
      `TS9256` and no "Oops, there is a problem converting your code"
      dialog.
- [ ] In the same local editor, the web simulator boots cleanly for a
      bare project using this extension (start icon appears, no
      "Cannot read properties of undefined", clean Problems pane).
- [ ] A full native (non-simulator) build succeeds after these
      changes, confirming the C++ ABI is unaffected by the TS-level
      type changes.

## Implementation Plan

**Approach**: Direct text edits to `src/sim.ts` only — no shim
signature changes on the C++ side (native build reads `shims.cpp`'s
own declarations, untouched by this ticket). Make the `int32`→`number`
edits and the empty-body edits in one pass since they're the same
file, same review.

**Files to modify**:
- `src/sim.ts` — parameter types and shim bodies per the lists above.

**Testing plan**:
- Local editor: load `http://localhost:3232/index.html?ws=fs`, create
  a bare project (or reuse `projects/blocktest`/`projects/plain`),
  attempt JS→Blocks conversion, confirm success.
- Local editor: reload with a bare `on start` program, confirm the
  simulator boots and the Problems pane is clean.
- Exercise the previously-empty shims that now have real bodies from
  the simulator (e.g., trigger "clear stall latch" from a block) to
  confirm no crash.
- Native build: run the project's normal pxt CLI cloud build; confirm
  it succeeds (this ticket makes no C++ changes, so this is a
  regression check, not new verification).
- No hardware flash is required for this ticket specifically (the
  int32 patch was already spot-verified on tovez during the triage
  session referenced in the issue) — a native build success is
  sufficient evidence the ABI is unaffected.

**Documentation updates**: None required — no public API/block
signature changes (int32 vs number is not visible to blocks; empty
vs. real sim bodies is not visible to blocks either).

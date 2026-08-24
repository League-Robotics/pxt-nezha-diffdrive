---
id: '001'
title: 'Stall latch: clear path and readback (block, wire SET-action field, docs)'
status: in-progress
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: stall-latch-invisible-dead-end.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Stall latch: clear path and readback (block, wire SET-action field, docs)

## Description

The stall detector ships enabled (500 ms of demanded duty with
near-zero encoder motion → `stallHalted_` latches, `diffdrive.cpp`).
Once latched, `drive()`/`driveDuty()` keep returning `kOk`
(`checkCommandable()` never checks `stallHalted_`), so every block and
wire verb reports success while the robot silently ignores everything
for the rest of the program — recoverable today only by a power cycle
(code review R-01/API-02, CONFIRMED, downgraded Critical→Major only
because power-cycle recovers).

This is a **missing-caller problem, not a missing-logic problem**: the
kernel already does everything right.
`DifferentialDrive::clearStallLatch()` (`diffdrive.h:201`,
`diffdrive.cpp:384`) already exists and correctly clears the latch on
the kernel's next `step()` (increments `clearStallReq_`, consumed by
`step()`'s `clearStallReq_ != seenClearStallReq_` check) — its **only**
caller anywhere in the package is a host-test shim. `Output.stallHalted`
(`diffdrive.h`) already exists and is already correctly populated
(`out_.stallHalted = stallHalted_`), and `shims.cpp`'s
`diagValue(2)` already returns it — just undocumented (main.ts's
`probe()` JSDoc lists ordinals 6/7/10-15 but not 2). STATUS's `flags`
bit 2 (`kFlagStallHalted`, `wire_adapter.cpp`) already reports it over
the wire too. Nothing in `diffdrive.{h,cpp}` changes in this ticket.

**What this ticket adds** (all thin forwards to existing, unchanged
kernel behavior):
1. Two new `shims.cpp` free functions: `void clearStall()` (calls
   `ensure().kernel.clearStallLatch()`) and `bool isStalled()` (returns
   `ensure().kernel.output().stallHalted`).
2. Two new dedicated `main.ts` Drive-group blocks, parked next to
   `emergencyStop()`/`clearEmergencyStop()`:
   - `clearStallLatch(): void` — `//% block="clear stall latch"
     advanced=true` `//% group="Drive"`, shim `_clearStallLatch()` →
     `clearStall()`.
   - `isStalled(): boolean` — `//% block="is stalled"` `//%
     group="Drive"` (NOT advanced — burying the fix that makes the
     latch visible defeats the point), shim `_isStalled()` →
     `isStalled()`.
   Simulator bodies for both: no-ops (`_clearStallLatch` does nothing;
   `_isStalled` always returns `false`) — the simulator has no stall
   model, matching the existing documented precedent for
   `setGeometry`/`setKernelValue` being no-ops in the browser
   (`specification.md` §5).
3. A new wire field, `stall_clear`, reachable through the **existing**
   generic `ConfigField`/`kFields`/`setKernelValue`/`getConfigValue`
   mechanism rather than a new top-level verb (see Design Rationale
   below and `sprint.md`'s Architecture section / `design/DESIGN.md`
   §5/§13 for the full reasoning):
   - `main.ts`: add `StallClear = 17` to the `ConfigField` enum, `//%
     block="clear stall latch"` (same label as the dedicated block —
     it reaches the same call).
   - `wire_adapter.cpp`: add `{"stall_clear", 17}` to `kFields`.
   - `shims.cpp`: `setKernelValue()` case 17: `if (v != 0.0f)
     k.clearStallLatch();` (ignore `value`'s magnitude, only
     nonzero-vs-zero matters — mirrors the ×1000 scaling convention:
     a wire `SET stall_clear 1` arrives as `value=1000`, `v=1.0f`).
     `getConfigValue()` case 17: `v = k.output().stallHalted ? 1.0f :
     0.0f;` — a convenience readback, not a stored value.
4. Deliberately **not** done: folding into `clearEmergencyStop()`/
   `ESTOP`, or adding a new top-level wire verb. See Design Rationale.

## Design Rationale

**Why a dedicated block + SET-action field, not folded into
`clearEmergencyStop()`, and not a new top-level verb:**

Folding is rejected on the same principle sprint 006 established for
`deliverStopNow()` deliberately not touching `estopLatch_` (see
`src/DESIGN.md` §9's "Stop delivery" entry) — the stall latch and the
e-stop latch are semantically distinct fault classes ("you commanded
past what the wheels could deliver" vs. "a human demanded everything
stop regardless of state"). Blurring their clear paths would
reintroduce exactly the ambiguity that decision fixed for a different
pair, and `UC-012`'s existing postcondition already says
`clearEmergencyStop()` "clears only the e-stop latch, not an
independent stall latch."

A new top-level wire verb (e.g. `STALL_CLEAR` in `kCommandTable`) is
rejected because this project has **no existing precedent for a
wire-level "clear a latch" verb at all** — `estopClear()`
(`shims.cpp`) has no wire verb today, block-only, confirmed by reading
`wire_handler.cpp`'s `kCommandTable` and `wire_adapter.cpp`'s
`onEstop()` (only sets the latch; there is no `onEstopClear()`).
Ticket 007 (this sprint) is separately resizing `kCommandTable` for
WIRE-09 — adding a new row to a table this sprint is simultaneously
trying to make less fragile is avoidable risk for no behavioral gain
over the SET-action route the review's own remedy text explicitly
names as sufficient ("expose `clearStallLatch` as... a SET-able wire
action"). Reusing the existing GET/SET grammar needs zero new
wire-handler surface.

**Accepted, minor consequence:** `stall_clear` also appears in the
generic `set config %field to %value` dropdown alongside the dedicated
block — two ways to trigger the same call. This is intentional
redundancy, not a defect: the dedicated block is for discoverability
(the whole point of this ticket), the wire field is for bench hosts
that only speak GET/SET.

## Acceptance Criteria

- [x] `DifferentialDrive::clearStallLatch()`/`Output.stallHalted` are
      confirmed unchanged (no edits to `diffdrive.h`/`diffdrive.cpp`
      in this ticket's diff).
- [x] A host test drives the kernel into the stall-latched state
      (sustained demanded duty + near-zero encoder velocity past
      `stallWindow`, using the existing `FakeMotor`/kernel harness
      pattern from `tests/host/test_kernel_harness.py`), confirms
      `drive()` still returns `kOk` while latched (documenting the
      existing, unchanged silent-success behavior this ticket does
      NOT change), calls `clearStallLatch()`, steps the kernel once,
      and confirms `Output.stallHalted` reads `false` and a subsequent
      `drive()` call actually commands nonzero duty again.
- [x] A host test exercises the wire path: `SET stall_clear 1`
      against a stalled `WireAdapter`+kernel fixture
      (`tests/host/wire_motion_verb_shim.cpp`/
      `test_wire_motion_verbs.py` pattern) acks and clears the latch;
      `GET stall_clear` before/after reads `1`/`0`.
- [x] `main.ts`'s `probe()` JSDoc comment is updated to name ordinal 2
      (`stallHalted`) instead of leaving it out of the documented list.
- [x] `docs/design/usecases.md` UC-002's stall error-flow bullet is
      rewritten from "not currently exposed as a block — see gap noted
      in the report to team-lead" to describe `is stalled`/
      `clear stall latch`, and gains the "separate from e-stop" note.
      UC-012's postcondition parenthetical is rewritten from pointing
      at the gap to pointing at the new dedicated block. (These are
      direct edits on the sprint branch — `usecases.md` is not part of
      this project's canonical design-doc-overlay set; see `sprint.md`'s
      Architecture section for why.)
- [x] `docs/design/specification.md` §4.2's block table gains rows for
      `is stalled`/`clear stall latch`; §4.8's `ConfigField` table
      gains the `StallClear`/17 row with its non-standard "Backing
      store" (a kernel action, not a `Config` field). Same
      direct-edit note as above.
- [x] Full existing host suite still passes (no regressions to
      `checkCommandable()`, `diagValue()`, or any existing `kFields`
      entry's behavior).
- [x] `main.ts` changes (the two new blocks, the `ConfigField` entry)
      are verified by a PXT build succeeding and a manual block-palette
      check — **not** by a host test; `main.ts` is outside the C++11
      host-test gate (see C++11 Gate Coverage below).

## C++11 Gate Coverage

- **Inside the gate** (`tests/host/` compiles at C++20; both real
  targets compile at C++11): `diffdrive.h`/`.cpp` (unchanged — verify
  the diff is empty), `wire_adapter.cpp`/`.h` (the new `kFields` row
  and `getConfigValue`/`setKernelValue` cases — wait, `setKernelValue`/
  `getConfigValue` themselves live in `shims.cpp`, see below).
- **Outside the gate** (target-only, `shims.cpp` includes `pxt.h` and
  cannot be host-compiled; `main.ts` has no host-test coverage at
  all): the two new `shims.cpp` free functions (`clearStall()`,
  `isStalled()`), the `setKernelValue()`/`getConfigValue()` case-17
  bodies, and everything in `main.ts`. A green host suite proves the
  kernel-level clear/readback logic and the wire-level GET/SET
  round-trip against a `WireAdapter` test double — it does **not**
  prove `shims.cpp`'s two new free functions or the `main.ts` blocks
  compile for either real embedded target. Do not report "host tests
  pass" as target-build evidence for those two pieces.

## Testing

- **Existing tests to run**: `tests/host/test_kernel_harness.py`,
  `tests/host/test_wire_motion_verbs.py`, `tests/host/test_wire_grammar.py`
  — confirm no regression to existing `kFields`/`ConfigField` entries
  or kernel stall behavior.
- **New tests to write**: kernel-level stall-latch clear test (see
  Acceptance Criteria); wire-level `stall_clear` GET/SET round-trip
  test, stalled and not-stalled.
- **Verification command**: `pytest tests/host/ -k "stall"` plus a full
  `pytest tests/host/` run before marking this ticket done.

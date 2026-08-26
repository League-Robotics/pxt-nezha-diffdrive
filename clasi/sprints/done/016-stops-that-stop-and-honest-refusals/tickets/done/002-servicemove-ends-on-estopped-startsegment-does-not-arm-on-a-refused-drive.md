---
id: '002'
title: serviceMove() ends on estopped; startSegment() does not arm on a refused drive()
status: done
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: move-engine-ignores-estop-and-drive-refusals.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# serviceMove() ends on estopped; startSegment() does not arm on a refused drive()

## Description

Two small, independent fixes in `src/motion/motion_engine.cpp`, both
host-portable (no `pxt.h`, no CODAL) and both host-testable directly
against `tests/host/motion_engine_shim.cpp`. **`src/core/diffdrive.{h,cpp}`
is vendored and byte-stable — this ticket never touches it**, only reads
its existing public surface (`Output.estopped`, the `Status` enum,
`drive()`'s existing return value).

### (a) `serviceMove()` does not end on e-stop

`serviceMove()`'s end condition (`motion_engine.cpp:360`) is:

```cpp
if ((distDone && yawDone) || expired || out.stallHalted || wrongWay) {
```

`out.estopped` (`DiffDrive::DifferentialDrive::Output::estopped`,
`diffdrive.h:142`) is not in that list, though it is published the same
way `stallHalted` already is. The kernel refuses to drive under the
e-stop latch, so the wheels are already safe — but the move engine does
not know, so `isMoveActive()` stays true and every `while (driveTick())`
loop spins to the deadline (measured, `stop_probe.cpp` scenario B: 1230
further ticks / 29.5 s after the latch). This is masked in normal
operation only because `shims.cpp:722 estopAll()` happens to call
`engine.endMove()` before `kernel.estop()` — an undocumented calling
order in a different file, and `kernel.emergencyStopMotors()` latches the
e-stop as a side effect that bypasses this ordering entirely.

**Fix**: add `|| out.estopped` to the end condition, so it reads
`if ((distDone && yawDone) || expired || out.stallHalted || wrongWay ||
out.estopped) {`.

### (b) `startSegment()` arms `move_.active` regardless of `drive()`'s refusal

`DifferentialDrive::drive()` returns a `Status`
(`diffdrive.h:71-79`: `kOk`, `kRefusedUnconfigured`, `kRefusedNotBegun`,
`kRefusedEstopped`, `kRefusedNonFinite`). `startSegment()`
(`motion_engine.cpp:98-139`) discards it:

```cpp
kernel_.drive(move_.velCmd * 0.25f, move_.twistCmd * 0.25f, remainingMs);
move_.active = true;
```

A refused move still arms `move_.active = true`, still reports progress,
still spins to its deadline, and still resolves as `kStop` on the wire —
indistinguishable from a move that ran and stopped normally.

**Fix**: capture the `Status` and only arm on success:

```cpp
const DiffDrive::DifferentialDrive::Status driveStatus =
    kernel_.drive(move_.velCmd * 0.25f, move_.twistCmd * 0.25f, remainingMs);
move_.active = (driveStatus == DiffDrive::DifferentialDrive::Status::kOk);
```

**Scope note**: the issue this ticket closes
(`move-engine-ignores-estop-and-drive-refusals.md`) also names three
*other* call sites that discard `drive()`'s `Status`
(`motion_engine.cpp:49` in `wheelsV()`, `:83` in `wheelsX()`/the shared
primitive, `:340` in `serviceMove()`'s own reissue). **Only the
`startSegment()` call site (the one that arms `move_.active`) is in
scope for this ticket** — the other three are lower-priority (a
continuous-drive command's own refusal is already visible through
`commandLooksActive()`/duty readback, and `serviceMove()`'s reissue is a
already-active move re-confirming its existing command, not a fresh
arming decision). Do not widen scope to those three call sites.

## Acceptance Criteria

- [x] `serviceMove()`'s end condition includes `out.estopped` alongside
      `stallHalted`/`expired`/`wrongWay`.
- [x] `startSegment()` sets `move_.active` from `kernel_.drive()`'s actual
      `Status` return, true only on `kOk`.
- [x] `src/core/diffdrive.h`/`diffdrive.cpp` are byte-unchanged.
- [x] A new host test proves: latching the kernel's e-stop mid-move (via a
      new `tests/host/motion_engine_shim.cpp` export wrapping
      `kernel.estop()`) causes `serviceMove()` to return `false` and
      `isMoveActive()` to read `false` on the very next call — not 1230
      ticks later — **without** going through anything resembling
      `shims.cpp`'s `estopAll()` ordering (this is the whole point: the
      fix must not depend on the undocumented endMove()-before-estop()
      call order).
- [x] A new host test proves: forcing `kernel_.drive()` to refuse (e.g.
      configuring the kernel with `maxDuty = 0`, which
      `Status::kRefusedUnconfigured`'s own doc comment names as its
      trigger, then calling `moveX()`) leaves `move_.active`/
      `isMoveActive()` reading `false` immediately after the call — not
      armed and silently spinning to a deadline.
- [x] Both new tests fail against the current (pre-fix)
      `motion_engine.cpp` and pass after the fix.

## Implementation Plan

### Approach

1. Edit `motion_engine.cpp`'s `serviceMove()` end-condition expression
   (line ~360) to add `|| out.estopped`.
2. Edit `motion_engine.cpp`'s `startSegment()` (line ~137-138) to capture
   `kernel_.drive()`'s `Status` and set `move_.active` from it, per the
   code shown above.
3. Extend `tests/host/motion_engine_shim.cpp` (its own header comment:
   "Extend this file's function list -- don't invent a second shim") with
   two small exports:
   - one that forces the kernel into the e-stop latch (wraps
     `handle->kernel.estop()`) — mirror the naming `kernel_shim.cpp`
     already uses for its own estop-adjacent exports where applicable;
   - one that reads back `Output.estopped` as an int (0/1), mirroring
     `kernel_shim.cpp`'s existing `kdOutEstopped` export
     (`test_cross_fiber_stop_settle_window.py`'s `k.out_estopped`
     property is the precedent to follow for naming/shape).
   Forcing a refusal does **not** need a new export — `meSetMaxDuty(handle,
   0.0)` before `meBegin`/`meMoveX` already reaches
   `Status::kRefusedUnconfigured` through the existing exported surface.
4. Add the two new tests, most naturally alongside
   `tests/host/test_motion_engine_primitives.py` (or a new
   `test_motion_engine_estop_and_refusal.py` if that reads cleaner —
   follow existing file-naming conventions in `tests/host/`).

### Files to modify

- `src/motion/motion_engine.cpp` — `serviceMove()`, `startSegment()`.
- `tests/host/motion_engine_shim.cpp` — two new exports.
- New or extended test file under `tests/host/`.

### Files explicitly NOT to modify

- `src/core/diffdrive.h`, `src/core/diffdrive.cpp` (vendored,
  byte-stable — this ticket only reads their existing public surface).
- The other three `drive()` call sites named in the issue
  (`motion_engine.cpp:49,83,340`) — out of scope per the note above.

### Testing plan

- **New tests**: as described in Acceptance Criteria — an e-stop-mid-move
  test and a refused-drive test, both against the real
  `DiffDrive::DifferentialDrive` kernel + `diffDrive::MotionEngine` over
  `FakeMotor` (no shims.cpp involvement needed — both fixes are entirely
  within the host-portable `motion_engine.cpp`).
- **Existing tests to run**: `uv run pytest tests/host/test_motion_engine_*.py`
  (scoped to the module this ticket touches).
- **Verification command**: the new test file's own path, plus the scoped
  run above.

### Documentation updates

None required by this ticket directly — `motion_engine.h`'s own header
comment does not currently document `serviceMove()`'s end-condition list
or `startSegment()`'s arming rule in a way that needs correcting (it
documents behavior at a higher level than this enumeration). The sprint's
stop-taxonomy table (ticket 006, `src/DESIGN.md`) is where this fix's
user-visible consequence — an e-stopped or refused move now resolves
honestly and quickly instead of spinning to its deadline — gets recorded
in one place alongside the other four mechanisms.

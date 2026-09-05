---
id: 008
title: 'Block API cleanup: one tick runner (world.ts calls motion.ts), shared arrival
  tolerance, const turnFirst, one stop block, delete cycleStat'
status: done
use-cases:
- SUC-007
depends-on:
- '007'
github-issue: ''
issue: goto-turn-rate-arrival-tolerance-tick-runner-cyclestat.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Block API cleanup: one tick runner (world.ts calls motion.ts), shared arrival tolerance, const turnFirst, one stop block, delete cycleStat

## Description

Four independently-confirmed findings, bundled because they are all
small, TS-layer-only, and cluster in the same two files
(`motion.ts`/`world.ts`) this sprint has already been editing (tickets
005-007 touch `sim.ts`/`shims.cpp`/`motion.ts`'s `startGoTo`; this
ticket is sequenced last so it lands on the settled post-007 shape of
`startGoTo`).

1. **Three tick runners.** `src/blocks/motion.ts`'s exported `move()`/
   `goTo()` (`startMove(...); while(_tickDrive());` /
   `startGoTo(...); while(_tickDrive());`), `src/blocks/world.ts`'s
   PRIVATE `tickedMove()`/`tickedGoTo()` (byte-for-byte the same two
   lines, just not exported), and `test/test.ts`'s `tickToCompletion()`
   (does MORE than the other two — checks `aborted`, calls
   `stopMove()`, samples OTOS — deliberately NOT touched by this
   ticket). `world.ts`'s copy is pure duplication with zero behavioral
   difference from `motion.ts`'s exported versions.
2. **Arrival tolerance gates only one go-to block.** `world.ts` owns
   `arriveTolCm` (default 1.0 cm, settable via `setArrivalTolerance()`)
   but only uses it for `goToWorld()`'s OWN JS-level early-return
   distance check — it is never threaded into the native call.
   `motion.ts`'s `startGoTo()` hardcodes `const goalArrive = 1` (mm)
   into `_goToR(...)` regardless of what `setArrivalTolerance()` was
   ever called with. So calling `setArrivalTolerance(3)` changes
   `goToWorld`'s own pre-check but has ZERO effect on the underlying
   `_goToR` call either block ultimately makes.
3. **`turnFirst` is a `let` nothing writes.** `world.ts` line ~157:
   `let turnFirst = 12.0` — grepped, no assignment anywhere else in the
   file.
4. **`stop`/`stop move` are now one operation, two blocks.**
   `src/blocks/stop.ts`'s `stop()` calls `_stopAll()`; `motion.ts`'s
   `stopMove()` calls `_endMove()`. Confirmed in `src/shims.cpp`:
   `stopAll()` and `endMove()` are now BYTE-IDENTICAL bodies
   (`engine.endMove(); kernel.neutral(); deliverStopNow(r);
   protocolReleaseBlockOwnership();`, modulo `stopAll()`'s `ensure()`
   vs `endMove()`'s null-check — functionally the same for any caller
   that has already touched the Rig).
5. **`cycleStat`/`_cycleStat` has no caller.** Grepped repo-wide
   (`src/`, `test/`, `tests/`, `tools/`): the only references are the
   shim's own definition (`shims.cpp`) and the simulator stub's own
   definition (`sim.ts`) — nothing calls either.

## Acceptance Criteria

- [x] `world.ts`'s private `tickedMove()`/`tickedGoTo()` are deleted;
      every call site that used them now calls `motion.ts`'s exported
      `move(distance, yaw)`/`goTo(x, y)` directly (import/namespace
      access as needed — both are in the same `diffDrive` namespace
      already, per the existing code, so no new import machinery should
      be needed).
  - [x] Confirm this is a pure behavior-preserving substitution: both
        old private functions and `motion.ts`'s exported versions do
        the identical `start*(...); while (_tickDrive());` — if
        `motion.ts`'s versions have picked up any additional behavior
        from tickets 005-007 that `world.ts`'s callers should NOT
        inherit (unlikely, but check), note it explicitly rather than
        silently accepting a behavior change here. Confirmed
        behavior-preserving, with one drifted premise resolved: the
        two bodies were NOT byte-identical — `world.ts`'s deleted
        `tickedMove()` carried an extra `if (distance == 0 && yaw ==
        0) return` guard `motion.ts`'s `move()` never had. Verified
        dead in practice: `tickedMove()` had exactly one call site
        (`goToWorld()`'s pivot branch, `move(0, bearing)`), gated on
        `Math.abs(bearing) >= turnFirst` (12 deg) — `bearing` can
        never be 0 there, so the guard never fired. Substituting
        `move()` is behavior-preserving for every real call.
- [x] Arrival tolerance: `arriveTolCm` (and `setArrivalTolerance()`)
      move to (or are otherwise shared with) `motion.ts` — the lower
      layer, per `sprint.md`'s Design Rationale on dependency
      direction — and `startGoTo()` reads the shared value instead of
      hardcoding `goalArrive = 1`. `world.ts`'s `goToWorld()` continues
      to use the SAME shared value for its own JS-level pre-check, so
      one `setArrivalTolerance()` call visibly affects both blocks.
      Renamed to `arriveTol` (no-units-in-identifiers.md — `Cm` was a
      unit suffix, the file was already being touched). Fully moved,
      not duplicated: `world.ts` has no second declaration.
  - [x] If `world.ts` must keep its own `setArrivalTolerance()` block
        for toolbox/backward-compatibility reasons, make it write
        through to the shared value rather than maintaining a second,
        independent copy — state which approach was taken and why.
        Not needed — the block itself moved to `motion.ts` wholesale
        (same exported name, same `//%` caption, so no toolbox-facing
        change); `world.ts` reads the shared state through a new
        one-line accessor, `arrivalTolerance()`, since TypeScript's
        cross-file namespace merging shares EXPORTED members by bare
        identifier but not plain `let`s (confirmed empirically via
        `tsc`: a bare reference to the unexported `arriveTol` from
        `world.ts` fails `TS2304`).
- [x] `world.ts`'s `turnFirst` becomes `const turnFirst = 12.0`.
- [x] `stop.ts`'s `stop()` remains the VISIBLE toolbox block (it
      already ranks above `stopMove` in the Stop group's weight
      ordering per that file's own sprint-021 comment).
      `motion.ts`'s `stopMove()` is marked `//% blockHidden=true` but
      remains an exported, callable function (every internal caller in
      `test.ts`/`world.ts`/elsewhere keeps working unchanged) — per
      `sprint.md`'s Design Rationale, this is an alias, not a deletion.
      Drifted premise: `stopMove` actually carried the HIGHER weight
      (290 vs `stop`'s 270 — descending weight renders first, so
      `stopMove` rendered ABOVE `stop`, not below it as this line and
      `sprint.md` both assert). Moot once `blockHidden=true` is set —
      a hidden block never reaches the toolbox regardless of weight —
      but `tests/host/test_block_toolbox_order.py`'s own baseline
      confirms the premise was stale before this ticket, not just
      imprecise prose.
- [x] `cycleStat`(`src/shims.cpp`)/`_cycleStat` (`src/blocks/sim.ts`)
      are deleted entirely, along with any now-dead
      `//% shim=diffDrive::cycleStat` annotation and the `sim.ts`
      comment referencing it. Re-grep repo-wide for `cycleStat` after
      the edit and confirm zero remaining references anywhere
      (including `docs/`, if any doc happens to mention it — check).
      Zero references remain in `src/`, `test/`, `tests/`, `tools/`
      (confirmed by grep and pinned by a new host test,
      `test_cyclestat_deleted.py`). `docs/code-review/**` and
      `clasi/sprints/done/**` still mention it as historical audit/
      planning record — left untouched deliberately, same as any
      other closed finding's paper trail.
- [x] A host test confirms `world.ts` no longer defines its own
      `tickedMove`/`tickedGoTo` (source-pin, confirming the DELETION,
      not just that `motion.ts`'s versions exist) and that both
      `goTo`/`goToWorld`'s native calls receive the SAME arrival
      tolerance value after a single `setArrivalTolerance()` call.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` (full suite — `cycleStat`'s deletion in particular needs a repo-wide check, not a scoped one, to be sure nothing else silently depended on the shim existing even without calling it, e.g. a diagnostic index table).
- **New tests to write**: the shared-tick-runner absence-of-duplication test and the shared-arrival-tolerance behavioral test described above.
- **TS type-check**: `npx tsc --noEmit`; this ticket also touches `src/shims.cpp` (`cycleStat` deletion), so also run the host-native ctypes build (see ticket 007's testing note) to confirm the native library still links with the shim removed.
- **Verification command**: `uv run pytest tests/host/ -v`

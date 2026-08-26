---
status: done
sprint: '016'
tickets:
- 016-005
---

# A running `RUN:` tour cannot be aborted, and an e-stopped tour emits a normal-looking transcript

Priority: **High** -- the failure mode is a *confidently wrong bench artifact*,
which is the thing this project's own operating rules warn about most.

## What happens

Every `RUN:` handler in `test/test.ts` (`tourRobot`, `tourWorld`, `tourWheels`,
`straightRun`, `goto`, `face`, `pivot`) runs its full multi-leg sequence inside
one MessageBus event handler, guarded only by the `touring` re-entry flag. There
is no `RUN:abort`, no per-leg abort check, and no consultation of e-stop state
anywhere in the file.

A wire `ESTOP` mid-tour:

1. `estopAll()` ends the current leg and latches the kernel -- wheels stop.
2. `tickedMove()`'s `while (driveTick())` exits.
3. **The handler proceeds to the next leg.** `startMove()` arms; `drive()` is
   refused silently (see `move-engine-ignores-estop-and-drive-refusals.md`);
   `move_.active` is set anyway; `serviceMove()` never checks `estopped`, so the
   loop spins for that leg's full deadline.
4. Repeat for every remaining leg.
5. `logFix()` emits a plausible `OCAL:` line at each corner from the stale OTOS
   cache.
6. `GAP:`, `TOUR:end`, and a letter on the display.

**The operator gets a complete, normal-looking tour transcript for a tour that
never moved.** Nothing in the emitted stream says "estopped".

## What to change

Three small pieces:

1. A module-level `aborted` flag, set by a new `RUN:abort` handler.
2. `tickedMove()` returns early if `aborted`; each tour's `for` loop breaks on
   it. `tickedMove()` is already the single choke point every leg goes through.
3. A terminal line that says *how* the tour ended -- `TOUR:end:ok` /
   `TOUR:end:abort` / `TOUR:end:estop` -- instead of always `TOUR:end`. The
   e-stop case is readable from `diffDrive.probe(1)` with no new firmware
   surface.

Fixing the `estopped` half of
`move-engine-ignores-estop-and-drive-refusals.md` also improves this a lot: each
post-estop leg would end on the next tick rather than at its deadline.

## Related: `logFix()` staleness is not marked in-line

`test/test.ts:105` emits `OERR:read-failed:<tag>` on a failed `readWorld()` and
then **still emits the `OCAL:` line** from the stale cache. Emitting anyway is
the right call (silence is indistinguishable from a fix at the origin), but the
`OCAL:` line carries no marker, so any consumer that greps `OCAL:` without
correlating the preceding `OERR:` reads a stale pose as fresh. Given
`tour-corner-fixes-are-stale-cache.md`, the staleness belongs in the line:
`OCAL:<tag>:<x>:<y>:<h>:<ok>`.

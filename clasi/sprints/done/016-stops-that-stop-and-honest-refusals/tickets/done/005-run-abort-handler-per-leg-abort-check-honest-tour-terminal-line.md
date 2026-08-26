---
id: '005'
title: RUN:abort handler, per-leg abort check, honest tour terminal line
status: done
use-cases:
- SUC-002
depends-on:
- '002'
github-issue: ''
issue: run-tours-cannot-be-aborted.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# RUN:abort handler, per-leg abort check, honest tour terminal line

## Description

`test/test.ts`'s tours (`tourRobot`, `tourWheels`, `tourWorld`) run their
full multi-leg sequence inside one `RUN:tour` `MessageBus` handler,
guarded only by the `touring` re-entry flag (line 21). There is no
`RUN:abort`, no per-leg abort check, and — separately from this ticket,
but improved *by* it via ticket 002's dependency — no honest terminal
line distinguishing a clean finish from an e-stopped or aborted one. An
e-stopped tour today proceeds through every remaining leg (each one now
spinning to its deadline before ticket 002; ending on the next tick after
ticket 002) and finishes with a plain `TOUR:end`, emitting plausible
`OCAL:` corner fixes from the stale OTOS cache the whole way — a
confidently wrong bench artifact.

This ticket adds three pieces, scoped exactly as the issue's own "What to
change" section describes:

1. A module-level `let aborted = false` flag (near the existing `let
   touring = false` at line 21), set by a new `RUN:abort` handler.
2. `tickedMove()` (line 31-39) returns early if `aborted` is set — it is
   the single choke point `tourWheels()` and `legToward()` (used by
   `tourRobot()`) both go through for every leg. Each tour's own `for`
   loop also checks `aborted` after each leg/corner and `break`s.
3. A terminal line that says *how* the tour ended — `TOUR:end:ok` /
   `TOUR:end:abort` / `TOUR:end:estop` — replacing the current
   unconditional `diffDrive.emitLine("TOUR:end")` in all three tours.

### Scope boundary: `tourWorld()` and `goToWorld()` — read before implementing

`tourWorld()` (line 253-289) does **not** call `tickedMove()` — it calls
`diffDrive.goToWorld(x, y)` directly (`src/blocks/world.ts:155`), which
runs its **own** internal `while (_tickDrive())` loop (`world.ts:230-236`,
the "shared runner for goToWorld's legs"). `src/blocks/world.ts` is **not**
in this sprint's Scope (see `sprint.md`'s Scope section — only
`shims.cpp`, `motion_engine.cpp`, `wire_adapter.cpp`, `sim.ts`, `test.ts`,
`tests/host/` are listed). **Do not modify `world.ts`.** This means:

- A plain `RUN:abort` during a `tourWorld()` leg cannot interrupt that
  *current* leg mid-flight (nothing inside `world.ts`'s runner checks the
  flag) — it only takes effect at the *next* corner, via the for-loop's
  own `aborted` check. This is a real, honest limitation of this ticket's
  scope, not an oversight — say so in a code comment at `tourWorld()`'s
  for loop.
- An e-stop *does* still interrupt the current `tourWorld()` leg promptly,
  because ticket 002's `serviceMove()` fix makes `_tickDrive()`/
  `driveTick()` return `false` on the next tick once `out.estopped` is
  set — `world.ts`'s own `while (_tickDrive())` loop exits on its own,
  with no `world.ts` change needed. This is why ticket 005 depends on
  ticket 002: the e-stop half of tour responsiveness comes from ticket
  002's fix, not from anything this ticket adds.

### Terminal line reason

Determine the reason at each tour's end, checking `aborted` before
consulting hardware state (an abort issued right as the tour was also
about to e-stop should report the operator's actual intent):

```ts
const reason = aborted ? "abort" : (diffDrive.probe(1) != 0 ? "estop" : "ok")
diffDrive.emitLine("TOUR:end:" + reason)
```

`diffDrive.probe(1)` reads `Output.estopped` (`shims.cpp`'s `diagValue()`
case 1) — "readable from `diffDrive.probe(1)` with no new firmware
surface," per the issue. `probe()` is already exported to `test.ts`;
no `shims.cpp` change is needed for this.

### Reset `aborted` per tour

Reset `aborted = false` at the start of each tour (alongside the existing
`touring = true` line), so a stale abort from a previous run does not
immediately kill the next one.

### `RUN:abort` handler

Add near the other `diffDrive.onRun(...)` registrations (~line 336-368).
Unlike most other RUN handlers it must work regardless of the `touring`
guard (an abort sent while nothing is touring is a harmless no-op; an
abort sent while a tour IS running must land even though that tour's own
handler is mid-execution on its own fiber — this mirrors the issue's own
observation that RUN handlers already interleave, which is exactly why
`touring` exists as a re-entrancy guard in the first place):

```ts
diffDrive.onRun("abort", function (arg: number) {
    aborted = true
})
```

## Acceptance Criteria

- [x] A new `RUN:abort` handler sets a module-level `aborted` flag.
- [x] `tickedMove()` checks `aborted` inside its `while (driveTick())` loop
      and returns early (after calling `diffDrive.stopMove()`, which
      after ticket 001 is a real stop) if set.
- [x] `tourRobot()`, `tourWheels()`, and `tourWorld()` each check `aborted`
      after every leg/corner and `break` their `for` loop if set.
- [x] All three tours emit `TOUR:end:ok` / `TOUR:end:abort` /
      `TOUR:end:estop` instead of the current unconditional `TOUR:end`,
      using the reason logic above.
- [x] `aborted` is reset to `false` at the start of each tour.
- [x] A host-issued `RUN:abort` mid-`tourWheels()` (or mid-`tourRobot()`)
      run stops the current leg within the next tick and the tour's
      terminal line reads `TOUR:end:abort`, with no further `OCAL:` lines
      emitted after the abort — verified per the Testing plan below (host
      test to whatever extent test.ts's own boundary allows; bench/manual
      confirmation for the rest).
- [x] `src/blocks/world.ts` is byte-unchanged.
- [x] The scope boundary above (an abort during a `tourWorld()` leg takes
      effect at the next corner, not mid-leg) is documented in a code
      comment at `tourWorld()`'s for loop.

## Findings

Implemented exactly as specified in `test/test.ts`:

- `let aborted = false` declared next to `let touring = false`.
- `diffDrive.onRun("abort", ...)` sets it, deliberately with NO `touring`
  guard (documented inline: it must land even while a tour's own handler
  is mid-execution on its own fiber).
- The abort check lives in `tickToCompletion()` — sprint 015's own shared
  tick-loop extraction, the single choke point `tickedMove()`,
  `tickedGoTo()`, and therefore `legToward()` and every tour all go
  through. It checks `aborted` inside the `while (diffDrive.driveTick())`
  loop and, if set, calls `diffDrive.stopMove()` (a real stop since
  ticket 001) and returns early.
- `tourRobot()`/`tourWheels()`/`tourWorld()` each reset `aborted = false`
  at the top (alongside `touring = true`), check `aborted` immediately
  after each leg/corner's own move call and `break` if set — placed
  **before** that iteration's `logFix()` call specifically, so an
  aborted leg never emits a plausible-looking `OCAL:` fix for a corner
  the robot never reached (`tourWheels()` checks after BOTH the straight
  leg and the turn, since one iteration issues two moves). Each tour's
  terminal line is now `TOUR:end:` + (`abort` if `aborted`, else `estop`
  if `diffDrive.probe(1) != 0`, else `ok`) — abort takes priority over
  estop when both are true, per the ticket's own stated priority (the
  operator's actual intent).
- `tourWorld()` carries the required scope-boundary comment at its for
  loop: `goToWorld()` runs its own tick loop inside `src/blocks/world.ts`
  (untouched, confirmed byte-unchanged by this ticket's own diff), so a
  plain abort there only takes effect at the next corner, not mid-leg;
  an e-stop still interrupts the current leg promptly regardless,
  courtesy of ticket 002's `serviceMove()` fix (`world.ts`'s own
  `while (_tickDrive())` loop exits on its own).
- Confirmed via `grep -rn "startswith('TOUR:end')"` that all three bench
  tools reading this line (`tour_practice.py`, `tour_watch.py`,
  `tour_run.py`) use a prefix match, so the new reason-suffixed form is
  backward compatible with them — no tool changes needed or made.

**Testing**, per the ticket's own honest framing (`test/test.ts` is a PXT
testFile, not host-compilable, and no TypeScript in this repo is executed
by any test): added an OPTIONAL, explicitly-labeled-as-non-substitutive
text-level regression pin,
`tests/host/test_run_abort_source_pin.py` (4 tests), following
`test_block_toolbox_order.py`'s own precedent of regex-asserting on `.ts`
source text without compiling it. Verified (via `git stash`) that all 4
fail against the pre-change `test/test.ts` and pass against the
post-change version — a real regression guard against someone silently
reverting the abort wiring, not proof the logic works at runtime. Real
verification is deferred to (a) the sprint's build checkpoint (ticket
007), and (b) bench/manual confirmation — NOT performed here (autonomous
overnight execution context, no bench access): the exact steps are
`RUN:tour:wheels` (or `:robot`) then `RUN:abort` partway through, over
USB or the zavaz radio relay, confirming the tour stops within one tick,
reports `TOUR:end:abort`, and emits no further `OCAL:` lines after the
abort.

Full `tests/host/` suite: 468 passed (no regressions from this ticket's
changes).

## Implementation Plan

### Approach

1. Add `let aborted = false` near `let touring = false` (line 21).
2. Add the `RUN:abort` handler near the other `onRun` registrations.
3. Edit `tickedMove()` to check `aborted` inside its loop and return early
   (calling `stopMove()` first) when set.
4. Edit `tourRobot()`, `tourWheels()`, `tourWorld()`: reset `aborted =
   false` at start; check `aborted` after each `for`-loop iteration and
   `break`; replace the terminal `diffDrive.emitLine("TOUR:end")` with the
   reason-aware line.
5. Add the scope-boundary comment to `tourWorld()`'s loop.

### Files to modify

- `test/test.ts` — `aborted` flag, `RUN:abort` handler, `tickedMove()`,
  `tourRobot()`, `tourWheels()`, `tourWorld()`.

### Files explicitly NOT to modify

- `src/blocks/world.ts` (out of sprint scope — see boundary note above).
- `straightRun()`, `leverCal()`, and the `goto`/`face`/`pivot` RUN
  handlers — the sprint's own Solution and SUC-002 scope this ticket to
  the three *tours* specifically; those other handlers are named in the
  issue's problem statement as sharing the same class of gap but are not
  in this ticket's or this sprint's stated scope. Do not widen it.

### Testing plan

`test/test.ts` includes CODAL/PXT types (`control.millis()`,
`diffDrive.*`, `basic.*`) and is explicitly **not** host-compilable —
`tests/host/README.md`'s own "What this does NOT cover yet" names
"PXT/simulator behavior (`src/*.ts`, `test/test.ts`, `test/testrig.ts`) —
a separate MakeCode-side test surface, not this one." No `pytest` test
can execute `tickedMove()`/`tourWheels()`/the new `RUN:abort` handler
directly. Given that boundary:

- **New tests**: none possible at the `tests/host/` level for this
  ticket's TS logic itself. If a text-level regression pin is wanted
  (following `tests/host/test_block_toolbox_order.py`'s precedent of
  regex-asserting on `.ts` source text without compiling it), a small
  host test asserting that `test/test.ts` contains an `onRun("abort", ...)`
  registration and that `tickedMove()`'s body references `aborted` is
  optional and not a substitute for real verification — do not treat a
  passing text-grep as proof the abort logic works.
- **Real verification**: this ticket's actual proof is (a) the sprint's
  build checkpoint (ticket 007), which proves `test.ts` still compiles
  and packages, and (b) manual/bench confirmation — send `RUN:tour:wheels`
  then `RUN:abort` partway through over the bench USB link or the zavaz
  radio relay, and confirm the tour stops within one tick and reports
  `TOUR:end:abort` with no further `OCAL:` lines. Record this
  confirmation (or, if deferred per the sprint's autonomous-execution
  context, the reason it was deferred and the exact steps to run it) in
  this ticket or the sprint's own closing notes.
- **Existing tests to run**: none in `tests/host/` are affected by this
  ticket (it touches only `test/test.ts`).
- **Verification command**: `uv run pytest` is not applicable to this
  ticket's own change; rely on the build checkpoint (ticket 007) and the
  manual bench confirmation above.

### Documentation updates

- None required beyond the in-code scope-boundary comment at
  `tourWorld()`'s for loop (Acceptance Criteria above). The sprint's
  stop-taxonomy table (ticket 006) covers the *stop mechanisms*
  specifically; tour-abort behavior is a related but separate surface
  the sprint's own Use Cases (SUC-002) already documents.

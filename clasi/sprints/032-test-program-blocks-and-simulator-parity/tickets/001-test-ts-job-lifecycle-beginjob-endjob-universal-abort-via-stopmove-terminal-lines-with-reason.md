---
id: "001"
title: "test.ts job lifecycle: beginJob/endJob, universal abort via stopMove, terminal lines with reason"
status: open
use-cases: [SUC-001]
depends-on: []
github-issue: ""
issue: "test-program-job-lifecycle-abort-profile-terminal-line.md"
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# test.ts job lifecycle: beginJob/endJob, universal abort via stopMove, terminal lines with reason

## Description

Confirmed against the CURRENT `test/test.ts` (not the issue's own
pre-030/031 prose): only 3 of ~11 `onRun()` motion handlers
(`tourRobot`, `tourWheels`, `tourWorld`) reset `aborted`, apply a
shaping profile, and emit a `<VERB>:end:<reason>` terminal line.
`squareTour`/`infinityTour`/`snakeTour`/`diamondTour`/`circleRun` never
call `openLoopProfile()`/`closedLoopProfile()` at all (they inherit
whatever profile the previous RUN command left set) and never emit a
reason-tagged terminal line — they emit `DBG:tour=...` then
`basic.showIcon(IconNames.Yes)` with nothing else. `pivot`/`face`/
`arc`/`straight` (`straightRun`)/`cal` (`leverCal`)/`goto` never reset
`aborted` and emit terminal lines with NO reason field at all
(`PIVOT:end`, `ARC:end`, `FACE:end`, `STRAIGHT:end:<pose>`, `GOTO:end`).
Because `tickToCompletion()` (the shared tick loop these all go
through) unconditionally checks the GLOBAL `aborted` flag and calls
`stopMove()` the moment it's true, a stale `aborted=true` left by an
earlier `RUN:abort` silently truncates the very next `RUN:pivot`/
`straight`/`face`/`cal`/`arc` to one tick, and that handler's own
terminal line reports it as if nothing happened.

Separately, `RUN:abort`'s handler (`test.ts` line ~608) only sets
`aborted = true` — it never calls `diffDrive.stopMove()`. For a
handler that already checks `aborted` in its own tick loop
(`tickToCompletion`/`tickArcSampled`), that's enough. It is NOT enough
for `RUN:goto` (world-frame `goToWorld()`), whose internal tick loop
lives in `src/blocks/world.ts` and has no visibility into `test.ts`'s
`aborted` variable at all — so today, `RUN:abort` sent during a
`goToWorld` leg cannot interrupt that leg; it only prevents the NEXT
leg/tour iteration from starting (checked via `if (aborted) break`
after the call returns). Since sprint 028 the abort/clearestop bypass
already runs NESTED inside whatever tick loop is currently active
(confirmed: `src/comms/protocol.h`'s own documented reentrant dispatch
path), so having the `abort` handler itself call `diffDrive.stopMove()`
makes abort interrupt ANY currently-active move in ANY file
immediately — no `aborted`-flag plumbing needed in `world.ts` at all.

## Acceptance Criteria

- [ ] A single `beginJob(name: string)` function in `test.ts`: sets
      `touring = true`, clears `aborted = false`, applies the shaping
      profile `name` calls for (open-loop vs closed-loop, matching what
      each handler already selects today), and resets `maxGap = 0`.
      Returns/no-ops per the existing `if (touring) return` re-entrancy
      guard convention (decide whether `beginJob` itself performs that
      guard check and returns a bool, or callers keep the guard and
      `beginJob` is unconditional — pick whichever keeps every call
      site as a two-line preamble, and document the choice at
      `beginJob`'s own definition).
- [ ] A single `endJob(reason: string)` function: emits
      `emitLine("GAP:" + maxGap)` then the terminal
      `<VERB>:end:<reason>` line, then `touring = false`. Reason is one
      of `"ok"`/`"abort"`/`"estop"`, using the SAME priority order
      `tourRobot`'s existing comment documents (abort takes priority
      over a coincident e-stop, since abort reflects operator intent).
      Decide (and document at the call site) how `endJob` learns the
      verb name for the `<VERB>:` prefix — a parameter, or read back
      via `diffDrive.runCommandText()`/the current run name.
- [ ] Every motion-issuing `onRun()` handler
      (`tour`/`straight`/`cal`/`goto`/`face`/`pivot`/`arc`/`square`/
      `infinity`/`snake`/`diamond`/`circle`, and the tour functions
      they call) uses `beginJob()`/`endJob()` instead of hand-rolling
      any subset of reset/profile/terminal-line — no handler is left
      with its OLD ad hoc terminal line format alongside the new
      mechanism.
- [ ] `squareTour`/`infinityTour`/`snakeTour`/`diamondTour`/`circleRun`
      now apply an explicit profile (decide open- vs closed-loop per
      tour, matching the speed/behavior each already assumes today —
      note in the ticket's own commit message which was chosen and
      why, since this is an observable behavior change for these five
      tours, not a pure refactor).
- [ ] The `abort` handler (`test.ts` line ~608) calls
      `diffDrive.stopMove()` in addition to `aborted = true`.
- [ ] A `RUN:goto` sent, then a `RUN:abort` sent while it's still
      running, stops the CURRENT leg (not just prevents the next one)
      — this is the one behavior in this ticket that most wants a
      source-level confirmation that `stopMove()`'s call path
      (`_endMove()`, `shims.cpp`) is unconditional and reachable from
      inside `world.ts`'s own `while (_tickDrive())` loop with no
      further plumbing (Open Question 1 in `sprint.md`'s Architecture
      section — confirm via a host/source-pin test, not just reasoning
      about it).
- [ ] `test_run_abort_source_pin.py` is extended: it must now assert
      `beginJob`/`endJob` exist and that EVERY motion-issuing
      `onRun()` handler's body references `beginJob(`, not just the
      three original tours.
- [ ] `test_run_tour_programs.py` is extended: every one of the eleven
      verbs (not just the three original tours) emits a terminal line
      containing `:end:` followed by a reason token.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/test_run_abort_source_pin.py tests/host/test_run_tour_programs.py` plus the full `tests/host/` suite (no sprint-close gate exists yet to catch a regression missed by a scoped run on ticket work outside a sprint — but this IS sprint ticket work with a lock, so a scoped run of the two files above plus anything else that imports/parses `test/test.ts` is sufficient per `.claude/rules/source-code.md`).
- **New tests to write**: extend the two files named above per the Acceptance Criteria; a new source-pin assertion that `diffDrive.stopMove()` appears inside the `abort` handler's body (regex/AST on `test.ts`).
- **TS type-check**: run `npx tsc --noEmit` (or the project's real gate — check for a `tsconfig.json`/`package.json` script first) against `test/test.ts` after the refactor; note in the PR/commit which form of type-check was used (`npx tsc --noEmit` needs only `node_modules`; a full `pxt build` in `.tmp/` also proves the simulator body compiles, per `extension-publish-pipeline` project memory, and is preferred if time allows).
- **Verification command**: `uv run pytest tests/host/test_run_abort_source_pin.py tests/host/test_run_tour_programs.py -v`

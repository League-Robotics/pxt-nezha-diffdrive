---
id: '001'
title: 'One named shaping profile per RUN: handler, recorded in the capture'
status: done
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: run-handlers-leave-a-global-shaping-profile.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# One named shaping profile per RUN: handler, recorded in the capture

## Description

`test/test.ts`'s `RUN:` handlers each set a different SUBSET of the
shaping knobs (`setTaperWindows`, `setTaperFloors`, `setRampMs`,
`setDefaultSpeed`, `setDefaultYawRate`) and never restore them, so the
same command behaves differently depending on what preceded it. This
is a reproducibility hole: every accuracy number this sprint (and
sprints 010/011) has taken is only meaningful if the shaping in force
during that run is known and recorded.

Measured inconsistency in the current file (line numbers as of this
sprint's base):

| Handler | taper windows | taper floors | ramp | default speed | default yaw rate |
|---|---|---|---|---|---|
| `openLoopProfile()` (line ~153) | 400, 180 | 25, 12 | 400 | 20 | 90 |
| `tourWorld()` (line ~313, inline duplicate of the above) | 400, 180 | 25, 12 | 400 | 20 | 90 |
| `RUN:goto` (line ~481, inline) | 120, 80 | 45, 35 | 180 | **40** | 120 |
| `RUN:face` (line ~498, inline) | -- | -- | -- | -- | 90 |
| `RUN:pivot` (line ~525, inline) | 400, 180 | 25, 12 | 400 | -- | `pivotYawRate` |

`RUN:face` is the sharpest instance: it sets only the yaw rate. Run
after `RUN:goto`, it closes its heading loop under `RUN:goto`'s fast
closed-loop taper/floor/ramp (120/80, 45/35, 180) instead of the
accuracy profile -- same command, different physical behaviour,
determined entirely by whatever ran before it. Nothing in the emitted
transcript records which profile was actually in force for any of
these handlers.

`tourWorld()` is a second, quieter instance of the same root cause: it
does not call `openLoopProfile()`, it re-types every one of its five
values inline, identically. That is not currently a behavioural bug
(the numbers match), but it is exactly the kind of duplication that
turns into one the next time someone tunes `openLoopProfile()` and
forgets `tourWorld()`'s copy.

`RUN:pivot` already shows the intended discipline for taper/floor/ramp
(re-sets all three every time, matching `openLoopProfile()`'s values)
but still does it by re-typing the literals rather than calling the
function, and it leaves `defaultSpeed` unset (harmless for a pure
in-place pivot, but stale/inherited rather than deterministic).

## What to change

1. Add a second named profile function, `closedLoopProfile()`,
   holding `RUN:goto`'s current values (taper 120/80, floors 45/35,
   ramp 180, default speed 40, default yaw rate 120) -- the
   fast/closed-loop counterpart to the existing `openLoopProfile()`.
2. Every handler that currently sets shaping knobs inline calls
   exactly one of the two named profile functions on entry, with no
   partial/inline `setTaper*`/`setRampMs`/`setDefaultSpeed`/
   `setDefaultYawRate` calls left outside `openLoopProfile()`,
   `closedLoopProfile()`, or an explicit one-off override placed
   IMMEDIATELY AFTER a call to one of them (so the deviation from the
   named profile is visible in the handler body, not buried).
   Concretely:
   - `tourWorld()`: replace its inline duplicate of
     `openLoopProfile()`'s five literals with a call to
     `openLoopProfile()`. No behaviour change.
   - `RUN:goto`: replace its inline literals with a call to the new
     `closedLoopProfile()`. No behaviour change.
   - `RUN:pivot`: replace its inline taper/floor/ramp literals with a
     call to `openLoopProfile()`, then set
     `diffDrive.setDefaultYawRate(pivotYawRate)` immediately after as
     the documented one-off override. This is a **small, intentional
     behaviour change**: `defaultSpeed` becomes deterministically 20
     (from `openLoopProfile()`) instead of stale-inherited from
     whatever handler ran previously. Record this in the ticket's
     completion notes -- it does not affect a pure pivot's motion
     (pivots do not use `defaultSpeed`), but it is worth stating
     explicitly rather than leaving it implicit.
   - `RUN:face`: currently the one genuine bug. Call
     `openLoopProfile()` on entry, then
     `diffDrive.setDefaultYawRate(90)` immediately after as the
     documented one-off (numerically a no-op today, since
     `openLoopProfile()`'s own default yaw rate is already 90 --
     but it makes the anchor explicit and visible instead of leaving
     `RUN:face` at the mercy of whatever profile the previous handler
     left behind, which is the actual bug being fixed). Anchoring on
     the accuracy profile rather than `closedLoopProfile()` is the
     right choice here: `RUN:face`'s job is to close a heading loop
     precisely, which is what the accuracy taper is tuned for.
   - `tourRobot()`, `tourWheels()`, `straightRun()`: already call
     `openLoopProfile()` -- confirm they still do and need no change.
   - `leverCal()` (`RUN:cal`) is intentionally OUT OF SCOPE: it sets
     its own slow, careful speed/yaw-rate pair (15, 45) that is not
     one of the two profiles in the issue's table, and the issue does
     not flag it. Leave it as-is.
3. Every handler's `DBG:` line records which named profile was in
   force, so a capture can be attributed to a known shaping
   configuration. For handlers that already emit a `DBG:` line
   (`tourRobot`, `tourWheels`, `tourWorld`, `straightRun`), append the
   profile name to it, e.g. `DBG:tour=robot:profile=open`. For
   handlers that emit none today (`RUN:goto`, `RUN:face`,
   `RUN:pivot`), add one, e.g. `DBG:goto:profile=closed`,
   `DBG:face:profile=open`, `DBG:pivot:profile=open`. Exact wire
   syntax is an implementation choice -- keep it consistent with the
   existing `DBG:<key>=<value>` convention -- but the profile name
   must be present and must be emitted from inside (or immediately
   after) the handler that actually set it, not inferred after the
   fact.

## Acceptance Criteria

- [x] `closedLoopProfile()` exists in `test/test.ts` and holds exactly
      `RUN:goto`'s current values (taper 120/80, floors 45/35, ramp
      180, default speed 40, default yaw rate 120).
- [x] `grep -n "setTaperWindows\|setTaperFloors\|setRampMs\|setDefaultSpeed\|setDefaultYawRate" test/test.ts`
      shows every call site is inside `openLoopProfile()`,
      `closedLoopProfile()`, or is a one-off override immediately
      following a call to one of the two, with a comment naming which
      profile it deviates from and why.
- [x] `tourWorld()` calls `openLoopProfile()` instead of duplicating
      its literals inline.
- [x] `RUN:goto` calls `closedLoopProfile()` instead of its inline
      literals.
- [x] `RUN:pivot` calls `openLoopProfile()` then overrides
      `defaultYawRate` to `pivotYawRate`; the resulting
      `defaultSpeed`-becomes-deterministic behaviour change is noted
      in the ticket's completion notes.
- [x] `RUN:face` calls `openLoopProfile()` then overrides
      `defaultYawRate` to 90, so it no longer inherits whatever
      profile the previous handler left behind.
- [x] Every handler's `DBG:` line (new or existing) names the active
      profile.
- [x] No RUN verb string, no numeric shaping value used by
      `tourRobot`/`tourWheels`/`straightRun`, and no existing
      `tests/tools/test_run_verbs.py` assertion changes as a result of
      this ticket (the fix is internal to how the values get set, not
      which values or which verbs exist).

## Completion Notes

- `closedLoopProfile()` added directly below `openLoopProfile()` in
  `test/test.ts`, holding exactly `RUN:goto`'s prior inline values
  (taper 120/80, floors 45/35, ramp 180, speed 40, yaw rate 120).
- `tourWorld()`, `RUN:goto` now call the two named profiles instead of
  duplicating/typing literals inline. `tourRobot()`, `tourWheels()`,
  `straightRun()` already called `openLoopProfile()` and needed no
  change beyond their `DBG:` line.
- `RUN:pivot` and `RUN:face` now call `openLoopProfile()` on entry,
  each followed immediately by a commented one-off
  `setDefaultYawRate()` override (`pivotYawRate` for pivot, 90 for
  face) -- the override is visible in the handler body, not buried.
- **Behaviour change (intentional, per plan)**: `RUN:pivot`'s
  `defaultSpeed` is now deterministically 20 (from
  `openLoopProfile()`) instead of stale-inherited from whichever
  handler last ran. This does not affect pivot motion -- pivots do not
  use `defaultSpeed` -- but it removes a latent nondeterminism.
- `RUN:face` no longer inherits `RUN:goto`'s closed-loop taper/floor/
  ramp when run right after a `RUN:goto`; it is now always anchored on
  the accuracy (open-loop) profile, which was the actual bug in the
  issue. Numerically the yaw-rate override is a no-op (both are 90),
  but taper/floors/ramp were the silent part of the bug and are now
  fixed too.
- `RUN:cal` (`leverCal()`) left untouched, out of scope per the plan --
  its own 15/45 speed/yaw pair is not one of the two named profiles
  and the issue does not flag it.
- Every handler's `DBG:` line now carries `:profile=open` or
  `:profile=closed`: `DBG:tour=robot:profile=open`,
  `DBG:tour=wheels:profile=open`, `DBG:tour=world:profile=open`,
  `DBG:straight=<cm>:profile=open`, `DBG:goto:profile=closed`,
  `DBG:face:profile=open`, `DBG:pivot:profile=open`.
- Verification: `grep -n "setTaperWindows\|setTaperFloors\|setRampMs\|setDefaultSpeed\|setDefaultYawRate" test/test.ts`
  shows exactly 14 matches: 5 inside `openLoopProfile()` (lines
  154-158), 5 inside `closedLoopProfile()` (lines 166-170), 2 inside
  `leverCal()`/`RUN:cal` (out of scope, unchanged), and 2 one-off
  overrides immediately after an `openLoopProfile()` call (`RUN:face`
  line 511, `RUN:pivot` line 546), each with an explanatory comment.
  `uv run pytest tests/tools/test_run_verbs.py` -- 22 passed, no RUN
  verb string or assertion changed. `npx tsc --noEmit -p tsconfig.json`
  -- clean, no errors (ticket 006 still runs the real `pxt build`
  checkpoint).

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/test_run_verbs.py`
  -- confirms this ticket has not touched any RUN verb string. There
  is no host-side unit harness for `test/test.ts`'s TypeScript handler
  bodies in this repo (only `pxt build`/`tsc` type-checks it, per
  sprint 019's build-checkpoint findings) -- ticket 006's build
  checkpoint is where this file's compile-correctness is actually
  verified.
- **New tests to write**: none in the Python/C++ host suite -- this
  ticket's substance is a TypeScript-side refactor with no new
  observable surface a host test could pin. Verification is the
  mechanical `grep` check above (record its output in completion
  notes) plus ticket 006's real `pxt build` confirming the file still
  compiles.
- **Verification command**: `grep -n "setTaperWindows\|setTaperFloors\|setRampMs\|setDefaultSpeed\|setDefaultYawRate" test/test.ts`
  followed by `uv run pytest tests/tools/test_run_verbs.py`.

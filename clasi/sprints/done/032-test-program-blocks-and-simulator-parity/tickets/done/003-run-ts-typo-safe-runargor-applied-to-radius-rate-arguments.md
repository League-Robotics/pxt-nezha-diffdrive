---
id: '003'
title: 'run.ts: typo-safe runArgOr(), applied to radius/rate arguments'
status: done
use-cases:
- SUC-001
depends-on:
- '001'
github-issue: ''
issue: test-program-job-lifecycle-abort-profile-terminal-line.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# run.ts: typo-safe runArgOr(), applied to radius/rate arguments

## Description

Confirmed in current `src/blocks/run.ts`: `runArg(i)` calls
`parseFloat(runArgText(i))` and maps BOTH "no such argument" (empty
text) and "argument present but unparseable" (`NaN`) to the SAME
return value, `0`. `test/test.ts`'s `circle` handler
(`diffDrive.onRun("circle", ...)`) then does
`diffDrive.runArgCount() > 0 ? diffDrive.runArg(0) : 30` — so
`RUN:circle:abc` has `runArgCount() == 1` (the text "abc" IS present)
and `runArg(0) == 0` (parseFloat("abc") is NaN, mapped to 0), producing
`circleRun(0, ...)`: eight 45° pivots-in-place with zero radius,
silently, instead of either erroring or falling back to the documented
default of 30. The same pattern applies to `infinity`/`snake`'s radius
arguments.

## Acceptance Criteria

- [x] `run.ts` gains `runArgOr(i: number, fallback: number): number`
      that returns `fallback` when the argument is ABSENT
      (`runArgText(i) == ""`) but returns `NaN` (or another
      unambiguous not-a-number sentinel — pick one and document it at
      the function) when the argument is PRESENT but unparseable,
      rather than silently substituting `fallback` or `0` for that
      case. Decide and document the exact contract (three distinct
      outcomes: absent → fallback; present+valid → the value;
      present+invalid → NOT the fallback, NOT 0) at the function's own
      doc comment.
  - [x] Distinguish "present but invalid" from a legitimately-zero
        argument (`RUN:circle:0` is a valid, if degenerate, radius) —
        the sentinel must not collide with a real value a caller might
        need.
- [x] `runArgOr` additionally rejects non-positive values for
      arguments that are geometrically a radius (per the Solution
      text's "rejects NaN and non-positive radii") — decide whether
      this validation lives inside `runArgOr` itself (parameterized,
      e.g. a `minExclusive` argument) or as a thin wrapper each radius
      call site uses; state the choice and why.
- [x] `test.ts`'s `circle`/`infinity`/`snake` handlers use `runArgOr`
      (or its radius-validating wrapper) instead of the
      `runArgCount() > 0 ? runArg(0) : default` pattern, and now emit a
      wire-visible error/ignore signal (an `ERR:` or `DBG:` line —
      match whatever error-reporting convention `test.ts` already uses
      elsewhere) rather than silently running with radius 0 when given
      an unparseable or non-positive radius argument.
- [x] `runArg()`'s own existing contract (0 for absent-or-invalid) is
      UNCHANGED for every other existing call site — this ticket adds
      `runArgOr`/its wrapper as a new, opt-in function; it does not
      change `runArg()`'s signature or behavior, to avoid an
      unreviewed behavior change at every other place `runArg()` is
      already called (`pivot`, `face`, `arc`, `straight`,
      `seedxy`, `turnrate`, etc. — leave these as `runArg()` unless a
      specific reason to change one surfaces during implementation, in
      which case note it).
- [x] A host test pins `runArgOr`'s three-way contract directly
      (absent → fallback; present+valid → value; present+invalid →
      neither) and pins that `RUN:circle:abc` no longer silently
      produces a radius-0 circle.

## Implementation Notes

- **Sentinel**: `NaN`, per the AC's own suggestion. Never collides
  with a real argument (`parseFloat("0")` is `0`, not `NaN`).
- **minExclusive lives inside `runArgOr` itself**, as a third,
  defaulted parameter (`minExclusive: number = NaN`, meaning "no
  bound"), not a per-call-site wrapper. Every current radius call site
  wants the identical rule ("reject <= 0"), so a wrapper would just be
  `runArgOr(i, fb, 0)` written out three times with a different name;
  parameterizing keeps the one function as the single place the rule
  lives, and a future non-radius caller can still get plain typo
  detection by leaving the third argument off.
- **Rejection behavior: refuse the job outright with a wire-visible
  `ARGERR:<verb>:radius:<raw text>` line, never a silent
  substitution and never a crash.** No existing "generic argument
  error" convention existed to match (`OERR:` is OTOS-specific); this
  introduces `ARGERR:` as that convention, patterned on `OERR:`'s own
  `<CODE>:<detail>` shape. Chosen over "fall back to the default and
  say so" because this is a student-facing verb: a fallback-with-log
  still runs *something* on a typo, which is exactly the "looks
  plausible" failure BT-22 exists to remove, whereas a refusal that
  names the bad text is unambiguous and still fully wire-visible to a
  bench tool or a student watching the console.
- **Scope note on the ticket title's "radius/rate arguments":** the
  acceptance criteria above (and the Solution text's "rejects NaN and
  non-positive radii") only ever specify a *radius* validation, and AC
  #4 explicitly lists `turnrate` among the call sites to leave
  unchanged unless a specific reason surfaced. None did — `turnrate`
  sets `pivotYawRate` directly from `runArg(0)`, with no fallback
  default to preserve (a bad value there already yields `0`, and
  `RUN:pivot` deterministically re-applies whatever rate is current
  every call, so there is no silent-plausible-run hazard shaped like
  BT-22's). Implemented per the acceptance criteria as written:
  `runArgOr` applied to `circle`/`infinity`/`snake`'s radius argument
  only; `turnrate` and every other existing `runArg()` site
  (`pivot`, `face`, `arc`, `straight`, `seedxy`) untouched.
- **Unknown `RUN:` verb names (the numeric-`RUN` sibling defect noted
  in `.claude/rules/`) are OUT OF SCOPE for this ticket.** That failure
  lives in `wireRunDispatch()`'s by-name loop in `run.ts` (a name with
  no matching handler is silently a no-op) — a different function and
  a different fix shape (the dispatcher itself would need an
  unmatched-name signal, e.g. via `onRunCommand`) than typo-safe
  *argument* parsing inside one already-matched handler. Left as a
  candidate for its own ticket/issue rather than folded in here.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` (`run.ts`'s argument-parsing contract may be pinned by an existing test — search for `runArg` in `tests/host/` before assuming there is none).
- **New tests to write**: a source-pin/TS-shape test for `runArgOr`'s three-way contract; a source-pin test that `circle`/`infinity`/`snake` no longer use the bare `runArgCount() > 0 ? runArg(0) : default` pattern for their radius argument.
- **TS type-check**: `npx tsc --noEmit`.
- **Verification command**: `uv run pytest tests/host/ -k "run_arg or run_dispatch" -v`

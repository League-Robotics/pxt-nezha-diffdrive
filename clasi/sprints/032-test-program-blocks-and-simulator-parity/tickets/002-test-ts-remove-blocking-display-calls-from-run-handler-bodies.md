---
id: '002'
title: 'test.ts: remove blocking display calls from RUN handler bodies'
status: open
use-cases:
- SUC-002
depends-on:
- '001'
github-issue: ''
issue: test-program-job-lifecycle-abort-profile-terminal-line.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# test.ts: remove blocking display calls from RUN handler bodies

## Description

Since sprint 028, every `onRun()` handler executes on the protocol
fiber itself (nested, reentrant dispatch — confirmed accurate in
`src/comms/protocol.h`'s own doc comments, which this ticket does NOT
need to touch). `basic.showNumber()` (~750 ms per call on real
hardware), `basic.showString()`, and `basic.pause()` all block the
calling fiber for their full duration. Confirmed still present by
direct grep of `test/test.ts`: `basic.showNumber(i + 1)` inside every
tour's per-leg loop body, `basic.pause(400)` (twice) inside `leverCal`,
and `basic.showString(...)` at the end of nearly every tour/handler.
While any one of these blocks, PING/ESTOP/RUN:abort sent to the robot
is not serviced until the call returns — the exact opposite of what
ticket 001's `stopMove()`-based universal abort needs to land promptly.

This ticket depends on ticket 001 because both touch the same handler
bodies; doing the job-lifecycle refactor first means this ticket edits
the POST-refactor `beginJob`/`endJob` shape rather than the old
hand-rolled one.

## Acceptance Criteria

- [ ] No `basic.pause(...)`, `basic.showString(...)`, or
      `basic.showNumber(...)` call remains anywhere in the call tree of
      any `onRun()` handler in `test.ts` (i.e. not just the handler's
      own body — also any helper function it calls, like `legToward()`,
      `leverCal()`, `circleRun()`).
- [ ] Per-iteration progress display (`basic.showNumber(i + 1)` inside
      tour loops) is either removed (relying on the already-non-blocking
      `DBG:`/telemetry lines for progress) or replaced with a
      non-blocking display primitive — decide which per Open Question 2
      in `sprint.md`'s Architecture section; record the choice and why
      in the commit message.
- [ ] Any END-of-handler display feedback (e.g. `basic.showString("A")`,
      `basic.showIcon(IconNames.Yes)`) that is NOT inside the timed
      per-tick loop is fine to keep AS IS if it happens strictly after
      `endJob()` has already emitted the terminal wire line — the
      concern here is servicing the wire DURING the job, not a final
      one-shot display after the job is already reported done. Confirm
      this distinction explicitly for each call site touched (don't
      blanket-delete every display call in the file).
- [ ] Button handlers (`input.onButtonPressed`) are unaffected by this
      ticket — they are not `onRun()` handlers and do not block wire
      responsiveness the same way (no bench operator is waiting on
      PING while a physical button is held).
- [ ] `basic.showIcon(IconNames.Yes)` at the end of the tour functions:
      confirm (source-read `pxt-microbit`'s own `basic.ts` or the
      MakeCode docs, not assumption) whether `showIcon` blocks the
      same way `showNumber`/`showString` do; if it does, it needs the
      same treatment; if it's a single-icon set with no scroll
      animation, it may be fine to leave as a final non-blocking write.
      State which was found, with the source checked, in the commit
      message (measurement-citations.md discipline: source-read is not
      "measured," say which it is).
- [ ] A source-pin test in `tests/host/` enforces "no blocking display
      call inside an `onRun()` handler's call tree" going forward
      (regex/AST scan of `test.ts`, following
      `test_run_abort_source_pin.py`'s own "source-text pinning, not
      compiled" precedent stated in that file's own module docstring).

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` (full host suite — this ticket changes control flow inside `test.ts` broadly enough that a scoped run risks missing an unrelated source-pin file that also greps `test.ts`).
- **New tests to write**: the source-pin test described in the last Acceptance Criterion above — check whether it fits naturally as an extension of `test_run_abort_source_pin.py` (same file, same "source-text pinning" style) or deserves its own file; prefer extending the existing one unless it grows unwieldy.
- **TS type-check**: `npx tsc --noEmit` (or a real `pxt build` in `.tmp/` if time allows — this ticket removes/replaces MakeCode API calls, which a `tsc`-only check cannot fully validate since `pxt`-provided globals may not resolve the same way).
- **Verification command**: `uv run pytest tests/host/ -v`

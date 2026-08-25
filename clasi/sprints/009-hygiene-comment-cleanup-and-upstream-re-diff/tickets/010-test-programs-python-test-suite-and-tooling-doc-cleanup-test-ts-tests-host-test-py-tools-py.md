---
id: '010'
title: Test programs, Python test suite, and tooling doc cleanup (test/*.ts, tests/host/test_*.py,
  tools/*.py)
status: open
use-cases: []
depends-on: []
github-issue: ''
issue: comment-cleanup-work-order.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Test programs, Python test suite, and tooling doc cleanup (test/*.ts, tests/host/test_*.py, tools/*.py)

## Description

Apply `comment-audit.md`'s items for `test/test.ts` (2 REWRITE),
`test/testrig.ts` (0 — KEEP only), the nine `tests/host/test_*.py`
files (~13 REWRITE, mostly dropping stale sprint-003-ticket prefixes
from docstrings), and `tools/otos_levercal.py`/`rotation_check.py`/
`tour_square.py` (4 REWRITE total; all other `tools/*.py` files are
KEEP-only), corrected per `verify-comments.md`.

**This sprint is behavior-neutral — two items in this ticket must stay
comment-only even though the audit's own handoff notes call them code
bugs:**

1. `tools/otos_levercal.py`'s docstring says the tool drives `RUN:8`
   (and `--verify` drives `RUN:14`); current firmware answers only
   `RUN:cal`/`RUN:cal:1` — the docstring and the code (line ~87, which
   still sends `RUN:8`/`RUN:14`) agree with each other but not with
   reality. The audit says "fix tool + docstring together" — **do not
   fix the tool's behavior in this sprint**; rewrite the docstring to
   state what the tool *actually does* (sends `RUN:8`/`RUN:14`) rather
   than implying it works, and note the mismatch. Record the audit's
   broader "handoff-2" class (`pivot_truth.py`, `rotation_check.py`,
   `truth_check.py`, `turn_sweep.py`, `tour_capture.py`/`tour_watch.py`/
   `tour_run.py`/`practice_chart.py` all speak a vocabulary current
   firmware doesn't answer, per the audit's handoff note 2) in this
   ticket's completion notes as a filing request for the team-lead —
   do not create a new CLASI issue mid-ticket, and do not fix any of
   these tools' behavior.
2. `tools/rotation_check.py`'s docstring says "firmware rotationScrub
   1.040, from a pivot measured at 369.2 deg" — stale: firmware now
   carries `rotationalSlip` 0.952, with the *opposite sign of effect*
   (per `motion_engine.h`, ticket 002's cluster). Rewrite the "why it
   exists" paragraph to reference the resolved value, consistent with
   ticket 002's authoritative derivation — do not reintroduce the
   0.915/1.040 confusion ticket 002 is specifically protecting against.

## Acceptance Criteria

- [ ] `test/test.ts`'s "used to log the previous values" comment
      (69-71) and `tourWorld` taper comment (229-239, 10-line
      misdiagnosis history) are compressed per the audit — the latter
      to 3 lines stating the resolved 200 mm/s value and correcting
      the "taper too slow" misdiagnosis to name the actual yaw-taper
      double-count bug.
- [ ] `test/testrig.ts` is confirmed KEEP-only (×8 blocks) — no edits.
- [ ] Each of the nine Python test files'
      (`test_kernel_harness.py`, `test_motion_engine_primitives.py`,
      `test_motion_engine_reductions.py`, `test_motion_engine_gotow.py`,
      `test_regression_post_move_neutral.py`,
      `test_regression_yaw_taper_pure_turn.py`, `test_wire_grammar.py`,
      `test_wire_motion_verbs.py`, `test_wire_reliability.py`)
      docstring/module-header and light in-body items are rewritten
      per the audit — drop sprint/ticket-number prefixes and "used to
      be in a later ticket" framing, keep the pipeline/session-scoped-
      compile rationale and every commit-anchor reference (e.g.
      `test_regression_post_move_neutral.py`'s `3e919e5`,
      `test_regression_yaw_taper_pure_turn.py`'s `bd9f005`) — these
      name the regression under test and must survive.
- [ ] `tools/otos_levercal.py`'s docstring is corrected per the
      Description above (states reality, doesn't fix the code); the
      linear-fit derivation and p0-exclusion measurement content is
      otherwise kept verbatim (confirmed KEEP by the audit).
- [ ] `tools/rotation_check.py`'s docstring is corrected per the
      Description above, consistent with `motion_engine.h`'s current
      derivation (ticket 002).
- [ ] `tools/tour_square.py`'s stale "permanent fix... needs a flash"
      claim (1-15, contradicted by `main.ts`'s already-shipped
      curvature cap) is corrected, and the self-contradictory
      split-vs-not-split block (134-142) is reduced to its actual
      conclusion: `// Splitting long legs was tried and made things
      worse (SE 10.7 -> 24.0 cm); one hop per corner.`
- [ ] The handoff-2 filing note (Description, item 1) is recorded in
      this ticket's completion notes.
- [ ] All remaining `tools/*.py` files (`camlink.py`, `robotlink.py`,
      `make_deploy.py`, `otos_bench.py`, `pivot_truth.py`,
      `practice_chart.py`, `reposition.py`, `tour_capture.py`,
      `tour_chart.py`, `tour_closedloop.py`, `tour_practice.py`,
      `tour_run.py`, `tour_watch.py`, `truth_check.py`,
      `turn_sweep.py`) are confirmed KEEP-only — no edits.

## C++11 gate coverage

**Not applicable.** `test/test.ts`/`test/testrig.ts` are TypeScript,
governed by the PXT compile (proven by ticket 012's build checkpoint,
since these are `pxt.json` `testFiles` promoted into the deploy build
by `make_deploy.py`), not the C++11 gate. The Python files (`tests/host/
test_*.py`, `tools/*.py`) are pure host-side Python — no compiled-
language build gate applies to them at all.

## Testing

- **Existing tests to run**: `uv run pytest` (full suite — this ticket
  touches the test files themselves, so the safest verification is
  that they still collect and pass unchanged).
- **New tests to write**: none — comment/docstring-only change; no
  tool behavior changes (see Description).
- **Verification command**: `uv run pytest`

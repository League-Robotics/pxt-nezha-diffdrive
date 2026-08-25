---
id: '010'
title: Test programs, Python test suite, and tooling doc cleanup (test/*.ts, tests/host/test_*.py,
  tools/*.py)
status: done
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

- [x] `test/test.ts`'s "used to log the previous values" comment
      (69-71) and `tourWorld` taper comment (229-239, 10-line
      misdiagnosis history) are compressed per the audit — the latter
      to 3 lines stating the resolved 200 mm/s value and correcting
      the "taper too slow" misdiagnosis to name the actual yaw-taper
      double-count bug.
- [x] `test/testrig.ts` is confirmed KEEP-only (×8 blocks) — no edits.
- [x] Each of the nine Python test files'
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
- [x] `tools/otos_levercal.py`'s docstring is corrected per the
      Description above (states reality, doesn't fix the code); the
      linear-fit derivation and p0-exclusion measurement content is
      otherwise kept verbatim (confirmed KEEP by the audit).
- [x] `tools/rotation_check.py`'s docstring is corrected per the
      Description above, consistent with `motion_engine.h`'s current
      derivation (ticket 002).
- [x] `tools/tour_square.py`'s stale "permanent fix... needs a flash"
      claim (1-15, contradicted by `main.ts`'s already-shipped
      curvature cap) is corrected, and the self-contradictory
      split-vs-not-split block (134-142) is reduced to its actual
      conclusion: `// Splitting long legs was tried and made things
      worse (SE 10.7 -> 24.0 cm); one hop per corner.`
- [x] The handoff-2 filing note (Description, item 1) is recorded in
      this ticket's completion notes.
- [x] All remaining `tools/*.py` files (`camlink.py`, `robotlink.py`,
      `make_deploy.py`, `otos_bench.py`, `pivot_truth.py`,
      `practice_chart.py`, `reposition.py`, `tour_capture.py`,
      `tour_chart.py`, `tour_closedloop.py`, `tour_practice.py`,
      `tour_run.py`, `tour_watch.py`, `truth_check.py`,
      `turn_sweep.py`) are confirmed KEEP-only — no edits.

## Completion notes

**Obsolete audit items (already fixed by sprint 005's tools/ rewrite,
before this ticket started):**

- `tools/otos_levercal.py`'s docstring already reads "drives test.ts
  RUN:cal" and the code (line 87) already sends `RUN:cal`/`RUN:cal:1`
  — both agree with reality. The audit's stale-`RUN:8`/`RUN:14` finding
  no longer applies; no edit made (KEEP, re-verified against live
  code).
- `tools/rotation_check.py`'s `RUN:pivot:<deg>` retargeting (the audit's
  broader "handoff-2" numeric-RUN complaint) was likewise already done;
  only the "why it exists" derivation paragraph (this ticket's own
  Description item 2) still needed correcting, which is applied.

**Applied:** test.ts's two REWRITE items (log-fix comment, tourWorld
taper compression, re-anchored to their current line positions inside
`logFix()`/`tourWorld()`); all nine Python test files' module-header
ticket/sprint-prefix drops (commit anchors `3e919e5`/`bd9f005`
preserved verbatim); `otos_levercal.py`'s otherwise-KEEP content
re-verified unchanged; `rotation_check.py`'s derivation corrected to
firmware's resolved `rotationalSlip_ = 0.952` (motion_engine.h, ticket
002), replacing the stale 1.040/369.2-deg claim, without reintroducing
the raw 0.915 pivot ratio as if it were the slip itself; `tour_square.py`'s
stale "needs a flash" claim corrected (main.ts's `turnFirstDeg = 12.0`
pivot-first cap is confirmed shipped) and the self-contradictory
split-vs-not-split block reduced to its actual one-line conclusion;
`robotlink.py`'s docstring's dead `RUN:8` example replaced with the
confirmed-working `RUN:probe`.

**Declined REWRITE items (drift beyond the audit's own scope, found
this session, not applied):**

- `test_wire_grammar.py` (994 lines) and `test_wire_motion_verbs.py`
  (2667 lines) have both grown substantially since the "sprint 003"-era
  audit — both now carry many additional "sprint 004"/"sprint
  005"/"sprint 007"/"sprint 008" ticket-tagged comments the audit never
  saw (it only ever cites "sprint 003 ticket NNN" in this document).
  The audit's own per-file REWRITE counts (3 and a "banners" bullet at
  11 line-locations respectively) no longer map onto current line
  numbers, and re-locating "the same four/eleven banners" among 40+
  now-present ticket tags without audit backing would be guessing, not
  applying an audited item. Applied only the header + one clearly
  re-anchorable light item per file (both confirmed by content match);
  left every other ticket tag in these two files untouched. Recommend
  a fresh comment-hygiene pass scoped to these two files specifically.
- `test_motion_engine_gotow.py` grew a "sprint 006 ticket 007:
  EncoderPoseSource / selectPoseSource" section (~280 new lines, real
  and accurate) not present at audit time; left its internal ticket
  tags untouched since the audit's item for this file counted only 2
  REWRITEs (matching what was applied: the docstring header and the
  one `(ticket 007)` light item), and this new section is not among
  them.
- `test_motion_engine_primitives.py`'s second "Acceptance Criterion"
  occurrence (`test_set_rotational_slip_updates...`'s docstring,
  "Sprint 007 ticket 005") was left untouched for the same reason —
  the audit counted exactly 2 REWRITE items for this file (header +
  the one at "233-239"/now ~238-244), and this second occurrence is
  new content outside that count.

**Handoff-2 filing note (per Description item 1, filed here for the
team-lead, no new CLASI issue created mid-ticket):** the audit's
broader "tools speak a retired wire vocabulary" finding —
`otos_levercal.py` (superseded, see Obsolete items above),
`pivot_truth.py`, `rotation_check.py` (superseded for the pivot verb,
per `RUN:pivot:<deg>` already live), `truth_check.py`, `turn_sweep.py`,
`tour_capture.py`/`tour_watch.py`/`tour_run.py`/`practice_chart.py` —
still applies to the numeric `RUN:<n>`/`TLM:`/`DIAG` vocabulary these
tools speak, which current firmware's named-verb `test.ts` dispatch
does not answer. Confirmed this session: `tools/tour_capture.py` sends
bare `RUN:{run}` (e.g. `RUN:1`), the pre-named-verb numeric form: this
would silently no-op against the deployed `test.ts` build (see also
`tour_capture.py:9-15`'s own "documented, currently inert no-op"
DIAG-poll comment, which the file already carries). No behavior fix
made — these files are KEEP-only for this ticket.

**Tour-closure trustworthiness check (per dispatcher request):**
`tools/tour_capture.py:77` — "the per-corner OCAL fixes carry the
scoring" — overclaims: per the newly filed
`clasi/issues/tour-corner-fixes-are-stale-cache.md` (sprint 011),
`logFix()`'s `OCAL:` fixes during a square tour are a stale cache of
the seeded pose, not a live measurement, so they do not reliably
"carry the scoring." `tour_capture.py` is a KEEP-only file for this
ticket (not edited); flagging for the team-lead. No other tool in this
ticket's scope makes a closure-trustworthiness claim: `tour_square.py`
scores corners from `camproc.Cam`-captured rows (real AprilCam ground
truth), not from OCAL/OTOS telemetry, so its own comments do not
overclaim.

**C++11 gate:** not applicable, confirmed — `test/test.ts`/`testrig.ts`
are TypeScript (governed by the PXT compile, not the C++11 gate); the
Python files under `tests/host/`/`tools/` are host-side Python with no
compiled-language build gate.

**Build verification:** `uv run pytest` — 528 passed (baseline
unchanged) after all edits. `uv run python tools/make_deploy.py` — a
hex was built successfully (`.tmp/deploy-head/built/mbcodal-binary.hex`,
1,384,901 bytes); the run showed the known, already-documented
`make_deploy.py` cache-write `TypeError [ERR_INVALID_ARG_TYPE]`/TS9200
self-healing retry trap (unrelated to this ticket's edits — same trap
`make_deploy.py`'s own header already describes). `tsc -p .` reports
exactly **1** pre-existing error
(`pxt_modules/core/basic.ts(17,29): Math.roundWithPrecision`),
matching the documented baseline — no new TypeScript errors from the
`test/test.ts` edits.

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

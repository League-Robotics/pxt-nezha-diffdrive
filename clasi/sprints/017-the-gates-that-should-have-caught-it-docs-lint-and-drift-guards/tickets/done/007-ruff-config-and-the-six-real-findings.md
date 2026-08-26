---
id: '007'
title: ruff config and the six real findings
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: no-lint-or-typecheck-gate.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# ruff config and the six real findings

## Description

`uvx ruff check tools tests` with no configuration in `pyproject.toml`
reports 211 findings; only 6 are real:

| Rule | Count | Real? | Notes |
|---|---:|---|---|
| `F811` redefined-while-unused | 91 | No | pytest fixture shadowing |
| `I001` unsorted imports | 39 | Style | the `sys.path.insert` prelude makes strict sorting awkward by construction |
| `EXE001` shebang not executable | 17 | Style | |
| `RUF100` unused noqa | 12 | Housekeeping | |
| `RUF059`, `PLW1510`, `RUF007` | 27 | Mostly intentional | |
| **`F401` unused import** | **4** | **Yes** | |
| **`B904` raise-without-from** | **2** | **Yes** | |
| `B023` loop-variable closure | 2 | No | thread joined within the iteration |
| `B008` call in default arg | 1 | Deliberate, but obscure | |

The `B904` findings are the ones with real consequences, not just tidiness:
`tools/tour_watch.py:150` and `tools/truth_check.py:144` do
`raise SystemExit(str(e)) ` inside an `except` block, which loses the
original exception chain -- specifically the `DeadTelemetryError` chain,
which is the one exception the fail-loud guard in that code path exists to
raise. Losing the chain defeats the guard's purpose in a traceback.

`pyproject.toml` currently has no `[tool.ruff]` section at all -- `ruff` is
running with pure defaults, which is why everything from pytest fixture
idioms to shebang bits shows up as "findings."

This is Python tooling only. No `src/` firmware code is affected (ruff
doesn't touch TypeScript or C++; see ticket 008 for the TS-side gate).

## What to change

1. Add a `[tool.ruff.lint]` block to `pyproject.toml` selecting a narrow,
   meaningful rule set -- `F` (pyflakes), `E9` (syntax errors), `B`
   (bugbear) is the set named in the source issue. Ignore `F811` under
   `tests/` (pytest fixture redefinition is idiomatic there) -- either via
   a per-file-ignore in `pyproject.toml` or by enabling
   `flake8-pytest-style` so fixtures are understood natively; per-file-ignore
   is simpler and sufficient. Do not enable `I001` (import sorting) given
   the `sys.path.insert` prelude constraint noted above, unless you first
   confirm it can coexist without forcing an awkward reordering -- if in
   doubt, leave it off and note why in a config comment.
2. Fix the four `F401` unused imports: `pytest` in
   `tests/host/test_wire_motion_completion.py:38`; `os`/`pytest` in
   `tests/tools/test_camproc.py:24,28`; `argparse` in
   `tools/otos_bench.py:22`.
3. Fix the two `B904` raise-without-from findings by adding `from e` (or the
   caught exception's name) so the original chain is preserved:
   `tools/tour_watch.py:150` and `tools/truth_check.py:144`.
4. Leave `B023` (loop-variable closure at `tools/truth_check.py:165`'s
   `def sampler(prev=math.degrees(c0))`) and `B008` alone -- both are
   flagged as not-real or deliberate-but-obscure in the source review;
   don't fix what isn't broken, but if the config naturally flags them,
   either confirm they're genuinely benign (thread joined within the
   iteration for B023) or add a narrow `noqa` with a one-line reason.
5. Confirm `ruff check tools tests` is clean under the new config.

## Acceptance Criteria

- [x] `pyproject.toml` has a `[tool.ruff.lint]` block selecting `F, E9, B`
      (or equivalent), with `F811` ignored under `tests/`.
- [x] The 4 real `F401` unused-import findings are fixed. (Re-measured: 6,
      not 4 -- see completion notes.)
- [x] The 2 real `B904` raise-without-from findings are fixed, preserving
      the exception chain. (Re-measured: 4, not 2 -- see completion notes.)
- [x] `ruff check tools tests` exits clean (0 findings) under the committed
      config.
- [x] No behavior change beyond the import removals and `from e` additions
      -- this is a lint-hygiene ticket, not a refactor. (Plus two further
      zero-behavior-change classes surfaced by re-measurement and fixed
      the same way -- see completion notes.)

## Completion notes (2026-08-26)

**Re-measured rather than trusting the ticket's counts -- the tree has
drifted since the review.** Selecting exactly `F, E9, B` (as specified)
surfaces more than the six findings this ticket names:

- **`F401` unused imports: 6, not 4.** The four named
  (`test_wire_motion_completion.py`, `test_camproc.py` x2,
  `otos_bench.py`) plus two new ones in
  `tests/host/test_goto_block_regression.py:46` (`LEFT`, `RIGHT`
  imported from `test_motion_engine_reductions`, unused). All 6 fixed
  the same way (import removed after confirming zero other reference
  in the file).
- **`B904` raise-without-from: 4, not 2.** The two named
  (`tour_watch.py:150`, `truth_check.py:144`) plus the exact same
  `except tlm.DeadTelemetryError as e: raise SystemExit(str(e))`
  pattern, losing the same chain, at `tools/rotation_check.py:85` and
  `tools/tour_capture.py:63` -- not touched by sprint 017 ticket 002's
  `tour_watch.py` edit, so not a byproduct of it; these two simply
  weren't in the original review's sample. All 4 fixed identically
  (` from e` appended).
- **Two further finding classes ticket 007 didn't anticipate, both
  fixed as zero-behavior-change lint hygiene** (in scope under a literal
  `select = ["F", "E9", "B"]`, same as the six named): `F541`
  f-string-without-placeholder (2: `tour_closedloop.py:148`,
  `tour_practice.py:224` -- extraneous `f` prefix removed, string
  content unchanged) and `B007` unused-loop-control-variable (4:
  `pivot_truth.py:83`, `reposition.py:47`, `tour_run.py:226`,
  `tour_square.py:70` -- renamed to `_name` per ruff's own convention,
  confirmed genuinely unused in each loop body first).
- **`B905` zip-without-explicit-strict: 15, NOT fixed -- deferred with
  a documented project-wide `ignore`.** Unlike the classes above, each
  site needs a per-call-site correctness judgment (would a length
  mismatch there indicate a real bug worth `strict=True` failing loudly
  on, or is truncation the relied-upon behavior, making `strict=False`
  the honest documentation of current behavior?) that a lint-hygiene
  ticket has no basis to make blind. Reviewing all 15 is a
  reasonably-sized follow-up, not part of this ticket -- flagging here
  so it isn't silently dropped. See the `ignore = ["B905"]` entry's own
  comment in `pyproject.toml`.
- **`B023`/`B008` (the ticket's named 2+1): confirmed genuinely benign
  as described** (`truth_check.py`'s `sampler` closure over
  `stop`/`cam_total` -- both are redefined fresh each pivot iteration,
  but `th.join()` always completes, or times out, before the next
  iteration rebinds them, so the closure never observes a stale
  binding) and left in place with narrow, reasoned `# noqa` comments
  rather than fixed or blanket-ignored, per the ticket's own guidance.
- **Did not add a pytest wrapper for `ruff check`.** The sprint
  briefing's top-level note says "consider wiring it into the test
  suite"; this ticket's own Testing section is explicit that no new
  test is needed ("`ruff check` itself is the gate... a CI/checklist
  step, not a pytest assertion") -- followed the ticket's own, more
  specific instruction.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/ tests/host/`
  (the import removals and exception-chain fixes touch files with existing
  test coverage -- confirm nothing broke, especially around
  `DeadTelemetryError` handling in `tour_watch.py`/`truth_check.py`).
- **New tests to write**: none required -- `ruff check` itself is the gate;
  no new pytest test is needed to prove ruff is configured (a CI/checklist
  step, not a pytest assertion).
- **Verification command**: `ruff check tools tests` (expect clean exit)
  and `uv run pytest tests/tools/ tests/host/`.

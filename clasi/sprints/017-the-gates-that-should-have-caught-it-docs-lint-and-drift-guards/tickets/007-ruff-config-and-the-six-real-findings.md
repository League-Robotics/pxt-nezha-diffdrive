---
id: '007'
title: ruff config and the six real findings
status: open
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

- [ ] `pyproject.toml` has a `[tool.ruff.lint]` block selecting `F, E9, B`
      (or equivalent), with `F811` ignored under `tests/`.
- [ ] The 4 real `F401` unused-import findings are fixed.
- [ ] The 2 real `B904` raise-without-from findings are fixed, preserving
      the exception chain.
- [ ] `ruff check tools tests` exits clean (0 findings) under the committed
      config.
- [ ] No behavior change beyond the import removals and `from e` additions
      -- this is a lint-hygiene ticket, not a refactor.

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

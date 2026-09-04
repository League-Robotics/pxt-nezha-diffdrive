---
status: pending
sprint: '033'
---

# Host harness: tsc gate skips with a reason, pin the run_tour travelCalib mirror, gate ruff, session-scope motion_lib, compile the uncovered TUs

Priority: **Low** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Finding: TL-19 ([tools-and-tests](../../../docs/code-review/2026-09-02/raw/tools-and-tests.md)). Triage #23.

## Description

Baseline this review: 922 passed, 1 failed --
`test_typescript_typecheck.py::test_tsc_noemit_is_clean` because
`node_modules/.bin/tsc` is absent in a fresh worktree; an environment
precondition surfacing as a red test. Also: seven `pxt.h`-bound
translation units are compiled by nothing; the C++11 gate passes `-I src`
the real build lacks; Python mirrors of `shims.cpp` are what some tests
test; one assert-less test; eleven identical `motion_lib` compiles per
session; `run_tour.py`'s travelCalib mirror is unpinned; ruff is not
gated.

## Remedy

`pytest.skip` with a reason when `tsc` is absent (and say how to install
it); pin the mirror; a `[tool.ruff]` gate in CI; session-scope the
compile fixture; either compile the seven TUs with a `pxt.h` stub or
record in `tests/DESIGN.md` why not.

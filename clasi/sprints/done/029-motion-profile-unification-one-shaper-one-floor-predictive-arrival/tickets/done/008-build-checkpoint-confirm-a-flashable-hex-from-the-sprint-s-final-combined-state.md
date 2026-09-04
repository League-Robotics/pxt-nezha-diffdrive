---
id: 008
title: 'Build checkpoint: confirm a flashable hex from the sprint''s final combined
  state'
status: done
use-cases:
- SUC-001
- SUC-002
- SUC-003
- SUC-004
depends-on:
- '005'
- '006'
- '007'
- 009
- '010'
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint: confirm a flashable hex from the sprint's final combined state

## Description

The mandatory, always-last build-checkpoint ticket, per the standing
convention in `docs/design/design.md`'s "Host-vs-target language
standard" section and `src/DESIGN.md` §11: this sprint touches
build-eligible source (`src/core/`, `src/motion/`, `src/shims.cpp`,
`src/comms/`, `src/blocks/`) across seven prior tickets at
`-std=c++11`-vs-`-std=c++20` risk (the host suite compiles at C++20;
both real targets compile at C++11), so a green host suite alone is
never evidence the sprint's final state actually compiles for the
robot. Depends on every ticket that touches `src/` or `test/test.ts`
(001-004 transitively through 007; 005 and 006 are the two remaining
independent branches).

Run `tools/make_deploy.py` against this sprint's own final combined
state (all eight tickets' changes merged, not a single ticket's diff in
isolation) and confirm a flashable hex results, using the triage
`build()` already implements (`tools/DESIGN.md`'s "Build checkpoint
triage" section): hard compile failures reported immediately; the
documented benign packaging-abort shape retried once automatically;
anything else reported as a failure requiring investigation, not
silently retried.

## Acceptance Criteria

- [x] `uv run python tools/make_deploy.py --robot tovez --radio-link` (the robot ticket 007
      used) from the sprint's final state (c12f2d3 + radio-robot-lib eafccd2 bake) produced
      `.tmp/deploy-head/built/binary.hex`, 1,689,686 bytes, attempt 1, every `nezha-diffdrive`
      `.cpp` compiled (build log 2026-09-04 13:03; bake lines: rotational_slip 1.01, lag_s 0.13,
      stop_distance_mm 0, motors left 2/−1 right 1/+1).
- [x] No packaging abort and no compile failure on the first attempt.
- [x] Flashed to tovez over zilch 13:05 (`mbdeploy deploy --remote tovez`): `HELLO` ->
      `device NEZHA2 robot tovez 2314287040`, `STATUS` at boot `otos=1 i2cf=0`.
- [x] Full suite `uv run pytest tests/host tests/tools -q`: 1163 passed in 145.65 s (2026-09-04 13:07).

## Implementation Plan

**Approach**: Run the build against the sprint branch's own tip
(after ticket 007 lands), not a synthetic combination — this is
specifically checking what will actually merge.

**Files to create/modify**: None expected (this ticket verifies, it
does not implement) — unless the build surfaces a real defect, in
which case fix it in the file(s) it names, per the triage's own hard-
failure guidance (`tools/DESIGN.md`).

**Testing plan**: `uv run python tools/make_deploy.py`; read the
triage verdict; if `UNKNOWN`/`HARD_FAILURE`, investigate per
`tools/DESIGN.md`'s "Build checkpoint triage" section before retrying
by hand.

**Documentation updates**: None expected, unless a real defect is found
and fixed, in which case document the fix the same way any other
ticket would.

---
id: '010'
title: 'Host harness: skip the tsc gate with a reason, gate ruff, pin the third travelCalib,
  one motion_lib fixture'
status: open
use-cases: [SUC-007]
depends-on: []
github-issue: ''
issue: host-harness-gaps.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Host harness: skip the tsc gate with a reason, gate ruff, pin the third travelCalib, one motion_lib fixture

## Description

Four host-harness gaps the review's own baseline run surfaced (922
passed, 1 failed).

**a. The `tsc` gate is an environment precondition reported as a defect.**
`tests/host/test_typescript_typecheck.py` opens with
`assert _TSC.is_file()`, so in a fresh worktree with no `npm install` the
suite's **only** failure is "node_modules is absent". Verified
2026-09-06: `node_modules/.bin/tsc` exists in this checkout, so the test
passes here -- the defect is real but only visible in a fresh tree. That
is the worst shape for it: it teaches the next agent, in a fresh
worktree, that a red suite is normal. The assertion message is good and
its reasoning is right (it deliberately refuses to fall back to
`npx tsc`, which resolves to an unrelated decoy package here) -- keep the
reasoning, change the outcome from fail to skip.

**b. `motion_lib` is compiled thirteen times per session.** Thirteen
files under `tests/host/` each define their own session-scoped
`motion_lib` fixture compiling the identical
`diffdrive.cpp + motion_engine.cpp + motion_engine_shim.cpp` list, and
there is **no `tests/host/conftest.py` at all**. `F811` is silenced
repo-wide in `pyproject.toml` partly because of this. The review counted
eleven; it is thirteen today. The suite takes ~149 s and this is most of
it.

**c. `travelCalib` has a third, unpinned copy.**
`tests/tools/test_travel_calib_drift.py` pins
`motion_engine.h` against `tour_chart.py`. `tests/system/run_tour.py`
carries `TRAVEL_CALIB = 0.7878` as a third copy that nothing checks --
and this exact constant is the one that drifted before (0.8102 mirrored
well past the 0.7878 camera-measured update).

**d. `ruff` is configured but not gated.** `pyproject.toml` has
`[tool.ruff.lint] select = ["F","E9","B"]` and now declares `ruff>=0.16`
in the dev group, but nothing in `tests/` or CI runs it. The review found
5 findings, all outside the two pytest roots: `tests/dev/closure.py`
(B007), `tests/dev/sweep_tcp.py` (F401), `tests/system/run_tour.py`
(F401 x2), `tests/system/tourfile.py` (B904).

**e. TL-18, riding along.**
`tests/tools/test_make_deploy_robot_channel.py` has a test *named*
`test_vevov_build_carries_channel_4` and a docstring saying vevov's
"configured channel is 4", beside its own derivation table asserting
`("vevov", (37, 43))`. The tests pass because they write their own
synthetic config -- so the *names* teach the wrong fleet fact.
`make_deploy.py`'s comments say the same. The fleet table in
`.claude/rules/playfield-testing.md` has vevov on **37/43**.

## Acceptance Criteria

- [ ] With `node_modules` absent the `tsc` test **skips with a reason**
      naming `npm ci` (or `npm install`); with it present it still runs
      and still fails on a real type error. Keep the existing
      no-`npx`-fallback reasoning in the skip message.
- [ ] One `tests/host/conftest.py` provides the session-scoped
      `motion_lib` fixture; all thirteen local definitions are deleted;
      the compile happens **once** per session.
- [ ] The `motion_lib` source list lives in exactly one place. If any of
      the thirteen compiled a *different* list, say so and handle it --
      do not silently unify two different fixtures into one.
- [ ] `tests/system/run_tour.py`'s `TRAVEL_CALIB` is pinned against
      `motion_engine.h` by extending
      `tests/tools/test_travel_calib_drift.py`.
- [ ] `ruff` is gated by a test that runs `ruff check` over `tools/` and
      `tests/` and fails on findings; the 5 existing findings are fixed
      so it passes. A test is the right gate here, not a CI workflow --
      this repo has one workflow (`publish-extension.yml`) and the
      developer signal is `uv run pytest`.
- [ ] With `ruff` gated, revisit the repo-wide `F811` silence in
      `pyproject.toml` -- if the conftest removal is what it existed for,
      narrow or delete it. If it is still needed elsewhere, say where.
- [ ] The `test_make_deploy_robot_channel.py` test names and docstrings,
      and `make_deploy.py`'s "vevov, ch 4" comments, say "the configured
      channel, whatever it is" rather than naming a stale number.
- [ ] `uv run pytest -q` is measurably faster; note the before/after in
      the ticket record.

## Implementation Plan

### Approach

Do (b) first -- it makes every later run cheaper. Then (a), (c), (d),
(e). (d) last, because fixing lint findings in `tests/dev/` and
`tests/system/` touches files the other items also touch.

For (a): `pytest.skip(reason=..., allow_module_level=False)` inside the
test, not a `skipif` on an import-time constant -- the reason string is
the whole point and it should name the fix.

### Files

- `tests/host/conftest.py` (new); the thirteen
  `test_motion_engine_*.py` / `test_goto_*.py` /
  `test_stop_move_zeros_continuous_drive.py` / `test_profile_probe.py`
  files (enumerate with `grep -rl 'def motion_lib' tests/host/`).
- `tests/host/test_typescript_typecheck.py`.
- `tests/tools/test_travel_calib_drift.py`, `tests/system/run_tour.py`.
- `pyproject.toml` (the `F811` silence), `tests/dev/closure.py`,
  `tests/dev/sweep_tcp.py`, `tests/system/tourfile.py`.
- `tests/tools/test_make_deploy_robot_channel.py`, `tools/make_deploy.py`.
- A new `tests/tools/test_ruff_clean.py` (or wherever fits the existing
  layout -- read `tests/DESIGN.md` first, it states the
  subdirectory-by-type policy).

### Re-anchoring

The issue says eleven `motion_lib` fixtures; it is thirteen. Enumerate
from the tree, not from the issue.

## Testing

- **Existing tests to run**: `uv run pytest tests/host -q` and
  `uv run pytest tests/tools -q` (foreground, scoped). This ticket
  touches enough of `tests/host/` that running that whole directory is
  the scoped run, not an escalation.
- **New tests to write**: the ruff gate; the extended travelCalib drift
  test covering the third copy.
- **How to verify the skip without deleting node_modules**: temporarily
  point the test's `_TSC` path at a nonexistent file via
  `monkeypatch`, and assert the outcome is a skip whose reason mentions
  `npm`. Do **not** move or delete the real `node_modules` -- other tests
  and the TypeScript typecheck depend on it.
- **Verification command**: `uv run pytest tests/host tests/tools -q`

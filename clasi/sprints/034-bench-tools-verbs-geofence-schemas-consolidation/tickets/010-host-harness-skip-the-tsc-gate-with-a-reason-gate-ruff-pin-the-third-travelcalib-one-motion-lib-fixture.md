---
id: '010'
title: 'Host harness: skip the tsc gate with a reason, gate ruff, pin the third travelCalib,
  one motion_lib fixture'
status: done
use-cases:
- SUC-007
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

- [x] With `node_modules` absent the `tsc` test **skips with a reason**
      naming `npm ci` (or `npm install`); with it present it still runs
      and still fails on a real type error. Keep the existing
      no-`npx`-fallback reasoning in the skip message.
- [x] One `tests/host/conftest.py` provides the session-scoped
      `motion_lib` fixture; all thirteen local definitions are deleted;
      the compile happens **once** per session.
- [x] The `motion_lib` source list lives in exactly one place. If any of
      the thirteen compiled a *different* list, say so and handle it --
      do not silently unify two different fixtures into one.
- [x] `tests/system/run_tour.py`'s `TRAVEL_CALIB` is pinned against
      `motion_engine.h` by extending
      `tests/tools/test_travel_calib_drift.py`.
- [x] `ruff` is gated by a test that runs `ruff check` over `tools/` and
      `tests/` and fails on findings; the 5 existing findings are fixed
      so it passes. A test is the right gate here, not a CI workflow --
      this repo has one workflow (`publish-extension.yml`) and the
      developer signal is `uv run pytest`.
- [x] With `ruff` gated, revisit the repo-wide `F811` silence in
      `pyproject.toml` -- if the conftest removal is what it existed for,
      narrow or delete it. If it is still needed elsewhere, say where.
- [x] The `test_make_deploy_robot_channel.py` test names and docstrings,
      and `make_deploy.py`'s "vevov, ch 4" comments, say "the configured
      channel, whatever it is" rather than naming a stale number.
- [x] `uv run pytest -q` is measurably faster; note the before/after in
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

## Implementation record

**a. `tsc` gate skips.** `tests/host/test_typescript_typecheck.py`'s
module-level `assert _TSC.is_file()` became a `pytest.skip()` inside the
test, with the reason naming `npm ci` (or `npm install`) AND carrying
the existing no-`npx`-fallback reasoning (the decoy `tsc` package this
environment resolves) forward verbatim in substance. Verified by
`test_missing_tsc_skips_rather_than_fails`, which `monkeypatch.setitem`s
the module's `_TSC` global to a `tmp_path` that does not exist and
asserts the outcome is a `pytest.skip.Exception` whose reason mentions
both `npm` and `npx`. The real `node_modules` is never moved or deleted;
with it present the gate still runs `tsc --noEmit` and still fails on a
real type error.

**b. One `motion_lib` fixture. Fixture count: THIRTEEN** (the issue said
eleven; `grep -rl 'def motion_lib' tests/host/` says thirteen today).
New `tests/host/conftest.py` holds `MOTION_SHIM_SOURCES`,
`_bind_motion_lib()` and the one session-scoped `motion_lib` fixture;
all thirteen local definitions, their thirteen copies of the source list
and their thirteen `_bind`/`_bind_probe`/`_bind_reconcile` functions are
deleted, along with the now-dead `pathlib`/`_TEST_DIR`/`_SRC_DIR`
preludes and the `# noqa: F401 -- motion_lib re-exported as a fixture`
imports in the four files that borrowed the fixture by import
(`test_kernel_reference_handling.py`, `test_regression_post_move_neutral.py`,
`test_regression_yaw_taper_pure_turn.py`, `test_segment_lazy_origin.py`).

**The source lists were IDENTICAL, all thirteen** -- `core/diffdrive.cpp`
+ `motion/motion_engine.cpp` + `motion/velocity_shaper.cpp` +
`tests/host/motion_engine_shim.cpp` (note `velocity_shaper.cpp`, which
the issue's own three-file description predates). Nothing was silently
unified. The thirteen `_bind` functions were merged into one union
binder after an `ast`-level check across all 70 bound symbols found
**zero** signature disagreements -- no symbol was bound two different
ways anywhere, so the union is well defined rather than a pick-one.
Consequence documented in `conftest.py` and `tests/host/DESIGN.md`:
those files now share ONE `ctypes.CDLL`, so
`test_segment_lazy_origin.py`'s call-time `_bind_rebase()`
(`meRebasePosition`, the one symbol outside the union) mutates shared
state and must stay signature-compatible.

**Timing, MEASURED 2026-09-06, `uv run pytest tests/host tests/tools -q`
on this checkout:**

| | tests | wall |
|---|---|---|
| before (at 8fb1bce) | 1719 passed | **75.30 s** (`/usr/bin/time -p` real 75.79) |
| after | 1722 passed | **57.88 s** and **58.47 s**, two runs (real 58.30 / 58.87) |

The three extra tests are this ticket's own (the tsc-skip test, the
run_tour travelCalib pin, the ruff gate). The remaining ~58 s is not the
compile: `tests/host` alone is now 28.90 s and `tests/tools` alone is
28.00 s, the latter untouched by this ticket.

**c. Third `travelCalib` pinned.** `tests/system/run_tour.py`'s
`TRAVEL_CALIB` is now checked against `src/motion/motion_engine.h`'s
`travelCalib_` by a second test in
`tests/tools/test_travel_calib_drift.py` (text-based, like its sibling:
`run_tour.py` opens a socket to a robot at import). Negative check run:
setting `run_tour.py`'s constant to the historical 0.8102 fails the new
test (`assert 0.7878 == 0.8102`) and leaves the tour_chart test passing,
so the two pins are independent. `run_tour.py` gained a comment saying
it is a mirror, naming the guard.

**d. `ruff` gated.** New `tests/tools/test_ruff_clean.py` shells the
concrete `ruff` binary (PATH, then `.venv/bin/`, never a bare name) over
`tools/` and `tests/`, passes no `--select` so the rule set stays
`pyproject.toml`'s, and folds ruff's output into the failure message. A
missing `ruff` skips with a reason naming `uv sync`. Verified both ways:
passes clean, and fails naming `F401` when a canary file with an unused
import is dropped into `tests/tools/`.

**Findings fixed: TEN, not the ticket's five** (that list is from
2026-09-02 and had gone stale; it also missed everything outside the
two `pytest` roots' neighbours). All ten:

| file | rule |
|---|---|
| `tests/dev/closure.py` | B007 (`for i` -> `for _`) |
| `tests/dev/sweep_tcp.py` | F401 (`sys`) |
| `tests/host/test_motion_engine_primitives.py` | F841 (`fdv = _ready(e)` -> `_ready(e)`) |
| `tests/host/test_wire_motion_verbs.py` | B007 + F841 x2 (`default_cruise`, a dead assignment whose comment survives as a comment) |
| `tests/system/run_tour.py` | F401 x2 (`os`, `tourfile.Twist`) |
| `tests/system/tourfile.py` | B904 (`raise ... from None`) |
| `tests/tools/test_field_dance_accel_bake.py` | F401 (`pytest`) |
| `tests/tools/test_fieldlink.py` | F401 (`pytest`) |

plus the ~29 F401s item (b)'s own deletions created (unused `ctypes`,
`compile_shared_lib`, `pytest`, `_bind` imports), fixed with
`ruff check --select F401 --fix`. The pre-existing B007 in
`tools/linefollow/stage.py` was already fixed by ticket 009.

**F811 decision: NARROWED, not deleted.** The conftest removal is NOT
what the silence existed for. With `[tool.ruff.lint.per-file-ignores]`
removed entirely, `ruff check tools tests` reports **115 F811** -- all
of them in `tests/host/`, and **none** of them about `motion_lib`. They
are the deliberate cross-module fixture imports of `kernel_lib`, `wa`,
`wg`, `wire_lib` and `motion_verb_lib` (heaviest in
`test_wire_reliability.py`, `test_wire_telemetry_frame.py` and
`test_wire_telemetry_projection.py`), which the native harness uses on
purpose. `tests/tools/`, `tests/dev/` and `tests/system/` have zero. So
the ignore is narrowed from `"tests/**"` to `"tests/host/**"`, with that
finding written into the comment beside it.

**e. TL-18.** `test_vevov_build_carries_channel_4` and
`test_tovez_build_carries_channel_3` are now
`test_a_named_robots_build_carries_its_configured_channel` and
`test_a_different_robot_gets_its_own_configured_channel`;
`test_unspecified_robot_default_carries_channel_4` is
`test_unspecified_robot_carries_the_default_robots_configured_channel`,
and its docstring no longer claims vevov is on 4. The synthetic configs
now use `_FIXTURE_CHANNEL`/`_FIXTURE_CHANNEL_B` (62/64 -- even, so
`_read_robot_radio_group()`'s name-derived-channel-needs-a-group guard
does not fire on a config that deliberately omits `radio_group`), under
a comment saying the numbers are fixture values and where the real fleet
table lives. **No test now names any board's real channel** except the
derivation table, where `("vevov", (37, 43))` is the derivation's own
output and correct. `tools/make_deploy.py`'s three "vevov, ch 4"
comments, `tools/DESIGN.md`'s matching sentence, and
`src/comms/radio_transport.h`'s own `// (vevov's fleet-assigned
channel...)` (comment only, in scope for the same reason) now say the
checked-in 4/10 is a legacy placeholder that every build overwrites from
the robot's own JSON, and point at
`.claude/rules/playfield-testing.md` for who is actually where.

**Design docs**, minimal direct updates only (ticket 012 does the truth
pass): `tests/host/DESIGN.md` (the conftest, the fixture, the shared-CDLL
consequence, the timing), `tests/tools/DESIGN.md` (the ruff gate as this
directory's one stated subprocess exception, the third travelCalib pin,
the invariant, the Exposes entry), `tests/DESIGN.md` (the `tools/`
row and paragraph). The overlay copies under
`clasi/sprints/034-.../design/` were not touched.

**Verification command**, foreground, this turn:
`uv run pytest tests/host tests/tools -q` -> **1722 passed in 58.47s**.
`uv run ruff check tools tests` -> **All checks passed!**

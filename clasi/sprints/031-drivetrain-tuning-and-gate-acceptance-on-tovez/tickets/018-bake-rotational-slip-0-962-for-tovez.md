---
id: 018
title: Bake rotational_slip 0.962 for tovez
status: in-progress
use-cases: []
depends-on: []
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Bake rotational_slip 0.962 for tovez

Type (b): programmer-implementable, no hardware.

## Description

tovez's `rotational_slip` was measured at 0.962 on 2026-09-05 (MEASURED
tovez 2026-09-05, `captures/session-b-20260905/ticket016/g1-slip0962/`,
12 alternating +-90 deg pivots, mean|err| 1.531 deg vs 4.604 deg
uncalibrated; the value was verified on the wire by a raw `GET` before
the run — see `docs/sprint-031-postmortem.md` §2.3). Today it is only
ever set live over the wire via `SET rotational_slip` and is lost on
every power cycle, so tovez ships with no turn calibration unless
someone happens to `SET` it in the same session.

Bake 0.962 the same way ticket 015 baked `twistHoldGain`: find where
per-robot constants reach the build — `tools/make_deploy.py`'s
per-robot injection, `radio-robot-lib/config/robots/tovez.json`'s
`geometry`/`firmware_bake` block (if present), and `src/shims.cpp`'s
`MotionEngine` seeding are the three places ticket 015 touched for its
constant — and put 0.962 wherever tovez's per-robot bake already lives.
Do **not** add it as a fleet-wide default in `motion_engine.h`: tigez's
independently measured value is 0.9617 (`tigez-turn-calibration-20260903.md`)
and vevov's differs again, so a shared default would be wrong for at
least one other board the moment it's read.

Cite the capture in a trailing `// MEASURED ...` comment at the point
where the value is set, per `.claude/rules/measurement-citations.md`.

## Acceptance Criteria

- [x] A tovez build reports `get rotational_slip 0.962000` on the wire
      with no `SET` having been sent since boot — pinned by a host test
      of the bake path (or a test of `make_deploy.py`'s per-robot
      injection, whichever mechanism the fix uses).
- [x] No other robot's `rotational_slip` changes as a result of this
      change (test covers at least one other robot's config, e.g.
      tigez or vevov, and asserts its value is unaffected).
- [x] The trailing comment at the bake site names
      `captures/session-b-20260905/ticket016/g1-slip0962/`.
- [x] Scoped tests pass (the modules touched by the bake path, not the
      full suite — the full suite runs once at `close_sprint`).

## Testing

- **Existing tests to run**: the host tests covering per-robot config
  injection / `make_deploy.py` and any existing `shims.cpp` seeding
  tests (whatever ticket 015 exercised for `twistHoldGain` is the
  template — run that same scoped set).
- **New tests to write**: a test that builds/loads tovez's config and
  asserts `rotational_slip == 0.962` with no `SET` issued; a test that
  builds/loads at least one other robot's config and asserts its
  `rotational_slip` is unchanged from its pre-existing value.
- **Verification command**: `uv run pytest` scoped to the touched
  modules (e.g. `uv run pytest tests/host/ -k "slip or make_deploy or shims"`
  — adjust to the actual test paths once the bake site is identified).
